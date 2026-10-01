"""Production H/V transaction through the experimental UI, with inert devices."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import test_hv_controls as fixtures
from test_reflection_scan import FakeClock
from experiment.stage_registration import local_to_stage, Orientation
from ui.h_only_validation import HOnlyServices
from ui.localization_pipeline import LocalizationPipelineServices
from ui.localization_orchestration import AcquisitionState, OwnershipStatus, OwnershipError
from ui.registration_state import RegistrationStatus, ContextEvent
from ui.translation_localization import TranslationServices
from ui.translation_registration import build_translation_registration


class FastTranslationServices(TranslationServices):
    def __init__(self,*a,**k):super().__init__(*a,clock=FakeClock(),**k)


class TranslationTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.HVQtTests.setUpClass.__func__)
    pump=fixtures.HVQtTests.pump
    cleanup_window=fixtures.HVQtTests.cleanup_window
    select_fixture_marker=fixtures.HVQtTests.select_fixture_marker

    def setUp(self):
        fixtures.HVQtTests.setUp(self)
        self.runner.services_type=FastTranslationServices
        self.assertFalse(self.window.translation_launch_enabled)
        self.window.translation_launch_enabled=True  # Inert fixture opt-in only.

    def run_production(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name,production=True)
        self.pump(lambda:not self.runner.busy)

    def assert_failed(self):
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED,self.controller.reasons)
        self.assertIsNone(self.state.registration)
        self.assertFalse(self.window.auto_relocation.run_display['translation_only_result']['registration_published'])

    def test_success_H_then_V_no_optional_calibration_calls(self):
        scan=LocalizationPipelineServices._scan
        calls=[]
        def scanning(service,name,*a,**k):
            calls.append(name)
            return scan(service,name,*a,**k)
        with ExitStack() as stack:
            for name in ('plan_profiles','classify_profiles','fit_rotation','refine_marker_center','build_stage_registration'):
                stack.enter_context(patch('ui.localization_pipeline.'+name,side_effect=AssertionError(name)))
            for name in ('classify_profiles','fit_rotation','refine_marker_center','build_stage_registration'):
                stack.enter_context(patch('ui.registration_state.'+name,side_effect=AssertionError(name)))
            stack.enter_context(patch.object(LocalizationPipelineServices,'_scan',scanning))
            self.run_production()
        self.assertEqual(calls,['initial_H','initial_V'])
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        self.assertEqual(self.state.status,RegistrationStatus.VALID)
        self.assertEqual(self.state.registration.registration.rotation_deg,0.)
        self.assertEqual(self.state.registration.registration_mode,'translation_only')
        self.assertFalse(self.state.registration.rotation_calibrated)
        self.assertEqual(self.state.registration.assumed_theta_deg,0.)
        self.assertEqual(self.state.registration.registration.orientation,Orientation.FLIP_X)
        self.assertEqual(local_to_stage(0,0,self.state.registration.registration),(1000.,2000.))
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.AVAILABLE)
        self.assertEqual(self.observed.position,(1000.,2000.))

    def test_default_runner_selects_translation_service(self):
        self.runner.services_type=HOnlyServices
        with patch('ui.h_only_controls.TranslationServices',FastTranslationServices):
            self.run_production()
        self.assertIsInstance(self.runner.services,TranslationServices)
        self.assertEqual(self.state.status,RegistrationStatus.VALID)

    def test_real_launch_is_gated_by_default(self):
        self.window.translation_launch_enabled=False
        with self.assertRaisesRegex(OwnershipError,'supervised_opt_in'):self.run_production()
        self.assertEqual(self.backend.calls,[])

    def test_primary_button_preview_confirm_publication_and_registered_preview(self):
        c=self.select_fixture_marker()
        c.fields['note'].setText('inert production test');c.fields['output'].setText(self.tmp.name)
        c.translation_preview_button.click()
        self.assertIsNotNone(c.reviewed,c.result.text())
        for checkbox in c.checks:checkbox.setChecked(True)
        c.translation_clearance.setChecked(True)
        self.window.auto_relocation.locate_button.click()
        self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.state.status,RegistrationStatus.VALID,self.controller.reasons)
        panel=self.window.auto_relocation
        self.assertIn('VALID — TRANSLATION ONLY',panel.status_label.text())
        self.assertIn('assumed 0° — not calibrated',panel.values_label.text())
        self.assertIn('rotation_assumed_zero_not_calibrated',panel.warnings_label.text())
        predictions=panel.selection.registered_predictions
        marker=panel.selection.assignments.marker
        self.assertEqual(predictions[marker.feature_id].stage_um,(1000.,2000.))
        target=next(iter(panel.selection.assignments.ms_assignments))
        self.assertEqual(predictions[target].stage_um,(385.,2150.))
        self.assertTrue(panel.selection._prediction_items)
        feature=panel.selection.assignments.ms_assignments[target].feature
        panel.selection.select_feature(feature)
        self.assertEqual(self.state.prediction.stage_um,(385.,2150.))
        self.assertIn('385.0',panel.prediction_label.text())
        self.assertTrue(panel.development_body.isHidden())
        self.assertTrue(hasattr(c,'hv_run_button') and hasattr(c,'multi_run_button'))
        self.assertFalse(hasattr(panel,'move_button'))

    def test_old_clearance_cannot_authorize_production(self):
        c=self.select_fixture_marker();c.translation_preview_button.click()
        for checkbox in c.checks:checkbox.setChecked(True)
        c.hv_clearance.setChecked(True)
        self.window.auto_relocation.locate_button.click()
        self.assertFalse(self.runner.busy)
        self.assertEqual(self.backend.calls,[])

    def test_H_failure_prevents_V_and_publication(self):
        with patch.object(LocalizationPipelineServices,'_scan',side_effect=ValueError('H failed')) as scan:
            self.run_production()
        self.assertEqual(scan.call_count,1)
        self.assert_failed()
        self.assertEqual(self.runner.services.report['return_status'],'NOT_ATTEMPTED')

    def test_V_failure_preserves_H_no_return_no_publication(self):
        original=LocalizationPipelineServices._scan
        def scanning(service,name,*a,**k):
            if name=='initial_V':raise ValueError('V failed')
            return original(service,name,*a,**k)
        with patch.object(LocalizationPipelineServices,'_scan',scanning):self.run_production()
        self.assert_failed()
        self.assertTrue((self.runner.services.path/'initial_H.jsonl').exists())
        self.assertEqual(self.runner.services.report['return_status'],'NOT_ATTEMPTED')

    def test_return_failure_prevents_publication(self):
        with patch.object(TranslationServices,'_return',side_effect=ValueError('return failed')):
            self.run_production()
        self.assert_failed()

    def test_cleanup_failure_quarantines_prevents_publication(self):
        self.backend.clear_fail=True
        self.run_production()
        self.assert_failed()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)

    def test_stale_context_before_publication_prevents_approval(self):
        original=self.controller.offer_candidate
        def offer(handle,evidence):
            original(handle,evidence)
            self.controller.handle_context_event(ContextEvent.INPUTS)
        with patch.object(self.controller,'offer_candidate',side_effect=offer):self.run_production()
        self.assertIn(self.controller.machine.state,(AcquisitionState.CANCELLED,AcquisitionState.FAILED))
        self.assertIsNone(self.state.registration)

    def test_cancel_after_H_prevents_V(self):
        original=TranslationServices.acquire_horizontal
        def horizontal(service,*a,**k):
            result=original(service,*a,**k)
            self.controller.request_cancel()
            return result
        with patch.object(TranslationServices,'acquire_horizontal',horizontal):self.run_production()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)
        self.assertIsNone(self.state.registration)
        self.assertFalse((self.runner.services.path/'initial_V.jsonl').exists())

    def test_no_publication_before_return_or_cleanup(self):
        original_return=TranslationServices._return
        original_release=TranslationServices.release_daq
        def returning(service,*a):
            self.assertIsNone(self.state.registration)
            return original_return(service,*a)
        def releasing(service):
            self.assertIsNone(self.state.registration)
            return original_release(service)
        with patch.object(TranslationServices,'_return',returning),patch.object(TranslationServices,'release_daq',releasing):
            self.run_production()
        self.assertIsNotNone(self.state.registration)

    def test_safe_failed_candidate_retains_prior_approval(self):
        self.run_production();approved=self.state.registration
        with patch.object(TranslationServices,'acquire_horizontal',side_effect=ValueError('H failure')):
            self.run_production()
        self.assertIs(self.state.registration,approved)
        self.assertEqual(self.state.status,RegistrationStatus.VALID)

    def test_frame_event_clears_approved_translation(self):
        self.run_production()
        self.controller.handle_context_event(ContextEvent.FRAME)
        self.assertIsNone(self.state.registration)

    def test_ordinary_motion_preserves_approval(self):
        self.run_production();approved=self.state.registration
        self.controller.handle_context_event(ContextEvent.MOVEMENT)
        self.assertIs(self.state.registration,approved)

    def test_invalid_center_and_orientation_rejected(self):
        self.run_production();evidence=self.state.evidence
        with self.assertRaises(ValueError):
            build_translation_registration(replace(evidence,horizontal_edge=replace(evidence.horizontal_edge,midpoint_um=float('nan'))))
        with self.assertRaises(ValueError):
            build_translation_registration(replace(evidence,context=replace(evidence.context,orientation=Orientation.FLIP_Y)))

    def test_journal_failure_prevents_publication(self):
        with patch('ui.localization_pipeline.load_scan',side_effect=ValueError('journal invalid')):
            self.run_production()
        self.assert_failed()

    def test_registration_build_failure_no_return(self):
        with patch('ui.translation_localization.build_translation_registration',side_effect=ValueError('bad registration')):
            self.run_production()
        self.assert_failed()
        self.assertEqual(self.runner.services.report['return_status'],'NOT_ATTEMPTED')

    def test_cleanup_failure_invalidates_prior_approval(self):
        self.run_production();self.backend.clear_fail=True
        self.run_production()
        self.assert_failed()

    def test_translation_evidence_cannot_enter_calibrated_run(self):
        self.run_production();evidence=self.state.evidence
        from ui.localization_orchestration import RunSettings, CleanupOutcome
        handle=self.controller.start(RunSettings(self.state.context,self.state.context_generation,'fixture'))
        with self.assertRaisesRegex(ValueError,'malformed_candidate'):
            self.controller.offer_candidate(handle,evidence)
        self.controller.finish(handle,succeeded=False,cleanup=CleanupOutcome(True,True))

    def test_translation_preview_clears_on_context_invalidation(self):
        self.select_fixture_marker()
        self.spec=replace(self.spec,bounds=replace(self.spec.bounds,frame_id=self.state.context.frame_id))
        self.run_production()
        panel=self.window.auto_relocation
        self.assertTrue(panel.selection.registered_predictions)
        self.controller.handle_context_event(ContextEvent.FRAME)
        panel.refresh()
        self.assertEqual(panel.selection.registered_predictions,{})
        self.assertEqual(panel.selection._prediction_items,[])

    def test_target_label_change_preserves_translation_registration(self):
        self.select_fixture_marker()
        self.spec=replace(self.spec,bounds=replace(self.spec.bounds,frame_id=self.state.context.frame_id))
        self.run_production()
        panel=self.window.auto_relocation;approved=self.state.registration
        assignments=panel.selection.assignments
        target=next(iter(assignments.ms_assignments))
        assignments.rename_ms(target,'operator label')
        panel.selection._refresh_assignments()
        self.assertIs(self.state.registration,approved)
        self.assertEqual(panel.selection.registered_predictions[target].label,'operator label')
