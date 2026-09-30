"""Qt H+V preview/runner integration with persistent fake Prior and fake NI."""
import unittest
from dataclasses import replace
from math import tanh
import test_h_only_controls as h_tests
from test_reflection_scan import FakeClock
from ui.hv_validation import HVServices, HVSpec, HVConfirmation
from ui.localization_orchestration import AcquisitionState, OwnershipError
from experiment.scan_1d import StageBounds


class FastHVServices(HVServices):
    def __init__(self,*a,**k):super().__init__(*a,clock=FakeClock(),**k)


class HVQtTests(unittest.TestCase):
    setUpClass=classmethod(h_tests.HOnlyQtTests.setUpClass.__func__)
    pump=h_tests.HOnlyQtTests.pump
    cleanup_window=h_tests.HOnlyQtTests.cleanup_window
    select_fixture_marker=h_tests.HOnlyQtTests.select_fixture_marker

    def setUp(self):
        h_tests.HOnlyQtTests.setUp(self)
        self.runner.services_type=FastHVServices
        self.spec=HVSpec((1000.,2000.),StageBounds(649,1351,1649,2351,'fixture-frame'))
        self.confirm=HVConfirmation(True,True,True,True,note='fake full rectangle',both_axes_clearance=True)
        original=self.backend.read
        def read(*a):
            result=original(*a)
            x,y=self.observed.position
            a[4][0,:]=1+3*(tanh((x-750)/3)-tanh((x-1250)/3))/2*(tanh((y-1750)/3)-tanh((y-2250)/3))/2
            return result
        self.backend.read=read

    def test_Qt_HV_success_no_publication(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        report=self.window.auto_relocation.run_display['hv_result']
        self.assertEqual(report['initial_center'],(1000,2000))
        self.assertEqual(report['cleanup_status'],'PASS')
        self.assertEqual(report['return_status'],'PASS')
        self.assertFalse(report['registration_published'])
        self.assertTrue((self.runner.services.path/'hv_result.json').exists())
        self.assertFalse(self.window.auto_relocation.locate_button.isEnabled())

    def test_preview_full_envelope_dynamic_X_and_separate_confirmation(self):
        c=self.select_fixture_marker()
        c.preview_button.click()
        for check in c.checks:check.setChecked(True)
        c.hv_preview_button.click()
        self.assertIsInstance(c.reviewed[0],HVSpec)
        self.assertEqual((c.reviewed[0].bounds.y_min_um,c.reviewed[0].bounds.y_max_um),(1649,2351))
        self.assertIn('DYNAMIC',c.result.text())
        self.assertIn('1650.0 to 2350.0',c.result.text())
        self.assertFalse(c.hv_clearance.isChecked())
        self.assertFalse(any(check.isChecked() for check in c.checks))
        self.assertFalse(c.run_button.isEnabled())
        self.assertTrue(c.hv_run_button.isEnabled())
        self.assertEqual(self.backend.calls,[])

    def test_old_confirmation_cannot_start_HV(self):
        self.confirm=replace(self.confirm,both_axes_clearance=False)
        with self.assertRaisesRegex(ValueError,'separate_both_axes'):
            self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.assertEqual(self.backend.calls,[])
        self.assertIsNone(self.controller.active)

    def test_switch_back_to_H_only_clears_review(self):
        c=self.select_fixture_marker();c.hv_preview_button.click();c.hv_clearance.setChecked(True)
        c.preview_button.click()
        self.assertNotIsInstance(c.reviewed[0],HVSpec)
        self.assertFalse(c.hv_clearance.isChecked())
        self.assertFalse(c.hv_run_button.isEnabled())
        self.assertTrue(c.run_button.isEnabled())

    def test_busy_blocks_both_actions(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        c=self.window.h_only_controls
        for button in (c.preview_button,c.hv_preview_button,c.run_button,c.hv_run_button):
            self.assertFalse(button.isEnabled())
        with self.assertRaises(OwnershipError):self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.pump(lambda:not self.runner.busy)

    def test_HV_cancel_and_deferred_close(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.window.close()
        self.assertFalse(self.window.prior_owner.closed)
        self.pump(lambda:self.window.prior_owner.closed)
        self.assertFalse(self.runner.busy)
        self.assertIsNone(self.state.registration)

    def test_edited_envelope_requires_new_preview(self):
        c=self.select_fixture_marker();c.hv_preview_button.click()
        c.hv_clearance.setChecked(True);c.fields['step'].setText('20')
        self.assertIsNone(c.reviewed)
        self.assertFalse(c.hv_run_button.isEnabled())
        self.assertFalse(c.hv_clearance.isChecked())
