"""OFFLINE PREDICTION ONLY. Explicit S37a example assignments, never hardware.

MS_1..MS_4 replay the order in test_gds_assignment's S37a example, not unsaved UI
state or inherent GDS labels. The current physical sample lacks fabricated MS
pixels. Predictions therefore cannot establish MS physical validation.
"""
import argparse
from hashlib import sha256
from itertools import combinations
from math import dist
from pathlib import Path
from statistics import mean

from experiment.gds_layout import load_gds
from experiment.layout_assignment import LayoutAssignments
from experiment.scan_1d import load_scan
from experiment.reflection_analysis import EdgeSettings, analyze_scan
from experiment.marker_profile_classification import ProfileGeometry, ProfileClass, classify_profiles
from experiment.marker_rotation import fit_rotation
from experiment.marker_center_refinement import refine_marker_center
from experiment.marker_stage_registration import build_stage_registration
from experiment.stage_registration import StageRegistration, local_to_stage, stage_to_local, transform_chip_layout_to_stage
from square_marker_profile_classification_check import JOURNALS
from square_marker_center_refinement_check import VERTICAL_JOURNAL, INITIAL_HORIZONTAL_JOURNAL


DEFAULT_GDS = Path(r'C:\Data\Yuxin\MS localization algorithm test\S37a.GDS')
MARKER_ID = '7ea7ba28d6ac774ff40e747491998e489c4ad1c558ff527f9e325e33cd503ae2'
TARGET_IDS = (
    '31e19ae2b4d187d97075b61db79e8ee12017f3c877394957ba78370af7d4a35a',
    '2def120d76aa214945074164a6ff1050a94c3c40c18860199e309671152d152c',
    '61be564e61dc3fa69660f60cda8def315b0cf2c34a9f762bf2bb78d7579d6f1e',
    'fab2dbb040c8aa9a9c9bd76cc58ead4d725dc5d532cd6afc9b203df7f9bd1e93',
)


def selected_layout(path):
    """Resolve explicitly reviewed occurrences; fail if unavailable, never guess.

    Visit only the reviewed hierarchy levels, not the millions of MS elements.
    Coordinates always come from the loaded geometry, never stored predictions.
    """
    layout = load_gds(path)
    root = layout.features('Arra')[0]
    arrays = [f for f in layout.children(root) if f.source_cell_name == 'Altug2009']
    if len(arrays) != 1:
        raise ValueError('Expected exactly one Altug2009 array')
    features = {}
    for occurrence in layout.children(arrays[0]):
        for feature in layout.children(occurrence):
            features[feature.feature_id] = feature
            if feature.feature_type == 'array':
                features.update((f.feature_id, f) for f in layout.children(feature))
    if any(key not in features for key in (MARKER_ID, *TARGET_IDS)):
        raise ValueError('Reviewed GDS occurrences missing; manual reassignment required')
    assignments = LayoutAssignments(layout)
    assignments.set_marker(features[MARKER_ID])
    for identifier in TARGET_IDS:
        assignments.add_ms(features[identifier])
    return assignments, assignments.build_chip_layout()


def accepted_chain(root):
    """Replay existing algorithms once per stage; no QC bypass or fitted constants."""
    edges_setting = EdgeSettings(expected_width_um=500, width_tolerance_um=100)
    vertical = load_scan(root / VERTICAL_JOURNAL)
    original = load_scan(root / INITIAL_HORIZONTAL_JOURNAL)
    ve, he = analyze_scan(vertical, edges_setting), analyze_scan(original, edges_setting)
    if vertical.settings.axis != 'y' or original.settings.axis != 'x' or not ve.valid or not he.valid:
        raise ValueError('Initial journal analysis failed')
    initial = (he.midpoint_um, ve.midpoint_um)
    profiles = []
    for i, filename in enumerate(JOURNALS, 1):
        scan = load_scan(root / filename)
        if scan.settings.axis != 'x':
            raise ValueError('Expected horizontal profile')
        edges = analyze_scan(scan, edges_setting)
        ys = [p.measured_um[1] for p in scan.points if p.measured_um is not None]
        valid = bool(ys) and edges.valid and len(ys) == len(scan.points) and max(ys)-min(ys) <= 1
        profiles.append(ProfileGeometry(f'P{i}', mean(ys) if ys else float('nan'),
            edges.left_edge_um, edges.right_edge_um, edges.midpoint_um, edges.width_um, valid))
    classification = classify_profiles(profiles, initial[1])
    for row in classification.profiles:
        print(row.profile.identifier, row.classification.value, row.reasons)
    print('Classifier sufficient / reasons:', classification.sufficient_for_rotation_fit, classification.reasons)
    if not classification.sufficient_for_rotation_fit or classification.usable_final_fits is None:
        raise ValueError('Classifier rejected dataset')
    central = tuple(r.profile for r in classification.profiles if r.classification is ProfileClass.CENTRAL)
    rotation = fit_rotation(classification, central)
    print('Rotation valid / warnings / reasons:', rotation.valid, rotation.warnings, rotation.reasons)
    if not rotation.valid or rotation.accepted_theta_deg is None:
        raise ValueError('Rotation rejected dataset')
    center = refine_marker_center(rotation, vertical, initial_center_um=initial)
    print('Center valid / warnings / reasons:', center.valid, center.warnings, center.reasons)
    return build_stage_registration(rotation, center)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gds', type=Path, default=DEFAULT_GDS)
    args = parser.parse_args(argv)
    print('OFFLINE PREDICTION ONLY; no physical validation. Current sample MS pixels are absent.')
    assignments, chip = selected_layout(args.gds)
    print('GDS:', args.gds, 'SHA256:', sha256(args.gds.read_bytes()).hexdigest())
    print('Marker identity / path:', assignments.marker.feature_id, assignments.marker.hierarchy_path)
    print('Marker GDS / local:', (chip.marker.center_gds_x, chip.marker.center_gds_y), (0, 0))
    result = accepted_chain(Path(__file__).resolve().parent)
    reg = result.registration
    print('Offline StageRegistration:', reg, 'implicit scale=1; shear=none')
    print('Retained warnings:', result.warnings)
    stage = transform_chip_layout_to_stage(chip, reg)
    origin_error = dist(stage.marker_stage_center, (reg.marker_stage_x_um, reg.marker_stage_y_um))
    local, predicted, errors = [], [], []
    zero = StageRegistration(0, 0, 0, reg.orientation)
    rotated = StageRegistration(0, 0, reg.rotation_deg, reg.orientation)
    print('Name | feature ID | absolute GDS XY | marker-local XY | predicted stage XY (um)')
    for pixel, assignment in zip(chip.ms_pixels, assignments.ms_assignments.values()):
        xy = (pixel.center_local_x, pixel.center_local_y)
        target = stage.ms_stage_centers[pixel.name]
        print(pixel.name, assignment.feature_id, (pixel.center_gds_x, pixel.center_gds_y), xy, tuple(target))
        print('  cell / path:', assignment.feature.source_cell_name, assignment.feature.hierarchy_path)
        print('  local / FLIP_X / rotated / final stage-minus-marker:', xy,
              tuple(local_to_stage(*xy, zero)), tuple(local_to_stage(*xy, rotated)),
              (target[0]-reg.marker_stage_x_um, target[1]-reg.marker_stage_y_um))
        local.append(xy)
        predicted.append(target)
        errors.append(dist(stage_to_local(*target, reg), xy))
    distance_errors = []
    for i, j in combinations(range(len(local)), 2):
        d_local, d_stage = dist(local[i], local[j]), dist(predicted[i], predicted[j])
        print('Pair distances:', chip.ms_pixels[i].name, chip.ms_pixels[j].name, d_local, d_stage)
        distance_errors.append(abs(d_local-d_stage))
    print('Marker-origin / max round-trip / max pairwise errors (um):', origin_error, max(errors), max(distance_errors))
    passed = max(origin_error, *errors, *distance_errors) <= 1e-9
    print('Transform mathematically valid:', passed, 'Physical target validated:', result.physically_validated)
    print('Hard-failure reasons:', () if passed else ('transform_invariant_failed',))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
