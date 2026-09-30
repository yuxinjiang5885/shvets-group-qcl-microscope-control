"""Replay committed journals through classification, rotation and center QC only."""
from pathlib import Path
from statistics import mean

from experiment.scan_1d import load_scan
from experiment.reflection_analysis import analyze_scan, EdgeSettings
from experiment.marker_profile_classification import ProfileGeometry, ProfileClass, classify_profiles
from experiment.marker_rotation import fit_rotation
from experiment.marker_center_refinement import CenterRefinementSettings, refine_marker_center
from square_marker_profile_classification_check import JOURNALS


VERTICAL_JOURNAL = 'vertical_marker_scan_9392a56a0a0e4517b9b897398376ee3b.jsonl'
INITIAL_HORIZONTAL_JOURNAL = 'gold_patch_scan_d3ea06d804ae4d36ae39f23e1aa1f0f4.jsonl'


def main():
    root = Path(__file__).resolve().parent
    settings = CenterRefinementSettings()
    print('Provisional engineering center-QC settings:', settings)
    edge_settings = EdgeSettings(expected_width_um=500, width_tolerance_um=100)
    vertical = load_scan(root / VERTICAL_JOURNAL)
    vertical_edges = analyze_scan(vertical, edge_settings)
    original_h = load_scan(root / INITIAL_HORIZONTAL_JOURNAL)
    original_edges = analyze_scan(original_h, edge_settings)
    if vertical.settings.axis != 'y' or original_h.settings.axis != 'x':
        raise ValueError('Unexpected initial journal axes')
    if not vertical_edges.valid or not original_edges.valid:
        print('Initial-center journal analysis failed:', original_edges, vertical_edges)
        return 1
    # Reconstructed from tracked raw evidence, also documented in Module 6.
    # Used for classifier geometry and comparison ONLY, never center regression.
    initial = (original_edges.midpoint_um, vertical_edges.midpoint_um)
    print('Initial center evidence:', INITIAL_HORIZONTAL_JOURNAL, VERTICAL_JOURNAL, initial)
    profiles = []
    for i, filename in enumerate(JOURNALS, 1):
        scan = load_scan(root / filename)
        if scan.settings.axis != 'x':
            raise ValueError('Expected horizontal journal: ' + filename)
        edges = analyze_scan(scan, edge_settings)
        ys = [p.measured_um[1] for p in scan.points if p.measured_um is not None]
        valid = bool(ys) and edges.valid and len(ys) == len(scan.points) and max(ys)-min(ys) <= 1
        profiles.append(ProfileGeometry(f'P{i}', mean(ys) if ys else float('nan'),
            edges.left_edge_um, edges.right_edge_um, edges.midpoint_um, edges.width_um, valid))
    classification = classify_profiles(profiles, initial[1])
    for row in classification.profiles:
        print(row.profile.identifier, row.classification.value, row.reasons)
    print('Classifier sufficient:', classification.sufficient_for_rotation_fit)
    print('CENTRAL IDs:', classification.central_identifiers)
    if not classification.sufficient_for_rotation_fit or classification.usable_final_fits is None:
        print('Classifier failure:', classification.reasons)
        return 1
    central = tuple(row.profile for row in classification.profiles if row.classification is ProfileClass.CENTRAL)
    rotation = fit_rotation(classification, central)
    print('Rotation accepted theta / statistical SE:', rotation.accepted_theta_deg,
          rotation.theta_mid_standard_error_deg)
    print('Rotation warnings / reasons:', rotation.warnings, rotation.reasons)
    print('Horizontal midpoint fit:', rotation.midpoint_fit)
    if not rotation.valid or rotation.accepted_theta_deg is None:
        return 1
    result = refine_marker_center(rotation, vertical, settings, initial_center_um=initial)
    for name, value in vars(result).items():
        print(name + ':', value)
    print('Angle-fit sensitivity ONLY: fixed measured line anchor and vertical constraint.')
    print('Not calibrated physical uncertainty; excludes slope/intercept covariance, vertical-edge')
    print('uncertainty, stage calibration, optical bias, classification selection, drift/systematics.')
    print('Constraint residuals are algebra sanity checks, not independent physical validation.')
    print('Stage-frame center only: no StageRegistration, targeting, or hardware activity.')
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
