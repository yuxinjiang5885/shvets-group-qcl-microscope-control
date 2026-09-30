"""Supervised single-H services. No vertical/fitting/publication or hardware imports."""
from dataclasses import dataclass, asdict
from math import isfinite, hypot
from pathlib import Path
from statistics import mean
import json
from experiment.scan_1d import ScanSettings, StageBounds
from ui.localization_pipeline import DaqSettings, LocalizationPipelineServices
from ui.localization_orchestration import OwnershipError


@dataclass(frozen=True)
class HOnlySpec:
    rough_start_xy: tuple
    bounds: StageBounds
    side_um: float = 500.
    scan_margin_um: float = 100.
    step_um: float = 10.
    width_tolerance_um: float = 100.
    position_tolerance_um: float = 1.
    polling_s: float = .01
    settling_s: float = .1
    movement_timeout_s: float = 5.
    readback_timeout_s: float = 2.
    daq_timeout_s: float = 2.
    stop_timeout_s: float = 2.
    daq: DaqSettings = DaqSettings()

    def __post_init__(self):
        values=(*self.rough_start_xy,self.side_um,self.scan_margin_um,self.step_um,self.width_tolerance_um)
        if (len(self.rough_start_xy)!=2 or not all(isfinite(v) for v in values)
                or min(self.side_um,self.scan_margin_um,self.step_um,self.width_tolerance_um)<=0
                or any(v != round(v) for v in self.rough_start_xy)
                or not self.bounds.contains(self.rough_start_xy)):
            raise ValueError('invalid_H_start_or_geometry')
        if (self.position_tolerance_um,self.polling_s,self.settling_s,self.movement_timeout_s,
                self.readback_timeout_s,self.daq_timeout_s,self.stop_timeout_s)!=(1.,.01,.1,5.,2.,2.,2.):
            raise ValueError('unreviewed_H_timing_or_tolerance')
        self.scan().positions()  # Validate entire path before handoff or movement.

    def scan(self):
        x,y=self.rough_start_xy
        half=self.side_um/2+self.scan_margin_um
        result=ScanSettings('x',x-half,x+half,self.step_um,y,self.bounds,
            movement_timeout_s=self.movement_timeout_s,settling_s=self.settling_s,
            settling_timeout_s=self.readback_timeout_s,read_timeout_s=self.daq_timeout_s,
            stop_timeout_s=self.stop_timeout_s,poll_interval_s=self.polling_s,
            position_tolerance_um=self.position_tolerance_um)
        if any(any(v!=round(v) for v in xy) for xy in result.positions()):
            raise ValueError('H_targets_must_match_integer_stage_resolution')
        return result


@dataclass(frozen=True)
class OperatorConfirmation:
    clearance: bool
    physical_emission_on: bool
    python_is_only_laser_owner: bool
    lockin_settings_confirmed: bool
    wavenumber_cm: float = 1500.
    note: str = ''

    def validate(self, context, laser):
        if any(v is not True for v in (self.clearance,self.physical_emission_on,
                self.python_is_only_laser_owner,self.lockin_settings_confirmed)):
            raise ValueError('operator_clearance_laser_lockin_confirmation_required')
        if not isfinite(self.wavenumber_cm) or self.wavenumber_cm<=0 or not self.note.strip():
            raise ValueError('operator_wavenumber_and_note_required')
        if not all((context.gds_path,context.marker_id,context.frame_id,context.sample_id,context.inputs_id)):
            raise ValueError('selected_GDS_marker_and_live_context_required')
        if any(str(v).startswith('archived-') for v in (context.frame_id,context.sample_id,context.inputs_id)):
            raise ValueError('archived_context_is_not_live_confirmation')
        if laser is None:
            raise ValueError('existing_Python_MIRcat_owner_required')
        # Cached flags are supporting evidence, never claimed as fresh readback.
        # enable() does not refresh isEmitting in the legacy wrapper. Never
        # mistake that stale cache for a reliable emission readback.
        for name in ('isArmed','isTuned'):
            value=getattr(laser,name,None)
            value=getattr(value,'value',value)
            if value is not True:
                raise ValueError('laser_cached_state_not_ready:'+name)


class InputHandoff:
    def __init__(self, bridge):
        self.bridge=bridge
        self.previous=None
        self.result='NOT_STARTED'
        self.restore_result='NOT_ATTEMPTED'

    def prepare(self):
        b=self.bridge
        blocked=[r for r in b.blockers() if r not in ('gamepad_handoff_required','hardware_joystick_disable_unconfirmed')]
        if blocked:
            raise OwnershipError('; '.join(blocked))
        motion=b.window.stageMotionWindow
        thread,worker=motion.threadG,motion.workerG
        if thread is None and worker is None:
            self.result='ALREADY_STOPPED'
        elif thread is None or worker is None:
            self.result='WORKER_STATE_UNCERTAIN';raise OwnershipError(self.result)
        else:
            worker.request_stop()
            if not thread.wait(3000):
                self.result='STOP_TIMEOUT';raise OwnershipError(self.result)
            if motion.threadG is not thread or motion.workerG is not worker:
                self.result='STALE_COMPLETION';raise OwnershipError(self.result)
            if thread.isRunning() or not thread.isFinished():
                self.result='WORKER_STILL_ACTIVE';raise OwnershipError(self.result)
            motion.release_gamepad()
            self.result='STOPPED_SUCCESSFULLY'
        self.previous=getattr(b.stage,'joystick_state',None)
        if type(self.previous) is not bool:
            self.result='JOYSTICK_STATE_UNCERTAIN';raise OwnershipError(self.result)
        try:
            b.stage.joystick(enable=False)
            if getattr(b.stage,'joystick_state',None) is not False:
                raise OwnershipError('joystick_acknowledgement_missing')
        except Exception:
            self.result='JOYSTICK_DISABLE_FAILURE';raise
        b.joystick_disabled=lambda: getattr(b.stage,'joystick_state',None) is False

    def restore(self, handle):
        if handle.settings.context_generation != self.bridge.controller.registration.context_generation:
            raise OwnershipError('input_restore_withheld_context_changed')
        if type(self.previous) is not bool:
            raise OwnershipError('no_recorded_joystick_state')
        try:
            self.bridge.execute_stage(handle,lambda:self.bridge.stage.joystick(enable=self.previous),2.,cleanup=True)
            if getattr(self.bridge.stage,'joystick_state',None) is not self.previous:
                raise OwnershipError('joystick_restore_unconfirmed')
        except Exception:
            self.restore_result='RESTORE_FAILURE';raise
        self.restore_result='RESTORE_SUCCESS_GAMEPAD_MANUAL_RESTART'
        return True


class HOnlyServices(LocalizationPipelineServices):
    def __init__(self,*args,confirmation,handoff,**kwargs):
        super().__init__(*args,**kwargs)
        self.confirmation,self.handoff=confirmation,handoff
        scan=self.spec.scan()
        self.report=dict(return_status='NOT_ATTEMPTED',cleanup_status='PENDING',
            run_id=self.handle.run_id,context_generation=self.handle.settings.context_generation,
            journal=str(self.path/'initial_H.jsonl'),requested_x=(scan.start_um,scan.end_um),
            fixed_y=scan.fixed_um,expected_points=len(scan.positions()),expected_width=self.spec.side_um,
            daq_cleanup='NOT_CREATED',idle_cleanup='PENDING',protective_stop='NOT_NEEDED')

    def prepare(self,settings):
        self.confirmation.validate(settings.context,self.bridge.window.laser)
        super().prepare(settings)
        (self.path/'operator_confirmation.json').write_text(json.dumps(asdict(self.confirmation),indent=2),encoding='utf-8')

    def _start_gate(self):
        t=self.spec.readback_timeout_s
        if self.stage.is_busy(timeout_s=t):raise ValueError('initial_stage_busy')
        actual=self.stage.get_position(timeout_s=t)
        if not self.spec.bounds.contains(actual) or hypot(*(a-b for a,b in zip(actual,self.spec.rough_start_xy)))>self.spec.position_tolerance_um:
            raise ValueError('confirmed_rough_start_mismatch')

    def work(self,settings,checkpoint,progress):
        scan,edge=self._scan('initial_H',self.spec.scan(),checkpoint,progress)
        xs=[p.measured_um[0] for p in scan.points];ys=[p.measured_um[1] for p in scan.points]
        self.report.update(journal=str(self.journals[0]),requested_x=(self.spec.scan().start_um,self.spec.scan().end_um),
            measured_x=(min(xs),max(xs)),measured_y=(min(ys),max(ys)),points=len(xs),
            left=edge.left_edge_um,right=edge.right_edge_um,midpoint=edge.midpoint_um,width=edge.width_um,
            expected_width=self.spec.side_um,edge_diagnostics=asdict(edge),
            warnings=('joystick_command_ack_only','laser_operator_confirmation_not_fresh_SDK_readback'))
        self._phase('success_only_return',checkpoint,progress)
        self.report['return_status']='FAILED_OR_INCOMPLETE'
        self._return(checkpoint)
        self.report['return_status']='PASS'
        return self.report.copy()

    def restore_inputs(self):
        result=self.handoff.restore(self.handle)
        self.report['input_restore']=self.handoff.restore_result
        return result

    def release_daq(self):
        self.report['daq_cleanup']='FAILED_OR_UNCONFIRMED'
        if self.task is None and self.bridge.daq.uncertain:
            return False  # Provider's partial setup cleanup already failed.
        result=super().release_daq()
        self.report['daq_cleanup']='PASS' if result else 'FAILED_OR_UNCONFIRMED'
        return result

    def confirm_idle(self):
        self.report['idle_cleanup']='FAILED_OR_UNCONFIRMED'
        result=super().confirm_idle()
        self.report['idle_cleanup']='PASS' if result else 'FAILED_OR_UNCONFIRMED'
        return result

    def protective_stop(self):
        self.report['protective_stop']='FAILED_OR_UNCONFIRMED'
        result=super().protective_stop()
        self.report['protective_stop']='PASS' if result else 'FAILED_OR_UNCONFIRMED'
        return result
