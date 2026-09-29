"""Offline-only journal reanalysis and classification; no registration or hardware."""
from pathlib import Path
from statistics import mean
from experiment.scan_1d import load_scan
from experiment.reflection_analysis import analyze_scan, EdgeSettings
from experiment.marker_profile_classification import (
    ProfileGeometry, ClassificationSettings, classify_profiles,
)

JOURNALS = (
    "square_marker_rotation_profile_1_b8390681856f4707b91b43b25bef7b73.jsonl",
    "square_marker_rotation_profile_2_339091a97742467c86a79b2d1a8b6690.jsonl",
    "square_marker_rotation_profile_3_41dd446e02484ba2b125a418522848a9.jsonl",
    "square_marker_rotation_profile_4_83265e6f5f414c2b8664ef88c634cf7e.jsonl",
    "square_marker_rotation_profile_5_d64822c6a95e47eea978eb0dc9cf079f.jsonl",
)


def main():
    profiles = []
    for i, filename in enumerate(JOURNALS, 1):
        scan = load_scan(Path(__file__).resolve().parent / filename)
        if scan.settings.axis != 'x':
            raise ValueError('Expected horizontal profile: ' + filename)
        edges = analyze_scan(scan, EdgeSettings(expected_width_um=500, width_tolerance_um=100))
        ys = [p.measured_um[1] for p in scan.points if p.measured_um is not None]
        y = mean(ys) if ys else float('nan')
        # An inconsistent Y path is not a horizontal profile geometry record.
        valid = edges.valid and len(ys) == len(scan.points) and max(ys)-min(ys) <= 1.0
        print(f'P{i}: {filename}; status={scan.status.value}; Y spread={max(ys)-min(ys) if ys else None}; edge reasons={edges.reasons}')
        profiles.append(ProfileGeometry(f'P{i}', y, edges.left_edge_um, edges.right_edge_um,
                                         edges.midpoint_um, edges.width_um, valid))
    settings = ClassificationSettings()
    result = classify_profiles(profiles, -26111.11348130628, settings)
    print('Settings:', settings)
    print('Seed:', result.seed_identifiers)
    print('Provisional angle ONLY:', result.provisional_rotation_deg, 'slope:', result.provisional_slope)
    print('Central interval:', result.central_y_interval_um, 'guarded:', result.guarded_central_y_interval_um)
    print('Width plateau/limit:', result.width_plateau_um, result.width_limit_um)
    print('Residual limits:', result.residual_limits_um)
    print('ID | measured Y | class | reasons | left | right | midpoint | width | width deviation | dy | central half-height | left residual | right residual | midpoint residual')
    for row in result.profiles:
        p = row.profile
        print(' | '.join(map(str, (p.identifier, p.measured_y_um, row.classification.value,
            row.reasons, p.left_edge_um, p.right_edge_um, p.midpoint_um, p.width_um,
            row.width_deviation_um, row.geometric_dy_um, row.central_half_height_um,
            row.left_residual_um, row.right_residual_um, row.midpoint_residual_um))))
    print('CENTRAL:', result.central_identifiers)
    print('CORNER_AFFECTED:', result.corner_affected_identifiers)
    print('INCONSISTENT:', result.inconsistent_identifiers)
    print('INVALID:', result.invalid_identifiers)
    print('Central side-slope disagreement:', result.slope_disagreement)
    print('Sufficient for LATER rotation fit:', result.sufficient_for_rotation_fit, result.reasons)
    print('No final production rotation or registration calculated.')


if __name__ == '__main__':
    main()
