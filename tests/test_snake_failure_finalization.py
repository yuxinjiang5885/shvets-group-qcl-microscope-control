"""Software-only failure finalization; devices and extracted workers are inert."""
import unittest
from types import SimpleNamespace
from time import monotonic, sleep
from PyQt6.QtCore import QObject, QThread, QTimer
from PyQt6.QtWidgets import QApplication
from test_snake_autofocus_service import (PI, Stage, SETTINGS, setup, scan_class,
    scan_parameters, WorkerStage, WorkerPI, WorkerLaser)
from ui.snake_autofocus_service import SnakeAutofocusService, AutofocusFailure
from ui.snake_workflow import SnakeWorkflow
from ui.snake_daq_lifecycle import SnakeDaqLifecycle, snake_worker_factory
from ui.localization_orchestration import OwnershipError, RunSettings
import numpy as np


class MismatchPI(PI):
    def __init__(self, final=True):
        super().__init__()
        self.final = final
    def qPOS(self, axis):
        count = len(self.calls)
        mismatch = count == 4 if self.final else count == 1
        return {1: self.position + (.25 if mismatch else 0)}


class DiagnosticsTests(unittest.TestCase):
    def test_phase_and_values_without_retry(self):
        for final in (False, True):
            pi=MismatchPI(final)
            service=SnakeAutofocusService(SETTINGS,Stage(),pi,lambda:np.ones((2,10)),
                                         lambda:None,lambda:True)
            with self.assertRaises(AutofocusFailure) as caught:service.run((30.,40.))
            error=caught.exception;d=error.diagnostics
            self.assertEqual(error.outcome,'PI_READBACK_FAILURE')
            self.assertEqual(d['phase'],'final_best' if final else 'sweep_point')
            self.assertEqual(d['target_um'],99.)
            self.assertEqual(d['actual_um'],99.25)
            self.assertEqual(d['delta_um'],.25)
            self.assertEqual(d['tolerance_um'],.1)
            self.assertGreater(d['position_read_count'],1)
            self.assertEqual(d['consecutive_in_tolerance_required'],2)
            self.assertEqual(d['on_target_poll_count'],1)
            self.assertEqual(d['timeout_s'],10.)
            self.assertGreaterEqual(d['elapsed_s'],0)
            self.assertTrue(service.stage_restored)
            self.assertEqual(len(pi.calls),4 if final else 1)

    def test_restore_failure_does_not_overwrite_pi_failure(self):
        stage=Stage();stage.fault='restore'
        service=SnakeAutofocusService(SETTINGS,stage,MismatchPI(),lambda:np.ones((2,10)),
                                     lambda:None,lambda:True)
        with self.assertRaises(AutofocusFailure) as caught:service.run((30.,40.))
        self.assertEqual(caught.exception.outcome,'PI_READBACK_FAILURE')
        self.assertTrue(service.cleanup_failures)


class TraceWriterTests(unittest.TestCase):
    def test_async_journal_records_and_flushes(self):
        import json
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from ui.snake_trace import SnakeTraceWriter
        with TemporaryDirectory() as directory:
            writer=SnakeTraceWriter(Path(directory)/'traces'/'snake.jsonl')
            for event in ('close_requested','shutdown_begin','close_accepted'):
                writer.record(dict(event=event,run_id='fake'))
            writer.finish();writer.thread.join(2)
            self.assertFalse(writer.thread.is_alive())
            self.assertIsNone(writer.error)
            rows=[json.loads(line) for line in writer.path.read_text().splitlines()]
            self.assertEqual([r['event'] for r in rows],['close_requested','shutdown_begin','close_accepted'])

    def test_disk_error_is_diagnostic_only(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from ui.snake_trace import SnakeTraceWriter
        with TemporaryDirectory() as directory:
            writer=SnakeTraceWriter(Path(directory))  # Cannot open a directory as a file.
            writer.thread.join(2)
            self.assertIsNotNone(writer.error)
            writer.record(dict(event='still_nonblocking'))

    def test_full_queue_drops_without_waiting(self):
        from queue import Queue
        from ui.snake_trace import SnakeTraceWriter
        writer=SnakeTraceWriter.__new__(SnakeTraceWriter)
        writer.queue=Queue(maxsize=1);writer.dropped=0
        writer.record(dict(event='one'));writer.record(dict(event='two'))
        self.assertEqual(writer.dropped,1)


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,_,self.bridge,self.owner,self.ni=setup()
        self.window.pi_scanner.pidevice=MismatchPI()
        self.parent=SnakeWorkflow(self.bridge,'test',SETTINGS)
        self.scope=SnakeDaqLifecycle(self.bridge,'test');self.scope.parent=self.parent
        self.parent.scope=self.scope;self.parent.bind()
        self.parameters=SimpleNamespace(stage=WorkerStage(self.window.stage,self.parent),
            laser=WorkerLaser(self.window.laser,self.parent))
        self.parameters.stage.goto(10.,20.)
        self.parameters.stage.set_position(0.,0.)

    def fail(self):
        with self.assertRaises(AutofocusFailure):
            self.parent.autofocus((20.,20.),self.parameters.stage,
                WorkerPI(self.window.pi_scanner.pidevice,self.parent))

    def finish(self):
        self.scope.finish_worker();self.parent.finish_worker(self.parameters)
        self.parent.finish_thread()

    def test_pi_failure_terminal_quarantine_with_independent_release(self):
        self.fail();self.finish()
        p=self.parent;s=p.snapshot()
        self.assertEqual(s['workflow_outcome'],'FAILED')
        self.assertFalse(s['active']);self.assertFalse(s['worker_active'])
        self.assertEqual(s['hardware_safety'],'QUARANTINED')
        self.assertEqual(s['primary_failure']['outcome'],'PI_READBACK_FAILURE')
        self.assertTrue(p.result.stage_restored);self.assertTrue(p.result.cleanup_verified)
        self.assertTrue(p.stage_verified);self.assertTrue(p.frame_restored)
        self.assertEqual(self.window.stage.position,(10.,20.))
        self.assertEqual(self.scope.tasks,[])
        self.assertTrue(self.scope.worker_done and self.scope.thread_done)
        self.assertEqual(self.scope.state,'RELEASE_CONFIRMED')
        self.assertTrue(self.bridge.legacy_daq_evidence.records[self.scope.token]['released'])
        self.assertFalse(self.bridge.legacy_daq_evidence.records[p.token]['released'])
        with self.assertRaises(OwnershipError):self.owner.run('manual',lambda:None)
        with self.assertRaises(OwnershipError):self.bridge.acquire(RunSettings(self.state.context,0,'test'))
        self.assertTrue(self.bridge.request_close())
        p.request_cancellation()
        self.assertFalse(p.cancellation.is_cancelled())
        self.assertTrue(p.close_requested);self.assertFalse(p.user_cancel_requested)
        self.assertEqual(p.primary_failure['outcome'],'PI_READBACK_FAILURE')

    def test_read_failure_can_release_after_verified_cleanup(self):
        self.ni.fail='read';self.fail();self.finish()
        self.assertEqual(self.parent.workflow_outcome,'FAILED')
        self.assertTrue(self.parent.released())
        self.assertEqual(self.parent.snapshot()['hardware_safety'],'VERIFIED_RELEASED')
        self.assertIsNone(self.bridge.snake_parent)
        self.owner.run('manual',lambda:None)
        self.assertTrue(self.bridge.request_close())

    def test_clear_failure_keeps_quarantine(self):
        self.ni.clear_fail=True;self.fail();self.finish()
        self.assertEqual(self.parent.primary_failure['outcome'],'PI_READBACK_FAILURE')
        self.assertTrue(self.parent.cleanup_failures)
        self.assertFalse(self.parent.result.cleanup_verified)
        self.assertFalse(self.parent.released())

    def test_frame_failure_retained_separately(self):
        self.fail()
        self.window.stage.set_position=lambda *a:(_ for _ in ()).throw(RuntimeError('frame failed'))
        self.finish()
        self.assertFalse(self.parent.frame_restored)
        self.assertIn('frame failed',' '.join(self.parent.cleanup_failures))
        self.assertEqual(self.parent.primary_failure['outcome'],'PI_READBACK_FAILURE')

    def test_laser_failure_does_not_skip_stage_evidence(self):
        self.fail()
        self.parameters.laser=SimpleNamespace(disable=lambda:(_ for _ in ()).throw(RuntimeError('laser unknown')))
        self.finish()
        self.assertTrue(self.parent.stage_verified and self.parent.frame_restored)
        self.assertFalse(self.parent.laser_verified)
        self.assertIn('laser unknown',self.parent.cleanup_failures)
        self.assertFalse(self.parent.released())

    def test_frame_readback_mismatch_keeps_quarantine(self):
        self.fail()
        self.window.stage.set_position=lambda *a:None
        self.finish()
        self.assertFalse(self.parent.frame_restored)
        self.assertFalse(self.parent.released())

    def test_native_uncertainty_prevents_frame_calls(self):
        self.fail();self.bridge.dispatcher.uncertain=True
        calls=[];self.window.stage.set_position=lambda *a:calls.append(a)
        self.finish()
        self.assertEqual(calls,[])
        self.assertFalse(self.parent.frame_restored)
        self.assertFalse(self.parent.stage_verified)
        self.assertTrue(self.parent.laser_verified)
        self.assertTrue(self.scope.released())

    def test_cleanup_cannot_authorize_motion_or_new_daq(self):
        self.fail();self.parent.phase='CLEANUP';self.parent.cleanup_authorized=True
        with self.assertRaises(OwnershipError):self.parameters.stage.goto(1,2)
        with self.assertRaises(OwnershipError):self.parent.check(cleanup=True)
        with self.assertRaises(OwnershipError):self.parent.phase_to('IMAGING')

    def test_running_close_requests_cancel_and_defers(self):
        self.assertFalse(self.bridge.request_close())
        self.assertTrue(self.parent.cancellation.is_cancelled())
        self.assertTrue(self.parent.close_requested)
        self.assertFalse(self.parent.user_cancel_requested)
        events=self.parent.snapshot()['breadcrumbs']
        self.assertIn('cancel_requested',[e['event'] for e in events])
        self.assertEqual(events[-1]['details']['reason'],'snake_worker_or_thread_running')

    def test_trace_storage_failure_cannot_change_result(self):
        events=self.parent._trace_events
        class Broken:
            def append(self,event):raise RuntimeError('trace unavailable')
        self.parent._trace_events=Broken()
        self.fail();self.finish()
        self.parent._trace_events=events
        self.assertEqual(self.parent.primary_failure['outcome'],'PI_READBACK_FAILURE')
        self.assertTrue(self.parent.stage_verified and self.parent.frame_restored)
        self.assertTrue(self.owner.released())
        self.assertFalse(self.parent.released())

    def test_trace_is_bounded_and_non_authoritative(self):
        for i in range(600):self.parent.trace('test',index=i)
        events=self.parent.snapshot()['breadcrumbs']
        self.assertEqual(len(events),512)
        self.assertEqual(events[-1]['details']['index'],599)
        self.assertEqual(self.ni.calls,[])
        self.assertFalse(self.parent.completed)


class ThreadFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_idle_uncertain_owner_retirement_has_no_native_cleanup(self):
        from ui.persistent_prior_owner import PersistentPriorOwner
        from test_persistent_prior_owner import NativeFake
        log=[]
        owner=PersistentPriorOwner(SimpleNamespace(),factory=lambda model:NativeFake(log,model),timeout_s=.5)
        owner.start();owner.dispatcher.uncertain=True
        self.assertTrue(owner.retire_quarantined())
        self.assertFalse(owner.running)
        self.assertTrue(owner.uncertain)
        self.assertFalse(owner.closed)  # Thread exit does not attest native disconnect.
        self.assertNotIn('disconnect',[name for name,_ in log])
        self.assertNotIn('close_session',[name for name,_ in log])

    def test_retirement_never_terminates_inflight_native_call(self):
        from threading import Event, Thread
        from ui.persistent_prior_owner import PersistentPriorOwner
        from test_persistent_prior_owner import NativeFake
        hold=(Event(),Event());log=[];errors=[]
        owner=PersistentPriorOwner(SimpleNamespace(),factory=lambda model:NativeFake(log,model,hold),timeout_s=.1)
        proxy=owner.start()
        def call():
            try:proxy.message('controller.stage.busy.get')
            except Exception as error:errors.append(error)
        caller=Thread(target=call);caller.start()
        try:
            self.assertTrue(hold[0].wait(1))
            caller.join(1);self.assertTrue(errors)
            self.assertFalse(owner.retire_quarantined())
            self.assertTrue(owner.running)
        finally:
            hold[1].set();caller.join(2)
            self.assertTrue(owner.retire_quarantined())
        self.assertNotIn('disconnect',[name for name,_ in log])

    def test_actual_qthread_failure_finalization_and_heartbeat(self):
        window,_,_,bridge,owner,ni=setup()
        qtwindow=QObject();qtwindow.__dict__.update(window.__dict__);bridge.window=qtwindow
        qtwindow.pi_scanner.pidevice=MismatchPI()
        qtwindow.auto_relocation=SimpleNamespace(failures_label=SimpleNamespace(setText=lambda text:None))
        parent=SnakeWorkflow(bridge,'snakeScan',SETTINGS)
        parameters,outputs=scan_parameters(qtwindow,patterns=1,wavelengths=(1658,))
        thread=QThread();qtwindow.threadRun=thread
        worker=snake_worker_factory(scan_class('snakeScan',outputs),bridge,thread,'snakeScan',parent=parent)
        worker.parameters=parameters
        ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1)
        worker.moveToThread(thread);thread.started.connect(worker.run);thread.start()
        deadline=monotonic()+5
        while not parent.completed and monotonic()<deadline:
            self.app.processEvents();sleep(.002)
        self.assertTrue(thread.wait(2000));self.assertTrue(parent.completed)
        self.assertEqual(parent.workflow_outcome,'FAILED');self.assertFalse(parent.worker_active)
        self.assertTrue(parent.frame_restored and parent.stage_verified)
        self.assertTrue(owner.released());self.assertEqual(ni.calls.count('clear'),1)
        self.assertEqual(outputs,[]);self.assertEqual(parent.scope.tasks,[])
        self.assertTrue(ticks)
        timer.stop();thread.deleteLater();qtwindow.deleteLater();self.app.processEvents()
