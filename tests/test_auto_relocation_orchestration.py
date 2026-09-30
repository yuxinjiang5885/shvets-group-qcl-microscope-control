"""Offline orchestration tests. Injected services never import device drivers."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from threading import Barrier, Event, Thread
import subprocess
import sys
import unittest

from ui.registration_state import (ContextEvent, RegistrationState, RegistrationStatus,
                                   replay_archived_evidence)
from ui.localization_orchestration import (
    AcquisitionState, Activity, CancellationToken, Cancelled, CleanupOutcome,
    Command, HardwareOwnershipController, LocalizationController, LocateMarkerWorker,
    OwnershipError, OwnershipStatus, READ_ONLY, RecoveryConfirmation, RunSettings,
    RunStateMachine, WorkerEvent)

ROOT = Path(__file__).resolve().parents[1]
GOOD = CleanupOutcome(True, True)


class FakeServices:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = []
        self.movement_attempted = False
        self.before_work = None
        self.prepare_error = False
        self.work_error = False
        self.fail_cleanup = None

    def prepare(self, settings):
        self.calls.append('prepare')
        if self.prepare_error:
            raise RuntimeError('partial_prepare_failure')

    def work(self, settings, checkpoint, progress):
        self.calls.append('work')
        self.movement_attempted = True  # Fake driver-entry marker, not a move.
        if self.before_work:
            self.before_work()
        checkpoint()
        if self.work_error:
            raise RuntimeError('work_failure')
        progress({'completed': 1})
        return self.evidence

    def _cleanup(self, name):
        self.calls.append(name)
        if self.fail_cleanup == name:
            raise RuntimeError('fake_cleanup_failure')
        return True

    def protective_stop(self):
        return self._cleanup('protective_stop')

    def release_daq(self):
        return self._cleanup('release_daq')

    def confirm_idle(self):
        return self._cleanup('confirm_idle')


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.owner = HardwareOwnershipController()

    def quarantine(self):
        lease = self.owner.acquire()
        self.owner.release(lease, CleanupOutcome(False, True))
        return lease

    def test_acquire_release_unique_ids(self):
        first = self.owner.acquire()
        self.assertEqual(len(first.authorities), 5)
        self.owner.release(first, GOOD)
        second = self.owner.acquire()
        self.assertNotEqual(first.run_id, second.run_id)
        self.owner.release(second, GOOD)
        self.assertEqual(self.owner.status, OwnershipStatus.AVAILABLE)

    def test_double_acquire_rejected(self):
        self.owner.acquire()
        with self.assertRaises(OwnershipError):
            self.owner.acquire()

    def test_stale_and_forged_release_rejected(self):
        first = self.owner.acquire()
        with self.assertRaises(OwnershipError):
            self.owner.release(replace(first), GOOD)
        self.owner.release(first, GOOD)
        second = self.owner.acquire()
        with self.assertRaises(OwnershipError):
            self.owner.release(first, GOOD)
        self.owner.assert_authority(second)

    def test_atomic_competing_acquire(self):
        barrier = Barrier(3)
        results = []
        def acquire():
            barrier.wait()
            try:
                results.append(self.owner.acquire())
            except OwnershipError:
                results.append(None)
        threads = [Thread(target=acquire) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(value is not None for value in results), 1)

    def test_each_legacy_blocker_prevents_lease(self):
        for activity in Activity:
            with self.subTest(activity=activity):
                self.owner.set_activity(activity, True)
                decision = self.owner.can_begin_localization()
                self.assertFalse(decision.allowed)
                self.assertIn('activity:' + activity.value, decision.reasons)
                with self.assertRaises(OwnershipError):
                    self.owner.acquire()
                self.owner.set_activity(activity, False)
        self.assertTrue(self.owner.can_begin_localization().allowed)

    def test_cleanup_failure_quarantines(self):
        for outcome in (CleanupOutcome(False, True), CleanupOutcome(True, False),
                        CleanupOutcome(True, True, False), CleanupOutcome(True, True, reasons=('unknown',))):
            owner = HardwareOwnershipController()
            owner.release(owner.acquire(), outcome)
            self.assertEqual(owner.status, OwnershipStatus.QUARANTINED)
            with self.assertRaises(OwnershipError):
                owner.acquire()

    def test_recovery_requires_explicit_complete_attestation(self):
        lease = self.quarantine()
        good = RecoveryConfirmation(lease.run_id, True, True, True, True, 'operator verified')
        for bad in (replace(good, run_id='stale'), replace(good, stage_idle=False),
                    replace(good, daq_released=False), replace(good, frame_verified=False),
                    replace(good, competing_activity_stopped=False), replace(good, operator_note='')):
            with self.assertRaises(OwnershipError):
                self.owner.acknowledge_recovery(bad)
        self.owner.acknowledge_recovery(good)
        self.assertTrue(self.owner.can_begin_localization().allowed)

    def test_late_activity_cannot_be_cleared_by_successful_cleanup(self):
        lease = self.owner.acquire()
        self.owner.set_activity(Activity.GAMEPAD, True)
        self.owner.set_activity(Activity.GAMEPAD, False)
        self.owner.release(lease, GOOD)
        self.assertEqual(self.owner.status, OwnershipStatus.QUARANTINED)

    def test_recovery_blocked_while_activity_or_lease_remains(self):
        lease = self.owner.acquire()
        self.owner.set_activity(Activity.GAMEPAD, True)
        confirmation = RecoveryConfirmation(lease.run_id, True, True, True, True, 'checked')
        with self.assertRaises(OwnershipError):
            self.owner.acknowledge_recovery(confirmation)
        self.owner.release(lease, GOOD)
        with self.assertRaises(OwnershipError):
            self.owner.acknowledge_recovery(confirmation)

    def test_all_busy_guards_and_read_only_categories(self):
        lease = self.owner.acquire()
        for command in Command:
            with self.subTest(command=command):
                self.assertEqual(self.owner.guard(command).allowed, command in READ_ONLY)
        self.owner.release(lease, CleanupOutcome(False, False))
        for command in Command:
            self.assertEqual(self.owner.guard(command).allowed, command in READ_ONLY)

    def test_guard_enforced_before_fake_callback(self):
        calls = []
        self.owner.acquire()
        with self.assertRaises(OwnershipError):
            self.owner.dispatch(Command.MANUAL_MOVE, lambda: calls.append('move'))
        self.owner.dispatch(Command.LOGS, lambda: calls.append('log'))
        self.assertEqual(calls, ['log'])
        self.assertFalse(self.owner.guard('unrecognized').allowed)

    def test_target_motion_never_enabled(self):
        self.assertFalse(self.owner.guard(Command.TARGET_MOTION).allowed)


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = replay_archived_evidence(ROOT)  # File reads and offline math only.

    def setUp(self):
        self.state = RegistrationState()
        self.state.set_context(self.evidence.context)
        self.state.accept(self.evidence)
        self.approved = self.state.approved_registration
        self.controller = LocalizationController(self.state)
        self.services = FakeServices(self.evidence)

    def start(self, token=None):
        return self.controller.start(RunSettings(self.state.context,
            self.state.context_generation, 'operator-verified-rough-start'), token)

    def run_worker(self, handle=None):
        worker = LocateMarkerWorker(self.controller, handle or self.start(), self.services)
        events = []
        worker.run(events.append)
        self.assertEqual(events[-1].name, 'finished')
        return worker, events

    def test_shared_transaction_lock_required(self):
        with self.assertRaisesRegex(ValueError, 'transaction_lock'):
            LocalizationController(self.state, HardwareOwnershipController())
        LocalizationController(self.state, HardwareOwnershipController(self.state.lock))

    def test_valid_state_transitions(self):
        for terminal in (AcquisitionState.COMPLETE, AcquisitionState.FAILED, AcquisitionState.CANCELLED):
            machine = RunStateMachine()
            machine.transition(AcquisitionState.RUNNING)
            if terminal is AcquisitionState.CANCELLED:
                machine.transition(AcquisitionState.CANCELLING)
            machine.transition(terminal)
            machine.transition(AcquisitionState.IDLE)

    def test_invalid_transition_rejected(self):
        machine = RunStateMachine()
        with self.assertRaises(ValueError):
            machine.transition(AcquisitionState.COMPLETE)
        machine.transition(AcquisitionState.RUNNING)
        with self.assertRaises(ValueError):
            machine.transition(AcquisitionState.RUNNING)

    def test_token_checkpoint(self):
        token = CancellationToken()
        token.checkpoint()
        token.request_cancel()
        self.assertTrue(token.is_cancelled())
        with self.assertRaises(Cancelled):
            token.checkpoint()

    def test_run_settings_immutable_and_stale_settings_rejected(self):
        settings = RunSettings(self.state.context, self.state.context_generation, 'rough')
        with self.assertRaises(FrozenInstanceError):
            settings.expected_rough_start_id = 'other'
        self.state.handle_context_event(ContextEvent.FRAME)
        with self.assertRaisesRegex(ValueError, 'stale_run_context'):
            self.controller.start(settings)
        with self.assertRaises(ValueError):
            RunSettings(self.state.context, 0, '')

    def test_start_preserves_approved_registration(self):
        self.start()
        self.assertIs(self.state.approved_registration, self.approved)
        self.assertEqual(self.state.status, RegistrationStatus.VALID)
        self.assertEqual(self.controller.snapshot()['acquisition'], 'RUNNING')

    def test_cancellation_before_work_has_no_cleanup_commands(self):
        token = CancellationToken()
        token.request_cancel()
        self.run_worker(self.start(token))
        self.assertEqual(self.services.calls, [])
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)
        self.assertIs(self.state.registration, self.approved)

    def test_cancel_during_work_preserves_approval_and_cleanup_order(self):
        self.services.before_work = self.controller.request_cancel
        self.run_worker()
        self.assertEqual(self.services.calls,
            ['prepare', 'work', 'protective_stop', 'release_daq', 'confirm_idle'])
        self.assertIs(self.state.registration, self.approved)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_cancel_does_not_interrupt_blocked_call_or_release_lease(self):
        entered, unblock = Event(), Event()
        def blocking_call():
            entered.set()
            if not unblock.wait(5):
                raise RuntimeError('test_block_timeout')
        self.services.before_work = blocking_call
        worker = LocateMarkerWorker(self.controller, self.start(), self.services)
        thread = Thread(target=worker.run)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.controller.request_cancel()
            self.assertTrue(thread.is_alive())
            self.assertEqual(self.controller.ownership.status, OwnershipStatus.LEASED)
            self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLING)
            self.assertNotIn('protective_stop', self.services.calls)
            self.assertFalse(self.controller.can_close())
        finally:
            unblock.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_worker_exception_retains_prior_and_reports_failure(self):
        self.services.work_error = True
        _, events = self.run_worker()
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertIs(self.state.registration, self.approved)
        self.assertIn('RuntimeError: work_failure', self.controller.reasons)
        self.assertIn('failed', [event.name for event in events])

    def test_prepare_failure_cleans_partial_resources_without_stop(self):
        self.services.prepare_error = True
        self.run_worker()
        self.assertEqual(self.services.calls, ['prepare', 'release_daq', 'confirm_idle'])
        self.assertIs(self.state.registration, self.approved)

    def test_success_publishes_only_after_cleanup(self):
        handle = self.start()
        self.controller.offer_candidate(handle, self.evidence)
        self.assertIs(self.state.registration, self.approved)
        self.assertTrue(self.controller.snapshot()['candidate_pending'])
        self.assertTrue(self.controller.finish(handle, succeeded=True, cleanup=GOOD))
        self.assertIsNot(self.state.registration, self.approved)
        self.assertEqual(self.controller.machine.state, AcquisitionState.COMPLETE)
        self.assertIsNone(self.controller.candidate_registration)

    def test_success_events_warnings_and_cleanup(self):
        _, events = self.run_worker()
        names = [event.name for event in events]
        self.assertEqual(names[0], 'started')
        self.assertIn('progress', names)
        self.assertIn('registration_completed', names)
        self.assertIn('left_right_angle_disagreement_warning', self.controller.warnings)
        self.assertIn('warning', names)
        self.assertEqual(self.services.calls, ['prepare', 'work', 'release_daq', 'confirm_idle'])
        self.assertEqual(self.controller.reasons, ())

    def test_candidate_hard_qc_failure_propagates_and_does_not_replace(self):
        self.services.evidence = replace(self.evidence, rotation=replace(self.evidence.rotation,
            valid=False, reasons=('synthetic_rotation_failure',)))
        self.run_worker()
        self.assertIs(self.state.registration, self.approved)
        self.assertIn('synthetic_rotation_failure', self.controller.reasons)
        self.assertIn('left_right_angle_disagreement_warning', self.controller.warnings)
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertIn('protective_stop', self.services.calls)

    def test_malformed_candidate_still_cleans_up_and_finishes(self):
        self.services.evidence = None
        self.run_worker()
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertIs(self.state.registration, self.approved)
        self.assertIn('ValueError: malformed_candidate', self.controller.reasons)
        self.assertEqual(self.services.calls[-3:], ['protective_stop', 'release_daq', 'confirm_idle'])

    def test_cleanup_failure_prevents_publish_and_invalidates_prior(self):
        for method in ('release_daq', 'confirm_idle'):
            with self.subTest(method=method):
                self.setUp()
                self.services.fail_cleanup = method
                self.run_worker()
                self.assertIsNone(self.state.registration)
                self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
                self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
                self.assertEqual(self.services.calls[-1], 'confirm_idle')
                with self.assertRaises(OwnershipError):
                    self.start()

    def test_unconfirmed_stop_quarantines_even_if_idle_later(self):
        self.services.work_error = True
        self.services.fail_cleanup = 'protective_stop'
        self.run_worker()
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
        self.assertIsNone(self.state.registration)

    def test_unknown_movement_tracking_quarantines_without_guessing_stop(self):
        def corrupt_tracking():
            self.services.movement_attempted = None
        self.services.before_work = corrupt_tracking
        self.services.work_error = True
        self.run_worker()
        self.assertNotIn('protective_stop', self.services.calls)
        self.assertIn('release_daq', self.services.calls)
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)

    def test_recovery_does_not_resurrect_approval(self):
        self.services.fail_cleanup = 'release_daq'
        self.run_worker()
        owner = self.controller.ownership
        owner.acknowledge_recovery(RecoveryConfirmation(owner.quarantined_run_id,
            True, True, True, True, 'fake external verification'))
        self.assertIsNone(self.state.registration)
        self.assertTrue(owner.can_begin_localization().allowed)

    def test_context_change_rejects_stale_candidate(self):
        handle = self.start()
        self.controller.offer_candidate(handle, self.evidence)
        generation = self.state.context_generation
        self.controller.handle_context_event(ContextEvent.FRAME)
        self.assertEqual(self.state.context_generation, generation + 1)
        self.assertFalse(self.controller.finish(handle, succeeded=True, cleanup=GOOD))
        self.assertIsNone(self.state.registration)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_all_sensitive_events_increment_and_invalidate(self):
        for event in ContextEvent:
            if event is ContextEvent.MOVEMENT:
                continue
            with self.subTest(event=event):
                self.setUp()
                generation = self.state.context_generation
                self.controller.handle_context_event(event)
                self.assertEqual(self.state.context_generation, generation + 1)
                self.assertIsNone(self.state.registration)

    def test_context_field_changes_increment_generation(self):
        for field in ('gds_path', 'gds_sha256', 'marker_id', 'frame_id', 'sample_id', 'inputs_id'):
            generation = self.state.context_generation
            self.state.set_context(replace(self.state.context, **{field: 'changed-' + field}))
            self.assertEqual(self.state.context_generation, generation + 1)

    def test_movement_and_targets_preserve_approval_and_generation(self):
        generation = self.state.context_generation
        self.controller.handle_context_event(ContextEvent.MOVEMENT)
        self.state.targets_changed(None)
        self.assertEqual(self.state.context_generation, generation)
        self.assertIs(self.state.registration, self.approved)
        with self.assertRaises(ValueError):
            self.controller.handle_context_event(ContextEvent.MOVEMENT,
                replace(self.state.context, frame_id='new'))

    def test_context_return_to_original_does_not_make_old_result_current(self):
        handle = self.start()
        original = self.state.context
        self.state.set_context(replace(original, sample_id='replacement'))
        self.state.set_context(original)
        with self.assertRaises(Cancelled):
            self.controller.offer_candidate(handle, self.evidence)
        self.assertIsNone(self.state.registration)

    def test_close_defers_until_cleanup_and_prevents_new_runs(self):
        handle = self.start()
        self.assertFalse(self.controller.request_close())
        self.assertTrue(handle.cancellation.is_cancelled())
        self.run_worker(handle)
        self.assertTrue(self.controller.can_close())
        with self.assertRaises(OwnershipError):
            self.start()

    def test_quarantine_blocks_close(self):
        self.services.fail_cleanup = 'release_daq'
        self.run_worker()
        self.assertFalse(self.controller.request_close())

    def test_stale_completion_cannot_release_or_cancel_new_run(self):
        old = self.start()
        self.controller.finish(old, succeeded=False, cleanup=GOOD)
        new = self.start()
        self.assertFalse(self.controller.finish(old, succeeded=True, cleanup=GOOD))
        self.assertFalse(self.controller.request_cancel(old))
        self.controller.ownership.assert_authority(new.lease)
        self.assertEqual(self.controller.machine.state, AcquisitionState.RUNNING)
        self.assertFalse(self.controller.event_is_current(
            WorkerEvent('finished', old.run_id, old.settings.context_generation)))

    def test_stale_worker_never_calls_services_or_uses_new_run_result(self):
        old = self.start()
        self.controller.finish(old, succeeded=False, cleanup=GOOD)
        new = self.start()
        _, events = self.run_worker(old)
        self.assertEqual(events[-1].detail, 'STALE')
        self.assertEqual(self.services.calls, [])
        self.assertIs(self.controller.active, new)

    def test_event_rejected_after_frame_change(self):
        handle = self.start()
        event = WorkerEvent('progress', handle.run_id, handle.settings.context_generation)
        self.assertTrue(self.controller.event_is_current(event))
        self.controller.handle_context_event(ContextEvent.FRAME)
        self.assertFalse(self.controller.event_is_current(event))

    def test_late_conflict_cancels_and_invalidates_prior(self):
        self.services.before_work = lambda: self.controller.report_activity(Activity.GAMEPAD, True)
        self.run_worker()
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
        self.assertIsNone(self.state.registration)

    def test_observer_exception_does_not_skip_cleanup(self):
        worker = LocateMarkerWorker(self.controller, self.start(), self.services)
        def broken_observer(event):
            raise RuntimeError('observer_failure')
        worker.run(broken_observer)
        self.assertTrue(worker.delivery_errors)
        self.assertEqual(self.controller.machine.state, AcquisitionState.COMPLETE)
        self.assertEqual(self.services.calls[-2:], ['release_daq', 'confirm_idle'])

    def test_terminal_events_do_not_read_a_new_runs_state(self):
        handle = self.start()
        worker = LocateMarkerWorker(self.controller, handle, self.services)
        events = []
        def observer(event):
            events.append(event)
            if event.name == 'warning':
                self.start()
        worker.run(observer)
        self.assertEqual(self.controller.machine.state, AcquisitionState.RUNNING)
        self.assertEqual(events[-1].detail, 'COMPLETE')
        self.assertTrue(all(event.run_id == handle.run_id for event in events))
        self.assertFalse(self.controller.event_is_current(events[-1]))

    def test_worker_cannot_be_reused(self):
        worker, _ = self.run_worker()
        with self.assertRaises(RuntimeError):
            worker.run()

    def test_cancel_after_candidate_before_publication(self):
        handle = self.start()
        self.controller.offer_candidate(handle, self.evidence)
        handle.cancellation.request_cancel()
        self.assertFalse(self.controller.finish(handle, succeeded=True, cleanup=GOOD))
        self.assertIs(self.state.registration, self.approved)

    def test_direct_context_mutation_during_cleanup_prevents_publication(self):
        original = self.services.release_daq
        def release():
            self.state.handle_context_event(ContextEvent.RECONNECT)
            return original()
        self.services.release_daq = release
        self.run_worker()
        self.assertIsNone(self.state.registration)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_core_fake_run_without_qt_or_hardware_imports(self):
        script = '''
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('instruments', 'PyDAQmx', 'pipython', 'inputs', 'PyQt6', 'qcl_scanning_imaging_ui') or fullname == 'experiment.routines':
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
sys.path.insert(0, 'tests')
from test_auto_relocation_orchestration import FakeServices, ROOT
from ui.registration_state import RegistrationState, replay_archived_evidence
from ui.localization_orchestration import LocalizationController, RunSettings, LocateMarkerWorker
evidence = replay_archived_evidence(ROOT)
state = RegistrationState()
state.set_context(evidence.context)
controller = LocalizationController(state)
handle = controller.start(RunSettings(state.context, state.context_generation, 'fake'))
LocateMarkerWorker(controller, handle, FakeServices(evidence)).run()
assert controller.machine.state.value == 'COMPLETE'
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], cwd=ROOT,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
