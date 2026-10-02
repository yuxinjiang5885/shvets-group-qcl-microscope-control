"""No vendor imports: task operations and Snake worker body are inert fakes."""
import unittest
from types import SimpleNamespace
from time import monotonic,sleep
from unittest.mock import MagicMock
from PyQt6.QtCore import QObject,QThread,pyqtSignal
from PyQt6.QtWidgets import QApplication
from test_operational_localization_bridge import environment
from ui.snake_daq_lifecycle import SnakeDaqLifecycle,snake_worker_factory
from ui.hardware_ownership_diagnostics import hardware_ownership_snapshot


from test_checked_snake_daq import make_factory, RAW_TASKS
from ui.checked_snake_daq import SnakeDaqError

NI = make_factory


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=environment()
        self.window.localization_bridge=self.bridge;self.window.translation_launch_enabled=True

    def scope(self):return SnakeDaqLifecycle(self.bridge,'run_snake_scan')

    def task(self,scope,fail=None):
        raw=NI(fail);task=scope.task_factory(raw, [b'Dev1/ai0', b'Dev1/ai1'])
        task.configure_triggered(b'/Dev1/PFI0',2,100000);task.start_task()
        return task,raw

    def test_twenty_scans_allow_localization_after_each_cleanup(self):
        for _ in range(20):
            scope=self.scope();task,raw=self.task(scope)
            self.assertTrue(hardware_ownership_snapshot(self.window)['production_ownership_blocked'])
            task.read_line(2);task.stop_task();task.clear_task()
            scope.finish_worker()
            self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)
            scope.attest_thread_done()
            report=hardware_ownership_snapshot(self.window)
            self.assertEqual(report['pending_acquisition_sources'],[])
            self.assertEqual(report['active_legacy_sources'],[])
            self.assertFalse(report['production_ownership_blocked'])
            self.assertFalse(report['legacy_daq_cleanup_unverified'])
            self.assertEqual(report['last_release_attestation']['lifecycle']['state'],'RELEASE_CONFIRMED')
            self.assertEqual(raw.calls.count('clear'),1)

    def test_worker_created_no_task_is_released(self):
        scope=self.scope();scope.finish_worker();scope.attest_thread_done()
        self.assertFalse(self.bridge.legacy_daq_cleanup_unverified)
        self.assertFalse(self.bridge.legacy_daq_evidence.ever_acquired)

    def test_wrapper_created_not_configured_no_native_cleanup_needed(self):
        scope=self.scope();raw=NI();scope.task_factory(raw, [b'Dev1/ai0', b'Dev1/ai1'])
        scope.finish_worker();scope.attest_thread_done()
        self.assertEqual(raw.calls,[]);self.assertTrue(scope.released())

    def test_cancel_or_python_exception_unwind_verifies_cleanup(self):
        for outcome in ('cancelled','worker_python_exception'):
            scope=self.scope();_,raw=self.task(scope);scope.error=outcome
            scope.finish_worker();scope.attest_thread_done()
            self.assertEqual(raw.calls[-2:],['stop','clear'])
            self.assertFalse(self.bridge.legacy_daq_cleanup_unverified)

    def test_active_scope_cannot_attest(self):
        scope=self.scope();self.task(scope)
        scope.attest_thread_done()  # not enough without worker/cleanup
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)

    def test_native_failures_distinguish_release_from_operation_failure(self):
        for failure in ('configure','start','read','stop','clear'):
            with self.subTest(failure=failure):
                scope=self.scope();raw=NI(failure);task=scope.task_factory(raw, [b'Dev1/ai0', b'Dev1/ai1'])
                try:
                    task.configure_triggered(b'/Dev1/PFI0',2,100000);task.start_task();task.read_line(2);task.stop_task();task.clear_task()
                except SnakeDaqError:pass
                scope.finish_worker();scope.attest_thread_done()
                self.assertEqual(self.bridge.legacy_daq_cleanup_unverified, failure=='clear')
                self.assertEqual(scope.state,'RELEASE_UNCERTAIN' if failure=='clear' else 'RELEASE_CONFIRMED')
                self.assertIsNotNone(scope.error)

    def test_one_release_cannot_clear_other_uncertain_source(self):
        self.bridge.mark_legacy_daq_uncertain('objective_unknown')
        scope=self.scope();self.task(scope);scope.finish_worker();scope.attest_thread_done()
        report=hardware_ownership_snapshot(self.window)
        self.assertEqual(report['pending_acquisition_sources'],['objective_unknown'])

    def test_history_bounded_after_many_scans(self):
        for _ in range(45):
            scope=self.scope();scope.finish_worker();scope.attest_thread_done()
        self.assertEqual(len(self.bridge.legacy_daq_evidence.records),32)

    def test_DAQ_does_not_change_registration_generation(self):
        before=self.state.context_generation
        scope=self.scope();self.task(scope);scope.finish_worker();scope.attest_thread_done()
        self.assertEqual(self.state.context_generation,before)


_raw_tasks=RAW_TASKS
MultiAI=make_factory()

class FakeSnake(QObject):
    finished=pyqtSignal()
    status_bar_msg=pyqtSignal(str)
    outData=pyqtSignal(object)
    outParams=pyqtSignal(object)
    def run(self):self.scan();self.finished.emit()
    def scan(self):
        task=MultiAI(['fakeX','fakeY'])
        task.configure_triggered(b'/Dev1/PFI0',2,100000);task.start_task();task.read_line(2)
        task.stop_task();task.clear_task()


class FailedSnake(FakeSnake):
    def scan(self):
        task=MultiAI(['fakeX','fakeY']);task.configure_triggered(b'/Dev1/PFI0',2,100000);task.start_task()
        raise ValueError('python processing failure')


class WorkerIntegrationTests(unittest.TestCase):
    def test_exception_cleanup_without_legacy_success_emission(self):
        app=QApplication.instance() or QApplication([])
        window,_,_,bridge=environment()
        qtwindow=QObject();qtwindow.__dict__.update(window.__dict__);bridge.window=qtwindow
        qtwindow.auto_relocation=SimpleNamespace(failures_label=MagicMock())
        thread=QThread();qtwindow.threadRun=thread
        worker=snake_worker_factory(FailedSnake,bridge,thread,'run_snake_scan')
        scope=worker._snake_daq_scope;success=[]
        worker.finished.connect(lambda:success.append(True))
        worker.moveToThread(thread);thread.started.connect(worker.run);thread.start()
        deadline=monotonic()+5
        while scope.state!='RELEASE_CONFIRMED' and monotonic()<deadline:
            app.processEvents();sleep(.001)
        self.assertTrue(thread.wait(2000))
        self.assertEqual(scope.state,'RELEASE_CONFIRMED',scope.error)
        self.assertEqual(success,[])
        self.assertEqual(_raw_tasks[-1].calls[-2:],['stop','clear'])
        thread.deleteLater();qtwindow.deleteLater();app.processEvents()

    def test_actual_stable_callback_private_globals_injection(self):
        from test_legacy_daq_attestation import actual_callback
        from ui.legacy_daq_tracking import invoke_acquisition
        app=QApplication.instance() or QApplication([])
        window,_,_,bridge=environment()
        qtwindow=QObject();qtwindow.__dict__.update(window.__dict__);bridge.window=qtwindow
        qtwindow.auto_relocation=SimpleNamespace(failures_label=MagicMock())
        qtwindow.btn={name:[MagicMock()] for name in ('Arm','Emission')}
        for widgets in qtwindow.btn.values():widgets[0].isChecked.return_value=True
        qtwindow.tabSnakeButtons={'Start':[MagicMock()]}
        qtwindow.stageMotionWindow.disable_stage_inputs=lambda:True
        qtwindow.pi_scanner=object();qtwindow.laser=object();qtwindow.wlUnits='invcm'
        from test_snake_autofocus_service import install_laser
        install_laser(bridge,qtwindow)
        qtwindow.stage.busy=lambda:'0'
        qtwindow.stage.get_position=lambda:(0.,0.)
        qtwindow.snakeBrowser=SimpleNamespace(scans=[])
        qtwindow.statusbar=MagicMock()
        for name in ('lock_controls','update_scanning_imaging_plot_patterns','update_scan_progress_from_snakeScan',
                     'plot_snakescans','update_scanning_imaging_parameters','grab'):
            setattr(qtwindow,name,MagicMock())
        callback=actual_callback('run_snake_scan',qtwindow,dict(__builtins__=__builtins__,QThread=QThread,snakeScan=FakeSnake,
                                                              snakeScanParameters=SimpleNamespace))
        invoke_acquisition(callback,bridge.mark_legacy_daq_uncertain,snake_bridge=bridge)
        scope=qtwindow.worker._snake_daq_scope
        deadline=monotonic()+5
        while scope.state!='RELEASE_CONFIRMED' and monotonic()<deadline:
            app.processEvents();sleep(.001)
        self.assertEqual(scope.state,'RELEASE_CONFIRMED',scope.error)
        self.assertEqual(len(bridge.legacy_daq_evidence.records),2)
        self.assertFalse(bridge.legacy_daq_cleanup_unverified)
        qtwindow.deleteLater();app.processEvents()

    def test_injected_worker_and_thread_completion(self):
        app=QApplication.instance() or QApplication([])
        window,_,_,bridge=environment()
        qtwindow=QObject();qtwindow.__dict__.update(window.__dict__);bridge.window=qtwindow
        qtwindow.auto_relocation=SimpleNamespace(failures_label=SimpleNamespace(setText=lambda _:None))
        thread=QThread();qtwindow.threadRun=thread
        worker=snake_worker_factory(FakeSnake,bridge,thread,'run_snake_scan')
        scope=worker._snake_daq_scope
        worker.moveToThread(thread);thread.started.connect(worker.run)
        worker.finished.connect(thread.quit);worker.finished.connect(worker.deleteLater)
        thread.start()
        deadline=monotonic()+5
        while scope.state!='RELEASE_CONFIRMED' and monotonic()<deadline:
            app.processEvents();sleep(.001)
        self.assertTrue(thread.wait(2000))
        self.assertEqual(scope.state,'RELEASE_CONFIRMED',scope.error)
        self.assertFalse(bridge.legacy_daq_cleanup_unverified)
        self.assertEqual(_raw_tasks[-1].calls[-5:],['attribute','start','read','stop','clear'])
        self.assertIs(FakeSnake.scan.__globals__['MultiAI'],MultiAI)
        thread.deleteLater();qtwindow.deleteLater();app.processEvents()
