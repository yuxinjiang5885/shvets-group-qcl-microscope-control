"""Objective ownership tests: inert NI backend and no instrument imports."""
from threading import Barrier, Event, Thread
from types import SimpleNamespace
import unittest

from test_operational_localization_bridge import environment, FakeThread
from test_localization_daq import FakeNI
from ui.objective_daq_lifecycle import ObjectiveDaqLifecycle
from ui.localization_orchestration import RunSettings, CleanupOutcome, OwnershipError, Activity
from ui.snake_daq_lifecycle import snake_worker_factory
from test_snake_daq_lifecycle import FakeSnake, MultiAI, _raw_tasks
from PyQt6.QtCore import QObject, QThread
from PyQt6.QtWidgets import QApplication


class ObjectiveNI(FakeNI):
    def DAQmxCfgSampClkTiming(self, *args):
        assert args[2:] == (10000, 2, 3, 10)
        return self.status('timing')


class ObjectiveLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.window, self.state, self.controller, self.bridge = environment()
        self.ni = ObjectiveNI()
        self.owner = ObjectiveDaqLifecycle(self.bridge, self.ni)

    def settings(self):
        return RunSettings(self.state.context, self.state.context_generation, 'fake')

    def acquire(self):
        return self.bridge.acquire(self.settings())

    def finish(self, handle, clean=True):
        self.controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(clean, clean))

    def test_never_opened_no_task_localization_allowed(self):
        self.assertEqual(self.ni.calls, [])
        self.finish(self.acquire())

    def test_acquisition_exactly_one_task_and_owner_bound_release(self):
        self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertEqual(self.ni.calls, ['create', 'channel1', 'channel2', 'timing',
                                        'start', 'read', 'stop', 'clear'])
        self.assertIs(self.ni.reset, False)
        self.assertEqual(self.ni.channels, [b'Dev1/ai0', b'Dev1/ai1'])
        self.assertTrue(self.owner.released())
        record = self.bridge.legacy_daq_evidence.records[self.owner.current.token]
        self.assertTrue(record['released'])
        self.assertIs(record['owner'], self.owner.current)
        self.finish(self.acquire())

    def test_autofocus_multiple_reads_one_operation_task(self):
        def focus():
            self.assertEqual(self.owner.state, 'ACTIVE')
            with self.assertRaisesRegex(OwnershipError, 'managed_objective_active'):
                self.acquire()
            with self.assertRaises(OwnershipError):
                self.controller.start(self.settings())
            for _ in range(3):
                self.owner.acquire_data()
        self.owner.run('autofocus', focus)
        self.assertEqual(self.ni.calls.count('create'), 1)
        self.assertEqual(self.ni.calls.count('read'), 3)
        self.assertEqual(self.ni.calls.count('clear'), 1)
        self.assertTrue(self.owner.released())
        self.finish(self.acquire())

    def test_all_native_failures_attempt_cleanup_and_fail_closed(self):
        for phase in ('create', 'channel1', 'timing', 'start', 'read', 'stop', 'clear'):
            with self.subTest(phase=phase):
                self.setUp()
                if phase == 'clear':
                    self.ni.clear_fail = True
                else:
                    self.ni.fail = phase
                with self.assertRaises(OwnershipError):
                    self.owner.run('acquire_signal', self.owner.acquire_data)
                self.assertEqual(self.ni.calls.count('clear'), 1)
                if phase in ('start', 'read', 'stop', 'clear'):
                    self.assertEqual(self.ni.calls.count('stop'), 1)
                self.assertEqual(self.owner.state, 'UNCERTAIN')
                self.assertFalse(self.owner.current.execution_in_flight)
                self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)
                with self.assertRaises(OwnershipError):
                    self.acquire()
                with self.assertRaises(OwnershipError):
                    self.controller.start(self.settings())
                before = list(self.ni.calls)
                with self.assertRaises(OwnershipError):
                    self.owner.run('retry', self.owner.acquire_data)
                self.assertEqual(self.ni.calls, before)

    def test_short_read_and_timeout_always_stop_and_clear(self):
        for attr in ('short', 'timeout'):
            with self.subTest(attr=attr):
                self.setUp()
                setattr(self.ni, attr, True)
                with self.assertRaises(OwnershipError):
                    self.owner.run('acquire_signal', self.owner.acquire_data)
                self.assertEqual(self.ni.calls[-2:], ['stop', 'clear'])

    def test_missing_native_handle_is_not_attested(self):
        self.ni.DAQmxCreateTask = lambda *args: 0
        with self.assertRaises(OwnershipError):
            self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertEqual(self.owner.state, 'UNCERTAIN')
        self.assertFalse(self.owner.current.task.clear_confirmed)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)

    def test_hardware_exception_swallowed_by_legacy_remains_uncertain(self):
        def callback():
            try:
                self.owner.hardware_call(lambda: (_ for _ in ()).throw(TimeoutError('fake')))
            except TimeoutError:
                pass
        with self.assertRaises(OwnershipError):
            self.owner.run('move_to', callback)
        self.assertEqual(self.owner.state, 'UNCERTAIN')
        self.assertEqual(self.ni.calls, [])

    def test_fresh_session_does_not_inherit_uncertainty(self):
        self.ni.clear_fail = True
        with self.assertRaises(OwnershipError):
            self.owner.run('acquire_signal', self.owner.acquire_data)
        old_session = self.bridge.legacy_daq_evidence.session_id
        self.setUp()
        self.assertNotEqual(old_session, self.bridge.legacy_daq_evidence.session_id)
        self.finish(self.acquire())

    def test_clear_wait_holds_no_transaction_lock_and_blocks_admission(self):
        entered, release = Event(), Event()
        errors = []
        original = self.ni.DAQmxClearTask
        def clear(handle):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test cleanup timeout')
            return original(handle)
        self.ni.DAQmxClearTask = clear
        def run():
            try:
                self.owner.run('acquire_signal', self.owner.acquire_data)
            except BaseException as error:
                errors.append(error)
        thread = Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.owner.state, 'RELEASING')
            acquired = self.state.lock.acquire(timeout=1)
            self.assertTrue(acquired)
            if acquired:
                self.state.lock.release()
            with self.assertRaisesRegex(OwnershipError, 'releasing'):
                self.acquire()
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(self.owner.released())

    def test_lease_blocks_then_clean_handback_without_restart(self):
        handle = self.acquire()
        for name in ('acquire_signal', 'move_to', 'autofocus', 'acquire_position'):
            with self.assertRaises(OwnershipError):
                self.owner.run(name, self.owner.acquire_data)
        self.assertEqual(self.ni.calls, [])
        self.finish(handle)
        self.assertEqual(self.ni.calls, [])  # No auto-resume.
        self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertTrue(self.owner.released())

    def test_quarantined_localization_blocks_objective(self):
        self.finish(self.acquire(), clean=False)
        with self.assertRaisesRegex(OwnershipError, 'quarantined'):
            self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertEqual(self.ni.calls, [])

    def test_historical_ownerless_evidence_never_cleared(self):
        token = self.bridge.mark_legacy_daq_uncertain('objective_widget_creation_or_reopen')
        with self.assertRaises(OwnershipError):
            self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertFalse(self.bridge.legacy_daq_evidence.records[token]['released'])
        self.assertEqual(self.ni.calls, [])

    def test_unknown_widget_remains_blocker(self):
        self.window.pi_scanner_widget = SimpleNamespace()
        with self.assertRaisesRegex(OwnershipError, 'objective_daq_autofocus_ownership_unconfirmed'):
            self.acquire()

    def test_managed_released_widget_allowed_and_replacement_blocked(self):
        widget = SimpleNamespace()
        self.owner.widget = self.window.pi_scanner_widget = widget
        self.finish(self.acquire())
        self.window.pi_scanner_widget = SimpleNamespace()
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_worker_active_denies_objective_before_hardware(self):
        self.window.threadRun = FakeThread()
        with self.assertRaisesRegex(OwnershipError, 'legacy_activity'):
            self.owner.run('autofocus', self.owner.acquire_data)
        self.assertEqual(self.ni.calls, [])

    def test_objective_stage_subcalls_authorized_but_competing_calls_denied(self):
        errors = []
        def competing():
            try:
                self.window.stage.message('controller.stage.goto-position 9 9')
            except OwnershipError as error:
                errors.append(str(error))
        def move():
            self.window.stage.message('controller.stage.goto-position 1 2')
            thread = Thread(target=competing)
            thread.start()
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.owner.run('move_to', move)
        self.assertEqual(self.window.stage.position, (1., 2.))
        self.assertEqual(errors, ['managed_objective_active'])
        self.assertTrue(self.owner.released())

    def test_localization_thread_completion_required_for_handback(self):
        handle = self.acquire()
        self.finish(handle)
        self.window.h_only_runner = SimpleNamespace(busy=True)
        with self.assertRaisesRegex(OwnershipError, 'worker_not_finished'):
            self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertEqual(self.ni.calls, [])
        self.window.h_only_runner.busy = False
        self.owner.run('acquire_signal', self.owner.acquire_data)
        self.assertTrue(self.owner.released())

    def test_late_competing_activity_revokes_objective_execution(self):
        calls = []
        def action():
            self.controller.report_activity(Activity.SCAN, True)
            self.owner.hardware_call(lambda: calls.append('unsafe'))
        with self.assertRaisesRegex(OwnershipError, 'conflicting_activity'):
            self.owner.run('move_to', action)
        self.assertEqual(calls, [])
        self.assertEqual(self.owner.state, 'UNCERTAIN')

    def test_operation_records_are_generation_bound(self):
        self.owner.run('first', self.owner.acquire_data)
        first = self.owner.current
        self.owner.run('second', self.owner.acquire_data)
        self.assertNotEqual(first.token, self.owner.current.token)
        self.assertEqual(first.generation, 1)
        self.assertEqual(self.owner.current.generation, 2)
        self.assertTrue(first.released())
        with self.assertRaises(OwnershipError):
            self.bridge.confirm_legacy_daq_release(first.token)

    def test_admission_race_exactly_one_winner(self):
        for _ in range(12):
            self.setUp()
            barrier, done = Barrier(2), Event()
            results, handles = [], []
            def objective():
                barrier.wait()
                try:
                    self.owner.run('autofocus', lambda: (results.append('objective'), done.wait(3)))
                except OwnershipError:
                    results.append('objective_denied')
                    done.set()
            def localization():
                barrier.wait()
                try:
                    handles.append(self.acquire())
                    results.append('localization')
                except OwnershipError:
                    results.append('localization_denied')
                finally:
                    done.set()
            threads = [Thread(target=objective), Thread(target=localization)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(4)
                self.assertFalse(thread.is_alive())
            self.assertIn(sorted(results), [sorted(['objective', 'localization_denied']),
                                           sorted(['localization', 'objective_denied'])])
            if handles:
                self.finish(handles[0])


def piScanner_widget(*args, **kwargs):
    raise AssertionError('unmanaged widget constructor reached')


class ObjectiveFallbackSnake(FakeSnake):
    def scan(self):
        piScanner_widget()


class ObjectiveWorkerDenialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def worker(self, base=FakeSnake):
        window, _, _, bridge = environment()
        qtwindow = QObject()
        qtwindow.__dict__.update(window.__dict__)
        bridge.window = qtwindow
        thread = QThread()
        worker = snake_worker_factory(base, bridge, thread, 'fake')
        self.addCleanup(qtwindow.deleteLater)
        self.addCleanup(thread.deleteLater)
        self.addCleanup(worker.deleteLater)
        return worker, bridge

    def test_worker_fallback_factory_is_denied(self):
        worker, bridge = self.worker(ObjectiveFallbackSnake)
        with self.assertRaisesRegex(OwnershipError, 'creation_unsupported'):
            worker.scan()
        self.assertFalse(bridge.legacy_daq_evidence.ever_acquired)

    def test_worker_autofocus_and_unknown_widget_denied_before_scan(self):
        for parameters in (
                SimpleNamespace(pi_scanner=SimpleNamespace(autofocus_on_imaging=True)),
                SimpleNamespace(pi_scanner_widget=object())):
            with self.subTest(parameters=parameters):
                worker, _ = self.worker()
                worker.parameters = parameters
                before = len(_raw_tasks)
                with self.assertRaisesRegex(OwnershipError, 'unsupported_in_V1'):
                    worker.scan()
                self.assertEqual(len(_raw_tasks), before)


if __name__ == '__main__':
    unittest.main()
