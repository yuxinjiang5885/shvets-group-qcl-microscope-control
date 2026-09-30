"""Inert operational objects; no driver or operational UI imports."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import unittest

from ui.registration_state import RegistrationState, RegistrationContext
from ui.localization_orchestration import (LocalizationController, RunSettings,
    CleanupOutcome, Command, OwnershipError, OwnershipStatus)
from ui.operational_localization_bridge import OperationalLocalizationBridge

ROOT = Path(__file__).resolve().parents[1]


class FakePrior:
    def __init__(self, position=(1000., 2000.)):
        self.position = position
        self.calls = []
        self.fail = None

    def message(self, command):
        self.calls.append(command)
        if self.fail and self.fail(command):
            raise RuntimeError('fake_controller_error')
        if command == 'controller.stage.busy.get':
            return 0, '0'
        if command == 'controller.stage.position.get':
            return 0, ','.join(map(str, self.position))
        if command.startswith('controller.stage.goto-position '):
            self.position = tuple(map(float, command.split()[-2:]))
        return 0, '0'

    def connect(self):
        self.calls.append('connect')

    def disconnect(self):
        self.calls.append('disconnect')

    def close_session(self):
        self.calls.append('close_session')


class FakeThread:
    def __init__(self, running=True):
        self.running = running
        self.wait_ok = True
        self.on_wait = None

    def isRunning(self):
        return self.running

    def isFinished(self):
        return not self.running

    def wait(self, milliseconds):
        if self.on_wait:
            self.on_wait()
        if self.wait_ok:
            self.running = False
        return self.wait_ok


class FakeMotion:
    def __init__(self, stage):
        self.stage = stage
        self.threadG = self.workerG = None
        self.threadMW = []

    def goto(self, x, y):
        self.stage.message(f'controller.stage.goto-position {x} {y}')

    def release_gamepad(self):
        self.threadG = self.workerG = None


def environment():
    stage = FakePrior()
    window = SimpleNamespace(stage=stage, stageMotionWindow=FakeMotion(stage))
    state = RegistrationState()
    state.set_context(RegistrationContext(marker_id='operator-marker', frame_id='fixture-frame'))
    controller = LocalizationController(state)
    bridge = OperationalLocalizationBridge(window, controller,
        executor=lambda call, timeout: call(), joystick_disabled=lambda: True)
    bridge.install_guards()
    return window, state, controller, bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.window, self.state, self.controller, self.bridge = environment()

    def acquire(self):
        return self.bridge.acquire(RunSettings(self.state.context, self.state.context_generation, 'confirmed-rough-start'))

    def test_construction_and_borrow_identity_without_connect(self):
        self.assertIs(self.bridge.stage, self.window.stage)
        self.assertEqual(self.window.stage.calls, [])
        handle = self.acquire()
        self.controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(True, True))
        self.assertEqual(self.window.stage.calls, [])

    def test_second_bridge_and_second_stage_rejected(self):
        with self.assertRaises(OwnershipError):
            OperationalLocalizationBridge(self.window, self.controller)
        other = SimpleNamespace(stage=FakePrior(), stageMotionWindow=FakeMotion(FakePrior()))
        with self.assertRaises(OwnershipError):
            OperationalLocalizationBridge(other, self.controller)
        shared = SimpleNamespace(stage=self.window.stage, stageMotionWindow=FakeMotion(self.window.stage))
        with self.assertRaises(OwnershipError):
            OperationalLocalizationBridge(shared, self.controller)

    def test_scan_repeat_imaging_multiple_workers_block(self):
        for attribute in ('threadRun', 'threadRep', 'threadMul'):
            with self.subTest(attribute=attribute):
                self.setUp()
                setattr(self.window, attribute, FakeThread())
                with self.assertRaisesRegex(OwnershipError, attribute):
                    self.acquire()

    def test_multiwell_blocks(self):
        self.window.stageMotionWindow.threadMW = FakeThread()
        with self.assertRaisesRegex(OwnershipError, 'threadMW'):
            self.acquire()

    def test_objective_and_autofocus_unknown_even_when_hidden(self):
        self.window.pi_scanner_widget = SimpleNamespace(visible=False)
        with self.assertRaisesRegex(OwnershipError, 'objective_daq_autofocus'):
            self.acquire()

    def test_deleted_or_unreadable_worker_fails_closed(self):
        thread = FakeThread()
        thread.isRunning = lambda: (_ for _ in ()).throw(RuntimeError('deleted Qt wrapper'))
        self.window.threadRun = thread
        with self.assertRaisesRegex(OwnershipError, 'state_unknown'):
            self.acquire()

    def gamepad(self):
        motion = self.window.stageMotionWindow
        motion.threadG = FakeThread()
        calls = []
        motion.workerG = SimpleNamespace(request_stop=lambda: calls.append('stop'))
        return motion, calls

    def test_gamepad_stopped_and_successful_handoff(self):
        self.assertTrue(self.bridge.quiesce_gamepad())
        motion, calls = self.gamepad()
        with self.assertRaisesRegex(OwnershipError, 'gamepad'):
            self.acquire()
        self.assertTrue(self.bridge.quiesce_gamepad())
        self.assertEqual(calls, ['stop'])
        self.acquire()

    def test_gamepad_timeout_blocks(self):
        motion, _ = self.gamepad()
        motion.threadG.wait_ok = False
        self.assertFalse(self.bridge.quiesce_gamepad())
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_stale_gamepad_completion_blocks(self):
        motion, _ = self.gamepad()
        motion.threadG.on_wait = lambda: setattr(motion, 'threadG', FakeThread())
        self.assertFalse(self.bridge.quiesce_gamepad())
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_hardware_joystick_unknown_blocks(self):
        self.bridge.joystick_disabled = lambda: None
        with self.assertRaisesRegex(OwnershipError, 'joystick'):
            self.acquire()

    def test_missing_owner_thread_executor_blocks(self):
        self.bridge.executor = None
        with self.assertRaisesRegex(OwnershipError, 'owner_thread'):
            self.acquire()

    def test_leased_legacy_stage_and_acquisition_callbacks_block(self):
        self.acquire()
        calls = []
        for command in (Command.IMAGING, Command.SPECTRUM, Command.GAMEPAD,
                        Command.MANUAL_MOVE, Command.FRAME_CHANGE, Command.OBJECTIVE_MOVE):
            with self.assertRaises(OwnershipError):
                self.bridge.dispatch(command, lambda: calls.append('unsafe'))
        self.assertFalse(self.window.stageMotionWindow.goto(1, 2))
        with self.assertRaises(OwnershipError):
            self.window.stage.message('controller.stage.goto-position 1 2')
        self.assertFalse(calls)
        self.assertEqual(self.window.stage.calls, [])

    def test_read_only_allowed(self):
        self.acquire()
        self.assertEqual(self.bridge.dispatch(Command.LOGS, lambda: 'cached'), 'cached')

    def test_no_disconnect_or_close_while_borrowed(self):
        self.acquire()
        for name in ('connect', 'disconnect', 'close_session'):
            with self.assertRaises(OwnershipError):
                getattr(self.window.stage, name)()
        self.assertFalse(self.window.stage.calls)

    def test_frame_hooks_cancel_and_increment(self):
        for event in ('set_position', 'home', 'reference', 'reset', 'reconnect',
                      'session_replacement', 'communication_loss', 'sample', 'gds',
                      'marker', 'orientation', 'inputs'):
            with self.subTest(event=event):
                self.setUp()
                handle = self.acquire()
                generation = self.state.context_generation
                self.bridge.frame_event(event)
                self.assertEqual(self.state.context_generation, generation+1)
                self.assertTrue(handle.cancellation.is_cancelled())

    def test_ordinary_movement_does_not_invalidate(self):
        generation = self.state.context_generation
        for event in ('goto', 'gamepad_move', 'return_to_zero'):
            self.bridge.frame_event(event)
        self.window.stageMotionWindow.goto(1, 2)
        self.assertEqual(self.state.context_generation, generation)

    def test_raw_coordinate_redefine_is_intercepted(self):
        generation = self.state.context_generation
        self.window.stage.message('controller.stage.position.set 0 0')
        self.assertEqual(self.state.context_generation, generation+1)

    def test_close_defers_and_continues_after_safe_cleanup(self):
        handle = self.acquire()
        calls = []
        self.assertFalse(self.bridge.request_close())
        self.assertTrue(handle.cancellation.is_cancelled())
        self.assertFalse(self.bridge.continue_close(lambda: calls.append('close')))
        self.controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(True, True))
        self.assertTrue(self.bridge.continue_close(lambda: calls.append('close')))
        self.assertEqual(calls, ['close'])

    def test_quarantine_prevents_close_and_new_acquisition(self):
        handle = self.acquire()
        self.controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(False, True))
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
        self.assertFalse(self.bridge.request_close())

    def test_daq_scoped_by_run_reset_false_and_stale_release_rejected(self):
        handle = self.acquire()
        task = object()
        with self.assertRaises(OwnershipError):
            self.bridge.claim_daq(handle, task, reset=True)
        self.bridge.claim_daq(handle, task)
        with self.assertRaises(OwnershipError):
            self.bridge.daq.release('stale', confirmed=True)
        self.assertIs(self.bridge.daq.task, task)
        self.assertTrue(self.bridge.release_daq(handle, True))

    def test_daq_conflict_blocks(self):
        self.bridge.daq.claim('other-run', object(), reset=False)
        with self.assertRaisesRegex(OwnershipError, 'daq_conflict'):
            self.acquire()

    def test_daq_cleanup_unknown_stays_owned(self):
        handle = self.acquire()
        self.bridge.claim_daq(handle, object())
        self.assertFalse(self.bridge.release_daq(handle, False))
        self.assertTrue(self.bridge.daq.uncertain)

    def test_stale_stage_call_rejected(self):
        old = self.acquire()
        self.controller.finish(old, succeeded=False, cleanup=CleanupOutcome(True, True))
        current = self.acquire()
        with self.assertRaises(OwnershipError):
            self.bridge.execute_stage(old, lambda: None, 2)
        self.controller.ownership.assert_authority(current.lease)

    def test_stage_proxy_uses_injected_executor(self):
        handle = self.acquire()
        calls = []
        self.bridge.executor = lambda callback, timeout: (calls.append(timeout), callback())[1]
        self.bridge.execute_stage(handle, lambda: self.window.stage.message('controller.stage.position.get'), 2)
        self.assertEqual(calls, [2])

    def test_commands_marshalled_to_one_executor_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import get_ident
        handle = self.acquire()
        caller = get_ident()
        with ThreadPoolExecutor(max_workers=1) as owner:
            self.bridge.executor = lambda callback, timeout: owner.submit(callback).result(timeout)
            observed = [self.bridge.execute_stage(handle, get_ident, 2) for _ in range(3)]
        self.assertEqual(len(set(observed)), 1)
        self.assertNotEqual(observed[0], caller)

    def test_driver_exception_invalidates_and_requests_cancel(self):
        handle = self.acquire()
        generation = self.state.context_generation
        self.window.stage.fail = lambda command: True
        with self.assertRaises(RuntimeError):
            self.bridge.execute_stage(handle, lambda: self.window.stage.message('controller.stage.position.get'), 2)
        self.assertGreater(self.state.context_generation, generation)
        self.assertTrue(handle.cancellation.is_cancelled())

    def test_session_replacement_blocks_borrow(self):
        self.window.stage = FakePrior()
        with self.assertRaisesRegex(OwnershipError, 'replaced'):
            self.acquire()

    def test_stable_ui_hash(self):
        self.assertEqual(sha256((ROOT/'qcl_scanning_imaging_ui.py').read_bytes()).hexdigest(),
            'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab')


if __name__ == '__main__':
    unittest.main()
