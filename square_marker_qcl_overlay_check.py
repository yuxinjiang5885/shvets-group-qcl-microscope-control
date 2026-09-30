"""Offline manual GDS selection and fixed-registration QCL overlay.

Uses normal snake UI display coordinates by explicit operator choice. No
hardware imports, screenshot registration, fitting, or registration adjustment.
Optional observed-center clicking is deferred; this overlay makes no accuracy
claim. External CSV/GDS remain untouched. Saved selections can be replayed.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from experiment.qcl_registration_validation import load_qcl_image, predict_selection, plot_overlay
from square_marker_stage_registration_check import accepted_chain, DEFAULT_GDS, MARKER_ID

CSV = Path(r'C:\Data\_experiment_data\2026-09-29_012\stacks\pattern0\lineScan_1500_0invcm.csv')


def resolve_path(model, hierarchy):
    """Replay an operator-selected Module 2 path; never choose by shape/name."""
    roots = [r for r in model.features() if r.hierarchy_path[0] == hierarchy[0]]
    if len(roots) != 1:
        raise ValueError('Selected root missing')
    feature = roots[0]
    for token in hierarchy[1:]:
        count = model.child_count(feature)
        if count > 10000:
            raise ValueError('Selected path exceeds replay budget')
        matches = [f for f in model.children(feature, limit=max(1, count)) if f.hierarchy_path[-1] == token]
        if len(matches) != 1:
            raise ValueError('Selected path missing or ambiguous')
        feature = matches[0]
    return feature


def replay_selection(path):
    from experiment.gds_layout import load_gds
    from experiment.layout_assignment import LayoutAssignments
    record = json.loads(path.read_text(encoding='utf-8'))
    if record['gds_sha256'] != sha256(DEFAULT_GDS.read_bytes()).hexdigest():
        raise ValueError('GDS differs from manually selected source')
    model = load_gds(DEFAULT_GDS)
    state = LayoutAssignments(model)
    for row in record['selections']:
        feature = resolve_path(model, row['hierarchy_path'])
        if feature.feature_id != row['feature_id']:
            raise ValueError('Feature identity mismatch')
        if row['is_reference']:
            state.set_marker(feature)
        else:
            state.add_ms(feature, row['label'])
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, help='Replay a saved manual selection report')
    parser.add_argument('--output-dir', type=Path, default=Path(tempfile.gettempdir()) /
                        ('module7_qcl_overlay_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    args = parser.parse_args(argv)
    image = load_qcl_image(CSV, x_origin_um=3300., y_origin_um=-25400.,
                           x_pixels=850, y_pixels=850, spacing_um=2.)
    print('CSV:', CSV, 'shape:', image.signal.shape, 'dtype:', image.signal.dtype,
          'finite:', image.signal.size, 'nonfinite: 0; min/max:', image.signal.min(), image.signal.max(), flush=True)
    print('UI display pixel center X/Y ranges:', (image.x_um[0], image.x_um[-1]),
          (image.y_um[0], image.y_um[-1]), 'extent:', image.extent_um, flush=True)
    print('Coordinate limitation: existing display mapping differs from acquisition triggers; no correction applied.', flush=True)
    registration = accepted_chain(Path(__file__).resolve().parent)

    def save(assignments):
        # No auto-selection. Bind the user's explicit choice to this chain's
        # reviewed physical reference, rather than silently attaching to another.
        if assignments.marker.feature_id != MARKER_ID:
            raise ValueError('Selected marker is not the reviewed lower reference for these journals. '
                             'Select the actual reference; registration is not reassigned automatically.')
        if Path(assignments.gds_layout.source_path).resolve() != DEFAULT_GDS.resolve():
            raise ValueError('Use the specified S37a.GDS source')
        predictions = predict_selection(assignments, registration)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report = args.output_dir / 'selection_and_predictions.json'
        figure_path = args.output_dir / 'qcl_registration_overlay.png'
        if report.exists() or figure_path.exists():
            raise ValueError('Output already exists; choose a new output directory')
        figure = plot_overlay(image, predictions, registration.warnings)
        figure.savefig(figure_path, dpi=180)
        record = dict(gds_path=str(DEFAULT_GDS), gds_sha256=sha256(DEFAULT_GDS.read_bytes()).hexdigest(),
            csv_path=str(CSV), csv_sha256=sha256(CSV.read_bytes()).hexdigest(),
            coordinate_convention=image.coordinate_convention, extent_um=image.extent_um,
            registration=asdict(registration.registration), warnings=registration.warnings,
            independent_validation_count=sum(not p.is_reference for p in predictions),
            physically_validated=False, selections=[asdict(p) for p in predictions])
        report.write_text(json.dumps(record, indent=2), encoding='utf-8')
        print('OFFLINE PREDICTION / IMAGE VALIDATION', flush=True)
        for p in predictions:
            print(p.label, p.feature_id, p.hierarchy_path, '\n GDS/local/stage:',
                  p.gds_center_um, p.local_center_um, p.stage_center_um,
                  '\n stage bbox / distance:', p.stage_bbox_um, p.distance_from_marker_um, flush=True)
        print('Independent validation features:', record['independent_validation_count'], flush=True)
        print('Warnings:', registration.warnings, '\nOverlay:', figure_path, '\nReport:', report, flush=True)

    if args.selection:
        save(replay_selection(args.selection))
        return 0
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from ui.gds_validation_selection import GDSValidationSelector
    app = QApplication.instance() or QApplication([])
    selector = GDSValidationSelector()
    selector.load_file(DEFAULT_GDS)
    completed = []

    def selected(assignments):
        try:
            save(assignments)
        except Exception as error:
            QMessageBox.warning(selector, 'Overlay not generated', str(error))
            return
        completed.append(True)
        selector.close()
        app.quit()

    selector.confirmed.connect(selected)
    selector.show()
    print('Waiting for manual reference and validation-feature selection.', flush=True)
    app.exec()
    return 0 if completed else 1


if __name__ == '__main__':
    raise SystemExit(main())
