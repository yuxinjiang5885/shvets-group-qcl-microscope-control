"""Numerical fakes and Qt queued calls only; no operational hardware imports."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from threading import Thread, Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
from pathlib import Path
from hashlib import sha256
import unittest

from test_operational_localization_bridge import environment
from test_reflection_scan import FakeClock
from experiment.scan_1d import StageBounds
from ui.localization_orchestration import RunSettings, CleanupOutcome, OwnershipStatus, OwnershipError
from ui.stage_command_dispatcher import (StageCommandDispatcher, DispatchRejected,
    NativeCallUncertain, qt_main_thread_target)


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.window, self.state, self.controller, self.bridge = environment()
        self.handle = self.bridge.acquire(RunSettings(self.state.context,
            self.state.context_generation, 'fixture'))
        self.api = self.bridge.stage_interface(self.handle,
            bounds=StageBounds(900,1100,1900,2100,'fixture-frame'), polling_s=.01, clock=FakeClock())

    def test_borrowed_identity_no_construction_or_connect(self):
        self.assertIs(self.window.stage, self.bridge.stage)
        self.assertEqual(self.window.stage.calls, [])

    def test_queued_target_is_not_vendor_thread_safety_evidence(self):
        self.bridge._submit = lambda call: None
        self.assertIn('Prior_session_execution_contract_unverified', self.bridge.blockers())

    def test_interface_does_not_expose_raw_driver(self):
        self.assertFalse(hasattr(self.api, 'stage'))
        source = Path('ui/localization_pipeline.py').read_text()
        self.assertNotIn('bridge.stage,', source)
        self.assertNotIn('PriorStageAdapter(', source)

    def test_readback(self):
        self.assertEqual(self.api.get_position(timeout_s=1), (1000.,2000.))

    def test_move(self):
        self.api.move_to(1001,2000,timeout_s=1)
        self.assertEqual(self.api.get_position(timeout_s=1), (1001.,2000.))

    def test_busy_to_idle(self):
        original = self.window.stage.message
        values = iter(['1','0'])
        self.window.stage.message = lambda cmd: (0,next(values)) if cmd.endswith('busy.get') else original(cmd)
        self.api.wait_until_idle(timeout_s=1)

    def test_smooth_stop(self):
        self.api.stop_smoothly(timeout_s=1)
        self.assertIn('controller.stop.smoothly', self.window.stage.calls)

    def test_stop_failure_quarantines(self):
        self.window.stage.fail = lambda cmd: 'stop' in cmd
        with self.assertRaises(Exception):
            self.api.stop(timeout_s=1)
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)

    def test_unauthorized_handle(self):
        with self.assertRaises(OwnershipError):
            self.bridge.execute_stage(SimpleNamespace(run_id='intruder'), lambda: 42, 1)

    def test_stale_run(self):
        self.controller.finish(self.handle, succeeded=False, cleanup=CleanupOutcome(True,True))
        with self.assertRaises(OwnershipError):
            self.api.get_position(timeout_s=1)

    def test_sdk_exception_propagates(self):
        self.window.stage.fail = lambda cmd: True
        with self.assertRaisesRegex(Exception, 'fake_controller_error'):
            self.api.get_position(timeout_s=1)

    def test_release_no_disconnect(self):
        self.controller.finish(self.handle, succeeded=False, cleanup=CleanupOutcome(True,True))
        self.assertTrue(self.bridge.dispatcher.shutdown())
        self.assertEqual(self.window.stage.calls, [])

    def queued(self):
        self.queue = []
        self.bridge.dispatcher._submit = self.queue.append

    def test_queued_timeout_skips_native_call(self):
        self.queued()
        with self.assertRaises(NativeCallUncertain):
            self.api.get_position(timeout_s=.01)
        self.queue.pop()()
        self.assertEqual(self.window.stage.calls, [])
        self.assertTrue(self.bridge.dispatcher.last_ticket.done.is_set())
        self.assertTrue(self.bridge.dispatcher.uncertain)

    def delayed(self, timeout=.03):
        self.entered, self.release = Event(), Event()
        self.native = []
        def submit(call):
            t = Thread(target=call)
            self.native.append(t)
            t.start()
        self.bridge.dispatcher._submit = submit
        def call():
            self.entered.set()
            self.release.wait(2)
            return 123
        def cleanup():
            self.release.set()
            for t in self.native:
                t.join(3)
        self.addCleanup(cleanup)
        with self.assertRaises(NativeCallUncertain):
            self.bridge.execute_stage(self.handle, call, timeout)

    def test_timeout_not_native_cancellation(self):
        self.delayed()
        self.assertTrue(self.entered.is_set())
        self.assertTrue(self.bridge.dispatcher.unresolved)
        self.assertFalse(self.bridge.dispatcher.last_ticket.done.is_set())
        self.assertTrue(self.bridge.dispatcher.uncertain)

    def test_timeout_quarantines_invalidates_cancels(self):
        self.delayed()
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
        self.assertTrue(self.handle.cancellation.is_cancelled())

    def test_timeout_blocks_second_move_and_stop(self):
        self.delayed()
        for action in (lambda: self.api.move_to(1001,2000,timeout_s=1),
                       lambda: self.api.stop(timeout_s=1)):
            with self.assertRaises(OwnershipError):
                action()
        self.assertEqual(self.window.stage.calls, [])

    def test_late_completion_does_not_restore_ownership(self):
        self.delayed()
        self.release.set()
        self.native[0].join(1)
        self.assertEqual(self.bridge.dispatcher.last_ticket.result, 123)
        self.assertFalse(self.bridge.dispatcher.unresolved)
        self.assertTrue(self.bridge.dispatcher.uncertain)
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)

    def test_shutdown_unresolved_not_completion(self):
        self.delayed()
        self.assertFalse(self.bridge.dispatcher.shutdown())
        self.assertTrue(self.bridge.dispatcher.unresolved)

    def test_late_completion_still_blocks_legacy_and_close(self):
        self.delayed()
        self.release.set(); self.native[0].join(1)
        self.assertFalse(self.bridge.request_close())
        with self.assertRaises(OwnershipError):
            self.window.stage.message('controller.stage.busy.get')

    def test_explicit_recovery_cannot_bypass_dispatcher_latch(self):
        from ui.localization_orchestration import RecoveryConfirmation
        self.delayed()
        self.release.set(); self.native[0].join(1)
        self.controller.finish(self.handle, succeeded=False, cleanup=CleanupOutcome(True,True))
        # Even externally acknowledged recovery does not reset this dispatcher.
        self.controller.ownership.acknowledge_recovery(RecoveryConfirmation(
            self.handle.run_id, True, True, True, True, 'inert externally verified recovery'))
        with self.assertRaises(OwnershipError):
            self.window.stage.message('controller.stage.busy.get')
        self.assertFalse(self.bridge.request_close())

    def test_no_hardware_imports(self):
        import subprocess, sys
        code = '''
import sys
class Deny:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('instruments', 'PyDAQmx', 'pipython') or fullname == 'qcl_scanning_imaging_ui':
            raise RuntimeError('forbidden hardware import: '+fullname)
sys.meta_path.insert(0,Deny())
import ui.stage_command_dispatcher
import ui.operational_localization_bridge
import ui.localization_pipeline
'''
        result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_closed_dispatcher_rejects(self):
        self.assertTrue(self.bridge.dispatcher.shutdown())
        with self.assertRaises(DispatchRejected):
            self.api.get_position(timeout_s=1)

    def test_second_command_rejected_while_first_queued(self):
        self.queued()
        result = []
        t = Thread(target=lambda: result.append(self.api.get_position(timeout_s=1)))
        t.start()
        deadline=monotonic()+1
        while not self.queue and monotonic()<deadline:
            sleep(.001)
        with self.assertRaises(DispatchRejected):
            self.api.is_busy(timeout_s=1)
        self.queue.pop()()
        t.join(1)
        self.assertEqual(result, [(1000.,2000.)])

    def test_successive_resolved_commands(self):
        self.api.get_position(timeout_s=1)
        self.api.is_busy(timeout_s=1)
        self.assertFalse(self.bridge.dispatcher.unresolved)

    def test_stale_queued_command_rechecked(self):
        queue=[]
        h=SimpleNamespace(run_id='old')
        valid=[True]
        errors=[]
        def auth(*args):
            if not valid[0]: raise OwnershipError('stale')
        d=StageCommandDispatcher(queue.append,auth,lambda *a: None)
        def caller():
            try: d.execute(h,lambda: self.fail('must not execute'),1)
            except Exception as e: errors.append(e)
        t=Thread(target=caller); t.start()
        deadline=monotonic()+1
        while not queue and monotonic()<deadline: sleep(.001)
        valid[0]=False; queue.pop()(); t.join(1)
        self.assertIsInstance(errors[0],OwnershipError)

    def test_legacy_raw_message_blocked(self):
        with self.assertRaises(OwnershipError):
            self.window.stage.message('controller.stage.position.get')

    def test_stable_ui_hash(self):
        self.assertEqual(sha256(Path('qcl_scanning_imaging_ui.py').read_bytes()).hexdigest(),
            'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab')

    def test_invalid_timeout(self):
        for value in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                self.bridge.execute_stage(self.handle,lambda: None,value)


class QtDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtCore import QCoreApplication
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_queued_stage_executes_main_thread_with_result_and_error(self):
        target=qt_main_thread_target()
        main=get_ident(); observed=[]; results=[]; errors=[]
        dispatcher=StageCommandDispatcher(target.submit,lambda *a: None,lambda *a: None)
        def call():
            observed.append(get_ident()); return 42
        def worker():
            results.append(dispatcher.execute(SimpleNamespace(run_id='test'),call,1))
            try:
                dispatcher.execute(SimpleNamespace(run_id='test'),lambda: 1/0,1)
            except Exception as e: errors.append(e)
        t=Thread(target=worker); t.start()
        deadline=monotonic()+2
        while t.is_alive() and monotonic()<deadline:
            self.app.processEvents(); sleep(.001)
        t.join(.1)
        self.assertFalse(t.is_alive())
        self.assertNotEqual(t.ident,main)
        self.assertEqual(observed,[main]); self.assertEqual(results,[42])
        self.assertIsInstance(errors[0],ZeroDivisionError)

    def test_qt_queue_timeout_no_late_execution(self):
        target=qt_main_thread_target(); errors=[]; calls=[]; quarantine=[]
        d=StageCommandDispatcher(target.submit,lambda *a: None,lambda *a: quarantine.append(a))
        def worker():
            try: d.execute(SimpleNamespace(run_id='test'),lambda: calls.append(1),.01)
            except Exception as e: errors.append(e)
        t=Thread(target=worker); t.start(); t.join(1)
        self.app.processEvents()
        self.assertIsInstance(errors[0],NativeCallUncertain)
        self.assertEqual(calls,[]); self.assertTrue(quarantine)

    def test_gui_thread_blocking_dispatch_rejected(self):
        target=qt_main_thread_target()
        with self.assertRaises(DispatchRejected): target.submit(lambda: None)

    def test_actual_fake_prior_method_on_main_thread(self):
        window,state,controller,bridge=environment()
        target=qt_main_thread_target()
        bridge.dispatcher._submit=target.submit
        handle=bridge.acquire(RunSettings(state.context,state.context_generation,'fixture'))
        api=bridge.stage_interface(handle,bounds=StageBounds(900,1100,1900,2100,'fixture-frame'),
            polling_s=.01,clock=FakeClock())
        original=window.stage.message
        threads=[]; results=[]
        def message(command):
            threads.append(get_ident()); return original(command)
        window.stage.message=message
        t=Thread(target=lambda: results.append(api.get_position(timeout_s=1)))
        t.start(); deadline=monotonic()+2
        while t.is_alive() and monotonic()<deadline:
            self.app.processEvents(); sleep(.001)
        t.join(.1)
        self.assertEqual(results,[(1000.,2000.)])
        self.assertEqual(threads,[get_ident()])
        self.assertNotEqual(t.ident,get_ident())
