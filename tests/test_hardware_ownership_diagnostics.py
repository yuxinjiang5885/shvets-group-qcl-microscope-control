"""Ownership diagnostics use cached state with inert experimental UI objects."""
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_operational_localization_bridge import environment, FakeThread
import test_h_only_controls as fixtures
from ui.hardware_ownership_diagnostics import hardware_ownership_snapshot
from ui.h_only_validation import InputHandoff
from ui.localization_orchestration import OwnershipError


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.window, self.state, self.controller, self.bridge = environment()
        self.window.localization_bridge = self.bridge
        self.window.translation_launch_enabled = True

    def snapshot(self):
        return hardware_ownership_snapshot(self.window)

    def test_fresh_session_defaults(self):
        data = self.snapshot()
        self.assertEqual(data['legacy_daq_state'], 'never_acquired')
        self.assertFalse(data['legacy_daq_cleanup_unverified'])
        self.assertFalse(data['legacy_daq_ever_acquired'])
        self.assertEqual(data['pending_acquisition_sources'], [])
        self.assertEqual(data['active_legacy_sources'], [])
        self.assertEqual(data['ownership_lease_state'], 'AVAILABLE')
        self.assertEqual(data['session_identity'], self.bridge.legacy_daq_evidence.session_id)
        self.assertEqual(data['context_generation'], self.state.context_generation)
        self.assertFalse(data['production_ownership_blocked'])

    def test_active_and_uncertain_sources(self):
        self.bridge.mark_legacy_daq_uncertain('worker_creation:run_experiment')
        self.window.threadRun = FakeThread()
        data = self.snapshot()
        self.assertIn('legacy_activity:threadRun', data['active_legacy_sources'])
        self.assertEqual(data['pending_acquisition_sources'], ['worker_creation:run_experiment'])
        self.assertEqual(data['legacy_daq_state'], 'release_uncertain')
        self.assertTrue(data['legacy_daq_cleanup_unverified'])

    def test_blockers_and_exact_error_match_production_handoff(self):
        self.bridge.mark_legacy_daq_uncertain('unconfirmed_test_owner')
        data = self.snapshot()
        self.assertEqual(data['blockers'], list(self.bridge.blockers()))
        with self.assertRaises(OwnershipError) as caught:
            InputHandoff(self.bridge).prepare()
        self.assertEqual(data['production_pre_handoff_error'], str(caught.exception))
        self.assertIn('legacy_DAQ_release_not_attested_fresh_session_required',
                      data['production_ownership_block_reasons'])

    def test_handoff_conditions_are_not_falsely_hard_failures(self):
        self.bridge.joystick_disabled = lambda: False
        self.window.stageMotionWindow.threadG = FakeThread()
        self.window.stageMotionWindow.workerG = object()
        data = self.snapshot()
        self.assertIn('hardware_joystick_disable_unconfirmed', data['blockers'])
        self.assertIn('gamepad_handoff_required', data['handoff_managed_conditions'])
        self.assertEqual(data['production_pre_handoff_blockers'], [])

    def test_objective_autofocus_and_last_error_visible(self):
        self.window.pi_scanner_widget = SimpleNamespace(daq=object())
        self.window.autofocus_active = True
        self.window.h_only_controls = SimpleNamespace(result=SimpleNamespace(text=lambda:'Not started: example'))
        data = self.snapshot()
        self.assertEqual(data['objective_owner_state']['state'], 'blocked_or_unconfirmed')
        self.assertEqual(data['autofocus_state'], 'active')
        self.assertEqual(data['last_attempt_error'], 'Not started: example')

    def test_release_diagnostic_and_restart_identity(self):
        token = self.bridge.mark_legacy_daq_uncertain('verified_fake_owner', owner=object(), verifier=lambda _:True)
        self.bridge.confirm_legacy_daq_release(token)
        data = self.snapshot()
        self.assertEqual(data['legacy_daq_state'], 'released')
        self.assertEqual(data['pending_acquisition_sources'], [])
        self.assertTrue(data['legacy_daq_ever_acquired'])
        *_, fresh = environment()
        self.assertNotEqual(data['session_identity'], fresh.legacy_daq_evidence.session_id)

    def test_stable_UI_hash(self):
        path = Path(__file__).resolve().parents[1]/'qcl_scanning_imaging_ui.py'
        self.assertEqual(sha256(path.read_bytes()).hexdigest(),
            'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab')


class PanelTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.HOnlyQtTests.setUpClass.__func__)
    setUp = fixtures.HOnlyQtTests.setUp
    cleanup_window = fixtures.HOnlyQtTests.cleanup_window
    pump = fixtures.HOnlyQtTests.pump

    def test_refresh_button_copyable_read_only_and_no_instrument_actions(self):
        panel = self.window.auto_relocation
        before_log = list(self.log)
        before_ni = list(self.backend.calls)
        before_controller = self.controller.snapshot()
        bridge = self.window.localization_bridge
        before_ledger = bridge.legacy_daq_evidence.snapshot()
        with ExitStack() as stack:
            # No hidden start, handoff, ownership mutation, native call or laser access.
            for obj, name in ((bridge,'acquire'), (bridge,'refresh'), (self.runner,'start'),
                              (self.window.stage,'get_position'), (self.window.stage,'joystick'),
                              (self.window.stage,'goto')):
                stack.enter_context(patch.object(obj,name,side_effect=AssertionError(name)))
            class NoLaser:
                def __getattribute__(self,name): raise AssertionError('laser access')
            stack.enter_context(patch.object(self.window,'laser',NoLaser()))
            panel.development_toggle.setChecked(True)
            panel.hardware_diagnostics_button.click()
        data = json.loads(panel.hardware_diagnostics_text.toPlainText())
        self.assertTrue(panel.hardware_diagnostics_text.isReadOnly())
        self.assertTrue(panel.development_body.isAncestorOf(panel.hardware_diagnostics_group))
        self.assertEqual(data['legacy_daq_state'], 'never_acquired')
        self.assertEqual(data['blockers'], list(bridge.blockers()))
        self.assertEqual(self.log, before_log)
        self.assertEqual(self.backend.calls, before_ni)
        self.assertEqual(self.controller.snapshot(), before_controller)
        self.assertEqual(bridge.legacy_daq_evidence.snapshot(), before_ledger)

    def test_refresh_updates_pending_source_without_starting_run(self):
        panel = self.window.auto_relocation
        self.window.localization_bridge.mark_legacy_daq_uncertain('source_for_operator')
        panel.hardware_diagnostics_button.click()
        data = json.loads(panel.hardware_diagnostics_text.toPlainText())
        self.assertEqual(data['pending_acquisition_sources'], ['source_for_operator'])
        self.assertIn('legacy_DAQ_release_not_attested_fresh_session_required', data['blockers'])
        self.assertFalse(self.runner.busy)

    def test_offline_panel_does_not_claim_clean_without_bridge(self):
        from ui.auto_relocation_widget import AutoRelocationWidget
        panel = AutoRelocationWidget()
        try:
            panel.hardware_diagnostics_button.click()
            data = json.loads(panel.hardware_diagnostics_text.toPlainText())
            self.assertFalse(data['available'])
            self.assertEqual(data['reason'], 'operational_bridge_not_attached')
        finally:
            panel.deleteLater()
