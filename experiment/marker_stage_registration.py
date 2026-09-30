"""QC bridge only; Module 5 remains the sole coordinate-transform implementation."""
from dataclasses import dataclass

from experiment.marker_center_refinement import CenterRefinementResult
from experiment.marker_rotation import RotationFitResult
from experiment.stage_registration import Orientation, StageRegistration


@dataclass(frozen=True)
class OfflineMarkerRegistration:
    """Mathematical registration approval does not establish physical targeting.

    The caller must associate the measured marker with the selected GDS marker.
    No scale/shear is introduced: Module 5's rigid orientation transform is used.
    """
    registration: StageRegistration
    warnings: tuple[str, ...]
    physically_validated: bool = False


def build_stage_registration(rotation: RotationFitResult,
                             center: CenterRefinementResult) -> OfflineMarkerRegistration:
    """Require matching accepted Module 7 results; reject with ValueError.

    No replacement center/angle/orientation arguments and no transformation math.
    Equality checks catch stale/mixed result objects, not fabricated provenance.
    """
    if rotation.valid is not True or rotation.reasons or rotation.accepted_theta_deg is None:
        raise ValueError('rotation_not_accepted')
    if center.valid is not True or center.reasons:
        raise ValueError('center_not_accepted')
    if (rotation.midpoint_fit is None or center.horizontal_midpoint_fit != rotation.midpoint_fit
            or center.accepted_theta_deg != rotation.accepted_theta_deg):
        raise ValueError('center_rotation_mismatch')
    registration = StageRegistration(center.x_center_stage_um, center.y_center_stage_um,
                                     rotation.accepted_theta_deg, Orientation.FLIP_X)
    warnings = tuple(dict.fromkeys((*rotation.warnings, *center.warnings)))
    return OfflineMarkerRegistration(registration, warnings)
