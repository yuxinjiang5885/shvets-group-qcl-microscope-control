"""Manual feature assignments and construction of Module 1 chip layouts.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Assignments are scoped to one loaded Module 2 model and one root GDS frame.
All geometry uses um. No automatic semantic classification is performed.
"""

from dataclasses import dataclass
from types import MappingProxyType

from experiment.chip_layout import ChipLayout, MSPixel, SquareMarker
from experiment.gds_layout import SelectableFeature


class MarkerReplacementRequired(ValueError):
    """Replacing an existing marker requires a deliberate replacement action."""


@dataclass(frozen=True)
class MSAssignment:
    name: str
    feature: SelectableFeature

    @property
    def feature_id(self):
        return self.feature.feature_id


class LayoutAssignments:
    """Validated manual assignments; failed operations leave state unchanged.

    Feature IDs retain physical occurrence identity independently of editable
    names. Ancestor/descendant assignments are disallowed to avoid assigning the
    same structure through two hierarchy levels. Disjoint repeated instances
    remain independent, even when they share cell names and dimensions.
    """

    def __init__(self, gds_layout):
        self.gds_layout = gds_layout
        self._marker = None
        self._ms = {}

    @property
    def marker(self):
        return self._marker

    @property
    def ms_assignments(self):
        return MappingProxyType(self._ms)

    @property
    def has_assignments(self):
        return self.marker is not None or bool(self._ms)

    def _features(self):
        return ([self.marker] if self.marker else []) + [entry.feature for entry in self._ms.values()]

    @staticmethod
    def _geometry(feature):
        if feature.bbox_um is None:
            raise ValueError("The selected feature has no physical geometry.")
        return (feature.center_x_um, feature.center_y_um, feature.width_um, feature.height_um)

    def _validate_feature(self, feature, *, replacing_marker=False):
        self.gds_layout.child_count(feature)  # Validate membership in the loaded model.
        if feature.feature_type == "array":
            raise ValueError("Select one physical array instance before assigning a role.")
        MSPixel("validation", *self._geometry(feature))
        for assigned in self._features():
            if replacing_marker and assigned is self.marker:
                continue
            if assigned.top_cell_name != feature.top_cell_name:
                raise ValueError("Assignments must use the same root GDS coordinate frame. Clear assignments first.")
            if assigned.feature_id == feature.feature_id:
                raise ValueError("This physical feature is already assigned. Remove its assignment first.")
            first, second = assigned.hierarchy_path, feature.hierarchy_path
            if first == second[:len(first)] or second == first[:len(second)]:
                raise ValueError("An ancestor or descendant of this feature is already assigned.")

    def set_marker(self, feature, *, replace=False):
        if self.marker and self.marker.feature_id == feature.feature_id:
            return
        self._validate_feature(feature, replacing_marker=True)
        try:
            SquareMarker(*self._geometry(feature))
        except ValueError as error:
            raise ValueError(f"Choose a square feature with positive equal width and height: {error}") from error
        if self.marker is not None and not replace:
            raise MarkerReplacementRequired("A marker is already assigned. Confirm replacement first.")
        self._marker = feature

    def _validate_name(self, name, excluding_id=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("MS name must not be empty.")
        name = name.strip()
        if any(entry.name == name for identifier, entry in self._ms.items() if identifier != excluding_id):
            raise ValueError(f"MS name {name!r} is already in use.")
        return name

    def add_ms(self, feature, name=None):
        self._validate_feature(feature)
        if name is None:
            existing = {entry.name for entry in self._ms.values()}
            number = 1
            while f"MS_{number}" in existing:
                number += 1
            name = f"MS_{number}"
        name = self._validate_name(name)
        assignment = MSAssignment(name, feature)
        self._ms[feature.feature_id] = assignment
        return assignment

    def rename_ms(self, feature_id, name):
        entry = self._ms[feature_id]
        name = self._validate_name(name, excluding_id=feature_id)
        self._ms[feature_id] = MSAssignment(name, entry.feature)

    def remove(self, feature_id):
        if self.marker and self.marker.feature_id == feature_id:
            self._marker = None
        elif feature_id in self._ms:
            del self._ms[feature_id]
        else:
            raise ValueError("The selected feature has no assignment.")

    def clear(self):
        self._marker = None
        self._ms.clear()

    @property
    def is_valid(self):
        return self.marker is not None and bool(self._ms)

    def build_chip_layout(self):
        """Create a fresh snapshot; Module 1 calculates every local coordinate."""
        if not self.is_valid:
            raise ValueError("A valid layout requires one marker and at least one MS pixel.")
        marker = SquareMarker(*self._geometry(self.marker))
        pixels = [MSPixel(entry.name, *self._geometry(entry.feature)) for entry in self._ms.values()]
        return ChipLayout(marker, pixels)
