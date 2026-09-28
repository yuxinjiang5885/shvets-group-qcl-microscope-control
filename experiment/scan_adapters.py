"""Adapt existing Prior stage and configured NI DAQ objects to Module 6.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Construction and import perform no device calls or instrument imports. The caller
owns connections, configuration, and exclusive access. Native calls are synchronous:
deadlines cannot preempt an unresponsive vendor DLL. See docs/scan_adapters.md.
"""

from math import fsum, hypot, isfinite
from numbers import Integral, Real
import time

from experiment.scan_1d import StageBounds


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def _timeout(value):
    value = _number(value, 'timeout_s')
    if value <= 0:
        raise ValueError('timeout_s must be positive')
    return value


class PriorStageAdapter:
    """Use checked stage.message replies instead of legacy error-discarding methods.

    Uses the existing integral-um command convention, rejecting fractional targets
    rather than silently rounding outside scan bounds. No home/zero/speed/joystick
    commands are issued. Recreate after controller frame changes. After transport
    failure or timeout, movement is latched off; stop remains available.
    """

    def __init__(self, stage, *, bounds: StageBounds, poll_interval_s=0.01, clock=time):
        if not callable(getattr(stage, 'message', None)):
            raise TypeError('Expected an existing stage with message(command)')
        if not isinstance(bounds, StageBounds):
            raise TypeError('Explicit StageBounds are required')
        self._stage = stage
        self.bounds = bounds
        self._poll = _timeout(poll_interval_s)
        self._clock = clock
        self._faulted = False

    def _command(self, command, deadline):
        if self._clock.monotonic() >= deadline:
            raise TimeoutError('Stage operation deadline expired')
        try:
            reply = self._stage.message(command)
            if self._clock.monotonic() >= deadline:
                raise TimeoutError('Prior SDK call exceeded deadline; physical state is uncertain')
            if not isinstance(reply, tuple) or len(reply) != 2:
                raise RuntimeError('Malformed Prior SDK reply')
            status, payload = reply
            if isinstance(status, bool) or not isinstance(status, Integral) or status != 0:
                raise RuntimeError(f'Prior SDK command failed: status={status!r}, reply={payload!r}')
            if not isinstance(payload, str):
                raise RuntimeError('Prior SDK payload must be text')
            return payload.strip()
        except BaseException:
            self._faulted = True
            raise

    def _busy(self, deadline):
        reply = self._command('controller.stage.busy.get', deadline)
        if reply not in ('0', '1', '2', '3'):
            self._faulted = True
            raise RuntimeError(f'Invalid stage busy reply: {reply!r}')
        return reply != '0'

    def _position(self, deadline):
        reply = self._command('controller.stage.position.get', deadline)
        try:
            fields = reply.split(',')
            if len(fields) != 2:
                raise ValueError('Expected X,Y')
            point = tuple(float(field) for field in fields)
            if not all(isfinite(value) for value in point):
                raise ValueError('Nonfinite position')
            return point
        except ValueError as error:
            self._faulted = True
            raise RuntimeError(f'Invalid stage position reply: {reply!r}') from error

    def move_to(self, x_um, y_um, *, timeout_s):
        deadline = self._clock.monotonic() + _timeout(timeout_s)
        if self._faulted:
            raise RuntimeError('Stage adapter faulted; movement disabled until operator recovery')
        target = (_number(x_um, 'x_um'), _number(y_um, 'y_um'))
        if any(not value.is_integer() for value in target):
            raise ValueError('Prior targets must be integral um; fractional targets are not rounded')
        if not self.bounds.contains(target):
            raise ValueError('Target outside adapter stage bounds')
        if self._busy(deadline):
            raise RuntimeError('Stage already moving; refusing another move')
        if not self.bounds.contains(self._position(deadline)):
            raise ValueError('Current position outside adapter bounds; unsafe approach')
        self._command(f'controller.stage.goto-position {int(target[0])} {int(target[1])}', deadline)

    def is_busy(self, *, timeout_s):
        return self._busy(self._clock.monotonic() + _timeout(timeout_s))

    def get_position(self, *, timeout_s):
        return self._position(self._clock.monotonic() + _timeout(timeout_s))

    def stop(self, *, timeout_s):
        """Request smooth stop and confirm idle under one shared deadline."""
        deadline = self._clock.monotonic() + _timeout(timeout_s)
        try:
            self._command('controller.stop.smoothly', deadline)
            while self._busy(deadline):
                remaining = deadline - self._clock.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Stage did not become idle after stop')
                self._clock.sleep(min(self._poll, remaining))
        except BaseException:
            self._faulted = True
            raise


class NIReflectionReader:
    """Reduce checked X/Y channel blocks to mean(hypot(X_i, Y_i)), in volts.

    Wrap a caller-configured MultiChannelAnalogInput with acquire_bounded(). No
    configure/reset/connect/clear calls are made. Explicit raw-channel clipping
    limits must match the configured inputs; check clipping BEFORE reduction.
    last_samples retains the latest returned block, including rejected blocks.
    """

    signal_unit = 'V'

    def __init__(self, analog_input, *, sample_number, channel_limits,
                 x_channel=0, y_channel=1, clock=time):
        if not callable(getattr(analog_input, 'acquire_bounded', None)):
            raise TypeError('DAQ must provide checked acquire_bounded(sampleNumber, timeout_s=...)')
        if isinstance(sample_number, bool) or not isinstance(sample_number, int) or sample_number < 1:
            raise ValueError('sample_number must be a positive integer')
        limits = tuple(tuple(_number(v, 'channel limit') for v in pair) for pair in channel_limits)
        if not limits or any(len(pair) != 2 or pair[0] >= pair[1] for pair in limits):
            raise ValueError('Each channel needs ordered low/high clipping limits')
        for index in (x_channel, y_channel):
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(limits):
                raise ValueError('Invalid lock-in channel index')
        if x_channel == y_channel:
            raise ValueError('X and Y must use distinct channels')
        self._input = analog_input
        self.sample_number = sample_number
        self.channel_limits = limits
        self.x_channel, self.y_channel = x_channel, y_channel
        self._clock = clock
        self.last_samples = None
        self._faulted = False

    def read(self, *, timeout_s):
        timeout_s = _timeout(timeout_s)
        if self._faulted:
            raise RuntimeError('DAQ adapter faulted; operator must inspect/recover the task')
        deadline = self._clock.monotonic() + timeout_s
        self.last_samples = None
        try:
            data = self._input.acquire_bounded(self.sample_number, timeout_s=timeout_s)
            self.last_samples = tuple(tuple(float(value) for value in channel) for channel in data)
            if self._clock.monotonic() >= deadline:
                raise TimeoutError('DAQ read exceeded deadline')
            if len(self.last_samples) != len(self.channel_limits):
                raise RuntimeError('Unexpected DAQ channel count')
            for values, (low, high) in zip(self.last_samples, self.channel_limits):
                if len(values) != self.sample_number:
                    raise RuntimeError('Unexpected DAQ sample count')
                if not all(isfinite(v) for v in values):
                    raise ValueError('Nonfinite raw DAQ samples')
                if any(v <= low or v >= high for v in values):
                    raise ValueError('Raw DAQ channel saturated or outside configured limits')
            value = fsum(hypot(x, y) / self.sample_number for x, y in
                         zip(self.last_samples[self.x_channel], self.last_samples[self.y_channel]))
            if not isfinite(value):
                raise ValueError('Nonfinite reflection magnitude')
            return value
        except BaseException:
            self._faulted = True
            raise
