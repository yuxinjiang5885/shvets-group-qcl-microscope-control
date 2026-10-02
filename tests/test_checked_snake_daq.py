"""Execute reviewed legacy method code against inert native functions only."""
import ast
import ctypes
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from ui.checked_snake_daq import CheckedSnakeDAQ, SnakeDaqError, reviewed_factory


RAW_TASKS = []


def make_factory(fail=None, status=-1, *, create_handle=True, short_read=False):
    path = Path(__file__).resolve().parents[1] / 'instruments' / 'ni_daq.py'
    tree = ast.parse(path.read_bytes(), filename=str(path))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'MultiChannelAnalogInput')
    calls = []
    def native(name):
        def call(*args):
            calls.append(name)
            if name == 'create':
                if create_handle: args[1]._obj.value = len(RAW_TASKS) + 1
                RAW_TASKS.append(SimpleNamespace(calls=calls))
            failures = fail if isinstance(fail, dict) else {fail: status}
            if name in failures:
                outcome = failures[name]
                if isinstance(outcome, Exception): raise outcome
                return outcome
            if name == 'read': args[6]._obj.value = args[1] - int(short_read)
            return 0
        return call
    ns = dict(np=np, TaskHandle=ctypes.c_void_p, byref=ctypes.byref,
              int32=ctypes.c_int32, DAQMX_TIMEOUT=20)
    for name, op in {'DAQmxCreateTask':'create', 'DAQmxCreateAIVoltageChan':'channel',
                     'DAQmxCfgSampClkTiming':'configure', 'DAQmxCfgDigEdgeStartTrig':'trigger',
                     'DAQmxSetTrigAttribute':'attribute', 'DAQmxStartTask':'start',
                     'DAQmxReadAnalogF64':'read', 'DAQmxStopTask':'stop',
                     'DAQmxClearTask':'clear'}.items(): ns[name] = native(op)
    for name in ('DAQmx_Val_Cfg_Default','DAQmx_Val_Volts','DAQmx_Val_Rising',
                 'DAQmx_Val_FiniteSamps','DAQmx_StartTrig_Retriggerable',
                 'DAQmx_Val_GroupByChannel'): ns[name] = 1
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec', dont_inherit=True), ns)
    factory = ns['MultiChannelAnalogInput']
    factory.calls = calls
    return factory


class CheckedTests(unittest.TestCase):
    def task(self, fail=None, status=-1):
        factory = reviewed_factory(make_factory(fail, status))
        return CheckedSnakeDAQ(factory([b'Dev1/ai0', b'Dev1/ai1']))

    def configured(self, fail=None, status=-1):
        task = self.task(fail, status)
        task.configure_triggered(b'/Dev1/PFI0', 2, 100000)
        return task

    def test_success(self):
        task = self.configured(); task.start_task()
        self.assertEqual(task.read_line(4).shape, (2,4))
        task.stop_task(); task.clear_task()
        for name in ('configure_verified','start_verified','read_verified','stop_verified','clear_verified'):
            self.assertTrue(getattr(task,name))
        self.assertFalse(task.uncertain)

    def test_clear_status_and_exception_failures(self):
        for outcome in (-1, 1, None, True, '0', RuntimeError('native failure')):
            with self.subTest(outcome=outcome):
                task=self.configured('clear',outcome)
                with self.assertRaises(SnakeDaqError): task.clear_task()
                self.assertFalse(task.clear_verified); self.assertTrue(task.uncertain)
                with self.assertRaises(SnakeDaqError): task.clear_task()
                self.assertEqual(task.raw.calls.count('clear'),1)

    def test_operation_failure_can_still_release(self):
        for failure in ('create','channel','configure','trigger','attribute','start','read','stop'):
            with self.subTest(failure=failure):
                task=self.task(failure)
                with self.assertRaises(SnakeDaqError):
                    task.configure_triggered(b'/Dev1/PFI0',2,100000)
                    task.start_task();task.read_line(2);task.stop_task()
                task.clear_task()
                self.assertTrue(task.clear_verified);self.assertFalse(task.uncertain)
                self.assertTrue(task.errors)

    def test_before_create_failure(self):
        task=self.task()
        with self.assertRaises(SnakeDaqError): task.start_task()
        self.assertFalse(task.native_creation_attempted)

    def test_identity_and_generation(self):
        first=self.configured();second=self.configured()
        self.assertNotEqual(first.generation,second.generation)
        first.raw.taskHandle.value=second.task_identity
        with self.assertRaises(SnakeDaqError):first.clear_task()
        self.assertEqual(first.raw.calls.count('clear'),0)
        second.clear_task();self.assertTrue(second.clear_verified)

    def test_no_reconfiguration_or_double_clear(self):
        task=self.configured()
        with self.assertRaises(SnakeDaqError):task.configure_triggered(b'x',2,100000)
        task.clear_task()
        with self.assertRaises(SnakeDaqError):task.clear_task()
        self.assertEqual(task.raw.calls.count('clear'),1)

    def test_unknown_factory_rejected_before_construction(self):
        with self.assertRaises(SnakeDaqError): reviewed_factory(lambda: None)

    def test_create_without_known_handle_is_uncertain(self):
        factory=make_factory('create', create_handle=False)
        task=CheckedSnakeDAQ(factory([b'Dev1/ai0',b'Dev1/ai1']))
        with self.assertRaises(SnakeDaqError):task.configure_triggered(b'x',2,100000)
        self.assertTrue(task.native_creation_attempted)
        self.assertFalse(task.native_task_created)
        with self.assertRaises(SnakeDaqError):task.clear_task()
        self.assertEqual(factory.calls,['create'])
        self.assertTrue(task.uncertain)

    def test_short_read_fails_and_cleans_up(self):
        factory=make_factory(short_read=True)
        task=CheckedSnakeDAQ(factory([b'Dev1/ai0',b'Dev1/ai1']))
        task.configure_triggered(b'x',2,100000);task.start_task()
        with self.assertRaisesRegex(SnakeDaqError,'short read'):task.read_line(2)
        task.stop_task();task.clear_task()
        self.assertFalse(task.read_verified);self.assertTrue(task.clear_verified)

    def test_foreign_thread_cannot_clear(self):
        from threading import Thread
        task=self.configured();errors=[]
        def other():
            try:task.clear_task()
            except SnakeDaqError as error:errors.append(error)
        thread=Thread(target=other);thread.start();thread.join()
        self.assertEqual(len(errors),1);self.assertFalse(task.clear_attempted)
        task.clear_task()


class ReleaseIntegrationTests(unittest.TestCase):
    def test_reset_rejected_before_factory_call(self):
        scope,_=self.scope();factory=make_factory()
        for args,kwargs in ((([b'Dev1/ai0'],None,True),{}),
                            (([b'Dev1/ai0'],),{'reset':True})):
            with self.assertRaises(ValueError):scope.task_factory(factory,*args,**kwargs)
        self.assertEqual(factory.calls,[])

    def scope(self):
        from test_operational_localization_bridge import environment
        from ui.snake_daq_lifecycle import SnakeDaqLifecycle
        _,_,_,bridge=environment()
        return SnakeDaqLifecycle(bridge,'checked_test'),bridge

    def test_fault_matrix_and_exact_clear_regression(self):
        for fail in ({'start':-1},{'start':-1,'clear':-1}, {'read':-1},
                     {'stop':-1},{'stop':-1,'clear':-1}, {'clear':-1},
                     {'clear':None},{'clear':RuntimeError('native exception')},
                     {'channel':-1}):
            with self.subTest(fail=fail):
                scope,bridge=self.scope();factory=make_factory(fail)
                task=scope.task_factory(factory,[b'Dev1/ai0',b'Dev1/ai1'])
                try:
                    task.configure_triggered(b'x',2,100000);task.start_task()
                    task.read_line(2);task.stop_task();task.clear_task()
                except SnakeDaqError:pass
                scope.finish_worker();scope.attest_thread_done()
                bad_clear='clear' in fail
                self.assertEqual(task.cleared,not bad_clear)
                self.assertEqual(task.raw.clear_verified,not bad_clear)
                self.assertEqual(scope.uncertain,bad_clear)
                self.assertEqual(bridge.legacy_daq_cleanup_unverified,bad_clear)
                self.assertIsNotNone(scope.error)
                self.assertEqual(factory.calls.count('clear'),1)
                self.assertLessEqual(factory.calls.count('stop'),1)

    def test_all_tasks_must_release_and_thread_is_not_enough(self):
        scope,bridge=self.scope()
        for failure in (None,'clear'):
            task=scope.task_factory(make_factory(failure),[b'Dev1/ai0',b'Dev1/ai1'])
            task.configure_triggered(b'x',2,100000)
        scope.attest_thread_done()
        self.assertTrue(bridge.legacy_daq_cleanup_unverified)
        scope.finish_worker();scope.attest_thread_done()
        self.assertTrue(bridge.legacy_daq_cleanup_unverified)
        self.assertTrue(scope.tasks[0].cleared);self.assertFalse(scope.tasks[1].cleared)

    def test_stale_attestation_does_not_release_new_scope(self):
        from ui.snake_daq_lifecycle import SnakeDaqLifecycle
        from ui.localization_orchestration import OwnershipError
        old,bridge=self.scope();old.finish_worker();old.attest_thread_done()
        new=SnakeDaqLifecycle(bridge,'new')
        with self.assertRaises(OwnershipError):bridge.confirm_legacy_daq_release(old.token)
        self.assertFalse(bridge.legacy_daq_evidence.records[new.token]['released'])
