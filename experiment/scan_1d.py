"""Hardware-independent, bounded step scans with durable offline scan journals.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Adapters must honor timeout_s, raise on device errors, and never reset coordinates.
There are intentionally no instrument imports or real hardware adapters here.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from math import ceil, hypot, isfinite
from pathlib import Path
import os
import time
from typing import Callable, Protocol


class Stage(Protocol):
    """All coordinates are um in the caller's unchanged controller frame.

    Movement must stay inside the rectangle spanned by its start and destination.
    Every call must return/raise within timeout_s; Python cannot interrupt a hung
    vendor call. is_busy returns bool (not the legacy driver's string). stop must
    request a stop AND confirm idle before returning; otherwise it must raise.
    """

    def move_to(self, x_um: float, y_um: float, *, timeout_s: float) -> None: ...
    def is_busy(self, *, timeout_s: float) -> bool: ...
    def get_position(self, *, timeout_s: float) -> tuple[float, float] | None: ...
    def stop(self, *, timeout_s: float) -> None: ...


class SignalReader(Protocol):
    """Return one scalar in settings.signal_unit; honor the finite timeout."""

    def read(self, *, timeout_s: float) -> float: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def time(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _position(value):
    if len(value) != 2:
        raise ValueError("Position must contain X and Y in um")
    return tuple(_finite(v, "position") for v in value)


@dataclass(frozen=True)
class StageBounds:
    x_min_um: float
    x_max_um: float
    y_min_um: float
    y_max_um: float
    frame_id: str

    def __post_init__(self):
        for name in ("x_min_um", "x_max_um", "y_min_um", "y_max_um"):
            _finite(getattr(self, name), name)
        if self.x_min_um > self.x_max_um or self.y_min_um > self.y_max_um:
            raise ValueError("Bounds must be ordered")
        if not isinstance(self.frame_id, str) or not self.frame_id.strip():
            raise ValueError("Bounds require an explicit controller frame_id")

    def contains(self, point):
        x, y = point
        return self.x_min_um <= x <= self.x_max_um and self.y_min_um <= y <= self.y_max_um


@dataclass(frozen=True)
class ScanSettings:
    axis: str
    start_um: float
    end_um: float
    step_um: float
    fixed_um: float
    bounds: StageBounds
    signal_unit: str = "V"
    movement_timeout_s: float = 5.0
    settling_s: float = 0.1
    settling_timeout_s: float = 2.0
    read_timeout_s: float = 1.0
    stop_timeout_s: float = 1.0
    poll_interval_s: float = 0.01
    position_tolerance_um: float = 1.0

    def positions(self):
        """Validate the entire path before any device call; include both ends."""
        if self.axis not in ("x", "y"):
            raise ValueError("axis must be 'x' or 'y'")
        for name in ("start_um", "end_um", "fixed_um", "step_um", "movement_timeout_s",
                     "settling_s", "settling_timeout_s", "read_timeout_s", "stop_timeout_s",
                     "poll_interval_s", "position_tolerance_um"):
            _finite(getattr(self, name), name)
        if any(getattr(self, name) <= 0 for name in
               ("step_um", "movement_timeout_s", "settling_timeout_s", "read_timeout_s",
                "stop_timeout_s", "poll_interval_s")):
            raise ValueError("Step and timeouts/poll interval must be positive")
        if not 0 <= self.settling_s < self.settling_timeout_s or self.position_tolerance_um < 0:
            raise ValueError("Invalid settling duration or position tolerance")
        if not isinstance(self.signal_unit, str) or not self.signal_unit.strip():
            raise ValueError("signal_unit must be explicit")
        distance = abs(self.end_um - self.start_um)
        count = distance / self.step_um
        if not isfinite(count) or count > 99999:
            raise ValueError("Path exceeds 100000 points")
        intervals = ceil(count)
        direction = 1 if self.end_um >= self.start_um else -1
        values = [self.start_um + direction * self.step_um * i for i in range(intervals)]
        values.append(self.end_um)
        points = tuple((v, self.fixed_um) if self.axis == "x" else (self.fixed_um, v) for v in values)
        if any(not self.bounds.contains(point) for point in points):
            raise ValueError("Requested path is outside permitted stage bounds")
        return points


class ScanStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class ScanPoint:
    index: int
    commanded_um: tuple[float, float]
    measured_um: tuple[float, float] | None
    signal: float
    timestamp_unix_s: float
    elapsed_s: float


@dataclass
class ScanResult:
    settings: ScanSettings
    status: ScanStatus = ScanStatus.FAILED
    points: list[ScanPoint] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    output_path: str | None = None
    initial_position_um: tuple[float, float] | None = None
    initial_position_source: str | None = None


class _Cancelled(Exception):
    pass


def _write_record(stream, record):
    # Strict JSON encodes NaN/Inf signal readings as strings, preserving evidence.
    stream.write(json.dumps(record, allow_nan=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _point_record(point):
    record = asdict(point)
    if not isfinite(point.signal):
        record["signal"] = repr(point.signal)
    return {"type": "point", **record}


def scan_1d(settings: ScanSettings, stage: Stage, signal_reader: SignalReader, *,
            output_path: str | Path, cancelled: Callable[[], bool] = lambda: False,
            initial_position_um: tuple[float, float] | None = None,
            clock: Clock = time) -> ScanResult:
    """Scan synchronously and journal every point; never overwrite an output file.

    No default output directory. Parent directory must already exist. If readback
    is unavailable, initial_position_um must be explicitly supplied in the bounds
    frame. This asserts the approach path's start; it is never inferred as zero.
    Cancellation is checked between bounded calls and while waiting. After any
    attempted movement, cancellation/failure requests stop, with no return move.
    Result always retains acquired points, even if storage or stop fails.
    """
    result = ScanResult(settings)
    stream = None
    movement_attempted = False
    started = clock.monotonic()

    def check_cancel():
        if cancelled():
            raise _Cancelled("Cancellation requested")

    def call(method, deadline, *args, check_after=True):
        check_cancel()
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            raise TimeoutError("Operation deadline expired")
        value = method(*args, timeout_s=remaining)
        if check_after and clock.monotonic() >= deadline:
            raise TimeoutError("Adapter exceeded operation deadline")
        return value

    def pause(deadline):
        check_cancel()
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            raise TimeoutError("Movement/settling deadline expired")
        clock.sleep(min(settings.poll_interval_s, remaining))

    def idle(deadline):
        value = call(stage.is_busy, deadline)
        if not isinstance(value, bool):
            raise TypeError("Stage.is_busy must return bool")
        return not value

    try:
        points = settings.positions()
        check_cancel()
        path = Path(output_path).expanduser().absolute()
        stream = path.open("x", encoding="utf-8")
        result.output_path = str(path)
        _write_record(stream, {"type": "header", "schema_version": 1,
                               "settings": asdict(settings), "position_unit": "um",
                               "timestamp_unit": "unix_s", "started_unix_s": clock.time()})
        deadline = clock.monotonic() + settings.movement_timeout_s
        if not idle(deadline):
            raise ValueError("Stage must be idle before scan")
        actual = call(stage.get_position, deadline)
        result.initial_position_source = "readback" if actual is not None else "caller"
        if actual is None:
            actual = initial_position_um
        if actual is None:
            raise ValueError("No initial readback: explicit initial_position_um is required")
        result.initial_position_um = _position(actual)
        if not settings.bounds.contains(result.initial_position_um):
            raise ValueError("Initial position/approach path is outside permitted bounds")
        _write_record(stream, {"type": "initial_position", "position_um": result.initial_position_um,
                               "source": result.initial_position_source})
        for index, target in enumerate(points):
            check_cancel()
            movement_attempted = True
            deadline = clock.monotonic() + settings.movement_timeout_s
            call(stage.move_to, deadline, *target)
            while not idle(deadline):
                pause(deadline)
            # Require an uninterrupted idle settling interval, with its own cap.
            deadline = clock.monotonic() + settings.settling_timeout_s
            idle_since = clock.monotonic()
            while True:
                if not idle(deadline):
                    idle_since = None
                else:
                    if idle_since is None:
                        idle_since = clock.monotonic()
                    if clock.monotonic() - idle_since >= settings.settling_s:
                        break
                pause(deadline)
            measured = call(stage.get_position, deadline)
            if measured is not None:
                measured = _position(measured)
                if not settings.bounds.contains(measured):
                    raise ValueError("Measured position outside permitted bounds")
                if hypot(measured[0] - target[0], measured[1] - target[1]) > settings.position_tolerance_um:
                    raise ValueError("Measured position differs from commanded position")
            read_deadline = clock.monotonic() + settings.read_timeout_s
            # Preserve a reading even if a defective adapter returns it too late.
            value = call(signal_reader.read, read_deadline, check_after=False)
            read_finished = clock.monotonic()
            value = float(value)
            point = ScanPoint(index, target, measured, value, clock.time(), clock.monotonic() - started)
            result.points.append(point)
            _write_record(stream, _point_record(point))
            if read_finished >= read_deadline:
                raise TimeoutError("Signal reader exceeded operation deadline")
            if not isfinite(value):
                raise ValueError("Nonfinite signal acquired")
            check_cancel()
        result.status = ScanStatus.COMPLETED
    except _Cancelled as error:
        result.status = ScanStatus.CANCELLED
        result.reasons.append(str(error))
    except KeyboardInterrupt:
        result.status = ScanStatus.CANCELLED
        result.reasons.append("Keyboard interrupt requested cancellation")
    except Exception as error:
        result.status = ScanStatus.FAILED
        result.reasons.append(f"{type(error).__name__}: {error}")
    finally:
        if movement_attempted and result.status != ScanStatus.COMPLETED:
            try:
                stop_start = clock.monotonic()
                stage.stop(timeout_s=settings.stop_timeout_s)
                if clock.monotonic() - stop_start >= settings.stop_timeout_s:
                    raise TimeoutError("Stop exceeded deadline")
            except Exception as error:
                result.status = ScanStatus.FAILED
                result.reasons.append(f"Stop failed: {error}")
        if stream is not None:
            try:
                _write_record(stream, {"type": "result", "status": result.status.value,
                                       "reasons": result.reasons, "point_count": len(result.points)})
            except Exception as error:
                result.status = ScanStatus.FAILED
                result.reasons.append(f"Journal finalization failed: {error}")
            finally:
                stream.close()
    return result


def load_scan(path: str | Path) -> ScanResult:
    """Read an offline journal, recovering intact points from a truncated tail.

    Missing/damaged completion records are failures, never successful scans.
    """
    with Path(path).open(encoding="utf-8") as stream:
        header = json.loads(stream.readline())
        if header.get("type") != "header" or header.get("schema_version") != 1:
            raise ValueError("Unsupported scan journal")
        values = header["settings"]
        values["bounds"] = StageBounds(**values["bounds"])
        settings = ScanSettings(**values)
        expected = settings.positions()
        result = ScanResult(settings, output_path=str(Path(path).absolute()))
        footer = False
        try:
            for line in stream:
                record = json.loads(line)
                if footer:
                    raise ValueError("Unexpected records after completion")
                kind = record.pop("type")
                if kind == "point":
                    record["commanded_um"] = _position(record["commanded_um"])
                    if record["measured_um"] is not None:
                        record["measured_um"] = _position(record["measured_um"])
                    record["signal"] = float(record["signal"])
                    point = ScanPoint(**record)
                    if point.index != len(result.points) or point.index >= len(expected) or point.commanded_um != expected[point.index]:
                        raise ValueError("Point sequence does not match requested path")
                    result.points.append(point)
                elif kind == "initial_position":
                    result.initial_position_um = _position(record["position_um"])
                    result.initial_position_source = record["source"]
                elif kind == "result":
                    result.status = ScanStatus(record["status"])
                    result.reasons = list(record["reasons"])
                    if record["point_count"] != len(result.points):
                        raise ValueError("Journal point count mismatch")
                    footer = True
                else:
                    raise ValueError("Unknown journal record")
        except (ValueError, KeyError, TypeError) as error:
            result.status = ScanStatus.FAILED
            result.reasons.append(f"Invalid/truncated journal: {error}")
        if not footer:
            result.status = ScanStatus.FAILED
            result.reasons.append("Missing completion record")
        if result.status == ScanStatus.COMPLETED and (len(result.points) != len(expected)
                                                     or any(not isfinite(p.signal) for p in result.points)):
            result.status = ScanStatus.FAILED
            result.reasons.append("Completed journal has incomplete/nonfinite data")
        return result
