"""Hardware-independent GDS and chip-local layout geometry, in micrometers (um).

Author: Yuxin Jiang
Email: yj546@cornell.edu

All centers and dimensions must be supplied in um; no unit conversion is done.
Chip-local axes retain the GDS axis directions and differ only by translation
from the marker center. Stage coordinates and registration are not represented.
"""

from dataclasses import dataclass, field
from math import isfinite


def _validate_geometry(center_gds_x, center_gds_y, width, height):
    """Reject nonfinite geometry and nonpositive dimensions."""
    for name, value in (
        ("center_gds_x", center_gds_x),
        ("center_gds_y", center_gds_y),
        ("width", width),
        ("height", height),
    ):
        if not isfinite(value):
            raise ValueError(f"{name} must be finite (um)")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive (um)")


@dataclass(frozen=True)
class SquareMarker:
    """Square gold marker defining the fixed chip-local origin; geometry in um."""

    center_gds_x: float
    center_gds_y: float
    width: float
    height: float
    center_local_x: float = field(default=0.0, init=False)
    center_local_y: float = field(default=0.0, init=False)

    def __post_init__(self):
        _validate_geometry(
            self.center_gds_x, self.center_gds_y, self.width, self.height
        )
        if self.width != self.height:
            raise ValueError("SquareMarker width and height must be equal")


@dataclass
class MSPixel:
    """Named MS rectangle in um; local centers are unset until layout calculation.

    After editing GDS geometry, call the owning layout's
    update_local_coordinates(). A pixel should belong to only one layout.
    """

    name: str
    center_gds_x: float
    center_gds_y: float
    width: float
    height: float
    center_local_x: float | None = field(default=None, init=False)
    center_local_y: float | None = field(default=None, init=False)

    def __post_init__(self):
        self.validate()

    def validate(self):
        """Validate the identifier and current GDS geometry."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("MS pixel name must be a nonempty string")
        _validate_geometry(
            self.center_gds_x, self.center_gds_y, self.width, self.height
        )


@dataclass
class ChipLayout:
    """One marker and MS pixels, with all geometry in um.

    Names are unique and case-sensitive. Local coordinates are calculated on
    construction. Recalculate after replacing the marker or editing pixels.
    """

    marker: SquareMarker
    ms_pixels: list[MSPixel] = field(default_factory=list)

    def __post_init__(self):
        self.ms_pixels = list(self.ms_pixels)
        self.update_local_coordinates()

    def _validate_pixels(self):
        names = set()
        for pixel in self.ms_pixels:
            pixel.validate()
            if pixel.name in names:
                raise ValueError(f"Duplicate MS pixel name: {pixel.name!r}")
            names.add(pixel.name)

    def update_local_coordinates(self):
        """Update every MS local center by subtracting the marker GDS center."""
        self._validate_pixels()
        for pixel in self.ms_pixels:
            pixel.center_local_x = pixel.center_gds_x - self.marker.center_gds_x
            pixel.center_local_y = pixel.center_gds_y - self.marker.center_gds_y

    def get_ms_pixel(self, name: str) -> MSPixel:
        """Return the named pixel, or raise KeyError if it does not exist."""
        self._validate_pixels()
        for pixel in self.ms_pixels:
            if pixel.name == name:
                return pixel
        raise KeyError(name)

    def summary(self) -> str:
        """Return labeled GDS/local centers and dimensions for debugging."""
        lines = [
            f"ChipLayout (um): {len(self.ms_pixels)} MS pixels",
            f"Marker: GDS=({self.marker.center_gds_x}, {self.marker.center_gds_y}), "
            f"local=(0.0, 0.0), size={self.marker.width} x {self.marker.height}",
        ]
        for pixel in self.ms_pixels:
            lines.append(
                f"{pixel.name}: GDS=({pixel.center_gds_x}, {pixel.center_gds_y}), "
                f"local=({pixel.center_local_x}, {pixel.center_local_y}), "
                f"size={pixel.width} x {pixel.height}"
            )
        return "\n".join(lines)
