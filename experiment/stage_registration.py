"""Pure chip-local/stage coordinate math, with all lengths in micrometers.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Apply orientation, then counterclockwise rotation, then marker translation.
Registration parameters are inputs; no fitting, UI, or hardware calls occur.
"""

from dataclasses import dataclass
from enum import Enum
from math import cos, isfinite, radians, sin
from numbers import Real
from types import MappingProxyType
from typing import Mapping, NamedTuple

from experiment.chip_layout import ChipLayout


class Orientation(str, Enum):
    """Signed permutation matrices. Swapped variants flip AFTER swapping.

    For example, swap_xy_flip_x maps (local_x, local_y) to (-local_y, local_x).
    Every matrix is orthogonal and contains only -1, 0, and 1.
    """

    IDENTITY = "identity"
    FLIP_X = "flip_x"
    FLIP_Y = "flip_y"
    FLIP_XY = "flip_xy"
    SWAP_XY = "swap_xy"
    SWAP_XY_FLIP_X = "swap_xy_flip_x"
    SWAP_XY_FLIP_Y = "swap_xy_flip_y"
    SWAP_XY_FLIP_XY = "swap_xy_flip_xy"

    @property
    def matrix(self):
        return {
            Orientation.IDENTITY: ((1, 0), (0, 1)),
            Orientation.FLIP_X: ((-1, 0), (0, 1)),
            Orientation.FLIP_Y: ((1, 0), (0, -1)),
            Orientation.FLIP_XY: ((-1, 0), (0, -1)),
            Orientation.SWAP_XY: ((0, 1), (1, 0)),
            Orientation.SWAP_XY_FLIP_X: ((0, -1), (1, 0)),
            Orientation.SWAP_XY_FLIP_Y: ((0, 1), (-1, 0)),
            Orientation.SWAP_XY_FLIP_XY: ((0, -1), (-1, 0)),
        }[self]


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


@dataclass(frozen=True)
class StageRegistration:
    """Marker stage position (um), physical rotation (degrees), and orientation.

    Positive rotation is counterclockwise in the stage coordinate plane, after
    applying the discrete mapping. Flip X is the current QCL default only;
    callers can select any Orientation explicitly. No scale or shear is fitted.
    """

    marker_stage_x_um: float
    marker_stage_y_um: float
    rotation_deg: float = 0.0
    orientation: Orientation = Orientation.FLIP_X

    def __post_init__(self):
        for name in ("marker_stage_x_um", "marker_stage_y_um", "rotation_deg"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        try:
            orientation = Orientation(self.orientation)
        except (ValueError, TypeError) as error:
            raise ValueError(f"Unknown orientation: {self.orientation!r}") from error
        object.__setattr__(self, "orientation", orientation)


class StagePoint(NamedTuple):
    stage_x_um: float
    stage_y_um: float


class LocalPoint(NamedTuple):
    local_x_um: float
    local_y_um: float


def local_to_stage(local_x_um: float, local_y_um: float,
                   registration: StageRegistration) -> StagePoint:
    """Return t + R(theta) B local, without altering the input coordinates."""
    local_x_um = _finite(local_x_um, "local_x_um")
    local_y_um = _finite(local_y_um, "local_y_um")
    mapping = registration.orientation.matrix
    oriented_x_um = mapping[0][0] * local_x_um + mapping[0][1] * local_y_um
    oriented_y_um = mapping[1][0] * local_x_um + mapping[1][1] * local_y_um
    rotation_rad = radians(registration.rotation_deg % 360.0)
    cosine, sine = cos(rotation_rad), sin(rotation_rad)
    stage_x_um = registration.marker_stage_x_um + cosine * oriented_x_um - sine * oriented_y_um
    stage_y_um = registration.marker_stage_y_um + sine * oriented_x_um + cosine * oriented_y_um
    return StagePoint(_finite(stage_x_um, "stage_x_um"), _finite(stage_y_um, "stage_y_um"))


def stage_to_local(stage_x_um: float, stage_y_um: float,
                   registration: StageRegistration) -> LocalPoint:
    """Return B transpose R transpose (stage - t); no matrix inversion needed."""
    delta_stage_x_um = _finite(stage_x_um, "stage_x_um") - registration.marker_stage_x_um
    delta_stage_y_um = _finite(stage_y_um, "stage_y_um") - registration.marker_stage_y_um
    rotation_rad = radians(registration.rotation_deg % 360.0)
    cosine, sine = cos(rotation_rad), sin(rotation_rad)
    oriented_x_um = cosine * delta_stage_x_um + sine * delta_stage_y_um
    oriented_y_um = -sine * delta_stage_x_um + cosine * delta_stage_y_um
    mapping = registration.orientation.matrix
    local_x_um = mapping[0][0] * oriented_x_um + mapping[1][0] * oriented_y_um
    local_y_um = mapping[0][1] * oriented_x_um + mapping[1][1] * oriented_y_um
    return LocalPoint(_finite(local_x_um, "local_x_um"), _finite(local_y_um, "local_y_um"))


@dataclass(frozen=True)
class StageLayout:
    """Immutable stage-center snapshot; does not add state to Module 1 objects.

    Names are the ChipLayout MS names. Module 4 separately retains GDS feature
    IDs; this transform never invents or replaces those identities.
    """

    registration: StageRegistration
    marker_stage_center: StagePoint
    ms_stage_centers: Mapping[str, StagePoint]

    def __post_init__(self):
        object.__setattr__(self, "ms_stage_centers", MappingProxyType(dict(self.ms_stage_centers)))


def transform_chip_layout_to_stage(chip_layout: ChipLayout,
                                   registration: StageRegistration) -> StageLayout:
    """Transform stored local centers into a separate stage-center snapshot.

    Call ChipLayout.update_local_coordinates() first if its GDS geometry was
    edited. This helper does not recalculate or mutate local/GDS coordinates.
    Empty layouts are supported; missing local centers and duplicate names fail.
    """
    centers = {}
    for pixel in chip_layout.ms_pixels:
        pixel.validate()
        if pixel.name in centers:
            raise ValueError(f"Duplicate MS pixel name: {pixel.name!r}")
        centers[pixel.name] = local_to_stage(pixel.center_local_x, pixel.center_local_y, registration)
    return StageLayout(registration, local_to_stage(0.0, 0.0, registration), centers)
