"""Experimental-only instrumentation around the existing Snake Scan worker.

No NI imports, connection/reset, new scan engine, or global monkey patch.
"""
from types import FunctionType
from PyQt6.QtCore import QObject, pyqtSlot
from ui.localization_orchestration import OwnershipError


class SnakeDaqLifecycle:
    def __init__(self, bridge, source):
        self.bridge=bridge
        self.tasks=[];self.worker_done=False;self.thread_done=False
        self.uncertain=False;self.ever_acquired=False;self.error=None
        self.state='CREATED'
        self.token=bridge.mark_legacy_daq_uncertain(source,owner=self,verifier=lambda owner:owner.released())

    def released(self):
        return (self.worker_done and self.thread_done and not self.uncertain
                and all(t.cleared for t in self.tasks))

    def snapshot(self):
        return dict(acquisition_id=self.token,state=self.state,ever_acquired=self.ever_acquired,
                    worker_done=self.worker_done,thread_done=self.thread_done,
                    owned_task_count=sum(not t.cleared for t in self.tasks),error=self.error)

    def task_factory(self, factory, *args, **kwargs):
        if kwargs.get('reset',False) is not False:
            raise ValueError('snake_DAQ_reset_not_allowed')
        try:
            raw=factory(*args,**kwargs)
        except Exception:
            self.uncertain=True;self.state='RELEASE_UNCERTAIN'
            raise
        task=TrackedSnakeTask(self,raw);self.tasks.append(task)
        return task

    def finish_worker(self):
        self.state='CLEANUP_IN_PROGRESS'
        for task in self.tasks:
            try:
                if not task.cleared:
                    if task.started and not task.stopped:task.stop_task()
                    if task.configured:task.clear_task()
                    else:task.cleared=True;task.raw=None  # wrapper existed, NI configure never entered
            except Exception as error:
                self.uncertain=True;self.error=repr(error)
        self.worker_done=True
        self.state='RELEASE_UNCERTAIN' if self.uncertain else 'AWAITING_THREAD_COMPLETION'

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
        try:return getattr(self.raw,name)(*args,**kwargs)
        except Exception:
            # Includes NI timeout: even a subsequent clear cannot erase uncertainty.
            self.owner.uncertain=True
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
        if self.started and not self.stopped:
            raise RuntimeError('snake_stop_not_confirmed')
        result=self._call('clear_task');self.cleared=True;self.raw=None
        return result


class SnakeCompletion(QObject):
    def __init__(self,bridge,thread,scope):
        super().__init__(bridge.window)
        self.bridge,self.thread,self.scope=bridge,thread,scope
        thread.finished.connect(self.complete)

    @pyqtSlot()
    def complete(self):
        self.bridge._finished_threads.add(id(self.thread))
        try:self.scope.attest_thread_done()
        except Exception as error:self.scope.error=repr(error)
        if self.scope.error:
            message='Snake Scan failed: '+self.scope.error+'; DAQ '+self.scope.state+'; laser state not confirmed'
            self.bridge.window.auto_relocation.failures_label.setText(message)
            if self.scope.released() and hasattr(self.bridge.window,'lock_controls'):
                self.bridge.window.lock_controls(lock=False)
            if hasattr(self.bridge.window,'statusbar'):
                self.bridge.window.statusbar.showMessage(message)
        self.deleteLater()


def snake_worker_factory(base, bridge, thread, source):
    scope=SnakeDaqLifecycle(bridge,source)
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
        def _check_objective(self):
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
            try:
                self._check_objective()
                super().run()
            except Exception as error:
                failed=True;scope.error=repr(error)
            finally:
                scope.finish_worker()
                if failed:
                    # Do not emit the legacy success signal: its UI slots assert
                    # laser emission disabled. An exception does not prove that.
                    thread=self.thread()
                    self.deleteLater()
                    thread.quit()
    worker=TrackedSnake()
    worker._snake_daq_scope=scope
    worker._snake_completion=SnakeCompletion(bridge,thread,scope)
    return worker
