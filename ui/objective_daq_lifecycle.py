"""Experimental Objective ownership. Importing this module never loads NI/PI."""
from dataclasses import dataclass, field
from threading import get_ident

from ui.localization_orchestration import Activity, OwnershipError
from ui.localization_daq import checked


@dataclass
class ObjectiveOperation:
    generation: int
    operation: str
    token: str = None
    task: object = None
    ever_acquired: bool = False
    execution_in_flight: bool = True
    uncertain: bool = False
    errors: list = field(default_factory=list)

    def released(self):
        return (not self.execution_in_flight and not self.uncertain
                and (self.task is None or self.task.clear_confirmed))

    def snapshot(self):
        task = self.task
        return dict(generation=self.generation, operation=self.operation, token=self.token,
                    execution_in_flight=self.execution_in_flight, uncertain=self.uncertain,
                    ever_acquired=self.ever_acquired,
                    task_identity=task.identity if task else None,
                    native_creation_attempted=task.create_attempted if task else False,
                    native_task_created=task.created if task else False,
                    clear_confirmed=task.clear_confirmed if task else None,
                    errors=list(self.errors))


class ObjectiveTask:
    """One checked finite task; retained only until its owning operation ends."""
    def __init__(self, backend):
        self.backend = backend
        self.device = backend.MultiChannelAnalogInput(
            [b'Dev1/ai0', b'Dev1/ai1'], limit=(-10., 10.), reset=False)
        self.create_attempted = self.created = self.clear_confirmed = False
        self.clear_attempted = False
        self.identity = None

    def configure(self):
        b, d = self.backend, self.device
        self.create_attempted = True
        try:
            checked(b.DAQmxCreateTask('', b.byref(d.taskHandle)), 'Objective CreateTask')
        finally:
            self.identity = d.taskHandle.value
            self.created = bool(self.identity)
        if not self.created:
            raise RuntimeError('Objective task handle missing')
        for channel in (b'Dev1/ai0', b'Dev1/ai1'):
            checked(b.DAQmxCreateAIVoltageChan(d.taskHandle, channel, '',
                b.DAQmx_Val_Cfg_Default, -10., 10., b.DAQmx_Val_Volts, None), 'Objective channel')
        checked(b.DAQmxCfgSampClkTiming(d.taskHandle, '', 10000,
            b.DAQmx_Val_Rising, b.DAQmx_Val_FiniteSamps, 10), 'Objective timing')

    def acquire(self):
        if self.clear_attempted:
            raise OwnershipError('objective_task_already_cleared')
        # The existing bounded read always attempts StopTask, even on start/read failure.
        return self.device.acquire_bounded(10, timeout_s=20.)

    def clear(self):
        if self.clear_attempted:
            raise OwnershipError('objective_clear_already_attempted')
        self.clear_attempted = True
        if self.device.taskHandle.value:
            checked(self.backend.DAQmxClearTask(self.device.taskHandle), 'Objective ClearTask')
        elif self.create_attempted:
            raise OwnershipError('objective_created_task_identity_unknown')
        self.clear_confirmed = True


class ObjectiveDaqLifecycle:
    """One registered owner. Reservation is atomic; hardware runs outside the lock."""
    def __init__(self, bridge, backend=None):
        self.bridge, self.backend = bridge, backend
        self.widget = None
        self.state = 'RELEASED'
        self.generation = 0
        self.current = None
        self.execution_thread = None
        with bridge.controller.registration.lock:
            if bridge.objective_owner is not None:
                raise OwnershipError('objective_owner_already_registered')
            if getattr(bridge.window, 'pi_scanner_widget', None) is not None:
                raise OwnershipError('unmanaged_objective_widget_exists')
            bridge.objective_owner = self

    def released(self):
        return (self.state == 'RELEASED' and self.execution_thread is None
                and (self.current is None or self.current.released()))

    def executing_here(self):
        return self.execution_thread == get_ident() and self.state == 'ACTIVE'

    def check_execution(self):
        if not self.executing_here() or self.current.uncertain:
            raise OwnershipError('objective_operation_not_authorized')
        reasons = self.bridge.controller.ownership.can_begin_localization().reasons
        conflicts = [r for r in reasons if r != 'activity:' + Activity.OBJECTIVE_DAQ.value]
        if conflicts:
            error = OwnershipError('objective_conflicting_activity: ' + '; '.join(conflicts))
            self.fail(error)
            raise error

    def fail(self, error):
        with self.bridge.controller.registration.lock:
            self.current.uncertain = True
            self.current.errors.append(repr(error))

    def hardware_call(self, callback, *args, **kwargs):
        self.check_execution()
        try:
            return callback(*args, **kwargs)
        except BaseException as error:
            self.fail(error)  # Legacy methods sometimes catch errors; retain independent evidence.
            raise

    def acquire_data(self):
        self.check_execution()
        op = self.current
        try:
            if op.task is None:
                with self.bridge.controller.registration.lock:
                    op.token = self.bridge.mark_legacy_daq_uncertain(
                        'managed_objective:' + op.operation, owner=op,
                        verifier=lambda owner: owner.released())
                    op.ever_acquired = True
                    self.bridge.legacy_daq_evidence.ever_acquired = True
                backend = self.backend
                if backend is None:
                    from instruments import ni_daq as backend
                op.task = ObjectiveTask(backend)
                op.task.configure()
            return op.task.acquire()
        except BaseException as error:
            self.fail(error)
            raise

    def run(self, operation, callback):
        b = self.bridge
        with b.controller.registration.lock:
            b.check_objective_admission(self)
            self.generation += 1
            op = ObjectiveOperation(self.generation, operation)
            self.current = op
            self.state = 'ACTIVE'
            self.execution_thread = get_ident()
            b.controller.report_activity(Activity.OBJECTIVE_DAQ, True)
        try:
            return callback()
        except BaseException as error:
            self.fail(error)
            raise
        finally:
            with b.controller.registration.lock:
                self.state = 'RELEASING'
            # No transaction lock is held across native task cleanup.
            try:
                if op.task is not None:
                    op.task.clear()
            except BaseException as error:
                self.fail(error)
            finally:
                with b.controller.registration.lock:
                    op.execution_in_flight = False
                    self.execution_thread = None
                    self.state = 'UNCERTAIN' if op.uncertain else 'RELEASED'
                    b.controller.report_activity(Activity.OBJECTIVE_DAQ, op.uncertain)
                    if self.released() and op.token is not None:
                        try:
                            b.confirm_legacy_daq_release(op.token)
                        except Exception as error:
                            self.fail(error)
                            self.state = 'UNCERTAIN'
                            b.controller.report_activity(Activity.OBJECTIVE_DAQ, True)
            if op.uncertain:
                raise OwnershipError('objective_ownership_uncertain: ' + '; '.join(op.errors))

    def snapshot(self):
        with self.bridge.controller.registration.lock:
            return dict(state=self.state, verified_released=self.released(),
                        **(self.current.snapshot() if self.current else dict(
                            generation=0, operation=None, execution_in_flight=False,
                            uncertain=False, ever_acquired=False, task_identity=None,
                            native_creation_attempted=False, native_task_created=False,
                            clear_confirmed=None, token=None, errors=[])))
