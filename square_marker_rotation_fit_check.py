"""Offline measured-journal classifier and rotation QC; no hardware or center fit."""
from pathlib import Path
from statistics import mean

from experiment.scan_1d import load_scan
from experiment.reflection_analysis import EdgeSettings, analyze_scan
from experiment.marker_profile_classification import ProfileGeometry, ProfileClass, classify_profiles
from experiment.marker_rotation import RotationSettings, fit_rotation
from square_marker_profile_classification_check import JOURNALS


def main():
    profiles = []
    for i, filename in enumerate(JOURNALS, 1):
        scan = load_scan(Path(__file__).resolve().parent / filename)
        if scan.settings.axis != 'x':
            raise ValueError('Expected horizontal scan: ' + filename)
        edges = analyze_scan(scan, EdgeSettings(expected_width_um=500, width_tolerance_um=100))
        ys = [p.measured_um[1] for p in scan.points if p.measured_um is not None]
        valid = bool(ys) and edges.valid and len(ys) == len(scan.points) and max(ys)-min(ys) <= 1
        profiles.append(ProfileGeometry(f'P{i}', mean(ys) if ys else float('nan'),
            edges.left_edge_um, edges.right_edge_um, edges.midpoint_um, edges.width_um, valid))
    classification = classify_profiles(profiles, -26111.11348130628)
    for row in classification.profiles:
        print(row.profile.identifier, row.classification.value, row.reasons)
    print('Classifier sufficient_for_rotation_fit:', classification.sufficient_for_rotation_fit)
    if not classification.sufficient_for_rotation_fit or classification.usable_final_fits is None:
        print('Classifier QC failed:', classification.reasons)
        return 1
    central = tuple(r.profile for r in classification.profiles if r.classification is ProfileClass.CENTRAL)
    settings = RotationSettings()
    print('Provisional production-QC settings:', settings)
    result = fit_rotation(classification, central, settings)
    print('Used IDs / count / measured Y span (um):', result.used_profile_ids,
          result.used_profile_count, result.measured_y_span_um)
    for name, fit in (('left', result.left_fit), ('right', result.right_fit), ('midpoint', result.midpoint_fit)):
        print(name, 'fit:', fit)
    print('theta_left / theta_right / theta_mid (deg):',
          result.theta_left_deg, result.theta_right_deg, result.theta_mid_deg)
    print('theta_mid statistical standard error (deg):', result.theta_mid_standard_error_deg)
    print('Regression uncertainty ONLY: assumes exact Y and independent equal-variance X errors;')
    print('not calibrated physical uncertainty; excludes drift, edge bias and classification selection effects.')
    print('Left/right angle disagreement (deg):', result.left_right_angle_disagreement_deg)
    for row in result.per_profile:
        print('Profile diagnostics:', row)
    print('Width mean / sample std / min / max / peak-to-peak (um):',
          result.width_mean_um, result.width_std_um, result.width_min_um,
          result.width_max_um, result.width_peak_to_peak_um)
    print('Warnings:', result.warnings)
    print('Final valid:', result.valid, 'Hard-failure reasons:', result.reasons)
    print('Diagnostic only:', result.diagnostic_only, 'Accepted production angle:', result.accepted_theta_deg)
    print('No center refinement or StageRegistration created.')
    return 0 if result.valid else 1


if __name__ == '__main__':
    raise SystemExit(main())
