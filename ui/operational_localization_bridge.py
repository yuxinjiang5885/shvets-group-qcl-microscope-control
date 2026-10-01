"""Experimental ownership wiring. No instrument imports or task/session factories.

The existing UI owns the stage lifetime. A command executor must be supplied by
an explicitly reviewed owner-thread integration; none is inferred from legacy use.
"""
from threading import local

from ui.localization_orchestration import (Activity, Command, GuardDecision,
    OwnershipError, READ_ONLY)
from ui.registration_state import ContextEvent
from ui.stage_command_dispatcher import StageCommandDispatcher
from ui.legacy_daq_tracking import LegacyDaqEvidence


MAIN_COMMANDS = {
    'run_experiment': Command.SPECTRUM, 'repeat_experiment': Command.REPEAT_SCAN,
    'multiple': Command.MULTIWELL, 'run_snake_scan': Command.SNAKE_SCAN,
    'repeat_snake_scan': Command.REPEAT_SCAN, 'run_scanning_imaging': Command.IMAGING,
    'show_pi_scanner_widget': Command.OBJECTIVE_MOVE,
}
STAGE_COMMANDS = {
    'goto': Command.MANUAL_MOVE, 'run_multiwell': Command.MULTIWELL,
    'goto_gamepad': Command.GAMEPAD, 'joystick': Command.GAMEPAD,
    'set_v': Command.SPEED_ACCELERATION, 'set_a': Command.SPEED_ACCELERATION,
    'update_readings': Command.MANUAL_MOVE,  # Live SDK queries are NOT cached reads.
}
FRAME_EVENTS = {
    'set_position': ContextEvent.FRAME, 'home': ContextEvent.FRAME,
    'reference': ContextEvent.FRAME, 'reset': ContextEvent.RECONNECT,
    'reconnect': ContextEvent.RECONNECT, 'session_replacement': ContextEvent.RECONNECT,
    'communication_loss': ContextEvent.RECONNECT, 'sample': ContextEvent.SAMPLE,
    'gds': ContextEvent.GDS, 'marker': ContextEvent.MARKER,
    'orientation': ContextEvent.ORIENTATION, 'inputs': ContextEvent.INPUTS,
    'goto': ContextEvent.MOVEMENT, 'gamepad_move': ContextEvent.MOVEMENT,
    'return_to_zero': ContextEvent.MOVEMENT,
}


class DaqOwnership:
    """Only bookkeeping. Does not create, clear, reset or steal a DAQ task."""
    def __init__(self):
        self.run_id = None
        self.task = None
        self.uncertain = False

    def claim(self, run_id, task, *, reset):
        if reset is not False or not run_id or task is None:
            raise OwnershipError('invalid_localization_daq_claim')
        if self.run_id is not None or self.uncertain:
            raise OwnershipError('daq_already_owned_or_uncertain')
        self.run_id, self.task = run_id, task

    def release(self, run_id, *, confirmed):
        if run_id != self.run_id:
            raise OwnershipError('stale_daq_release')
        if confirmed is not True:
            self.uncertain = True
            return False
        self.run_id, self.task = None, None
        self.uncertain = False
        return True


class OperationalLocalizationBridge:
    def __init__(self, window, controller, *, executor=None, submit=None,
                 execution_contract_reviewed=False, joystick_disabled=None):
        self.window, self.controller = window, controller
        self.stage = getattr(window, 'stage', None)
        self.executor = executor  # execute(callable, timeout_s); must marshal to verified owner.
        # executor is retained for existing inert test injection only. Live use
        # supplies a nonblocking queued submitter, never a blocking executor.
        self._submit = submit
        self.execution_contract_reviewed = execution_contract_reviewed
        self.dispatcher = StageCommandDispatcher(
            submit if submit is not None else lambda call: self.executor(call, 2.),
            self._authorize_stage, self._quarantine_stage)
        self.joystick_disabled = joystick_disabled or (lambda: None)
        self.daq = DaqOwnership()
        self._authority = local()
        self._threads = []
        self._finished_threads = set()
        self._calls_active = 0
        self._frame_active = False
        self.movement_attempted = False
        self.close_pending = False
        self.guards_installed = False
        self.legacy_daq_evidence = LegacyDaqEvidence()
        if getattr(window, '_operational_localization_bridge', None) is not None:
            raise OwnershipError('second_stage_owner_bridge')
        if self.stage is not None and getattr(self.stage, '_localization_bridge_owner', None) is not None:
            raise OwnershipError('stage_already_borrowed_by_another_bridge')
        motion = getattr(window, 'stageMotionWindow', None)
        if motion is not None and getattr(motion, 'stage', None) is not self.stage:
            raise OwnershipError('second_stage_owner_detected')
        window._operational_localization_bridge = self
        if self.stage is not None:
            self.stage._localization_bridge_owner = self

    def frame_event(self, name):
        self.controller.handle_context_event(FRAME_EVENTS[name])

    @property
    def legacy_daq_cleanup_unverified(self):
        return self.legacy_daq_evidence.uncertain

    @legacy_daq_cleanup_unverified.setter
    def legacy_daq_cleanup_unverified(self, value):
        if value is True:
            self.mark_legacy_daq_uncertain('external_unverified_assignment')
        elif value is not False or self.legacy_daq_evidence.uncertain:
            raise OwnershipError('legacy_DAQ_cannot_clear_without_verified_release')

    def mark_legacy_daq_uncertain(self, source, *, owner=None, verifier=None):
        with self.controller.registration.lock:
            return self.legacy_daq_evidence.acquired_or_uncertain(source, owner=owner, verifier=verifier)

    def confirm_legacy_daq_release(self, token):
        """No GUI reset/attest-clean button. Requires an owner-bound verifier.

        Current uninstrumented legacy workers have no verifier and remain blocked
        even after finished. This hook is for positively instrumented owners only.
        """
        with self.controller.registration.lock:
            if self.controller.active is not None or self._calls_active:
                raise OwnershipError('legacy_DAQ_release_while_activity_active')
            if any(reason.startswith(('legacy_activity:', 'legacy_thread_state_unknown:'))
                   or reason in ('legacy_daq_active','autofocus_active','objective_motion_active',
                                 'objective_daq_active','objective_ownership_uncertain',
                                 'objective_daq_autofocus_ownership_unconfirmed')
                   for reason in self.blockers()):
                raise OwnershipError('legacy_DAQ_owner_still_active_or_unknown')
            self.legacy_daq_evidence.confirm_release(token)

    def _remember_threads(self):
        motion = getattr(self.window, 'stageMotionWindow', None)
        for obj, names in ((self.window, ('threadRun', 'threadRep', 'threadMul')),
                           (motion, ('threadMW',))):
            if obj is None:
                continue
            for name in names:
                thread = getattr(obj, name, None)
                if thread is None or isinstance(thread, list):
                    continue
                if all(thread is not old for old, _ in self._threads):
                    self._threads.append((thread, name))
                    signal = getattr(thread, 'finished', None)
                    if signal is not None:
                        signal.connect(lambda t=thread: self._finished_threads.add(id(t)))

    def blockers(self):
        """Read Python/Qt lifecycle only; never poll any physical instrument."""
        reasons = []
        if self.stage is None or self.window.stage is not self.stage:
            reasons.append('stage_session_missing_or_replaced')
        motion = getattr(self.window, 'stageMotionWindow', None)
        if motion is None or getattr(motion, 'stage', None) is not self.stage:
            reasons.append('stage_window_identity_unverified')
        if self.executor is None and self._submit is None:
            reasons.append('owner_thread_executor_unverified')
        if self._submit is not None and not self.execution_contract_reviewed:
            reasons.append('Prior_session_execution_contract_unverified')
        if self.dispatcher.uncertain or self.dispatcher.closed:
            reasons.append('stage_dispatcher_uncertain_or_closed')
        if not self.guards_installed:
            reasons.append('operational_guards_not_installed')
        try:
            if self.joystick_disabled() is not True:
                reasons.append('hardware_joystick_disable_unconfirmed')
        except Exception:
            reasons.append('hardware_joystick_state_unknown')
        self._remember_threads()
        for thread, name in self._threads:
            if id(thread) in self._finished_threads:
                continue
            try:
                if thread.isRunning() or not thread.isFinished():
                    reasons.append('legacy_activity:' + name)
            except Exception:
                reasons.append('legacy_thread_state_unknown:' + name)
        game_thread = getattr(motion, 'threadG', None)
        game_worker = getattr(motion, 'workerG', None)
        if game_thread is not None or game_worker is not None:
            reasons.append('gamepad_handoff_required')
        if getattr(self.window, 'pi_scanner_widget', None) is not None:
            reasons.append('objective_daq_autofocus_ownership_unconfirmed')
        if self.legacy_daq_cleanup_unverified:
            reasons.append('legacy_DAQ_release_not_attested_fresh_session_required')
            reasons.append('legacy_DAQ_pending_sources:'+repr([
                row['source'] for row in self.legacy_daq_evidence.records.values() if not row['released']]))
        for name in ('autofocus_active','objective_motion_active','objective_daq_active',
                     'objective_ownership_uncertain','legacy_daq_active'):
            if getattr(self.window,name,False) is not False:
                reasons.append(name)
        if self.daq.uncertain or (self.daq.run_id is not None and
                (self.controller.active is None or self.daq.run_id != self.controller.active.run_id)):
            reasons.append('daq_conflict_or_uncertain')
        if self._calls_active:
            reasons.append('legacy_callback_active')
        if self._frame_active:
            reasons.append('frame_operation_active')
        return tuple(reasons)

    def refresh(self):
        with self.controller.registration.lock:
            reasons = self.blockers()
            # One composite blocker does not erase separately reported activities.
            self.controller.report_activity(Activity.FRAME_CHANGE, bool(reasons))
            return GuardDecision(not reasons, reasons)

    def quiesce_gamepad(self, timeout_ms=3000):
        """Explicit handoff only. May call a worker stop in a future live run.

        Never called during construction. No claim about the input daemon.
        """
        if self.controller.active is not None:
            raise OwnershipError('handoff_requires_no_localization_lease')
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise ValueError('positive_gamepad_wait_required')
        motion = self.window.stageMotionWindow
        thread, worker = motion.threadG, motion.workerG
        if thread is None and worker is None:
            return True
        if thread is None or worker is None:
            return False
        worker.request_stop()
        if not thread.wait(timeout_ms):
            return False
        if motion.threadG is not thread or motion.workerG is not worker:
            return False
        if thread.isRunning() or not thread.isFinished():
            return False
        motion.release_gamepad()
        return motion.threadG is None and motion.workerG is None

    def acquire(self, settings):
        with self.controller.registration.lock:
            decision = self.refresh()
            if not decision.allowed:
                raise OwnershipError('; '.join(decision.reasons))
            handle = self.controller.start(settings)
            self.movement_attempted = False
            return handle

    def claim_daq(self, handle, task, *, reset=False):
        with self.controller.registration.lock:
            self.controller.checkpoint(handle)
            self.daq.claim(handle.run_id, task, reset=reset)

    def release_daq(self, handle, confirmed):
        with self.controller.registration.lock:
            if handle is not self.controller.active:
                raise OwnershipError('stale_run_daq_cleanup')
            return self.daq.release(handle.run_id, confirmed=confirmed)

    def execute_stage(self, handle, callback, timeout_s, *, cleanup=False):
        """All adapter operations must traverse the selected owner executor.

        No fallback to the calling worker thread is allowed. Native interruption
        is not supplied. Cleanup ignores cancellation, never lease/identity checks.
        """
        if self.executor is None and self._submit is None:
            raise OwnershipError('owner_thread_executor_unverified')
        def authorized():
            with self.controller.registration.lock:
                if handle is not self.controller.active or self.window.stage is not self.stage:
                    raise OwnershipError('stale_stage_authority')
                self.controller.ownership.assert_authority(handle.lease)
                if not cleanup:
                    self.controller.checkpoint(handle)
            self._authority.run_id = handle.run_id
            try:
                if hasattr(self.stage, 'execution_timeout'):
                    with self.stage.execution_timeout(timeout_s):
                        return callback()
                return callback()
            finally:
                self._authority.run_id = None
        return self.dispatcher.execute(handle, authorized, timeout_s, cleanup=cleanup)

    def _authorize_stage(self, handle, cleanup=False):
        with self.controller.registration.lock:
            if handle is not self.controller.active or self.window.stage is not self.stage:
                raise OwnershipError('stale_stage_authority')
            self.controller.ownership.assert_authority(handle.lease)
            if not cleanup:
                self.controller.checkpoint(handle)

    def _quarantine_stage(self, handle, reason):
        with self.controller.registration.lock:
            self.controller.ownership.quarantine(handle.lease, reason)
            self.controller.registration.invalidate(reason)
            self.controller.request_cancel(handle)

    def stage_interface(self, handle, *, bounds, polling_s, clock):
        """Adapter over a message-only capability; raw Prior never leaves bridge."""
        from experiment.scan_adapters import PriorStageAdapter
        bridge = self
        class Messages:
            def message(self, command):
                return bridge.execute_stage(handle, lambda: bridge.stage.message(command),
                    self.timeout_s, cleanup=self.cleanup)
        class Interface:
            def _call(self, name, args, timeout_s, cleanup=False):
                bridge._authorize_stage(handle, cleanup)
                # An interface is worker-confined; SDK serialization is global
                # to the bridge dispatcher. No shared mutable per-call authority.
                local_messages = Messages()
                local_messages.timeout_s, local_messages.cleanup = timeout_s, cleanup
                local_adapter = PriorStageAdapter(local_messages, bounds=bounds,
                    poll_interval_s=polling_s, clock=clock)
                try:
                    return getattr(local_adapter, name)(*args, timeout_s=timeout_s)
                except Exception:
                    if name == 'stop':
                        bridge._quarantine_stage(handle, 'protective_stop_failed')
                    raise

            def get_position(self, *, timeout_s):
                return self._call('get_position', (), timeout_s)

            def is_busy(self, *, timeout_s):
                return self._call('is_busy', (), timeout_s)

            def move_to(self, x, y, *, timeout_s):
                return self._call('move_to', (x, y), timeout_s)

            def stop(self, *, timeout_s):
                return self._call('stop', (), timeout_s, cleanup=True)

            stop_smoothly = stop

            def wait_until_idle(self, *, timeout_s):
                deadline = clock.monotonic() + timeout_s
                while True:
                    bridge._authorize_stage(handle)
                    remaining = deadline - clock.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('wait_until_idle_timeout')
                    if not self.is_busy(timeout_s=remaining):
                        return
                    clock.sleep(min(polling_s, remaining))
        return Interface()

    def dispatch(self, command, callback, *args, frame=None, **kwargs):
        with self.controller.registration.lock:
            if (self.dispatcher.uncertain or self.dispatcher.unresolved) and command not in READ_ONLY:
                raise OwnershipError('native_stage_execution_unresolved_or_quarantined')
            decision = self.controller.ownership.guard(command)
            if not decision.allowed:
                raise OwnershipError('; '.join(decision.reasons))
            self._calls_active += 1
            if frame:
                self.frame_event(frame)
            try:
                return callback(*args, **kwargs)
            finally:
                self._calls_active -= 1
                self._remember_threads()

    def install_guards(self):
        """Dynamic stage-window callbacks plus the shared driver's command boundary.

        Objective creation is intercepted at the main subclass; an existing
        objective widget blocks all localization, regardless of visibility.
        """
        if self.guards_installed:
            return True
        motion = getattr(self.window, 'stageMotionWindow', None)
        if motion is None or self.stage is None or not callable(getattr(self.stage, 'message', None)):
            return False
        if hasattr(self.stage, 'command_guard'):
            def proxy_guard(method, callback):
                run = self.controller.active
                if run and getattr(self._authority, 'run_id', None) == run.run_id:
                    self.controller.ownership.assert_authority(run.lease)
                    return callback()
                frame = {'set_position': 'set_position', 'reference': 'reference',
                         'connect': 'reconnect', 'disconnect': 'reconnect'}.get(method)
                return self.dispatch(Command.FRAME_CHANGE if frame else Command.MANUAL_MOVE,
                                     callback, frame=frame)
            self.stage.command_guard = proxy_guard
        for name, command in STAGE_COMMANDS.items():
            original = getattr(motion, name, None)
            if callable(original):
                def guarded(*args, _call=original, _cmd=command, **kwargs):
                    try:
                        return self.dispatch(_cmd, _call, *args, **kwargs)
                    except OwnershipError as error:
                        # Do not let a rejected Qt callback escape its event loop.
                        self.last_guard_failure = str(error)
                        return False
                setattr(motion, name, guarded)
        original_message = self.stage.message
        def invoke(command):
            try:
                result = original_message(command)
                if not isinstance(result, tuple) or len(result) != 2 or result[0] != 0:
                    self.frame_event('communication_loss')
                return result
            except Exception:
                self.frame_event('communication_loss')
                raise
        def message(command):
            run = self.controller.active
            if run and getattr(self._authority, 'run_id', None) == run.run_id:
                self.controller.ownership.assert_authority(run.lease)
                if str(command).startswith('controller.stage.goto-position '):
                    self.movement_attempted = True
                return invoke(command)
            frame = None
            text = str(command).lower()
            if any(word in text for word in ('position.set', 'set-position', 'home', 'reference', 'reset', 'connect')):
                frame = 'set_position'
            return self.dispatch(Command.FRAME_CHANGE if frame else Command.MANUAL_MOVE,
                                 invoke, command, frame=frame)
        self.stage.message = message
        for name in ('connect', 'disconnect', 'close_session'):
            original = getattr(self.stage, name, None)
            if callable(original):
                def session_call(*args, _call=original, **kwargs):
                    return self.dispatch(Command.FRAME_CHANGE, _call, *args, frame='reconnect', **kwargs)
                setattr(self.stage, name, session_call)
        self.guards_installed = True
        laser=getattr(self.window,'laser',None)
        if laser is not None:
            for name in ('arm','stabilize','enable','tune','sweep','sweep_and_forget',
                         'set_qcl_parameters','set_wl_trigger_parameters'):
                original=getattr(laser,name,None)
                if callable(original):
                    def guarded_laser(*args,_call=original,**kwargs):
                        try:
                            return self.dispatch(Command.SPECTRUM,_call,*args,**kwargs)
                        except OwnershipError as error:
                            self.last_guard_failure = str(error)
                            return False  # A rejected Qt callback must not unwind Qt.
                    setattr(laser,name,guarded_laser)
            # Emission-off remains an operator safety action; it cancels the run.
            for name in ('disable','disarm'):
                original=getattr(laser,name,None)
                if callable(original):
                    def laser_off(*args,_call=original,**kwargs):
                        self.controller.request_cancel()
                        return _call(*args,**kwargs)
                    setattr(laser,name,laser_off)
        return True

    def owner_uncertain(self, reason):
        run = self.controller.active
        if run is not None:
            self._quarantine_stage(run, reason)
        else:
            self.controller.registration.invalidate(reason)

    def request_close(self):
        self.close_pending = True
        if self.dispatcher.uncertain or self.dispatcher.unresolved:
            self.controller.request_cancel()
            return False
        return self.controller.request_close()

    def continue_close(self, callback):
        if (not self.close_pending or self.dispatcher.uncertain or self.dispatcher.unresolved
                or not self.controller.can_close()):
            return False
        callback()
        return True
