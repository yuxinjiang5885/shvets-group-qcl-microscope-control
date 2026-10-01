"""H/V registration evidence; Module 5 alone implements coordinate transforms."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from experiment.scan_1d import ScanResult, ScanStatus
from experiment.reflection_analysis import EdgeResult
from experiment.stage_registration import StageRegistration, Orientation

if TYPE_CHECKING:
    from ui.registration_state import RegistrationContext


@dataclass(frozen=True)
class TranslationEvidence:
    context: 'RegistrationContext'
    run_id: str
    horizontal: ScanResult
    vertical: ScanResult
    horizontal_edge: EdgeResult
    vertical_edge: EdgeResult
    source_hashes: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranslationRegistration:
    registration: StageRegistration
    warnings: tuple[str, ...]
    registration_mode: str = 'translation_only'
    rotation_calibrated: bool = False
    assumed_theta_deg: float = 0.0
    physically_validated: bool = False


def build_translation_registration(evidence):
    """No fitting, reanalysis, orientation inference, or claimed angle uncertainty.

    The caller supplies the verified H/V journals and existing edge results.
    The controller separately gates return, cleanup, cancellation and publication.
    """
    if evidence.context.orientation is not Orientation.FLIP_X:
        raise ValueError('translation_only_requires_FLIP_X')
    if not evidence.run_id or not evidence.context.marker_id:
        raise ValueError('translation_evidence_identity_missing')
    if len(evidence.source_hashes) != 2 or len({p for p, _ in evidence.source_hashes}) != 2:
        raise ValueError('translation_requires_two_verified_journals')
    for axis, scan, edge in (('x', evidence.horizontal, evidence.horizontal_edge),
                             ('y', evidence.vertical, evidence.vertical_edge)):
        if (scan.settings.axis != axis or scan.status is not ScanStatus.COMPLETED
                or scan.reasons or not edge.valid or edge.reasons
                or not scan.points or any(p.measured_um is None for p in scan.points)
                or len(scan.points) != len(scan.settings.positions())):
            raise ValueError('translation_scan_not_accepted:'+axis)
    registration = StageRegistration(evidence.horizontal_edge.midpoint_um,
        evidence.vertical_edge.midpoint_um, 0.0, Orientation.FLIP_X)
    warnings = tuple(dict.fromkeys((*evidence.warnings, 'rotation_assumed_zero_not_calibrated')))
    return TranslationRegistration(registration, warnings)
