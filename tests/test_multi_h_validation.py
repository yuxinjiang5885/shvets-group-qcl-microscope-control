"""Complete supervised profile acquisition/classification, no real hardware."""
from dataclasses import replace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from test_h_only_validation import setup_environment
from test_localization_pipeline import FakeDAQ
from test_reflection_scan import FakeClock
from experiment.scan_1d import StageBounds, load_scan
from experiment.marker_profile_classification import classify_profiles, ProfileClass
from ui.h_only_validation import InputHandoff
from ui.hv_validation import HVConfirmation
from ui.multi_h_validation import MultiHSpec, MultiHConfirmation, MultiHServices
from ui.localization_orchestration import LocateMarkerWorker, RunSettings, AcquisitionState, OwnershipStatus


class MultiHTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=setup_environment()
        self.spec=MultiHSpec((1000.,2000.),StageBounds(299,1701,1399,2601,'fixture-frame'))
        self.confirm=MultiHConfirmation(True,True,True,True,note='full profile rectangle',
            both_axes_clearance=True,multi_profile_clearance=True)
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.task=FakeDAQ(self.window.stage,self.spec.daq)
        self.events=[];self.hook=None

    def run_multi(self):
        handoff=InputHandoff(self.bridge);handoff.prepare()
        self.handle=self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='multi_h'))
        self.services=MultiHServices(self.bridge,self.handle,self.spec,self.tmp.name,lambda _:self.task,
            clock=FakeClock(),confirmation=self.confirm,handoff=handoff)
        def observe(event):
            self.events.append(event)
            if self.hook:self.hook(event)
        LocateMarkerWorker(self.controller,self.handle,self.services).run(observe)

    def at(self,phase,action):
        self.hook=lambda e:action() if e.name=='phase_changed' and e.detail==phase else None

    def no_return(self):
        self.assertNotEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertEqual(self.services.report['return_status'],'NOT_ATTEMPTED')

    def test_success_seven_scans_classifier_ready_return(self):
        self.run_multi()
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        r=self.services.report
        self.assertEqual(len(self.services.journals),7)
        self.assertEqual(r['central_count'],5)
        self.assertTrue(r['sufficient_for_rotation_fit'])
        self.assertTrue(r['usable_final_fits_available'])
        self.assertTrue(r['ready_for_rotation_fit'])
        self.assertEqual(r['accepted_y_span_um'],394)
        self.assertEqual(r['return_status'],'PASS')
        self.assertEqual(self.window.stage.position,self.spec.rough_start_xy)
        self.assertEqual(self.task.clear_count,1)

    def test_H_failure_prevents_later(self):
        self.task.flat=True
        with patch.object(MultiHSpec,'plan',side_effect=AssertionError('must not plan')):self.run_multi()
        self.no_return();self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_V_failure_prevents_planning(self):
        self.at('initial_V',lambda:setattr(self.task,'flat',True))
        with patch.object(MultiHSpec,'plan',side_effect=AssertionError('must not plan')):self.run_multi()
        self.no_return();self.assertFalse(list(self.services.path.glob('profile_*.jsonl')))

    def test_planner_symmetric_default_and_not_historical_offsets(self):
        ys,scans=self.spec.plan((1000,2000))
        self.assertEqual(ys,(1803,1902,2000,2098,2197))
        self.assertEqual(tuple(y-2000 for y in ys),tuple(2000-y for y in reversed(ys)))
        self.assertEqual(len(set(ys)),5)
        self.assertTrue(all(s.axis=='x' for s in scans))

    def test_planner_uses_measured_vertical_midpoint(self):
        stage=self.window.stage
        class ShiftedMarker:
            @property
            def position(self):return stage.position[0],stage.position[1]-11.25
        self.task.stage=ShiftedMarker()
        self.run_multi()
        center=self.services.report['initial_center']
        self.assertGreater(center[1],2010)
        self.assertEqual(self.services.report['planned_profile_y'],self.spec.plan(center)[0])
        self.assertNotEqual(self.services.report['planned_profile_y'],self.spec.plan((1000,2000))[0])

    def test_rounding_guard_and_distinct_rechecked(self):
        ys,_=self.spec.plan((1000.2,2000.49))
        from math import cos,sin,radians
        limit=250*(cos(radians(5))-sin(radians(5)))-30
        self.assertTrue(all(abs(y-2000.49)<=limit for y in ys))
        self.assertEqual(len(set(ys)),5)

    def test_insufficient_planning_span_rejected(self):
        with self.assertRaises(ValueError):replace(self.spec,required_y_span_um=450)

    def test_HV_only_clearance_insufficient(self):
        with self.assertRaisesRegex(ValueError,'full_possible_envelope'):
            replace(self.spec,bounds=StageBounds(649,1351,1649,2351,'fixture-frame'))

    def test_dynamic_plan_outside_bounds_before_profile_motion(self):
        with patch.object(MultiHServices,'acquire_initial_center',return_value=(5000,6000)):
            self.run_multi()
        self.no_return();self.assertEqual(self.task.reads,0)

    def test_profile_one_failure_stops(self):
        self.at('profile_H_01',lambda:setattr(self.task,'fail',True))
        self.run_multi();self.no_return()
        self.assertFalse((self.services.path/'profile_H_02.jsonl').exists())

    def test_profile_N_failure_no_retry_or_extra(self):
        self.at('profile_H_03',lambda:setattr(self.task,'fail',True))
        self.run_multi();self.no_return()
        self.assertTrue((self.services.path/'profile_H_03.jsonl').exists())
        self.assertFalse((self.services.path/'profile_H_04.jsonl').exists())
        self.assertEqual(len(list(self.services.path.glob('*.jsonl'))),5)

    def test_profile_journal_failure_stops(self):
        def read(path):
            if path.stem=='profile_H_02':raise ValueError('journal_failure')
            return load_scan(path)
        with patch('ui.localization_pipeline.load_scan',side_effect=read):self.run_multi()
        self.no_return();self.assertFalse((self.services.path/'profile_H_03.jsonl').exists())

    def test_distinct_finalized_journals(self):
        self.run_multi()
        self.assertEqual([p.stem for p in self.services.journals],['initial_H','initial_V']+[f'profile_H_{i:02d}' for i in range(1,6)])
        for path in self.services.journals:self.assertEqual(len(load_scan(path).points),71)

    def test_cancel_between_profiles(self):
        self.hook=lambda e:self.controller.request_cancel() if e.name=='profile_completed' and e.detail['profile_completed']=='profile_H_02' else None
        self.run_multi();self.no_return()
        self.assertFalse((self.services.path/'profile_H_03.jsonl').exists())

    def test_cancel_during_profile(self):
        original=self.task.acquire_bounded
        def read(*a,**k):
            if self.task.reads==150:self.controller.request_cancel()
            return original(*a,**k)
        self.task.acquire_bounded=read;self.run_multi();self.no_return()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)

    def test_complete_set_passed_once_no_trimming(self):
        with patch('ui.multi_h_validation.classify_profiles',wraps=classify_profiles) as classify:
            self.run_multi()
        classify.assert_called_once()
        rows=classify.call_args.args[0]
        self.assertEqual(len(rows),5)
        self.assertEqual(tuple(p.identifier for p in rows),tuple(f'profile_H_{i:02d}' for i in range(1,6)))

    def test_inconsistent_preserved_and_reported(self):
        from ui.localization_pipeline import analyze_scan
        def analyze(scan,settings):
            edge=analyze_scan(scan,settings)
            if scan.settings.axis=='x' and scan.settings.fixed_um>2190:
                edge=replace(edge,left_edge_um=edge.left_edge_um+20,right_edge_um=edge.right_edge_um+20,midpoint_um=edge.midpoint_um+20)
            return edge
        with patch('ui.localization_pipeline.analyze_scan',side_effect=analyze):self.run_multi()
        self.assertEqual(len(self.services.report['profiles']),5)
        self.assertEqual(self.services.report['profiles'][-1]['classification'],'INCONSISTENT')
        self.assertEqual(self.services.report['central_count'],4)

    def test_corner_profiles_handled_by_classifier(self):
        self.spec=replace(self.spec,supported_rotation_deg=0,center_uncertainty_um=0,boundary_guard_um=5)
        self.run_multi()
        states=[r['classification'] for r in self.services.report['profiles']]
        self.assertEqual(states[0],'CORNER_AFFECTED')
        self.assertEqual(states[-1],'CORNER_AFFECTED')
        self.assertEqual(len(states),5)

    def test_invalid_optical_profile_forwarded_not_removed(self):
        self.at('profile_H_05',lambda:setattr(self.task,'flat',True))
        with patch('ui.multi_h_validation.classify_profiles',wraps=classify_profiles) as classify:self.run_multi()
        self.assertEqual(len(classify.call_args.args[0]),5)
        self.assertFalse(classify.call_args.args[0][-1].edge_valid)
        self.assertEqual(self.services.report['profiles'][-1]['classification'],'INVALID')
        self.assertEqual(len(self.services.journals),7)

    def test_classifier_insufficient_blocks_return(self):
        def insufficient(*a,**k):return replace(classify_profiles(*a,**k),sufficient_for_rotation_fit=False,usable_final_fits=None,reasons=('fixture_insufficient',))
        with patch('ui.multi_h_validation.classify_profiles',side_effect=insufficient):self.run_multi()
        self.no_return();self.assertFalse(self.services.report['ready_for_rotation_fit'])
        self.assertIn('fixture_insufficient',self.services.report['classifier_reasons'])

    def test_classifier_exception_blocks_return(self):
        with patch('ui.multi_h_validation.classify_profiles',side_effect=ValueError('classifier_failed')):self.run_multi()
        self.no_return()

    def test_no_production_rotation_center_registration(self):
        with patch('ui.localization_pipeline.fit_rotation',side_effect=AssertionError('forbidden')), \
             patch('ui.localization_pipeline.refine_marker_center',side_effect=AssertionError('forbidden')), \
             patch('ui.localization_pipeline.build_stage_registration',side_effect=AssertionError('forbidden')):
            self.run_multi()
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertIsNone(self.state.registration)
        self.assertFalse(any(e.name=='registration_completed' for e in self.events))
        self.assertFalse(self.services.report['production_rotation_executed'])

    def test_return_only_after_successful_classifier(self):
        original=MultiHServices._return
        def returning(service,checkpoint):
            self.assertEqual(len(service.journals),7)
            self.assertTrue(service.report['ready_for_rotation_fit'])
            original(service,checkpoint)
        with patch.object(MultiHServices,'_return',returning):self.run_multi()
        self.assertEqual(self.services.report['return_status'],'PASS')

    def test_return_failure_invalidates_success(self):
        with patch.object(MultiHServices,'_return',side_effect=ValueError('return_failed')):self.run_multi()
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED)
        self.assertEqual(self.services.report['return_status'],'FAILED_OR_INCOMPLETE')

    def test_cleanup_failure_quarantines(self):
        self.task.clear_fails=True;self.run_multi()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertEqual(self.window.stage.joystick_calls,[False])

    def test_old_HV_confirmation_rejected(self):
        self.confirm=HVConfirmation(True,True,True,True,note='HV only',both_axes_clearance=True)
        self.run_multi();self.no_return();self.assertEqual(self.task.reads,0)

    def test_new_clearance_required(self):
        self.confirm=replace(self.confirm,multi_profile_clearance=False)
        self.run_multi();self.no_return();self.assertEqual(self.task.reads,0)

    def test_context_change_prevents_profiles(self):
        self.at('profile_planning',lambda:self.bridge.frame_event('reset'))
        self.run_multi();self.no_return()
        self.assertFalse(list(self.services.path.glob('profile_*.jsonl')))

    def test_cancel_before_classifier(self):
        self.at('profile_classification',self.controller.request_cancel)
        self.run_multi();self.no_return()

    def test_cancel_before_return(self):
        self.at('success_only_return',self.controller.request_cancel)
        self.run_multi()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)
        self.assertEqual(self.window.stage.position[1],2197)
