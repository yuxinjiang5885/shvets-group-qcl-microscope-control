"""Offline lifecycle and Qt contracts. Never import the operational hardware UI."""
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import gdstk
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QTabWidget, QWidget
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from experiment.gds_layout import load_gds
from experiment.layout_assignment import LayoutAssignments
from experiment.stage_registration import Orientation, local_to_stage
from ui.registration_state import RegistrationState, RegistrationStatus, replay_archived_evidence
from ui.auto_relocation_widget import AutoRelocationWidget
from ui.localization_orchestration import RunSettings, CleanupOutcome
from qcl_scanning_imaging_autorelocation_ui import OfflineAutoRelocationWindow, operational_window_class

ROOT = Path(__file__).resolve().parents[1]


class AutoRelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.real = replay_archived_evidence(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'layout.gds'
        lib = gdstk.Library()
        cell = lib.new_cell('manual')
        cell.add(gdstk.rectangle((-250, -250), (250, 250)),
                 gdstk.rectangle((600, 0), (630, 300)),
                 gdstk.rectangle((800, 0), (830, 300)))
        lib.write_gds(self.path)
        self.widget = AutoRelocationWidget(evidence_loader=lambda: self.evidence)
        self.addCleanup(self.widget.close)
        self.widget.selection.load_file(self.path)
        self.model = self.widget.selection.layout_model
        features = self.model.children(self.model.features()[0])
        self.marker = next(f for f in features if f.width_um == 500)
        self.targets = sorted((f for f in features if f.width_um == 30), key=lambda f: f.center_x_um)
        self.widget.selection.select_feature(self.marker)
        self.widget.selection.assign_marker()
        self.widget.selection.select_feature(self.targets[0])
        self.widget.selection.assign_ms()
        # Synthetic selection binding for lifecycle tests only; real chain is
        # separately tested with its original archived source and marker identity.
        self.evidence = replace(self.real, context=self.widget.state.context)

    def accept(self):
        self.widget.load_registration()
        self.assertEqual(self.widget.state.status, RegistrationStatus.VALID)

    def test_original_ui_unchanged(self):
        self.assertEqual(sha256((ROOT / 'qcl_scanning_imaging_ui.py').read_bytes()).hexdigest(),
            'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab')

    def test_entry_import_and_offline_construction_without_hardware(self):
        script = '''
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('instruments', 'PyDAQmx', 'pipython', 'inputs', 'qcl_scanning_imaging_ui') or fullname == 'experiment.routines':
            raise AssertionError('Forbidden hardware import: '+fullname)
sys.meta_path.insert(0, Block())
from PyQt6.QtWidgets import QApplication
from qcl_scanning_imaging_autorelocation_ui import OfflineAutoRelocationWindow
app=QApplication([])
window=OfflineAutoRelocationWindow()
window.show()
app.processEvents()
assert window.tabs.tabText(0) == 'Auto Relocation'
window.close()
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fake_legacy_subclass_preserves_controls(self):
        class InertMainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.tabs = QTabWidget()
                self.setCentralWidget(self.tabs)
                for title in ('Single', 'Snake scan', 'Scanning imaging (Legacy)'):
                    self.tabs.addTab(QWidget(), title)
                self.existing_button = QPushButton('Existing control', self)
                self.called = False
                self.existing_button.clicked.connect(self.callback)
            def callback(self):
                self.called = True
        window = operational_window_class(InertMainWindow)()
        self.addCleanup(window.close)
        self.assertIsInstance(window, InertMainWindow)
        self.assertEqual([window.tabs.tabText(i) for i in range(4)],
            ['Single', 'Snake scan', 'Scanning imaging (Legacy)', 'Auto Relocation'])
        window.existing_button.click()
        self.assertTrue(window.called)
        self.assertFalse(window.auto_relocation.locate_button.isEnabled())

    def test_manual_assignment_labels_ids_retained(self):
        state = self.widget.selection.assignments
        state.rename_ms(self.targets[0].feature_id, 'operator target')
        self.widget.selection._refresh_assignments()
        self.assertEqual(self.widget.targets.currentText(), 'operator target')
        self.assertEqual(self.widget.targets.currentData(), self.targets[0].feature_id)
        self.assertEqual(state.marker.feature_id, self.marker.feature_id)

    def test_no_automatic_selection(self):
        widget = AutoRelocationWidget()
        self.addCleanup(widget.close)
        widget.selection.load_file(self.path)
        self.assertIsNone(widget.selection.assignments.marker)
        self.assertFalse(widget.selection.assignments.ms_assignments)
        self.assertFalse(widget.predict_button.isEnabled())

    def test_warning_does_not_invalidate(self):
        self.accept()
        self.assertIn('left_right_angle_disagreement_warning', self.widget.warnings_label.text())
        self.assertEqual(self.widget.state.reasons, ())
        self.assertTrue(self.widget.predict_button.isEnabled())

    def test_failed_rotation_is_visible_and_not_predictable(self):
        self.evidence = replace(self.evidence, rotation=replace(self.evidence.rotation,
            valid=False, reasons=('test_rotation_failure',)))
        self.widget.load_registration()
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
        self.assertIsNone(self.widget.state.registration)
        self.assertIn('rotation_not_accepted', self.widget.failures_label.text())
        self.assertIn('test_rotation_failure', self.widget.failures_label.text())
        self.assertIn('left_right_angle_disagreement_warning', self.widget.warnings_label.text())
        self.assertFalse(self.widget.predict_button.isEnabled())

    def test_failed_classifier_rejected(self):
        self.evidence = replace(self.evidence, classification=replace(self.evidence.classification,
            sufficient_for_rotation_fit=False))
        self.widget.load_registration()
        self.assertEqual(self.widget.state.reasons, ('classifier_not_accepted',))

    def test_missing_classifier_fit_rejected(self):
        self.evidence = replace(self.evidence, classification=replace(self.evidence.classification,
            usable_final_fits=None))
        self.widget.load_registration()
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)

    def test_failed_replay_clears_old_approval(self):
        self.accept()
        def fail():
            raise ValueError('journal_read_failed')
        self.widget._evidence_loader = fail
        self.widget.load_registration()
        self.assertIsNone(self.widget.state.registration)
        self.assertEqual(self.widget.state.reasons, ('journal_read_failed',))

    def test_mismatched_evidence_context_rejected(self):
        self.evidence = replace(self.evidence, context=replace(self.evidence.context, marker_id='other'))
        self.widget.load_registration()
        self.assertEqual(self.widget.state.reasons, ('evidence_context_mismatch',))

    def test_context_changes_invalidate_without_resurrection(self):
        self.accept()
        for field in ('frame_id', 'sample_id', 'inputs_id'):
            original = self.widget.context_fields[field].text()
            self.widget.context_fields[field].setText('changed')
            self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
            self.assertIsNone(self.widget.state.registration)
            self.widget.context_fields[field].setText(original)
            self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
            self.accept()

    def test_orientation_change_invalidates(self):
        self.accept()
        self.widget.orientation.setCurrentText('FLIP_Y')
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
        self.widget.load_registration()
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)

    def test_marker_change_invalidates(self):
        self.accept()
        self.widget.selection.assignments.remove(self.marker.feature_id)
        self.widget.selection._refresh_assignments()
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
        self.assertIsNone(self.widget.state.registration)

    def test_gds_reload_invalidates(self):
        self.accept()
        # No dialog needed after explicitly clearing assignments.
        self.widget.selection.assignments.clear()
        self.widget.selection.load_file(self.path)
        self.assertEqual(self.widget.state.status, RegistrationStatus.INVALID)
        self.assertIsNone(self.widget.state.registration)

    def test_target_edits_preserve_registration_clear_prediction(self):
        self.accept()
        registration = self.widget.state.registration
        self.widget.predict_target()
        self.assertIsNotNone(self.widget.state.prediction)
        self.widget.selection.select_feature(self.targets[1])
        self.widget.selection.assign_ms()
        self.assertIs(self.widget.state.registration, registration)
        self.assertIsNone(self.widget.state.prediction)
        self.widget.selection.assignments.rename_ms(self.targets[0].feature_id, 'renamed')
        self.widget.selection._refresh_assignments()
        self.assertIs(self.widget.state.registration, registration)
        self.widget.targets.setCurrentIndex(1)
        self.assertIs(self.widget.state.registration, registration)

    def test_predict_uses_existing_transform(self):
        self.accept()
        with patch('ui.registration_state.local_to_stage', wraps=local_to_stage) as transform:
            QTest.mouseClick(self.widget.predict_button, Qt.MouseButton.LeftButton)
            transform.assert_called_once()
        prediction = self.widget.state.prediction
        expected = local_to_stage(*prediction.marker_local_um, self.widget.state.registration.registration)
        self.assertEqual(prediction.stage_um, tuple(expected))
        self.assertIn('OFFLINE PREDICTION ONLY', self.widget.prediction_label.text())

    def test_review_keeps_upstream_objects(self):
        self.accept()
        self.widget.review_button.click()
        self.assertIs(self.widget.state.evidence, self.evidence)
        for name in ('classification:', 'rotation:', 'center:', 'source_hashes:'):
            self.assertIn(name, self.widget.review_text.toPlainText())

    def test_initial_and_registering_states(self):
        state = RegistrationState()
        self.assertEqual(state.status, RegistrationStatus.NOT_REGISTERED)
        state.begin()
        self.assertEqual(state.status, RegistrationStatus.REGISTERING)
        with self.assertRaisesRegex(ValueError, 'registration_not_valid'):
            state.predict('anything')

    def test_real_archive_chain(self):
        self.assertEqual(self.real.classification.central_identifiers, ('P1', 'P2', 'P3', 'P4'))
        state = RegistrationState()
        state.set_context(self.real.context)
        state.accept(self.real)
        self.assertEqual(state.status, RegistrationStatus.VALID)
        self.assertAlmostEqual(state.registration.registration.marker_stage_x_um, 4214.965309833208)
        self.assertAlmostEqual(state.registration.registration.marker_stage_y_um, -26111.10204224153)
        self.assertAlmostEqual(state.registration.registration.rotation_deg, 0.13199759820576185)
        self.assertEqual(len(self.real.source_hashes), 7)

    def test_real_manual_selection_replay_and_prediction(self):
        # Replay operator-selected identities from committed evidence, not a
        # geometry/semantic search. Requires the same external GDS as prior suites.
        from square_marker_qcl_overlay_check import replay_selection, DEFAULT_GDS
        if not DEFAULT_GDS.exists():
            self.skipTest('External S37a GDS unavailable')
        assignments = replay_selection(ROOT / 'docs/evidence/module7/selection_and_predictions.json')
        panel = AutoRelocationWidget()
        self.addCleanup(panel.close)
        panel.selection.set_layout(assignments.gds_layout)
        panel.selection.assignments = assignments
        panel.selection._refresh_assignments()
        panel.load_registration()
        self.assertEqual(panel.state.status, RegistrationStatus.VALID, panel.state.reasons)
        panel.targets.setCurrentText('P=1.6')
        panel.predict_target()
        self.assertAlmostEqual(panel.state.prediction.stage_um[0], 3538.5603696740036)
        self.assertAlmostEqual(panel.state.prediction.stage_um[1], -26612.386667895684)
        self.assertEqual(panel.targets.count(), 6)

    def test_failed_center_rejected(self):
        self.evidence = replace(self.evidence, center=replace(self.evidence.center,
            valid=False, reasons=('test_center_failure',)))
        self.widget.load_registration()
        self.assertIsNone(self.widget.state.registration)
        self.assertIn('test_center_failure', self.widget.failures_label.text())


    def test_orchestration_shell_idle_and_locate_disabled(self):
        self.assertIn('Acquisition: IDLE', self.widget.acquisition_label.text())
        self.assertIn('ownership: AVAILABLE', self.widget.acquisition_label.text())
        self.assertFalse(self.widget.locate_button.isEnabled())

    def test_running_shell_blocks_replay_preserves_review_and_approval(self):
        self.accept()
        state = self.widget.state
        approved = state.registration
        handle = self.widget.orchestration.start(RunSettings(
            state.context, state.context_generation, 'fake-start'))
        self.widget.refresh()
        self.assertIn(handle.run_id, self.widget.acquisition_label.text())
        self.assertIn('approved retained: True', self.widget.acquisition_label.text())
        self.assertFalse(self.widget.load_button.isEnabled())
        self.assertFalse(self.widget.selection.isEnabled())
        self.assertFalse(self.widget.orientation.isEnabled())
        self.assertTrue(self.widget.review_button.isEnabled())
        self.widget.load_registration()
        self.assertIs(state.registration, approved)
        self.assertFalse(self.widget.locate_button.isEnabled())

    def test_quarantine_is_visible_and_keeps_controls_disabled(self):
        self.accept()
        state = self.widget.state
        controller = self.widget.orchestration
        handle = controller.start(RunSettings(state.context, state.context_generation, 'fake-start'))
        controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(False, False))
        self.widget.refresh()
        self.assertIn('QUARANTINED', self.widget.acquisition_label.text())
        self.assertIn('ownership_uncertain', self.widget.failures_label.text())
        self.assertFalse(self.widget.load_button.isEnabled())
        self.assertFalse(self.widget.locate_button.isEnabled())

    def test_qt_worker_adapter_delivers_typed_events(self):
        from ui.localization_worker import LocateMarkerQtWorker
        from ui.localization_orchestration import LocateMarkerWorker
        from test_auto_relocation_orchestration import FakeServices
        state = self.widget.state
        controller = self.widget.orchestration
        handle = controller.start(RunSettings(state.context, state.context_generation, 'fake-start'))
        adapter = LocateMarkerQtWorker(LocateMarkerWorker(controller, handle, FakeServices(self.evidence)))
        events = []
        adapter.started.connect(events.append)
        adapter.warning.connect(events.append)
        adapter.registration_completed.connect(events.append)
        adapter.finished.connect(events.append)
        adapter.run()
        self.assertEqual(events[0].name, 'started')
        self.assertEqual(events[-1].name, 'finished')
        self.assertEqual(events[-1].detail, 'COMPLETE')
        self.assertTrue(all(event.run_id == handle.run_id for event in events))


if __name__ == '__main__':
    unittest.main()
