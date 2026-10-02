"""Snake parent authority in the existing activity/attestation registry."""
from dataclasses import dataclass, replace
from threading import get_ident
from types import FunctionType
from math import isfinite
from contextlib import nullcontext
from uuid import uuid4
from collections import deque
from itertools import count
from time import time, monotonic_ns

from ui.localization_orchestration import Activity, Command, OwnershipError, CancellationToken
from ui.objective_daq_lifecycle import ObjectiveOperation, ObjectiveTask
from ui.snake_autofocus_service import (SnakeAutofocusService, AutofocusResult,
                                       AutofocusFailure, AutofocusPoint, report_progress)


@dataclass(frozen=True)
class SnakeAutofocusTelemetry:
    kind: str
    parent_token: str
    parent_generation: str
    child_token: str
    child_generation: int
    requested_wavelength: float | None = None
    units: str = ''
    qcl: int | None = None
    point: AutofocusPoint | None = None
    result: AutofocusResult | None = None


class SnakeWorkflow:
    def __init__(self, bridge, source, settings=None):
        self.bridge, self.source, self.settings = bridge, source, settings
        self.generation = uuid4().hex
        self.launch_thread = get_ident()
        self.worker_identity = None
        self.phase = 'PREPARE'
        self.cancellation = CancellationToken()
        self.scope = None
        self.child = None
        self.result = None
        self.telemetry = None
        self.requested_tune = (None, '', None)
        self.uncertain = False
        self.completed = False
        self.stage_verified = False
        self.laser_verified = False
        self.frame_restored = True
        self.frame_origin = None
        self.last_stage_target = None
        self.cleanup_authorized = False
        self.launch_aborted = False
        self.workflow_outcome = 'RUNNING'
        self.primary_failure = None
        self.cleanup_failures = []
        self.close_requested = False
        self.user_cancel_requested = False
        self.cleanup_operation = None
        self.stage_cleanup_unsafe = False
        self.worker_thread = None
        self._trace_events = deque(maxlen=512)
        self._trace_sequence = count(1)
        with bridge.controller.registration.lock:
            if getattr(bridge, 'snake_parent', None) is not None:
                raise OwnershipError('snake_parent_already_exists')
            decision = bridge.controller.ownership.guard(Command.SNAKE_SCAN)
            reasons = [r for r in bridge.blockers() if r not in
                       ('legacy_callback_active','hardware_joystick_disable_unconfirmed')]
            if not decision.allowed or reasons:
                raise OwnershipError('; '.join((*decision.reasons, *reasons)))
            if settings is not None and (bridge.objective_owner is None or not bridge.objective_owner.released()):
                raise OwnershipError('managed_objective_required')
            self.token = bridge.mark_legacy_daq_uncertain('snake_workflow:'+source,
                owner=self, verifier=lambda owner: owner.released())
            bridge.snake_parent = self
            bridge.controller.report_activity(Activity.SNAKE_WORKFLOW, True)

    def trace(self, event, **details):
        """Bounded cached breadcrumbs, matching PhaseTrace fields; no I/O or authority."""
        try:
            try:
                running = self.worker_thread.isRunning() if self.worker_thread is not None else None
            except RuntimeError:
                running = False if self.completed else None  # Qt object deleted after finished.
            record = dict(run_id=self.token, generation=self.generation,
                sequence=next(self._trace_sequence), timestamp=time(), monotonic_ns=monotonic_ns(),
                thread_id=get_ident(), event=event, phase=self.phase,
                workflow_outcome=self.workflow_outcome, worker_active=self.worker_active,
                snake_thread_running=running,
                workflow_terminal=self.completed, parent_present=self.bridge.snake_parent is self,
                hardware_safety='VERIFIED_RELEASED' if self.released() else
                    'QUARANTINED' if self.completed else 'UNCERTAIN', details=details)
            self._trace_events.append(record)
            writer = getattr(self.bridge, 'snake_trace_writer', None)
            if writer is not None: writer.record(record)
        except Exception:
            pass  # Diagnostics may never interrupt hardware, cleanup, or Qt delivery.

    def released(self):
        if self.launch_aborted:
            return self.scope is None and not self.uncertain
        return (self.completed and not self.uncertain and self.stage_verified
                and not self.bridge.dispatcher.uncertain and not self.bridge.dispatcher.unresolved
                and self.laser_verified and self.frame_restored and self.scope is not None
                and self.scope.released() and (self.child is None or
                    (self.child.released() and self.bridge.legacy_daq_evidence.records.get(
                        self.child.token, {}).get('released') is True)))

    def executing_here(self):
        return get_ident() == (self.worker_identity or self.launch_thread)

    @property
    def worker_active(self):
        return not self.completed and not self.launch_aborted

    def record_failure(self, error):
        if self.primary_failure is None:
            self.primary_failure = dict(outcome=getattr(error, 'outcome', 'WORKFLOW_FAILURE'),
                detail=str(error), pi_diagnostics=getattr(error, 'diagnostics', None))
        self.trace('worker_failure_recorded', primary_failure=self.primary_failure)

    def request_cancellation(self, *, closing=False):
        if closing: self.close_requested = True
        if not self.worker_active: return
        if not closing: self.user_cancel_requested = True
        self.cancellation.request_cancel()
        self.trace('cancel_requested', source='close' if closing else 'user')

    def cleanup_failure(self, error):
        self.cleanup_failures.append(str(error))
        self.uncertain = True
        if self.completed and self.workflow_outcome == 'SUCCESS':
            self.workflow_outcome = 'FAILED'
        self.scope.error = self.scope.error or str(error)

    def authorize_finalization(self, operation):
        """Only named finalization operations; never permits new motion or DAQ."""
        b = self.bridge
        if (b.snake_parent is not self or self.completed or not self.executing_here()
                or self.phase != 'CLEANUP' or not self.cleanup_authorized
                or operation not in ('busy', 'get_position', 'set_position', 'laser_off')):
            raise OwnershipError('snake_finalization_not_authorized')
        if self.child is not None and self.child.execution_in_flight:
            raise OwnershipError('objective_child_still_executing')
        if operation != 'laser_off' and (self.stage_cleanup_unsafe
                or b.dispatcher.uncertain or b.dispatcher.unresolved):
            raise OwnershipError('native_stage_cleanup_not_authorized')
        reasons = b.controller.ownership.can_begin_localization().reasons
        if any(r != 'activity:'+Activity.SNAKE_WORKFLOW.value for r in reasons):
            raise OwnershipError('snake_finalization_conflicting_authority')

    def check(self, *, cleanup=False):
        b = self.bridge
        if b.snake_parent is not self or self.completed or not self.executing_here():
            raise OwnershipError('stale_or_foreign_snake_parent')
        if self.uncertain or b.dispatcher.uncertain or b.dispatcher.unresolved:
            raise OwnershipError('snake_authority_uncertain')
        reasons = b.controller.ownership.can_begin_localization().reasons
        if any(r != 'activity:'+Activity.SNAKE_WORKFLOW.value for r in reasons):
            raise OwnershipError('snake_conflicting_authority: '+repr(reasons))
        if not cleanup and not self.cleanup_authorized:
            if self.cancellation.is_cancelled(): raise AutofocusFailure('CANCELLED')

    def bind(self):
        with self.bridge.controller.registration.lock:
            if self.worker_identity is not None: raise OwnershipError('worker_already_bound')
            self.worker_identity = get_ident()
            self.check()

    def abort_launch(self):
        b = self.bridge
        with b.controller.registration.lock:
            if self.scope is not None or b.snake_parent is not self:
                raise OwnershipError('cannot_abort_started_snake')
            if b.dispatcher.uncertain or b.dispatcher.unresolved:
                self.uncertain = True
                return
            self.launch_aborted = True
            b.legacy_daq_evidence.confirm_release(self.token)
            b.controller.report_activity(Activity.SNAKE_WORKFLOW, False)
            b.snake_parent = None

    def finish_worker(self, parameters):
        self.phase = 'CLEANUP'
        self.trace('worker_cleanup_begin')
        self.cleanup_authorized = True
        self.trace('laser_cleanup_begin')
        try:
            if not self.laser_verified:
                self.authorize_finalization('laser_off')
                parameters.laser.disable()
        except Exception as error:
            self.cleanup_failure(error)
        self.trace('laser_cleanup_result', verified=self.laser_verified)
        self.trace('stage_final_verification_begin')
        try:
            self.authorize_finalization('busy')
            idle = str(parameters.stage.busy()) == '0'
            point = parameters.stage.get_position()
            self.stage_verified = idle and len(point) == 2 and all(isfinite(v) for v in point)
            if self.stage_verified and not self.frame_restored and self.frame_origin is not None:
                self.trace('frame_restore_begin')
                # Restore only coordinate labels after a cancelled/failed scan,
                # never issue an unrequested physical return move.
                point = parameters.stage.get_position()
                restored = tuple(a+b for a,b in zip(point,self.frame_origin))
                parameters.stage.set_position(*restored)
                self.frame_restored = False
                readback = parameters.stage.get_position()
                self.stage_verified = len(readback) == 2 and all(abs(a-b) <= 1. for a,b in
                    zip(readback,restored))
                self.frame_restored = self.stage_verified
                self.trace('frame_restore_result', verified=self.frame_restored)
            if not self.stage_verified or not self.frame_restored:
                self.cleanup_failure('snake_stage_cleanup_unverified')
        except Exception as error:
            self.cleanup_failure(error)
            self.trace('frame_restore_result', verified=self.frame_restored, error=str(error))
        finally:
            self.cleanup_authorized = False
            self.trace('stage_final_verification_result', verified=self.stage_verified)
            self.trace('worker_done', cleanup_failures=tuple(self.cleanup_failures))

    def finish_thread(self):
        self.trace('parent_finalize_begin')
        b = self.bridge
        with b.controller.registration.lock:
            if b.snake_parent is not self: raise OwnershipError('stale_parent_completion')
            self.scope.thread_done = True
            self.completed = True
            self.workflow_outcome = ('CANCELLED' if self.primary_failure and
                self.primary_failure['outcome'] == 'CANCELLED' else
                'FAILED' if self.primary_failure or self.cleanup_failures or self.scope.error else
                'CANCELLED' if self.cancellation.is_cancelled() else 'SUCCESS')
            # DAQ scope evidence is independent of parent PI/frame safety.
            try:
                if self.scope.released():
                    b.legacy_daq_evidence.confirm_release(self.scope.token)
                    self.scope.state = 'RELEASE_CONFIRMED'
                else:
                    self.scope.state = 'RELEASE_UNCERTAIN'
            except Exception as error:
                self.cleanup_failure(error)
            if not self.released():
                self.uncertain = True
                if self.workflow_outcome == 'SUCCESS': self.workflow_outcome = 'FAILED'
                self.phase = 'UNCERTAIN'
                self.scope.error = self.scope.error or 'snake_parent_cleanup_unverified'
                self.trace_terminal()
                return
            try:
                b.legacy_daq_evidence.confirm_release(self.token)
            except Exception as error:
                self.cleanup_failure(error)
                self.phase = 'UNCERTAIN'
                self.trace_terminal()
                return
            self.scope.state = 'RELEASE_CONFIRMED'
            self.phase = 'COMPLETE'
            b.controller.report_activity(Activity.SNAKE_WORKFLOW, False)
            b.last_snake_parent, b.snake_parent = self, None
            self.trace_terminal()

    def trace_terminal(self):
        self.trace('parent_terminal_outcome', outcome=self.workflow_outcome)
        self.trace('parent_safety_state')
        self.trace('parent_reference_retained_or_cleared', retained=self.bridge.snake_parent is self)

    def phase_to(self, phase):
        with self.bridge.controller.registration.lock:
            if self.worker_identity is None: raise OwnershipError('snake_worker_not_bound')
            self.check()
            if self.child is not None and not self.child.released():
                raise OwnershipError('objective_child_not_released')
            if self.scope and any(not t.cleared for t in self.scope.tasks):
                raise OwnershipError('snake_imaging_task_not_cleared')
            self.phase = phase

    def authorize_child(self, op, parent_token, parent_generation):
        with self.bridge.controller.registration.lock:
            self.check(cleanup=self.cleanup_authorized)
            if (parent_token != self.token or parent_generation != self.generation
                    or self.phase != 'AUTOFOCUS' or self.child is not op
                    or self.bridge.objective_owner.current is not op
                    or not op.execution_in_flight):
                raise OwnershipError('stale_or_foreign_objective_child')

    def autofocus(self, target, stage, pi):
        self.phase_to('AUTOFOCUS')
        b, owner = self.bridge, self.bridge.objective_owner
        with b.controller.registration.lock:
            self.check()
            if owner is None or not owner.released(): raise OwnershipError('objective_not_released')
            owner.generation += 1
            op = ObjectiveOperation(owner.generation, 'snake_autofocus')
            self.child = op
            owner.current, owner.state, owner.execution_thread = op, 'ACTIVE', get_ident()
            op.token = b.mark_legacy_daq_uncertain('snake_autofocus:'+self.token,
                owner=op, verifier=lambda current: current is self.child and current.released())
        service = None
        result = AutofocusResult('UNCERTAIN')
        wavelength, units, qcl = self.requested_tune
        def publish(kind, *, point=None, result=None):
            report_progress(self.telemetry, SnakeAutofocusTelemetry(
                kind, self.token, self.generation, op.token, op.generation,
                wavelength, units, qcl, point, result))
        publish('start')
        def authorize():
            self.authorize_child(op, self.token, self.generation)
        def acquire():
            authorize()
            if op.task is None:
                backend = owner.backend
                if backend is None:
                    from instruments import ni_daq as backend
                op.ever_acquired = True
                b.legacy_daq_evidence.ever_acquired = True
                op.task = ObjectiveTask(backend)
                try: op.task.configure()
                except Exception as error: raise AutofocusFailure('DAQ_CONFIGURE_FAILURE', error) from error
            try: return op.task.device.acquire_bounded(10, timeout_s=self.settings.read_timeout)
            except Exception as error:
                text = str(error).lower()
                kind = 'STOP' if 'stop' in text else 'START' if 'start' in text else 'READ'
                raise AutofocusFailure('DAQ_'+kind+'_FAILURE', error) from error
        try:
            service = SnakeAutofocusService(self.settings, stage, pi, acquire, authorize,
                lambda: not (b.dispatcher.uncertain or b.dispatcher.unresolved or self.uncertain),
                progress=lambda point: publish('point', point=point))
            # Cleanup stage moves must remain authorized after cooperative cancellation.
            service_stage_move = service.stage_move
            def move(point, restoring=False):
                self.cleanup_authorized = restoring
                try: return service_stage_move(point, restoring)
                finally: self.cleanup_authorized = False
            service.stage_move = move
            result = service.run(target)
        except Exception as error:
            self.trace('autofocus_failure_received', outcome=getattr(error, 'outcome', 'UNCERTAIN'),
                       detail=str(error), pi_diagnostics=getattr(error, 'diagnostics', None))
            op.errors.append(repr(error))
            result = AutofocusResult(getattr(error, 'outcome', 'UNCERTAIN'),
                stage_restored=bool(service and service.stage_restored),
                pi_verified=bool(service and service.pi_verified), detail=str(error),
                pi_diagnostics=getattr(error, 'diagnostics', None),
                cleanup_failures=tuple(service.cleanup_failures) if service else ())
            self.record_failure(error)
            self.cleanup_failures.extend(result.cleanup_failures)
            self.stage_cleanup_unsafe = self.stage_cleanup_unsafe or bool(service and service.stage_motion_uncertain)
        finally:
            with b.controller.registration.lock:
                if owner.current is op: owner.state = 'RELEASING'
            try:
                if op.task is not None: op.task.clear()
            except Exception as error:
                op.errors.append(repr(error)); op.uncertain = True
                self.cleanup_failures.append(str(error))
                if result.outcome == 'SUCCESS':
                    result = replace(result, outcome='DAQ_CLEAR_FAILURE', detail=str(error))
            with b.controller.registration.lock:
                op.execution_in_flight = False
                if b.snake_parent is not self or self.child is not op or owner.current is not op:
                    op.uncertain = self.uncertain = True
                    raise OwnershipError('stale_child_completion')
                owner.execution_thread = None
                owner.state = 'UNCERTAIN' if op.uncertain else 'RELEASED'
                if op.released():
                    # Exact child attestation, not global legacy-worker release.
                    try:
                        b.legacy_daq_evidence.confirm_release(op.token)
                        self.trace('objective_child_release_verified', child_token=op.token)
                    except Exception as error:
                        op.uncertain = self.uncertain = True
                        owner.state = 'UNCERTAIN'
                        op.errors.append(repr(error))
                        self.cleanup_failures.append(str(error))
                        if result.outcome == 'SUCCESS':
                            result = replace(result, outcome='UNCERTAIN', detail=str(error))
                result = replace(result, cleanup_verified=op.released())
                self.result = result
        if (not result.stage_restored or not result.cleanup_verified
                or result.outcome.startswith('PI_')):
            self.uncertain = True
        # Outside ownership locks, after checked cleanup and child attestation.
        publish('result', result=result)
        if result.outcome != 'SUCCESS':
            error = AutofocusFailure(result.outcome, result.detail, diagnostics=result.pi_diagnostics)
            self.record_failure(error)
            raise error
        self.phase_to('IMAGING')
        return result

    def snapshot(self):
        native_owner = getattr(self.bridge.window, 'prior_owner', None)
        native_dispatcher = getattr(native_owner, 'dispatcher', None)
        native_pending = self.bridge.dispatcher.unresolved or bool(
            native_dispatcher and native_dispatcher.unresolved)
        writer = getattr(self.bridge, 'snake_trace_writer', None)
        return dict(type=self.source, parent_token=self.token, generation=self.generation,
            worker_identity=self.worker_identity, phase=self.phase, completed=self.completed,
            active=self.worker_active, worker_active=self.worker_active,
            native_execution_active=native_pending,
            reservation_retained=self.bridge.snake_parent is self,
            workflow_outcome=self.workflow_outcome,
            hardware_safety='VERIFIED_RELEASED' if self.released() else
                'QUARANTINED' if self.completed else 'UNCERTAIN',
            primary_failure=self.primary_failure, cleanup_failures=list(self.cleanup_failures),
            close_requested=self.close_requested, uncertain=self.uncertain,
            user_cancel_requested=self.user_cancel_requested,
            breadcrumbs=list(self._trace_events.copy()),
            trace_journal=dict(path=str(writer.path), dropped=writer.dropped, error=writer.error)
                if writer is not None else None,
            trace_setup_error=getattr(self.bridge, 'snake_trace_error', None),
            cleanup_evidence=dict(objective_execution_finished=self.child is None or not self.child.execution_in_flight,
                objective_daq_released=self.child is None or self.child.released(),
                imaging_daq_released=bool(self.scope and self.scope.released()),
                stage_verified=self.stage_verified, frame_restored=self.frame_restored,
                laser_verified=self.laser_verified, worker_done=bool(self.scope and self.scope.worker_done),
                thread_done=bool(self.scope and self.scope.thread_done),
                no_unresolved_native_call=not native_pending),
            cancelled=self.cancellation.is_cancelled(), stage_verified=self.stage_verified,
            laser_verified=self.laser_verified, frame_restored=self.frame_restored,
            child=dict(self.child.snapshot(), parent_token=self.token, parent_generation=self.generation,
                worker_identity=self.worker_identity,
                state='UNCERTAIN' if self.child.uncertain else
                      'RELEASED' if self.child.released() else 'ACTIVE') if self.child else None,
            imaging_tasks=[task.raw.snapshot() for task in self.scope.tasks] if self.scope else [],
            autofocus_result=self.result.__dict__ if self.result else None)


class TargetSetter:
    __slots__ = ('adapter', 'index')
    def __init__(self, adapter, index): self.adapter, self.index = adapter, index
    def emit(self, value): self.adapter.target[self.index] = float(value)


class WorkerObjectiveAdapter:
    __slots__ = ('parent', 'stage', 'pi', 'target', 'set_target_x_signal', 'set_target_y_signal')
    def __init__(self, parent, stage, pi):
        self.parent, self.stage, self.pi = parent, stage, pi
        self.target = [None, None]
        self.set_target_x_signal = TargetSetter(self, 0)
        self.set_target_y_signal = TargetSetter(self, 1)
    def autofocus(self):
        if any(value is None for value in self.target): raise AutofocusFailure('INVALID_PARAMETERS')
        origin = self.parent.frame_origin
        if origin is None: raise AutofocusFailure('INVALID_PARAMETERS', 'pattern frame missing')
        settings = self.parent.settings
        target = (settings.absolute_target_x-origin[0], settings.absolute_target_y-origin[1])
        if tuple(self.target) != target:
            raise AutofocusFailure('INVALID_PARAMETERS', 'legacy target differs from frozen settings')
        return self.parent.autofocus(target, self.stage, self.pi)


class WorkerStage:
    """Only the audited Snake/service stage surface; no GUI references."""
    __slots__ = ('raw', 'parent')
    methods = frozenset(('goto','busy','get_position','set_position','set_speed','arm_trigger'))
    def __init__(self, raw, parent): self.raw, self.parent = raw, parent
    def __getattr__(self, name):
        if name not in self.methods: raise AttributeError(name)
        def call(*args, **kwargs):
            finalizing = self.parent.phase == 'CLEANUP' and self.parent.cleanup_authorized
            if finalizing:
                self.parent.authorize_finalization(name)
            else:
                self.parent.check(cleanup=self.parent.cleanup_authorized)
            previous_frame = self.parent.frame_restored
            if name == 'set_position': self.parent.frame_restored = False
            timeout = getattr(self.raw, 'execution_timeout', None)
            context = (timeout(self.parent.settings.movement_timeout)
                       if timeout is not None and self.parent.settings is not None else nullcontext())
            try:
                if finalizing: self.parent.cleanup_operation = name
                with context: result = getattr(self.raw, name)(*args, **kwargs)
            except Exception:
                self.parent.uncertain = True
                self.parent.stage_cleanup_unsafe = True
                raise
            finally:
                if finalizing: self.parent.cleanup_operation = None
            if name == 'set_position':
                # Audited routines alternate zeroing/restoration, including origin (0,0).
                if previous_frame:
                    self.parent.frame_origin = self.parent.last_stage_target
                self.parent.frame_restored = not previous_frame
            if name == 'goto':
                self.parent.last_stage_target = tuple(args) if args else (kwargs['x'],kwargs['y'])
            return result
        return call


class WorkerPI:
    """Bound PI transport timeout per call; restore the manual connection setting."""
    __slots__ = ('raw', 'parent')
    def __init__(self, raw, parent): self.raw, self.parent = raw, parent
    def read_position_bounded(self, timeout_s):
        self.parent.check()
        previous = self.raw.timeout
        try:
            self.raw.timeout = max(1, int(min(timeout_s, self.parent.settings.movement_timeout) * 1000))
            return self.raw.qPOS(1)
        finally:
            self.raw.timeout = previous
    def __getattr__(self, name):
        if name not in ('MOV','qPOS','qONT'): raise AttributeError(name)
        def call(*args):
            self.parent.check()
            previous = self.raw.timeout
            try:
                self.raw.timeout = max(1, int(self.parent.settings.movement_timeout * 1000))
                return getattr(self.raw, name)(*args)
            finally: self.raw.timeout = previous
        return call


class WorkerLaser:
    __slots__ = ('raw', 'parent')
    methods = frozenset(('tune','get_current','get_pulse_rate','get_pulse_width'))
    def __init__(self, raw, parent): self.raw, self.parent = raw, parent
    def __getattr__(self, name):
        if name not in self.methods: raise AttributeError(name)
        def call(*args, **kwargs):
            self.parent.check()
            if name == 'tune':
                # Requested context only; no extra hardware readback.
                values = dict(zip(('qcl', 'wl', 'wlUnits'), args))
                values.update(kwargs)
                self.parent.requested_tune = (values.get('wl'), values.get('wlUnits', 'um'),
                                              values.get('qcl'))
            return getattr(self.raw, name)(*args, **kwargs)
        return call
    def disable(self):
        # Preserve the existing disable algorithm; verify its SDK statuses rather
        # than trusting cached isEmitting or its normal Python return.
        original = self.parent.bridge.snake_laser_disable
        function = original.__func__
        namespace = dict(function.__globals__)
        sdk = namespace['SDK']
        observed = []
        class CheckedSDK:
            def __getattr__(self, name):
                if name not in ('MIRcatSDK_IsEmissionOn','MIRcatSDK_TurnEmissionOff'):
                    raise OwnershipError('unexpected_laser_cleanup_call')
                def call(*args):
                    status = getattr(sdk, name)(*args)
                    if type(status) is not int or status != 0:
                        raise OwnershipError('laser_cleanup_unverified')
                    observed.append(name)
                    return status
                return call
        namespace['SDK'] = CheckedSDK()
        FunctionType(function.__code__, namespace)(original.__self__)
        if not observed or original.__self__.isEmitting.value is not False:
            raise OwnershipError('laser_off_not_verified')
        self.parent.laser_verified = True
