"""Serialized queued execution; no hardware imports, sessions or native cancellation.

submit must enqueue promptly, never wait for a native call. Inline submit is only
appropriate for inert tests. A timed-out ticket stays latched until explicit
external recovery/reconstruction, even after a native call eventually returns.
"""
from dataclasses import dataclass, field
from math import isfinite
from threading import Event, Lock
from time import monotonic


class DispatchRejected(RuntimeError):
    pass


class NativeCallUncertain(TimeoutError):
    pass


@dataclass
class CommandTicket:
    run_id: str
    done: Event = field(default_factory=Event)
    started: bool = False
    expired: bool = False
    result: object = None
    error: BaseException = None


class StageCommandDispatcher:
    def __init__(self, submit, authorize, quarantine):
        self._submit, self._authorize, self._quarantine = submit, authorize, quarantine
        self._lock = Lock()
        self._active = None
        self.last_ticket = None
        self.uncertain = False
        self.closed = False

    @property
    def unresolved(self):
        with self._lock:
            return self._active is not None and not self._active.done.is_set()

    def execute(self, handle, call, timeout_s, *, cleanup=False):
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('positive_finite_dispatch_timeout_required')
        self._authorize(handle, cleanup)
        with self._lock:
            if self.closed or self.uncertain or self._active is not None:
                raise DispatchRejected('dispatcher_closed_uncertain_or_in_flight')
            ticket = CommandTicket(handle.run_id)
            self._active = self.last_ticket = ticket
            self._handle = handle
        deadline = monotonic() + timeout_s

        def execute_queued():
            try:
                with self._lock:
                    if ticket.expired or self.closed:
                        raise DispatchRejected('expired_queued_command_not_executed')
                self._authorize(handle, cleanup)  # Revalidate after queue delay.
                with self._lock:
                    if ticket.expired or self.closed:
                        raise DispatchRejected('expired_queued_command_not_executed')
                    ticket.started = True
                ticket.result = call()
            except BaseException as error:
                ticket.error = error
            finally:
                ticket.done.set()

        try:
            self._submit(execute_queued)
        except BaseException as error:
            # A faulty submitter could have queued work before raising. Fail closed.
            ticket.error = error
            self._latch(handle, ticket, 'stage_dispatch_submission_uncertain')
            raise
        if not ticket.done.wait(max(0., deadline-monotonic())) or monotonic() > deadline:
            self._latch(handle, ticket, 'stage_dispatch_timeout_native_state_uncertain')
            raise NativeCallUncertain('caller_timed_out_native_call_not_cancelled')
        with self._lock:
            self._active = None
        if ticket.error is not None:
            raise ticket.error
        return ticket.result

    def _latch(self, handle, ticket, reason):
        with self._lock:
            ticket.expired = True
            self.uncertain = True
        self._quarantine(handle, reason)

    def shutdown(self):
        """No disconnect, no thread termination; False means completion unproven."""
        with self._lock:
            self.closed = True
            if self._active is not None and not self._active.done.is_set():
                self.uncertain = True
                self._active.expired = True
                unresolved = True
            else:
                unresolved = False
        if unresolved:
            self._quarantine(self._handle, 'dispatcher_shutdown_native_state_uncertain')
        return not self.uncertain


def qt_main_thread_target():
    """Create only on Qt's main thread; worker callers enqueue individual SDK calls.

    A hung native call can freeze GUI event handling. Worker timeout still latches
    uncertainty; it cannot make the GUI responsive or safely stop the SDK call.
    """
    from PyQt6.QtCore import QCoreApplication, QObject, QThread, Qt, pyqtSignal, pyqtSlot
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError('create_stage_target_on_Qt_main_thread')

    class Target(QObject):
        requested = pyqtSignal(object)

        def __init__(self):
            super().__init__()
            self.requested.connect(self.execute, Qt.ConnectionType.QueuedConnection)

        @pyqtSlot(object)
        def execute(self, call):
            call()

        def submit(self, call):
            if QThread.currentThread() == self.thread():
                raise DispatchRejected('blocking_dispatch_from_execution_thread')
            self.requested.emit(call)

    return Target()
