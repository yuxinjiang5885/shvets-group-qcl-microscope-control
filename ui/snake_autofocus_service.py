"""Worker-only autofocus algorithm and immutable settings; no Qt dependencies."""
from dataclasses import dataclass
import logging
from math import isfinite
from time import monotonic, sleep
import numpy as np


class AutofocusFailure(RuntimeError):
    def __init__(self, outcome, detail='', *, diagnostics=None):
        self.outcome = outcome
        self.diagnostics = diagnostics
        super().__init__(outcome + ': ' + str(detail))


@dataclass(frozen=True)
class SnakeAutofocusSettings:
    absolute_target_x: float
    absolute_target_y: float
    sweep_min_offset: float
    sweep_max_offset: float
    sweep_step: float
    pi_min: float = 0.
    pi_max: float = 400.
    stage_position_tolerance: float = 1.
    pi_position_tolerance: float = .1
    movement_timeout: float = 10.
    read_timeout: float = 20.
    pi_confirmation_window: float = .4
    pi_confirmation_poll: float = .01

    def __post_init__(self):
        if any(isinstance(v, bool) or not isfinite(v) for v in self.__dict__.values()):
            raise AutofocusFailure('INVALID_PARAMETERS', 'finite numeric settings required')
        if (self.sweep_step <= 0 or self.sweep_max_offset < self.sweep_min_offset
                or self.pi_max <= self.pi_min or self.stage_position_tolerance <= 0
                or self.pi_position_tolerance <= 0 or self.movement_timeout <= 0
                or self.read_timeout <= 0
                or self.pi_confirmation_window < .001 or self.pi_confirmation_poll <= 0
                or (self.sweep_max_offset-self.sweep_min_offset)/self.sweep_step > 10000):
            raise AutofocusFailure('INVALID_PARAMETERS', 'invalid range, step, tolerance or timeout')


@dataclass(frozen=True)
class AutofocusResult:
    outcome: str
    best_position: float | None = None
    stage_restored: bool = False
    pi_verified: bool = False
    cleanup_verified: bool = False
    detail: str = ''
    best_signal: float | None = None
    pi_diagnostics: dict | None = None
    cleanup_failures: tuple = ()


@dataclass(frozen=True)
class AutofocusPoint:
    sequence: int
    position: float
    signal: float


def report_progress(callback, event):
    """Observability only: a broken subscriber cannot change hardware outcomes."""
    if callback is not None:
        try:
            callback(event)
        except Exception:
            logging.getLogger(__name__).exception('Snake autofocus telemetry delivery failed')


class SnakeAutofocusService:
    def __init__(self, settings, stage, pi, acquire, checkpoint, stage_trusted, *, progress=None):
        self.settings, self.stage, self.pi = settings, stage, pi
        self.acquire, self.checkpoint, self.stage_trusted = acquire, checkpoint, stage_trusted
        self.stage_restored = self.pi_verified = False
        self.stage_motion_uncertain = False
        self.progress = progress
        self.cleanup_failures = []
        self.pi_diagnostics = None

    def checked(self, outcome, callback, *args):
        try: return callback(*args)
        except AutofocusFailure: raise
        except Exception as error: raise AutofocusFailure(outcome, error) from error

    def position(self):
        point = self.checked('STAGE_READBACK_MISMATCH', self.stage.get_position)
        if len(point) != 2 or not all(isfinite(v) for v in point):
            raise AutofocusFailure('STAGE_READBACK_MISMATCH', point)
        return tuple(point)

    def stage_move(self, point, restoring=False):
        outcome = 'STAGE_RESTORE_FAILURE' if restoring else 'STAGE_MOVE_FAILURE'
        deadline = monotonic() + self.settings.movement_timeout
        self.checked(outcome, self.stage.goto, *point)
        while True:
            busy = self.checked(outcome, self.stage.busy)
            if monotonic() >= deadline or str(busy) not in ('0','1','2','3'):
                self.stage_motion_uncertain = True
                raise AutofocusFailure(outcome, 'idle not confirmed')
            if str(busy) == '0': break
            sleep(.01)
        if any(abs(a-b) > self.settings.stage_position_tolerance
               for a,b in zip(self.position(), point)):
            raise AutofocusFailure('STAGE_READBACK_MISMATCH', 'target mismatch')

    def pi_position(self, timeout_s=None):
        try:
            if timeout_s is None:
                value = self.checked('PI_READBACK_FAILURE', self.pi.qPOS, 1)[1]
            else:
                bounded = getattr(self.pi, 'read_position_bounded', None)
                if bounded is not None:
                    value = bounded(timeout_s)[1]
                else:
                    # Inert/direct service adapters use the same transport budget.
                    previous = self.pi.timeout
                    try:
                        self.pi.timeout = max(1, int(timeout_s * 1000))
                        value = self.pi.qPOS(1)[1]
                    finally:
                        self.pi.timeout = previous
            if not isfinite(value): raise ValueError('nonfinite PI position')
            return float(value)
        except Exception as error: raise AutofocusFailure('PI_READBACK_FAILURE', error) from error

    def pi_move(self, target, *, phase='sweep_point', sweep_index=None):
        started = monotonic()
        deadline = started + self.settings.movement_timeout
        polls = 0
        self.checked('PI_MOVE_FAILURE', self.pi.MOV, 1, float(target))
        while True:
            polls += 1
            try: on_target = self.checked('PI_WAIT_FAILURE', self.pi.qONT, 1)[1]
            except Exception as error: raise AutofocusFailure('PI_WAIT_FAILURE', error) from error
            if monotonic() >= deadline: raise AutofocusFailure('PI_WAIT_FAILURE', 'timeout')
            if on_target is True: break
            if on_target is not False: raise AutofocusFailure('PI_WAIT_FAILURE', 'unknown on-target state')
            sleep(.01)
        confirmation_started = monotonic()
        confirmation_deadline = confirmation_started + self.settings.pi_confirmation_window
        reads = consecutive = 0
        actual = minimum_delta = None
        samples = []
        def diagnostics():
            delta = None if actual is None else actual-target
            return dict(phase=phase, sweep_index=sweep_index, target_um=float(target),
                actual_um=actual, last_actual_um=actual, final_actual_um=actual,
                delta_um=delta, final_delta_um=delta, minimum_delta_seen_um=minimum_delta,
                tolerance_um=self.settings.pi_position_tolerance,
                timeout_s=self.settings.movement_timeout, elapsed_s=monotonic()-started,
                confirmation_window_s=self.settings.pi_confirmation_window,
                confirmation_elapsed_s=monotonic()-confirmation_started,
                on_target_poll_count=polls, position_read_count=reads, wait_result=on_target,
                consecutive_in_tolerance_required=2, consecutive_in_tolerance_observed=consecutive,
                samples=tuple(samples))
        while True:
            self.checkpoint()
            remaining = confirmation_deadline-monotonic()
            if remaining < .001: break  # PI timeout resolution is milliseconds.
            reads += 1
            try:
                actual = self.pi_position(remaining)
            except AutofocusFailure as error:
                self.pi_diagnostics = diagnostics()
                raise AutofocusFailure('PI_READBACK_FAILURE', str(error),
                                       diagnostics=self.pi_diagnostics) from error
            delta = abs(actual-target)
            minimum_delta = delta if minimum_delta is None else min(minimum_delta, delta)
            consecutive = consecutive+1 if delta <= self.settings.pi_position_tolerance else 0
            samples.append(dict(actual_um=actual, delta_um=actual-target,
                                elapsed_s=monotonic()-confirmation_started))
            if monotonic() >= confirmation_deadline: break  # Never accept a late transport result.
            if consecutive >= 2:
                self.pi_diagnostics = diagnostics()
                return
            sleep(min(self.settings.pi_confirmation_poll, max(0., confirmation_deadline-monotonic())))
        self.pi_diagnostics = diagnostics()
        raise AutofocusFailure('PI_READBACK_FAILURE', f'confirmation deadline: {self.pi_diagnostics}',
                               diagnostics=self.pi_diagnostics)

    def run(self, target):
        self.stage_restored = True  # No movement has occurred at the first checkpoint.
        self.checkpoint()
        entry = self.position()
        best = None
        failure = None
        try:
            self.stage_restored = False
            self.stage_move(target)
            center = self.pi_position()
            s = self.settings
            positions = np.arange(center+s.sweep_min_offset,
                                  center+s.sweep_max_offset+s.sweep_step, s.sweep_step)
            results = []
            for sweep_index, position in enumerate(positions, 1):
                self.checkpoint()
                if not s.pi_min <= position <= s.pi_max: continue
                self.pi_move(position, phase='sweep_point', sweep_index=sweep_index)
                data = self.acquire()
                self.checkpoint()
                signal = float(np.mean(np.hypot(data[0], data[1])))
                if isfinite(signal):
                    results.append((float(position), signal))
                    report_progress(self.progress, AutofocusPoint(len(results), float(position), signal))
            if not results: raise AutofocusFailure('NO_VALID_FOCUS_RESULT')
            best, best_signal = max(results, key=lambda item: item[1])
            self.pi_move(best, phase='final_best')
            self.pi_verified = True
        except Exception as error:
            failure = error
        finally:
            # Cancellation is observed before restoration but cannot skip safe cleanup.
            try: self.checkpoint()
            except Exception as error:
                if failure is None: failure = error
            if self.stage_trusted() and not self.stage_motion_uncertain:
                try:
                    self.stage_move(entry, restoring=True)
                    self.stage_restored = True
                except Exception as error:
                    self.cleanup_failures.append(str(error))
                    if failure is None: failure = error
            else:
                error = AutofocusFailure('STAGE_RESTORE_FAILURE', 'stage authority uncertain')
                self.cleanup_failures.append(str(error))
                if failure is None: failure = error
        if failure is not None: raise failure
        self.checkpoint()
        return AutofocusResult('SUCCESS', best, self.stage_restored, self.pi_verified,
                               best_signal=best_signal, pi_diagnostics=self.pi_diagnostics)
