"""Load generic GDS geometry and expose lazy hierarchical selections.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Geometry is in micrometers. Native cells use their own GDS cell frames;
features use their named top-level GDS frame, never chip-local or stage frames.
Native gdstk objects are retained for rendering and must be treated as read-only.
No marker/MS classification or hardware imports belong in this module.
"""

from collections import Counter
from dataclasses import dataclass
from functools import cached_property
import hashlib
import json
from math import cos, sin
from pathlib import Path
from types import MappingProxyType

import gdstk


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _hull(points):
    """Convex hull without expanding reference arrays into individual polygons."""
    points = sorted(set(tuple(map(float, point)) for point in points))
    if len(points) <= 1:
        return tuple(points)

    def cross(first, second, third):
        return ((second[0] - first[0]) * (third[1] - first[1])
                - (second[1] - first[1]) * (third[0] - first[0]))

    lower, upper = [], []
    for target, sequence in ((lower, points), (upper, reversed(points))):
        for point in sequence:
            while len(target) >= 2 and cross(target[-2], target[-1], point) <= 0:
                target.pop()
            target.append(point)
    return tuple(lower[:-1] + upper[:-1])


@dataclass(frozen=True)
class Transform:
    """Affine map from a cell frame to its parent/root GDS frame, in um.

    Matrix: ((a, b), (c, d)); translation: (offset_x_um, offset_y_um).
    """

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    offset_x_um: float = 0.0
    offset_y_um: float = 0.0

    def apply(self, point):
        return (self.a * point[0] + self.b * point[1] + self.offset_x_um,
                self.c * point[0] + self.d * point[1] + self.offset_y_um)

    def compose(self, child):
        """Return self(child(point))."""
        origin = self.apply((child.offset_x_um, child.offset_y_um))
        return Transform(
            self.a * child.a + self.b * child.c,
            self.a * child.b + self.b * child.d,
            self.c * child.a + self.d * child.c,
            self.c * child.b + self.d * child.d, *origin,
        )

    @classmethod
    def from_reference(cls, reference):
        angle, scale = reference.rotation, reference.magnification
        reflection = -1 if reference.x_reflection else 1
        return cls(scale * cos(angle), -scale * sin(angle) * reflection,
                   scale * sin(angle), scale * cos(angle) * reflection,
                   *reference.origin)


@dataclass(frozen=True)
class RepetitionInfo:
    """Offsets in the containing cell frame (um), before ancestor transforms.

    Grid offsets use column-major order. Explicit offsets include the origin.
    A reference's rotation/reflection is already included in its grid vectors.
    """

    columns: int = 1
    rows: int = 1
    column_vector_um: tuple = (0.0, 0.0)
    row_vector_um: tuple = (0.0, 0.0)
    explicit_offsets_um: tuple = ()

    @property
    def count(self):
        return len(self.explicit_offsets_um) or self.columns * self.rows

    def offset(self, index):
        if not 0 <= index < self.count:
            raise IndexError(index)
        if self.explicit_offsets_um:
            return self.explicit_offsets_um[index]
        column, row = divmod(index, self.rows)
        return tuple(column * self.column_vector_um[axis]
                     + row * self.row_vector_um[axis] for axis in (0, 1))

    def hull_offsets(self):
        if self.explicit_offsets_um:
            return _hull(self.explicit_offsets_um)
        return tuple(self.offset(index) for index in
                     (0, self.rows - 1, (self.columns - 1) * self.rows,
                      self.count - 1))

    @classmethod
    def from_native(cls, repetition):
        if repetition.size == 0:
            return cls()
        if repetition.columns is not None:
            if repetition.spacing is not None:
                column = (repetition.spacing[0], 0.0)
                row = (0.0, repetition.spacing[1])
            else:
                column, row = tuple(repetition.v1), tuple(repetition.v2)
            return cls(repetition.columns, repetition.rows, column, row)
        return cls(explicit_offsets_um=tuple(
            sorted(tuple(map(float, offset)) for offset in repetition.get_offsets())
        ))


@dataclass(frozen=True)
class SelectableFeature:
    """A selection in top_cell_name's GDS frame; empty cells have no bbox.

    Center is the bounding-box midpoint, not an area centroid. Layer pairs
    describe polygon/path geometry; native text labels have no physical extent.
    """

    feature_id: str
    feature_type: str
    source_cell_name: str
    top_cell_name: str
    hierarchy_path: tuple[str, ...]
    parent_feature_id: str | None
    bbox_um: tuple[float, float, float, float] | None
    layer_datatypes: tuple[tuple[int, int], ...]
    transform_to_top: Transform
    repetition: RepetitionInfo | None = None

    @property
    def bbox_min_x_um(self):
        return None if self.bbox_um is None else self.bbox_um[0]

    @property
    def bbox_min_y_um(self):
        return None if self.bbox_um is None else self.bbox_um[1]

    @property
    def bbox_max_x_um(self):
        return None if self.bbox_um is None else self.bbox_um[2]

    @property
    def bbox_max_y_um(self):
        return None if self.bbox_um is None else self.bbox_um[3]

    @property
    def center_x_um(self):
        return None if self.bbox_um is None else (self.bbox_um[0] + self.bbox_um[2]) / 2

    @property
    def center_y_um(self):
        return None if self.bbox_um is None else (self.bbox_um[1] + self.bbox_um[3]) / 2

    @property
    def width_um(self):
        return None if self.bbox_um is None else self.bbox_um[2] - self.bbox_um[0]

    @property
    def height_um(self):
        return None if self.bbox_um is None else self.bbox_um[3] - self.bbox_um[1]


def _polygon_signature(polygon):
    # Normalize vertex starting point and winding for stable content identities.
    points = [tuple(map(float, point)) for point in polygon.points]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    candidates = []
    for sequence in (points, list(reversed(points))):
        minimum = min(sequence)
        for index, point in enumerate(sequence):
            if point == minimum:
                candidates.append(sequence[index:] + sequence[:index])
    return (polygon.layer, polygon.datatype, min(candidates))


class GDSLayout:
    """Read-only-by-contract native geometry plus lazy selections.

    Use load_gds() to construct. cells retains normalized gdstk.Cell objects,
    including polygons, paths, labels, references, properties and repetitions.
    Do not mutate them: cached geometry and feature IDs would become stale.
    """

    def __init__(self, source_path, user_unit_m, precision_m, library):
        self.source_path = Path(source_path)
        self.user_unit_m = user_unit_m
        self.precision_m = precision_m
        self.database_unit_m = precision_m
        self.cells = MappingProxyType({cell.name: cell for cell in library.cells})
        if len(self.cells) != len(library.cells):
            raise ValueError("Duplicate GDS cell names")
        self._validate_hierarchy()
        self.top_level_cells = tuple(sorted(cell.name for cell in library.top_level()))
        self._geometry_cache = {}
        self._contexts = {}
        self._features = {}

    def _validate_hierarchy(self):
        active, complete = set(), set()

        def visit(name):
            if name in active:
                raise ValueError(f"Cyclic GDS hierarchy at {name!r}")
            if name in complete:
                return
            active.add(name)
            for reference in self.cells[name].references:
                if reference.cell_name not in self.cells:
                    raise ValueError(f"Unresolved GDS reference: {reference.cell_name!r}")
                visit(reference.cell_name)
            active.remove(name)
            complete.add(name)

        for name in self.cells:
            visit(name)

    @cached_property
    def hierarchy(self):
        """Cell dependency names; native references retain placements and arrays."""
        return MappingProxyType({name: tuple(sorted({ref.cell_name for ref in cell.references}))
                                 for name, cell in self.cells.items()})

    def _element_geometry(self, element):
        if isinstance(element, gdstk.Reference):
            points, layers = self._cell_geometry(element.cell_name)
            transform = Transform.from_reference(element)
            points = tuple(transform.apply(point) for point in points)
        else:
            polygons = [element] if isinstance(element, gdstk.Polygon) else element.to_polygons()
            points = _hull(point for polygon in polygons for point in polygon.points)
            layers = tuple(sorted({(polygon.layer, polygon.datatype) for polygon in polygons}))
        repetition = RepetitionInfo.from_native(element.repetition)
        points = _hull((point[0] + offset[0], point[1] + offset[1])
                       for point in points for offset in repetition.hull_offsets())
        return points, layers

    def _cell_geometry(self, name):
        if name not in self._geometry_cache:
            cell = self.cells[name]
            points, layers = [], set()
            for element in [*cell.polygons, *cell.paths, *cell.references]:
                element_points, element_layers = self._element_geometry(element)
                points.extend(element_points)
                layers.update(element_layers)
            self._geometry_cache[name] = (_hull(points), tuple(sorted(layers)))
        return self._geometry_cache[name]

    def _elements(self, name):
        cell = self.cells[name]
        entries = []
        for element in [*cell.polygons, *cell.paths, *cell.references]:
            repetition = RepetitionInfo.from_native(element.repetition)
            if isinstance(element, gdstk.Reference):
                kind = "array" if repetition.count > 1 else "reference"
                signature = (element.cell_name, element.origin, element.rotation,
                             element.magnification, element.x_reflection)
                label = element.cell_name
            elif isinstance(element, gdstk.Polygon):
                kind, label = "polygon", "polygon"
                signature = _polygon_signature(element)
            else:
                kind, label = "path", "path"
                signature = sorted(_polygon_signature(poly) for poly in element.to_polygons())
            digest = _digest((kind, signature, repetition.__dict__))
            entries.append((f"{kind}:{label}:{digest}", element))
        counts = Counter()
        for token, element in sorted(entries, key=lambda entry: entry[0]):
            duplicate = counts[token]
            counts[token] += 1
            yield f"{token}:{duplicate}", element

    def _make_feature(self, kind, source, top, path, parent, points, layers,
                      geometry_transform, instance_transform, context, repetition=None):
        transformed = tuple(geometry_transform.apply(point) for point in points)
        bbox = None
        if transformed:
            bbox = (min(point[0] for point in transformed), min(point[1] for point in transformed),
                    max(point[0] for point in transformed), max(point[1] for point in transformed))
        feature = SelectableFeature(_digest(path), kind, source, top, path, parent,
                                    bbox, layers, instance_transform, repetition)
        self._contexts[feature.feature_id] = context
        self._features[feature.feature_id] = feature
        return feature

    def features(self, top_cell_name=None):
        """Return one grouped feature per top-level cell (or one selected root)."""
        names = self.top_level_cells if top_cell_name is None else (top_cell_name,)
        result = []
        for name in names:
            points, layers = self._cell_geometry(name)
            result.append(self._make_feature(
                "cell", name, name, (f"cell:{name}",), None, points, layers,
                Transform(), Transform(), ("cell", name, Transform()),
            ))
        return tuple(result)

    def children(self, feature, *, start=0, limit=100):
        """Return a page of immediate children, preserving top-level coordinates.

        Arrays expand into placed cell instances only on this explicit call.
        Then children(instance) exposes its references/polygons. No descendants
        are flattened automatically. Empty/label-only cells have no children.
        """
        if start < 0 or limit < 1:
            raise ValueError("start must be nonnegative and limit must be positive")
        if self._features.get(feature.feature_id) != feature:
            raise ValueError("Feature must be obtained from this layout")
        kind, value, parent_transform = self._contexts[feature.feature_id]
        result = []
        if kind == "array":
            reference = value
            repetition = feature.repetition
            points, layers = self._cell_geometry(reference.cell_name)
            for index in range(start, min(start + limit, repetition.count)):
                offset = repetition.offset(index)
                translation = Transform(offset_x_um=offset[0], offset_y_um=offset[1])
                transform = parent_transform.compose(translation).compose(Transform.from_reference(reference))
                path = feature.hierarchy_path + (f"instance:{index}",)
                result.append(self._make_feature(
                    "reference", reference.cell_name, feature.top_cell_name, path,
                    feature.feature_id, points, layers, transform, transform,
                    ("cell", reference.cell_name, transform),
                ))
        elif kind == "cell":
            for index, (token, element) in enumerate(self._elements(value)):
                if index < start:
                    continue
                if index >= start + limit:
                    break
                points, layers = self._element_geometry(element)
                repetition = RepetitionInfo.from_native(element.repetition)
                source = value
                transform = parent_transform
                context = ("leaf", None, transform)
                if isinstance(element, gdstk.Reference):
                    source = element.cell_name
                    transform = parent_transform.compose(Transform.from_reference(element))
                    feature_kind = "array" if repetition.count > 1 else "reference"
                    context = (("array", element, parent_transform) if feature_kind == "array"
                               else ("cell", source, transform))
                else:
                    feature_kind = "polygon" if isinstance(element, gdstk.Polygon) else "path"
                result.append(self._make_feature(
                    feature_kind, source, feature.top_cell_name,
                    feature.hierarchy_path + (token,), feature.feature_id,
                    points, layers, parent_transform, transform, context,
                    repetition if repetition.count > 1 else None,
                ))
        return tuple(result)

    def child_count(self, feature):
        """Total immediate children, for pagination without array expansion."""
        if self._features.get(feature.feature_id) != feature:
            raise ValueError("Feature must be obtained from this layout")
        kind, value, _ = self._contexts[feature.feature_id]
        if kind == "array":
            return feature.repetition.count
        if kind == "cell":
            cell = self.cells[value]
            return len(cell.polygons) + len(cell.paths) + len(cell.references)
        return 0

    def summary(self, *, depth=1, limit=100):
        """Readable bounded traversal; depth=0 shows roots only."""
        if depth < 0 or limit < 1:
            raise ValueError("depth must be nonnegative and limit must be positive")
        lines = [f"Source: {self.source_path}",
                 f"User unit: {self.user_unit_m:g} m; precision: {self.precision_m:g} m",
                 "All geometry: um; each root has its own GDS coordinate frame",
                 f"Top-level cells: {', '.join(self.top_level_cells)}"]
        counts = Counter()

        def visit(feature, level):
            counts[feature.feature_type] += 1
            lines.append(
                f"{'  ' * level}{feature.feature_id} {feature.feature_type} "
                f"cell={feature.source_cell_name!r} "
                f"center=({feature.center_x_um}, {feature.center_y_um}) "
                f"size=({feature.width_um}, {feature.height_um}) "
                f"layers={feature.layer_datatypes} "
                f"repetitions={feature.repetition.count if feature.repetition else 1} "
                f"path={' / '.join(feature.hierarchy_path)}"
            )
            if level < depth:
                for child in self.children(feature, limit=limit):
                    visit(child, level + 1)
                remaining = self.child_count(feature) - limit
                if remaining > 0:
                    lines.append(f"{'  ' * (level + 1)}... {remaining} more children (paginated)")

        for root in self.features():
            visit(root, 0)
        lines.append(f"Displayed selectable features: {sum(counts.values())}; by type: {dict(counts)}")
        return "\n".join(lines)


def load_gds(source_path) -> GDSLayout:
    """Read a GDS file without writing it; normalize all geometry to um.

    Preserve original unit/precision metadata in meters. Cyclic or unresolved
    references are rejected before computing bounds. Paths are retained natively
    and polygonized only for geometric bounds; labels are retained as metadata.
    """
    path = Path(source_path).expanduser().resolve(strict=True)
    user_unit_m, precision_m = gdstk.gds_units(path)
    library = gdstk.read_gds(path, unit=1e-6)
    return GDSLayout(path, user_unit_m, precision_m, library)
