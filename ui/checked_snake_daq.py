"""Checked private call paths for the reviewed legacy Snake DAQ implementation.

No vendor import or global patch. Installed PyDAQmx 1.4.6 returns integer status,
raises for negative status, and warns for positive status. Require exactly zero;
None or another unknown result cannot establish release.
"""
from pathlib import Path
from types import CodeType, FunctionType
from numbers import Integral
from uuid import uuid4
from threading import get_ident


class SnakeDaqError(RuntimeError):
    def __init__(self, operation, detail):
        self.operation = operation
        super().__init__(f'{operation}: {detail}')


def reviewed_factory(factory):
    """Check code without importing/executing the hardware module."""
    source = Path(__file__).resolve().parents[1] / 'instruments' / 'ni_daq.py'
    module = compile(source.read_bytes(), str(source), 'exec', dont_inherit=True)
    cls = next(c for c in module.co_consts if isinstance(c, CodeType)
               and c.co_name == 'MultiChannelAnalogInput')
    expected = {c.co_name: c for c in cls.co_consts if isinstance(c, CodeType)}
    for name in ('__init__', 'configure_triggered', 'start_task', 'read_line',
                 'stop_task', 'clear_task'):
        if getattr(getattr(factory, name, None), '__code__', None) != expected[name]:
            raise SnakeDaqError('factory', 'unreviewed legacy DAQ implementation')
    return factory


class CheckedSnakeDAQ:
    sequences = {
        'configure_triggered': ('DAQmxCreateTask', 'DAQmxCreateAIVoltageChan',
                               'DAQmxCfgSampClkTiming', 'DAQmxCfgDigEdgeStartTrig',
                               'DAQmxSetTrigAttribute'),
        'start_task': ('DAQmxStartTask',), 'read_line': ('DAQmxReadAnalogF64',),
        'stop_task': ('DAQmxStopTask',), 'clear_task': ('DAQmxClearTask',),
    }

    def __init__(self, raw):
        reviewed_factory(type(raw))
        self.raw = raw
        self.execution_thread = get_ident()
        self.generation = uuid4().hex
        self.task_identity = None
        self.native_creation_attempted = self.native_task_created = False
        self.configure_verified = self.start_verified = self.read_verified = False
        self.start_attempted = self.stop_attempted = self.clear_attempted = False
        self.stop_verified = self.clear_verified = False
        self.uncertain = False
        self.errors = []

    def snapshot(self):
        result = {name: getattr(self, name) for name in (
            'generation', 'task_identity', 'native_creation_attempted',
            'native_task_created', 'configure_verified', 'start_attempted',
            'start_verified', 'read_verified', 'stop_attempted', 'stop_verified',
            'clear_attempted', 'clear_verified', 'uncertain', 'errors')}
        result['errors'] = list(self.errors)
        result['operation_failed'] = bool(self.errors)
        return result

    def _run(self, operation, *args):
        if get_ident() != self.execution_thread:
            raise SnakeDaqError(operation, 'foreign execution thread')
        if self.clear_attempted:
            raise SnakeDaqError(operation, 'task cleanup already attempted')
        if operation == 'configure_triggered':
            if self.native_creation_attempted:
                raise SnakeDaqError(operation, 'task generation cannot be reconfigured')
        elif not self.task_identity or self.raw.taskHandle.value != self.task_identity:
            self.uncertain = True
            raise SnakeDaqError(operation, 'missing or replaced task identity')
        if operation in ('start_task', 'read_line') and (self.errors or not self.configure_verified):
            raise SnakeDaqError(operation, 'task not ready or acquisition previously failed')
        if operation == 'start_task' and self.start_attempted:
            raise SnakeDaqError(operation, 'start already attempted')
        if operation == 'read_line' and (not self.start_verified or self.stop_attempted):
            raise SnakeDaqError(operation, 'read requires running task')
        if operation == 'clear_task':
            self.clear_attempted = True
        if operation == 'start_task':
            self.start_attempted = True
        if operation == 'stop_task':
            if self.stop_attempted:
                raise SnakeDaqError(operation, 'stop already attempted')
            self.stop_attempted = True
        function = getattr(type(self.raw), operation)
        namespace = dict(function.__globals__)
        observed = []

        def wrap(name, native):
            def call(*values):
                if name == 'DAQmxCreateTask':
                    self.native_creation_attempted = True
                try:
                    status = native(*values)
                finally:
                    if name == 'DAQmxCreateTask':
                        self.task_identity = self.raw.taskHandle.value
                        self.native_task_created = bool(self.task_identity)
                if isinstance(status, bool) or not isinstance(status, Integral) or status != 0:
                    raise SnakeDaqError(name, f'unverified native status {status!r}')
                if name == 'DAQmxCreateTask' and not self.native_task_created:
                    raise SnakeDaqError(name, 'successful create without task identity')
                if name == 'DAQmxReadAnalogF64' and values[6]._obj.value != values[1]:
                    raise SnakeDaqError(name, 'short read')
                observed.append(name)
                return status
            return call

        for name in self.sequences[operation]:
            namespace[name] = wrap(name, namespace[name])
        private = FunctionType(function.__code__, namespace)
        try:
            result = private(self.raw, *args)
            expected = list(self.sequences[operation])
            if operation == 'configure_triggered':
                expected[1:2] = ['DAQmxCreateAIVoltageChan'] * self.raw.numberOfChannel
            if observed != expected:
                raise SnakeDaqError(operation, 'native call sequence unverified')
            flag = {'configure_triggered': 'configure_verified', 'start_task': 'start_verified',
                    'read_line': 'read_verified', 'stop_task': 'stop_verified',
                    'clear_task': 'clear_verified'}[operation]
            setattr(self, flag, True)
            if operation == 'clear_task':
                self.uncertain = False
            return result
        except BaseException as error:
            self.errors.append(f'{operation}: {error}')
            self.uncertain = True
            raise SnakeDaqError(operation, str(error)) from error

    def configure_triggered(self, *args): return self._run('configure_triggered', *args)
    def start_task(self): return self._run('start_task')
    def read_line(self, *args): return self._run('read_line', *args)
    def stop_task(self): return self._run('stop_task')
    def clear_task(self): return self._run('clear_task')
