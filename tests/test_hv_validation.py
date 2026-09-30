"""H+V orchestration through real scan/analysis APIs and inert stage/DAQ."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from test_h_only_validation import setup_environment
from test_localization_pipeline import FakeDAQ
from test_reflection_scan import FakeClock
from experiment.scan_1d import StageBounds, load_scan
from ui.h_only_validation import InputHandoff, OperatorConfirmation
from ui.hv_validation import HVSpec, HVConfirmation, HVServices
from ui.localization_orchestration import (LocateMarkerWorker, RunSettings,
    AcquisitionState, OwnershipStatus)


class HVTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=setup_environment()
        self.spec=HVSpec((1000.,2000.),StageBounds(649,1351,1649,2351,'fixture-frame'))
        self.confirm=HVConfirmation(True,True,True,True,note='reviewed 2D',both_axes_clearance=True)
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.task=FakeDAQ(self.window.stage,self.spec.daq)
        self.events=[];self.hook=None

    def run_hv(self):
        handoff=InputHandoff(self.bridge);handoff.prepare()
        self.handle=self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='hv'))
        self.services=HVServices(self.bridge,self.handle,self.spec,self.tmp.name,lambda _:self.task,
            clock=FakeClock(),confirmation=self.confirm,handoff=handoff)
        def observe(event):
            self.events.append(event)
            if self.hook:self.hook(event)
        LocateMarkerWorker(self.controller,self.handle,self.services).run(observe)

    def at(self,phase,action):
        self.hook=lambda e:action() if e.name=='phase_changed' and e.detail==phase else None

    def failed_without_return(self):
        self.assertNotEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertEqual(self.services.report['return_status'],'NOT_ATTEMPTED')

    def test_success_initial_center_and_only_two_profiles(self):
        self.run_hv()
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        self.assertEqual(self.services.report['initial_center'],(1000,2000))
        self.assertEqual(self.services.report['v_points'],71)
        self.assertEqual(self.services.report['points'],71)
        self.assertEqual([p.stem for p in self.services.journals],['initial_H','initial_V'])
        self.assertEqual(self.window.stage.position,(1000,2000))
        self.assertEqual(self.task.clear_count,1)

    def test_H_failure_prevents_V_and_return(self):
        self.task.flat=True;self.run_hv();self.failed_without_return()
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_H_journal_failure_prevents_V(self):
        with patch('ui.localization_pipeline.load_scan',side_effect=ValueError('journal_failure')):self.run_hv()
        self.failed_without_return()
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())
        self.assertTrue((self.services.path/'initial_H.jsonl').exists())

    def test_rounding_nearest_ties_even(self):
        for x,expected in ((1000.49,1000),(1000.5,1000),(1001.5,1002),(1000.9,1001)):
            self.assertEqual(self.spec.vertical(x).fixed_um,expected)

    def test_negative_rounding(self):
        spec=replace(self.spec,rough_start_xy=(-1000,2000),bounds=StageBounds(-1351,-649,1649,2351,'fixture-frame'))
        self.assertEqual(spec.vertical(-1001.5).fixed_um,-1002)

    def test_outside_dynamic_X_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside_reviewed'):self.spec.vertical(1351)

    def test_full_rectangle_prevalidated(self):
        with self.assertRaises(ValueError):replace(self.spec,bounds=StageBounds(649,1351,1999,2001,'fixture-frame'))

    def test_cancel_after_H_prevents_V(self):
        self.hook=lambda e:self.controller.request_cancel() if e.name=='profile_completed' else None
        self.run_hv();self.failed_without_return()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_cancel_before_V_motion(self):
        self.at('before_vertical',self.controller.request_cancel)
        self.run_hv();self.failed_without_return()
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_V_movement_failure(self):
        self.at('initial_V',lambda:setattr(self.window.stage,'fail',lambda c:'goto-position' in c))
        self.run_hv();self.failed_without_return()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertTrue(any('goto-position' in c for c in self.window.stage.calls))

    def test_V_read_failure(self):
        self.at('initial_V',lambda:setattr(self.task,'fail',True))
        self.run_hv();self.failed_without_return()
        self.assertTrue((self.services.path/'initial_V.jsonl').exists())

    def test_V_journal_failure(self):
        def read(path):
            if path.stem=='initial_V':raise ValueError('V_journal_failure')
            return load_scan(path)
        with patch('ui.localization_pipeline.load_scan',side_effect=read):self.run_hv()
        self.failed_without_return()
        self.assertEqual(len(list(self.services.path.glob('*.jsonl'))),2)

    def invalid_v(self,reason):
        from ui.localization_pipeline import analyze_scan
        def analyze(scan,settings):
            result=analyze_scan(scan,settings)
            return replace(result,valid=False,reasons=(reason,)) if scan.settings.axis=='y' else result
        with patch('ui.localization_pipeline.analyze_scan',side_effect=analyze):self.run_hv()
        self.failed_without_return();self.assertIn(reason,str(self.controller.reasons))

    def test_V_ambiguity(self):self.invalid_v('ambiguous_edges')
    def test_V_width_failure(self):self.invalid_v('width_outside_tolerance')

    def test_return_after_both_finalized(self):
        original=HVServices._return
        def returning(service,checkpoint):
            self.assertEqual(len(service.journals),2)
            for path in service.journals:self.assertEqual(len(load_scan(path).points),71)
            original(service,checkpoint)
        with patch.object(HVServices,'_return',returning):self.run_hv()
        self.assertEqual(self.services.report['return_status'],'PASS')

    def test_return_failure_blocks_success(self):
        with patch.object(HVServices,'_return',side_effect=RuntimeError('return_failed')):self.run_hv()
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED)
        self.assertEqual(self.services.report['return_status'],'FAILED_OR_INCOMPLETE')

    def test_cleanup_failure_quarantines(self):
        self.task.clear_fails=True;self.run_hv()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertEqual(self.window.stage.joystick_calls,[False])

    def test_no_rotation_center_or_registration_calls(self):
        with patch('ui.localization_pipeline.fit_rotation',side_effect=AssertionError('forbidden')), \
             patch('ui.localization_pipeline.refine_marker_center',side_effect=AssertionError('forbidden')), \
             patch('ui.localization_pipeline.classify_profiles',side_effect=AssertionError('forbidden')), \
             patch('ui.localization_pipeline.build_stage_registration',side_effect=AssertionError('forbidden')):
            self.run_hv()
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertIsNone(self.state.registration)
        self.assertFalse(any(e.name=='registration_completed' for e in self.events))
        self.assertTrue(any(isinstance(e.detail,dict) and e.detail.get('hv_complete') for e in self.events))

    def test_old_H_confirmation_rejected(self):
        self.confirm=OperatorConfirmation(True,True,True,True,note='H only')
        self.run_hv();self.failed_without_return();self.assertEqual(self.task.reads,0)

    def test_separate_2D_confirmation_required(self):
        self.confirm=replace(self.confirm,both_axes_clearance=False)
        self.run_hv();self.failed_without_return();self.assertEqual(self.task.reads,0)

    def test_cancel_during_V(self):
        original=self.task.acquire_bounded
        def read(*a,**k):
            if self.task.reads==80:self.controller.request_cancel()
            return original(*a,**k)
        self.task.acquire_bounded=read
        self.run_hv();self.failed_without_return()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)

    def test_cancel_after_V_verification_no_return(self):
        self.hook=lambda e:self.controller.request_cancel() if e.name=='profile_completed' and e.detail['profile_completed']=='initial_V' else None
        self.run_hv();self.failed_without_return()

    def test_frame_change_before_V(self):
        self.at('before_vertical',lambda:self.bridge.frame_event('reset'))
        self.run_hv();self.failed_without_return()
        self.assertIsNone(self.state.registration)

    def test_Y_convention_increasing(self):
        self.run_hv();v=load_scan(self.services.journals[1])
        self.assertEqual(v.settings.axis,'y')
        self.assertEqual(v.points[0].measured_um,(1000,1650))
        self.assertEqual(v.points[-1].measured_um,(1000,2350))

    def test_report_preserves_warnings_and_rounding_delta(self):
        self.run_hv();r=self.services.report
        self.assertEqual(r['v_x_rounding_delta'],0)
        self.assertEqual(r['chosen_v_x'],1000)
        self.assertIn('joystick_command_ack_only',r['warnings'])
        self.assertIn('vertical_edge_diagnostics',r)
        self.assertEqual(r['v_measured_y'],(1650,2350))

    def test_no_archived_coordinate_defaults(self):
        spec=replace(self.spec,rough_start_xy=(5000,-1000),bounds=StageBounds(4649,5351,-1351,-649,'other-frame'))
        self.assertEqual(spec.vertical(5002.2).positions()[0],(5002,-1350))
