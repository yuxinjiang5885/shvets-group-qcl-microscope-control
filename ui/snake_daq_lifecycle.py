"""Experimental-only instrumentation around the existing Snake Scan worker.

No NI imports, connection/reset, new scan engine, or global monkey patch.
"""
from types import FunctionType
from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSlot, pyqtSignal
from ui.localization_orchestration import OwnershipError
from ui.checked_snake_daq import CheckedSnakeDAQ, reviewed_factory


class SnakeDaqLifecycle:
    @property
    def uncertain(self):
        return self._uncertain or any(t.raw.uncertain for t in self.tasks)

    @uncertain.setter
    def uncertain(self, value):
        self._uncertain = value

    def __init__(self, bridge, source):
        self.bridge=bridge
        self.tasks=[];self.worker_done=False;self.thread_done=False
        self.uncertain=False;self.ever_acquired=False;self.error=None
        self.state='CREATED'
        self.parent = None
        self.token=bridge.mark_legacy_daq_uncertain(source,owner=self,verifier=lambda owner:owner.released())

    def released(self):
        return (self.worker_done and self.thread_done and not self.uncertain
                and all(t.cleared or not t.raw.native_creation_attempted for t in self.tasks))

    def snapshot(self):
        return dict(acquisition_id=self.token,state=self.state,ever_acquired=self.ever_acquired,
                    worker_done=self.worker_done,thread_done=self.thread_done,
                    owned_task_count=sum(t.raw.native_creation_attempted and not t.cleared for t in self.tasks),error=self.error,
                    tasks=[t.raw.snapshot() for t in self.tasks])

    def task_factory(self, factory, *args, **kwargs):
        if self.parent is not None:
            if self.parent.settings is not None and self.parent.phase != 'IMAGING':
                raise OwnershipError('autofocus_success_required_before_imaging')
            self.parent.phase_to('IMAGING')
        if kwargs.get('reset', args[2] if len(args) > 2 else False) is not False:
            raise ValueError('snake_DAQ_reset_not_allowed')
        try:
            raw=CheckedSnakeDAQ(reviewed_factory(factory)(*args,**kwargs))
        except Exception:
            self.uncertain=True;self.state='RELEASE_UNCERTAIN'
            raise
        task=TrackedSnakeTask(self,raw);self.tasks.append(task)
        return task

    def finish_worker(self):
        if self.parent is not None: self.parent.trace('snake_daq_cleanup_begin')
        self.state='CLEANUP_IN_PROGRESS'
        for task in self.tasks:
            if task.cleared:
                continue
            if task.raw.start_attempted and not task.raw.stop_attempted:
                try:task.stop_task()
                except Exception as error:self.error=repr(error)
            # Stop failure must not skip clear. Never retry either native call.
            if task.raw.task_identity and not task.raw.clear_attempted:
                try:task.clear_task()
                except Exception as error:self.error=repr(error)
            if task.raw.native_creation_attempted and not task.cleared:
                self.uncertain=True
        self.worker_done=True
        self.state='RELEASE_UNCERTAIN' if self.uncertain else 'AWAITING_THREAD_COMPLETION'
        if self.parent is not None:
            self.parent.trace('snake_daq_cleanup_complete', state=self.state,
                              tasks_cleared=all(t.cleared for t in self.tasks))

    def attest_thread_done(self):
        self.thread_done=True
        if self.released():
            self.bridge.confirm_legacy_daq_release(self.token)
            self.state='RELEASE_CONFIRMED'
        else:self.state='RELEASE_UNCERTAIN'


class TrackedSnakeTask:
    def __init__(self,owner,raw):
        self.owner,self.raw=owner,raw
        self.configured=self.started=self.stopped=self.cleared=False

    def _call(self,name,*args,**kwargs):
        if self.owner.parent is not None and name not in ('stop_task','clear_task'):
            self.owner.parent.check()
        try:return getattr(self.raw,name)(*args,**kwargs)
        except Exception as error:
            # Operation failure remains visible even after verified resource release.
            self.owner.error=repr(error)
            raise

    def configure_triggered(self,*a,**k):
        self.configured=True;self.owner.ever_acquired=True;self.owner.state='ACQUIRED'
        self.owner.bridge.legacy_daq_evidence.ever_acquired=True
        return self._call('configure_triggered',*a,**k)

    def start_task(self):
        self.started=True;self.owner.state='ACTIVE'
        return self._call('start_task')

    def read_line(self,*a,**k):return self._call('read_line',*a,**k)

    def stop_task(self):
        result=self._call('stop_task');self.stopped=True
        return result

    def clear_task(self):
        result=self._call('clear_task');self.cleared=self.raw.clear_verified
        if self.owner.parent is not None and self.owner.parent.settings is not None:
            self.owner.parent.phase = 'PREPARE'
        return result


class SnakeCompletion(QObject):
    def __init__(self,bridge,thread,scope):
        super().__init__(bridge.window)
        self.bridge,self.thread,self.scope=bridge,thread,scope
        thread.finished.connect(self.complete)

    @pyqtSlot()
    def complete(self):
        if self.scope.parent is not None: self.scope.parent.trace('thread_finished')
        self.bridge._finished_threads.add(id(self.thread))
        try:
            if self.scope.parent is not None: self.scope.parent.finish_thread()
            else: self.scope.attest_thread_done()
        except Exception as error:self.scope.error=repr(error)
        if self.scope.error:
            parent = self.scope.parent
            laser = 'laser off verified' if parent is not None and parent.laser_verified else 'laser state not confirmed'
            primary = (parent.primary_failure['detail'] if parent is not None and parent.primary_failure
                       else self.scope.error)
            message='Snake Scan failed: '+primary+'; DAQ '+self.scope.state+'; '+laser
            if parent is not None:
                message += '; workflow '+parent.workflow_outcome+'; hardware '+parent.snapshot()['hardware_safety']
            self.bridge.window.auto_relocation.failures_label.setText(message)
            if (self.scope.released() and (parent is None or parent.released())
                    and hasattr(self.bridge.window,'lock_controls')):
                self.bridge.window.lock_controls(lock=False)
            if hasattr(self.bridge.window,'statusbar'):
                self.bridge.window.statusbar.showMessage(message)
        if self.bridge.close_pending and hasattr(self.bridge.window, 'close'):
            QTimer.singleShot(0, self.bridge.window.close)
        self.deleteLater()


def snake_worker_factory(base, bridge, thread, source, *, parent=None):
    scope=SnakeDaqLifecycle(bridge,source)
    scope.parent = parent
    if parent is not None: parent.scope = scope
    if parent is not None: parent.worker_thread = thread
    scan=base.scan
    namespace=dict(scan.__globals__)
    raw_factory=namespace['MultiAI']
    namespace['MultiAI']=lambda *a,**k:scope.task_factory(raw_factory,*a,**k)
    if 'piScanner_widget' in namespace:
        def objective_factory(*a,**k):
            raise OwnershipError('worker_origin_objective_creation_unsupported_in_V1')
        namespace['piScanner_widget']=objective_factory
    private_scan=FunctionType(scan.__code__,namespace,scan.__name__,scan.__defaults__,scan.__closure__)

    class TrackedSnake(base):
        verified_finished = pyqtSignal()
        autofocus_progress = pyqtSignal(object)

        @property
        def finished(self):
            # Legacy run requests success before our cleanup. Buffer that request.
            worker = self
            class Completion:
                def connect(self, *a, **k): return worker.verified_finished.connect(*a, **k)
                def emit(self): worker._success_requested = True
            return Completion()

        def __setattr__(self, name, value):
            if name == 'parameters' and parent is not None and not isinstance(value, list):
                if QThread.currentThread() != bridge.window.thread():
                    raise OwnershipError('snake_parameter_snapshot_requires_GUI_thread')
                from copy import copy
                from types import SimpleNamespace
                from ui.snake_workflow import WorkerStage, WorkerLaser, WorkerObjectiveAdapter, WorkerPI
                value = copy(value)
                value.stage = WorkerStage(value.stage, parent)
                value.laser = WorkerLaser(value.laser, parent)
                settings = parent.settings
                value.pi_scanner = SimpleNamespace(autofocus_on_imaging=settings is not None,
                    target_x=settings.absolute_target_x if settings else None,
                    target_y=settings.absolute_target_y if settings else None)
                value.pi_scanner_widget = (WorkerObjectiveAdapter(parent, value.stage,
                    WorkerPI(bridge.window.pi_scanner.pidevice, parent)) if settings else None)
            super().__setattr__(name, value)

        def _check_objective(self):
            if parent is not None:
                parent.check()
                return
            parameters = getattr(self, 'parameters', None)
            scanner = getattr(parameters, 'pi_scanner', None)
            if getattr(scanner, 'autofocus_on_imaging', False):
                raise OwnershipError('worker_origin_autofocus_unsupported_in_V1')
            widget = getattr(parameters, 'pi_scanner_widget', None)
            if (widget is not None and not isinstance(widget, list)
                    and not bridge.managed_objective(widget)):
                raise OwnershipError('worker_origin_unmanaged_objective_unsupported_in_V1')

        def scan(self):
            self._check_objective()
            return private_scan(self)
        def run(self):
            failed=False
            self._success_requested = False
            try:
                if parent is not None: parent.bind()
                self._check_objective()
                super().run()
            except Exception as error:
                failed=True;scope.error=repr(error)
                if parent is not None: parent.record_failure(error)
            finally:
                scope.finish_worker()
                if parent is not None:
                    parent.finish_worker(self.parameters)
                    failed = failed or parent.uncertain or scope.uncertain
                if not failed and self._success_requested and not scope.uncertain:
                    if parent is not None: parent.trace('thread_quit_requested', via='verified_finished')
                    self.verified_finished.emit()
                else:
                    # Do not emit the legacy success signal: its UI slots assert
                    # laser emission disabled. An exception does not prove that.
                    thread=self.thread()
                    self.deleteLater()
                    if parent is not None: parent.trace('thread_quit_requested', via='failure')
                    thread.quit()
    worker=TrackedSnake()
    worker._snake_daq_scope=scope
    worker._snake_completion=SnakeCompletion(bridge,thread,scope)
    if parent is not None and parent.settings is not None:
        parent.telemetry = worker.autofocus_progress.emit
        try:
            widget = getattr(bridge.window, 'pi_scanner_widget', None)
            if bridge.managed_objective(widget):
                worker.autofocus_progress.connect(widget.receive_snake_autofocus_telemetry,
                                                 Qt.ConnectionType.QueuedConnection)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Snake autofocus display connection unavailable')
    return worker
