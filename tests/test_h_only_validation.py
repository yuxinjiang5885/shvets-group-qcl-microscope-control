"""Single-H acquisition and handoff using inert stage/DAQ objects only."""
from dataclasses import replace
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from test_operational_localization_bridge import environment, FakeThread
from test_localization_pipeline import FakeDAQ
from test_reflection_scan import FakeClock
from experiment.scan_1d import StageBounds
from ui.h_only_validation import HOnlySpec, OperatorConfirmation, InputHandoff, HOnlyServices
from ui.localization_orchestration import LocateMarkerWorker, RunSettings, AcquisitionState, OwnershipStatus, OwnershipError


def setup_environment():
    window,state,controller,bridge=environment()
    state.set_context(replace(state.context,gds_path='fixture.gds',sample_id='fixture-sample',inputs_id='fixture-input'))
    window.laser=SimpleNamespace(isArmed=True,isTuned=True,isEmitting=False)
    window.stage.joystick_state=True
    window.stage.joystick_calls=[]
    def joystick(enable):
        window.stage.joystick_calls.append(enable)
        window.stage.joystick_state=enable
    window.stage.joystick=joystick
    return window,state,controller,bridge


class HOnlyTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=setup_environment()
        self.spec=HOnlySpec((1000.,2000.),StageBounds(649,1351,1999,2001,'fixture-frame'))
        self.confirm=OperatorConfirmation(True,True,True,True,note='fixture operator clearance')
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.handoff=InputHandoff(self.bridge)
        self.events=[];self.hook=None
        self.task=FakeDAQ(self.window.stage,self.spec.daq)

    def run_h(self):
        self.handoff.prepare()
        self.handle=self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='h_only'))
        self.services=HOnlyServices(self.bridge,self.handle,self.spec,self.tmp.name,lambda _:self.task,
            clock=FakeClock(),confirmation=self.confirm,handoff=self.handoff)
        def observe(event):
            self.events.append(event)
            if self.hook:self.hook(event)
        LocateMarkerWorker(self.controller,self.handle,self.services).run(observe)

    def test_success_one_H_return_cleanup_no_registration(self):
        self.run_h()
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        self.assertEqual(len(self.services.journals),1)
        self.assertEqual(self.services.report['points'],71)
        self.assertAlmostEqual(self.services.report['midpoint'],1000)
        self.assertAlmostEqual(self.services.report['width'],500)
        self.assertEqual(self.services.report['return_status'],'PASS')
        self.assertEqual(self.window.stage.position,self.spec.rough_start_xy)
        self.assertEqual(self.task.clear_count,1)
        self.assertEqual(self.window.stage.joystick_calls,[False,True])
        self.assertIsNone(self.state.registration)
        self.assertFalse(any(e.name=='registration_completed' for e in self.events))
        self.assertFalse(any('initial_V' in str(e.detail) for e in self.events))

    def test_rough_start_mismatch_no_task_or_move(self):
        self.window.stage.position=(1002.,2000.)
        self.run_h()
        self.assertIn('confirmed_rough_start_mismatch',str(self.controller.reasons))
        self.assertEqual(self.task.reads,0)
        self.assertFalse(any('goto-position' in c for c in self.window.stage.calls))

    def test_envelope_rejected_before_handoff(self):
        with self.assertRaises(ValueError):replace(self.spec,bounds=StageBounds(700,1300,1999,2001,'fixture-frame'))
        self.assertEqual(self.window.stage.calls,[])

    def test_not_archived_coordinates(self):
        spec=replace(self.spec,rough_start_xy=(5000,4000),bounds=StageBounds(4600,5400,3999,4001,'new-frame'))
        self.assertEqual(spec.scan().positions()[0],(4650,4000))

    def test_journal_failure(self):
        with patch('ui.localization_pipeline.load_scan',side_effect=ValueError('journal_broken')):self.run_h()
        self.assertIn('journal_broken',str(self.controller.reasons))
        self.assertEqual(self.services.report['return_status'],'NOT_ATTEMPTED')

    def test_flat_edges_fail_no_return(self):
        self.task.flat=True;self.run_h()
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED)
        self.assertEqual(self.services.report['return_status'],'NOT_ATTEMPTED')

    def test_width_invalid(self):
        from ui.localization_pipeline import analyze_scan
        def bad(*a,**k):return replace(analyze_scan(*a,**k),valid=False,reasons=('width_outside_tolerance',))
        with patch('ui.localization_pipeline.analyze_scan',side_effect=bad):self.run_h()
        self.assertIn('width_outside_tolerance',str(self.controller.reasons))

    def test_return_failure_blocks_success(self):
        with patch.object(HOnlyServices,'_return',side_effect=ValueError('return_failed')):self.run_h()
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED)
        self.assertEqual(self.services.report['return_status'],'FAILED_OR_INCOMPLETE')

    def test_cleanup_failure_quarantines_no_restore(self):
        self.task.clear_fails=True;self.run_h()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertEqual(self.window.stage.joystick_calls,[False])

    def test_restore_failure_quarantines(self):
        original=self.window.stage.joystick
        def fail(enable):
            if enable:raise RuntimeError('restore_failed')
            original(enable)
        self.window.stage.joystick=fail;self.run_h()
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertEqual(self.handoff.restore_result,'RESTORE_FAILURE')

    def test_cancel_before_H(self):
        self.hook=lambda e:self.controller.request_cancel() if e.name=='phase_changed' and e.detail=='initial_H' else None
        self.run_h()
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)
        self.assertEqual(self.task.reads,0)
        self.assertEqual(self.services.report['return_status'],'NOT_ATTEMPTED')

    def test_frame_change_during_scan_blocks_success_restore(self):
        self.hook=lambda e:self.bridge.frame_event('reset') if e.name=='profile_completed' else None
        self.run_h()
        self.assertNotEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertEqual(self.window.stage.joystick_calls,[False])
        self.assertIsNone(self.state.registration)

    def test_gamepad_idle(self):
        self.handoff.prepare();self.assertEqual(self.handoff.result,'ALREADY_STOPPED')

    def gamepad(self):
        motion=self.window.stageMotionWindow
        motion.threadG=FakeThread();motion.workerG=SimpleNamespace(request_stop=lambda:None)
        return motion

    def test_gamepad_confirmed_stop(self):
        motion=self.gamepad();self.handoff.prepare()
        self.assertEqual(self.handoff.result,'STOPPED_SUCCESSFULLY');self.assertIsNone(motion.workerG)

    def test_gamepad_timeout(self):
        self.gamepad().threadG.wait_ok=False
        with self.assertRaisesRegex(OwnershipError,'STOP_TIMEOUT'):self.handoff.prepare()
        self.assertEqual(self.window.stage.joystick_calls,[])

    def test_stale_gamepad_completion(self):
        motion=self.gamepad();motion.threadG.on_wait=lambda:setattr(motion,'workerG',object())
        with self.assertRaisesRegex(OwnershipError,'STALE_COMPLETION'):self.handoff.prepare()

    def test_worker_still_active(self):
        motion=self.gamepad();motion.threadG.wait=lambda _:True
        with self.assertRaisesRegex(OwnershipError,'WORKER_STILL_ACTIVE'):self.handoff.prepare()

    def test_uncertain_worker(self):
        self.window.stageMotionWindow.threadG=FakeThread()
        with self.assertRaisesRegex(OwnershipError,'WORKER_STATE_UNCERTAIN'):self.handoff.prepare()

    def test_unknown_joystick(self):
        self.window.stage.joystick_state=None
        with self.assertRaisesRegex(OwnershipError,'JOYSTICK_STATE_UNCERTAIN'):self.handoff.prepare()

    def test_joystick_disable_failure(self):
        self.window.stage.joystick=lambda **_:(_ for _ in ()).throw(RuntimeError('SDK_error'))
        with self.assertRaises(RuntimeError):self.handoff.prepare()
        self.assertEqual(self.handoff.result,'JOYSTICK_DISABLE_FAILURE')

    def test_joystick_no_ack(self):
        self.window.stage.joystick=lambda **_:None
        with self.assertRaisesRegex(OwnershipError,'acknowledgement'):self.handoff.prepare()

    def test_all_objective_acquisition_flags_block(self):
        for flag in ('autofocus_active','objective_motion_active','objective_daq_active','objective_ownership_uncertain','legacy_daq_active'):
            with self.subTest(flag=flag):
                setattr(self.window,flag,True)
                with self.assertRaises(OwnershipError):self.handoff.prepare()
                setattr(self.window,flag,False)
        self.window.objective_motion_active=None
        with self.assertRaises(OwnershipError):self.handoff.prepare()

    def test_existing_objective_task_blocks_even_hidden(self):
        self.window.pi_scanner_widget=SimpleNamespace(visible=False)
        with self.assertRaises(OwnershipError):self.handoff.prepare()

    def test_prior_legacy_acquisition_cleanup_unknown_blocks(self):
        self.bridge.legacy_daq_cleanup_unverified=True
        with self.assertRaisesRegex(OwnershipError,'legacy_DAQ_release'):self.handoff.prepare()

    def test_laser_operator_confirmation_required(self):
        for field in ('clearance','physical_emission_on','python_is_only_laser_owner','lockin_settings_confirmed'):
            with self.subTest(field=field),self.assertRaises(ValueError):
                replace(self.confirm,**{field:False}).validate(self.state.context,self.window.laser)

    def test_no_second_laser_connection(self):
        self.confirm.validate(self.state.context,self.window.laser)
        with self.assertRaises(ValueError):self.confirm.validate(self.state.context,None)

    def test_cached_emission_not_mistaken_for_fresh_readback(self):
        self.assertFalse(self.window.laser.isEmitting)
        self.confirm.validate(self.state.context,self.window.laser)

    def test_archived_frame_rejected(self):
        with self.assertRaises(ValueError):self.confirm.validate(replace(self.state.context,frame_id='archived-frame'),self.window.laser)

    def test_live_context_identity_required(self):
        with self.assertRaises(ValueError):self.confirm.validate(replace(self.state.context,sample_id=''),self.window.laser)

    def test_read_failure_cleans_once(self):
        self.task.fail=True;self.run_h()
        self.assertEqual(self.task.clear_count,1)
        self.assertEqual(self.controller.machine.state,AcquisitionState.FAILED)

    def test_all_conflicting_commands_rejected(self):
        from ui.localization_orchestration import Command,READ_ONLY
        self.handoff.prepare()
        self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='h_only'))
        calls=[]
        for command in Command:
            if command in READ_ONLY:continue
            with self.subTest(command=command),self.assertRaises(OwnershipError):
                self.bridge.dispatch(command,lambda:calls.append(command))
        self.assertEqual(calls,[])

    def test_laser_mutations_blocked_off_cancels(self):
        # Install on an inert existing laser owner, just as the real bridge does.
        from ui.operational_localization_bridge import OperationalLocalizationBridge
        from ui.localization_orchestration import LocalizationController
        from ui.registration_state import RegistrationState
        from test_operational_localization_bridge import FakePrior,FakeMotion
        calls=[];stage=FakePrior();state=RegistrationState()
        state.set_context(self.state.context)
        laser=SimpleNamespace(enable=lambda:calls.append('enable'),tune=lambda:calls.append('tune'),disable=lambda:calls.append('off'))
        window=SimpleNamespace(stage=stage,stageMotionWindow=FakeMotion(stage),laser=laser)
        controller=LocalizationController(state)
        bridge=OperationalLocalizationBridge(window,controller,executor=lambda call,t:call(),joystick_disabled=lambda:True)
        bridge.install_guards()
        handle=bridge.acquire(RunSettings(state.context,state.context_generation,'fixture',purpose='h_only'))
        self.assertFalse(laser.enable());self.assertFalse(laser.tune())
        self.assertEqual(calls,[])
        laser.disable()
        self.assertEqual(calls,['off'])
        self.assertTrue(handle.cancellation.is_cancelled())

    def test_H_only_rejects_candidate_publication(self):
        self.handoff.prepare()
        handle=self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='h_only'))
        with self.assertRaisesRegex(ValueError,'cannot_publish'):self.controller.offer_candidate(handle,None)


if __name__=='__main__':unittest.main()
