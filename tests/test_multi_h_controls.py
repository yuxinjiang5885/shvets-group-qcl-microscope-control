"""Qt multi-profile action with inert persistent Prior and injected fake NI."""
import unittest
from dataclasses import replace
from unittest.mock import patch
import test_hv_controls as hv_tests
from test_reflection_scan import FakeClock
from ui.h_only_validation import HOnlyServices
from ui.multi_h_validation import MultiHSpec, MultiHConfirmation, MultiHServices
from ui.localization_orchestration import AcquisitionState, OwnershipError
from experiment.scan_1d import StageBounds


class FastMultiServices(MultiHServices):
    def __init__(self,*a,**k):super().__init__(*a,clock=FakeClock(),**k)


class MultiHQtTests(unittest.TestCase):
    setUpClass=classmethod(hv_tests.HVQtTests.setUpClass.__func__)
    pump=hv_tests.HVQtTests.pump
    cleanup_window=hv_tests.HVQtTests.cleanup_window
    select_fixture_marker=hv_tests.HVQtTests.select_fixture_marker

    def setUp(self):
        hv_tests.HVQtTests.setUp(self)
        self.runner.services_type=FastMultiServices
        self.spec=MultiHSpec((1000.,2000.),StageBounds(299,1701,1399,2601,'fixture-frame'))
        self.confirm=MultiHConfirmation(True,True,True,True,note='full profile rectangle',
            both_axes_clearance=True,multi_profile_clearance=True)

    def test_Qt_success_report_and_no_registration(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        r=self.window.auto_relocation.run_display['multi_h_result']
        self.assertEqual(r['central_count'],5)
        self.assertEqual(len(r['profiles']),5)
        self.assertTrue(r['multi_h_complete'])
        self.assertTrue(r['ready_for_rotation_fit'])
        self.assertFalse(r['registration_published'])
        self.assertFalse(r['production_rotation_executed'])
        self.assertFalse(self.window.auto_relocation.locate_button.isEnabled())
        self.assertTrue((self.runner.services.path/'multi_h_result.json').exists())
        self.assertEqual(self.backend.calls.count('clear'),1)

    def test_default_runner_routes_multi_service(self):
        self.runner.services_type=HOnlyServices
        with patch('ui.h_only_controls.MultiHServices',FastMultiServices):
            self.runner.start(self.spec,self.confirm,self.tmp.name)
            self.pump(lambda:not self.runner.busy)
        self.assertIsInstance(self.runner.services,MultiHServices)
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE)

    def test_preview_full_rectangle_and_dynamic_coordinates(self):
        c=self.select_fixture_marker();c.hv_preview_button.click()
        c.hv_clearance.setChecked(True)
        c.multi_preview_button.click()
        self.assertIsNotNone(c.reviewed,c.result.text())
        self.assertIsInstance(c.reviewed[0],MultiHSpec)
        bounds=c.reviewed[0].bounds
        self.assertEqual((bounds.x_min_um,bounds.x_max_um,bounds.y_min_um,bounds.y_max_um),(299,1701,1399,2601))
        self.assertIn('1803',c.result.text())
        self.assertIn('Final X/Y derive from measured H/V center',c.result.text())
        self.assertFalse(c.multi_clearance.isChecked())
        self.assertFalse(c.hv_clearance.isChecked())
        self.assertFalse(c.run_button.isEnabled());self.assertFalse(c.hv_run_button.isEnabled())
        self.assertTrue(c.multi_run_button.isEnabled())
        self.assertEqual(self.backend.calls,[])

    def test_HV_checkbox_alone_cannot_authorize_multi(self):
        c=self.select_fixture_marker();c.fields['note'].setText('fixture');c.multi_preview_button.click()
        for check in c.checks:check.setChecked(True)
        c.hv_clearance.setChecked(True)
        c.multi_run_button.click()
        self.assertFalse(self.runner.busy)
        self.assertEqual(self.backend.calls,[])
        self.assertIn('Not started',c.result.text())

    def test_click_launches_correct_mode(self):
        c=self.select_fixture_marker();c.fields['note'].setText('fixture');c.fields['output'].setText(self.tmp.name)
        c.multi_preview_button.click()
        for check in c.checks:check.setChecked(True)
        c.multi_clearance.setChecked(True)
        c.multi_run_button.click()
        self.assertTrue(self.runner.busy,c.result.text())
        self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.runner.services.handle.settings.purpose,'multi_h')
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)

    def test_busy_disables_all_three_actions(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        c=self.window.h_only_controls
        for b in (c.preview_button,c.hv_preview_button,c.multi_preview_button,c.run_button,c.hv_run_button,c.multi_run_button):
            self.assertFalse(b.isEnabled())
        with self.assertRaises(OwnershipError):self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.pump(lambda:not self.runner.busy)

    def test_close_cancels_and_defers_shutdown(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name);self.window.close()
        self.assertFalse(self.window.prior_owner.closed)
        self.pump(lambda:self.window.prior_owner.closed)
        self.assertFalse(self.runner.busy)
        self.assertIsNone(self.state.registration)

    def test_field_edit_invalidates_sequence_review(self):
        c=self.select_fixture_marker();c.multi_preview_button.click();c.multi_clearance.setChecked(True)
        c.fields['margin'].setText('110')
        self.assertIsNone(c.reviewed);self.assertFalse(c.multi_clearance.isChecked())
        self.assertFalse(c.multi_run_button.isEnabled())

    def test_mode_switch_preserves_separate_H_HV_actions(self):
        c=self.select_fixture_marker();c.multi_preview_button.click();c.multi_clearance.setChecked(True)
        c.hv_preview_button.click()
        self.assertTrue(c.hv_run_button.isEnabled());self.assertFalse(c.multi_run_button.isEnabled())
        self.assertFalse(c.multi_clearance.isChecked())
        c.preview_button.click()
        self.assertTrue(c.run_button.isEnabled());self.assertFalse(c.hv_run_button.isEnabled())

    def test_manual_narrow_bounds_rejected_before_handoff(self):
        c=self.select_fixture_marker();c.hv_preview_button.click();c.automatic_bounds.setChecked(False)
        c.multi_preview_button.click()
        self.assertIsNone(c.reviewed)
        self.assertIn('full_possible_envelope',c.result.text())
        self.assertEqual(self.backend.calls,[])
