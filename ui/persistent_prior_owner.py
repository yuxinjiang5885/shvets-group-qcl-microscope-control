"""Experimental-only Prior lifetime. Importing this module initializes no devices.

Only the owner QObject touches the raw driver, including construction/destruction.
Synchronous callers queue work to its persistent QThread. No force termination or
implicit recovery is provided. Context retains the owner even after a timeout.
"""
from threading import Lock, local
from contextlib import contextmanager
from time import monotonic
from math import isfinite
from types import SimpleNamespace, FunctionType
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from ui.stage_command_dispatcher import StageCommandDispatcher, DispatchRejected


METHODS = frozenset(('message', 'busy', 'get_position', 'get_speed', 'get_acc',
    'goto', 'identify', 'joystick', 'move_at_velocity', 'move_rel', 'reference',
    'set_acc', 'set_position', 'set_speed', 'stop_smoothly', 'encoder_res',
    'arm_trigger', 'make_snakes', 'wait_until_ready'))
ATTRIBUTES = frozenset(('speeds', 'steps', 'accs', 'defaultSpeed', 'defaultAcc', 'realHw'))
# Retain an uncertain native lifetime rather than destroying a running QThread
# during failed window construction. Only confirmed shutdown removes it.
_LIVE_OWNERS = set()


def real_stage_factory(model):
    # Invoked only on the owner thread by explicit experimental hardware startup.
    from instruments.hld117 import stage
    return stage(model=model)


def _value(value):
    """Only copied data may cross the owner boundary, never native objects."""
    if value is None or type(value) in (str, bool, int, float):
        return value
    if type(value) in (tuple, list):
        return type(value)(_value(v) for v in value)
    if type(value) is dict:
        return {_value(k): _value(v) for k,v in value.items()}
    raise TypeError('non_data_stage_return_rejected')


class _OwnerWorker(QObject):
    requested = pyqtSignal(object)

    def __init__(self, factory, model, port):
        super().__init__()
        self.__factory, self.__model, self.__port = factory, model, port
        self.__raw = None
        self.requested.connect(self.execute, Qt.ConnectionType.QueuedConnection)

    @pyqtSlot(object)
    def execute(self, call):
        call()

    def initialize(self):
        self.__raw = self.__factory(self.__model)
        # The legacy wrapper discards SDK statuses in connect/goto/etc. Validate
        # its shared message boundary on the owner thread for ALL callers.
        message = self.__raw.message
        def checked(*args, **kwargs):
            result = message(*args, **kwargs)
            if not isinstance(result, tuple) or len(result) != 2 or result[0] != 0:
                raise RuntimeError('Prior_native_command_failed:' + repr(result))
            return result
        self.__raw.message = checked
        self.__raw.connect(self.__port)
        self.__raw.identify()

    def invoke(self, method, args, kwargs):
        if method in ATTRIBUTES:
            return _value(getattr(self.__raw, method))
        return _value(getattr(self.__raw, method)(*args, **kwargs))

    def cleanup(self):
        if self.__raw is None:
            return
        self.__raw.disconnect()
        status = self.__raw.close_session()
        if status != 0:
            raise RuntimeError('Prior_close_session_failed:' + repr(status))
        del self.__raw.message  # Break checked-message/bound-method reference cycle.
        self.__raw = None  # Final raw reference/destruction stays on this thread.


class StageProxy:
    def __init__(self, owner):
        self.__owner = owner
        self.__timeouts = local()
        self.command_guard = None
        self.joystick_state = None  # Last acknowledged software command, not physical readback.

    @contextmanager
    def execution_timeout(self, seconds):
        previous = getattr(self.__timeouts, 'seconds', None)
        self.__timeouts.seconds = seconds
        try:
            yield
        finally:
            self.__timeouts.seconds = previous

    def _invoke(self, method, *args, **kwargs):
        callback = lambda: self.__owner.call(method, args, kwargs,
            timeout_s=getattr(self.__timeouts, 'seconds', None))
        joy = None
        if method == 'joystick':
            joy = kwargs.get('enable', args[0] if args else True)
        elif method == 'message' and args:
            joy = {'controller.stage.joyxyz.on': True,
                   'controller.stage.joyxyz.off': False}.get(args[0])
        try:
            result = self.command_guard(method, callback) if self.command_guard else callback()
        except Exception:
            if joy is not None:
                self.joystick_state = None
            raise
        if joy is not None:
            self.joystick_state = bool(joy)
        return result

    def __getattr__(self, name):
        if name in METHODS:
            return lambda *args, **kwargs: self._invoke(name, *args, **kwargs)
        if name in ATTRIBUTES:
            return self._invoke(name)
        raise AttributeError(name)

    def connect(self, *args, **kwargs):
        raise DispatchRejected('owner_already_connected_no_second_connect')

    def disconnect(self):
        def close():
            if not self.__owner.shutdown():
                raise DispatchRejected('owner_cleanup_unconfirmed')
        return self.command_guard('disconnect', close) if self.command_guard else close()

    def close_session(self):
        if not self.__owner.closed:
            raise DispatchRejected('session_cleanup_owned_by_shutdown')
        return 0


class PersistentPriorOwner:
    def __init__(self, context, *, factory=real_stage_factory, model='HLD117', port=3, timeout_s=5.):
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('positive_finite_owner_timeout_required')
        if getattr(context, '_persistent_prior_owner', None) is not None:
            raise DispatchRejected('second_Prior_owner_for_context')
        context._persistent_prior_owner = self
        _LIVE_OWNERS.add(self)
        self.timeout_s = timeout_s
        self.closed = False
        self.started = False
        self._closing = False
        self.on_uncertain = None
        self._serial = Lock()
        self._handle = SimpleNamespace(run_id='persistent-Prior-owner')
        self._thread = QThread()
        self._worker = _OwnerWorker(factory, model, port)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self.dispatcher = StageCommandDispatcher(self._submit, lambda *a: None, self._uncertain)
        self.proxy = StageProxy(self)

    def _submit(self, call):
        if QThread.currentThread() == self._thread:
            raise DispatchRejected('recursive_owner_call')
        self._worker.requested.emit(call)

    def _uncertain(self, handle, reason):
        if self.on_uncertain:
            self.on_uncertain(reason)

    @property
    def running(self):
        return self._thread.isRunning()

    @property
    def uncertain(self):
        return self.dispatcher.uncertain

    def _execute(self, call, timeout_s=None):
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('positive_finite_owner_timeout_required')
        deadline = monotonic()+timeout_s
        if not self._serial.acquire(timeout=timeout_s):
            raise TimeoutError('owner_queue_wait_timeout_no_command_submitted')
        try:
            remaining = deadline-monotonic()
            if remaining <= 0:
                raise TimeoutError('owner_queue_wait_timeout_no_command_submitted')
            def data_only():
                try:
                    return True, call()
                except BaseException as error:
                    # Tracebacks can retain raw driver frames. Only copied error
                    # text crosses this lifetime boundary, never the traceback.
                    return False, type(error).__name__ + ': ' + str(error)
            success, result = self.dispatcher.execute(self._handle, data_only, remaining)
            if not success:
                raise RuntimeError(result)
            return result
        finally:
            self._serial.release()

    def start(self):
        if self.started or self.closed:
            raise DispatchRejected('owner_start_once_only')
        self.started = True
        self._thread.start()
        try:
            self._execute(self._worker.initialize)
        except Exception:
            # No second call while native state is uncertain. If construction
            # returned an ordinary error, cleanup the partial session on owner.
            if not self.uncertain:
                self.shutdown()
            raise
        return self.proxy

    def call(self, method, args=(), kwargs=None, *, timeout_s=None):
        if not self.started or self.closed or self._closing or method not in METHODS | ATTRIBUTES:
            raise DispatchRejected('owner_call_not_available')
        args, kwargs = _value(args), _value(kwargs or {})
        def invoke():
            if self._closing:
                raise DispatchRejected('owner_closing')
            return self._worker.invoke(method, args, kwargs)
        return self._execute(invoke, timeout_s)

    def shutdown(self):
        if self.closed:
            return True
        self._closing = True
        if self.uncertain or self.dispatcher.unresolved:
            return False
        try:
            self._execute(self._worker.cleanup)
        except Exception:
            self.dispatcher.uncertain = True
            self._uncertain(self._handle, 'Prior_owner_cleanup_failed')
            return False
        self.dispatcher.shutdown()
        self._thread.quit()
        if not self._thread.wait(int(self.timeout_s*1000)):
            return False
        self.closed = True
        _LIVE_OWNERS.discard(self)
        return True

    def retire_quarantined(self):
        """Stop idle delivery for process exit without claiming native cleanup.

        Never disconnect an uncertain session or terminate a native call. A call
        still executing must return before normal Qt thread exit can complete.
        Retain the owner/evidence; this is not recovery or a released session.
        """
        self._closing = True
        self.dispatcher.shutdown()
        self._thread.quit()
        return self._thread.wait(int(self.timeout_s * 1000))


def constructor_with_proxy(base_class, proxy):
    """Private constructor globals: no global/module monkey patch or UI copy.

    Preserve original code, defaults and __class__ closure (zero-arg super).
    The base initializer still owns its temporary *delivery* QThread; it creates
    no stage/session and emits only the already-connected proxy.
    """
    original = base_class.__init__
    if 'stageInitializer' not in original.__code__.co_names:
        raise RuntimeError('base_constructor_has_no_stage_initializer_injection_point')
    class ProxyInitializer(QObject):
        stageInitialized = pyqtSignal()
        stageInstance = pyqtSignal(object)
        def __init__(self, **kwargs):
            super().__init__()
        def stage_initialize(self):
            self.stageInstance.emit(proxy)
            self.stageInitialized.emit()
    namespace = dict(original.__globals__)
    namespace['stageInitializer'] = ProxyInitializer
    return FunctionType(original.__code__, namespace, original.__name__,
                        original.__defaults__, original.__closure__)
