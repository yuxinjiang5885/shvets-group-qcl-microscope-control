"""Six-point supervised hardware scan using the unchanged Module 6 engine.

Python QCL UI must be closed; vendor MIRcat GUI controls emission independently.
Operator verifies clearance, exclusive stage/DAQ ownership, and emission state.
No laser, objective, SR865A, homing, zeroing, speed, or acceleration controls.
Native calls can hang beyond deadlines. Keep independent stop available.
The operator must disable emission after completion or failure.
"""

import argparse
from math import hypot
from pathlib import Path
import sys
import time
import traceback
from uuid import uuid4

from instruments.hld117 import stage
from instruments import ni_daq as daq
from experiment.scan_adapters import PriorStageAdapter, NIReflectionReader
from experiment.scan_1d import StageBounds, ScanSettings, ScanStatus, scan_1d, load_scan


START = (4918, -23417)
TARGETS = tuple((x, START[1]) for x in range(4918, 5019, 20))
BOUNDS = StageBounds(4917, 5019, -23418, -23416,
                     frame_id="integrated-six-point-current-controller-frame")
SETTINGS = ScanSettings(
    axis="x", start_um=4918, end_um=5018, step_um=20, fixed_um=-23417,
    bounds=BOUNDS, signal_unit="V", movement_timeout_s=5.0,
    settling_s=0.1, settling_timeout_s=2.0, read_timeout_s=2.0,
    stop_timeout_s=2.0, poll_interval_s=0.01, position_tolerance_um=1.0)


def log(message):
    print(message, flush=True)


def checked(status, operation):
    log(f"{operation}: status={status!r}")
    if status is not None and status != 0:
        raise RuntimeError(f"{operation} failed: {status}")


def configure_daq(device):
    # Same checked finite configuration as the validated stationary harness.
    checked(daq.DAQmxCreateTask("", daq.byref(device.taskHandle)), "CreateTask")
    if not device.taskHandle.value:
        raise RuntimeError("No valid DAQ task handle")
    for channel in device.physicalChannel:
        checked(daq.DAQmxCreateAIVoltageChan(
            device.taskHandle, channel, "", daq.DAQmx_Val_Cfg_Default,
            -10.0, 10.0, daq.DAQmx_Val_Volts, None), f"CreateChannel {channel!r}")
    checked(daq.DAQmxCfgSampClkTiming(
        device.taskHandle, "", 100000, daq.DAQmx_Val_Rising,
        daq.DAQmx_Val_FiniteSamps, 32), "Configure finite internal clock")


class GuardedStage(stage):
    def __init__(self):
        self.move_attempts = 0
        self.return_authorized = False
        super().__init__(model="HLD117")

    def message(self, command, verbose=False):
        allowed = {"controller.connect 3", "controller.disconnect",
                   "controller.stage.position.get", "controller.stage.busy.get"}
        moving = command.startswith("controller.stage.goto-position")
        if moving:
            sequence = TARGETS + (START,)
            if self.move_attempts >= len(sequence):
                raise RuntimeError("Additional movement blocked")
            x, y = sequence[self.move_attempts]
            if command != f"controller.stage.goto-position {x} {y}":
                raise RuntimeError(f"Out-of-sequence target blocked: {command}")
            if self.move_attempts == len(TARGETS) and not self.return_authorized:
                raise RuntimeError("Return blocked: scan/journal not verified")
            log(f"Driver-entry movement attempt: {command}")
            self.move_attempts += 1
        elif command == "controller.stop.smoothly":
            if not self.move_attempts:
                raise RuntimeError("Physical stop blocked before movement attempt")
        elif command not in allowed:
            raise RuntimeError(f"Command blocked: {command}")
        status, reply = super().message(command, verbose=verbose)
        if status != 0:
            raise RuntimeError(f"{command}: status={status}, reply={reply!r}")
        return status, reply


class ReportingStage(PriorStageAdapter):
    def __init__(self, device):
        super().__init__(device, bounds=BOUNDS, poll_interval_s=0.01)
        self.stop_attempted = False
        self.stop_result = "not needed"
        self.target = None
        self.measured = None

    def move_to(self, x_um, y_um, *, timeout_s):
        self.target = (x_um, y_um)
        self.measured = None
        log(f"Commanded coordinate: {self.target} um")
        return super().move_to(x_um, y_um, timeout_s=timeout_s)

    def get_position(self, *, timeout_s):
        self.measured = super().get_position(timeout_s=timeout_s)
        log(f"Measured coordinate: {self.measured} um")
        return self.measured

    def stop(self, *, timeout_s):
        if not self._stage.move_attempts:
            self.stop_result = "suppressed: no driver-entry movement attempt"
            log(self.stop_result)
            return
        self.stop_attempted = True
        self.stop_result = "attempted; idle not confirmed"
        super().stop(timeout_s=timeout_s)
        self.stop_result = "smooth stop confirmed idle"
        log(self.stop_result)


class ReportingReader(NIReflectionReader):
    def __init__(self, device, stage_adapter):
        super().__init__(device, sample_number=32,
                         channel_limits=((-9.9, 9.9), (-9.9, 9.9)),
                         x_channel=0, y_channel=1)
        self.stage_adapter = stage_adapter

    def read(self, *, timeout_s):
        value = super().read(timeout_s=timeout_s)
        log(f"Acquired: command={self.stage_adapter.target}, "
            f"measured={self.stage_adapter.measured}, magnitude={value:.12g} V "
            "(engine journals this point next)")
        return value


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("Return deadline expired")
    return value


def return_to_start(adapter):
    if adapter.is_busy(timeout_s=2.0):
        raise RuntimeError("Stage busy before return")
    position = adapter.get_position(timeout_s=2.0)
    if not BOUNDS.contains(position) or hypot(
            position[0] - TARGETS[-1][0], position[1] - TARGETS[-1][1]) > 1:
        raise RuntimeError("Unexpected scan endpoint before return")
    deadline = time.monotonic() + 5.0
    adapter.move_to(*START, timeout_s=remaining(deadline))
    while adapter.is_busy(timeout_s=remaining(deadline)):
        time.sleep(min(0.01, remaining(deadline)))
    remaining(deadline)
    deadline = time.monotonic() + 2.0
    idle_since = None
    while True:
        busy = adapter.is_busy(timeout_s=remaining(deadline))
        now = time.monotonic()
        remaining(deadline)
        if busy:
            idle_since = None
        elif idle_since is None:
            idle_since = now
        elif now - idle_since >= 0.1:
            break
        time.sleep(min(0.01, remaining(deadline)))
    position = adapter.get_position(timeout_s=remaining(deadline))
    if not BOUNDS.contains(position) or hypot(
            position[0] - START[0], position[1] - START[1]) > 1:
        raise RuntimeError("Return position outside 1 um tolerance")
    if adapter.is_busy(timeout_s=remaining(deadline)):
        raise RuntimeError("Stage busy after return readback")
    remaining(deadline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent /
                        f"integrated_scan_{uuid4().hex}.jsonl")
    output = parser.parse_args().output.absolute()
    device = analog = adapter = reader = result = None
    connection_attempted = False
    errors = []
    scan_report = "not started"
    return_report = "not attempted"
    stage_cleanup = "no session created"
    daq_cleanup = "no task created"
    log("REQUIRES: Python QCL UI closed; exclusive stage/DAQ access; safe path")
    log("Vendor GUI controls laser only; operator confirms emission and settings")
    log(f"Targets: {TARGETS}; output: {output}")
    try:
        if not output.parent.is_dir() or output.exists():
            raise ValueError("Output must be a new file in an existing directory")
        device = GuardedStage()
        if device.session < 0:
            raise RuntimeError("Invalid Prior SDK session")
        adapter = ReportingStage(device)
        connection_attempted = True
        checked(device.message("controller.connect 3")[0], "Connect COM3")
        if adapter.is_busy(timeout_s=2.0):
            raise RuntimeError("Initially busy; no movement authorized")
        if adapter.get_position(timeout_s=2.0) != START:
            raise RuntimeError("Initial position must be exactly (4918, -23417)")
        analog = daq.MultiChannelAnalogInput(
            [b"Dev1/ai0", b"Dev1/ai1"], limit=(-10.0, 10.0), reset=False)
        configure_daq(analog)
        reader = ReportingReader(analog, adapter)
        # Recheck after DAQ setup, immediately before entering the engine.
        if adapter.is_busy(timeout_s=2.0) or adapter.get_position(timeout_s=2.0) != START:
            raise RuntimeError("Initial idle/coordinate gate changed during setup")
        scan_report = "started; completion not verified"
        result = scan_1d(SETTINGS, adapter, reader, output_path=output)
        scan_report = f"{result.status.value}; {len(result.points)}/6 points; {result.reasons}"
        for point in result.points:
            log(f"Result point {point.index}: commanded={point.commanded_um}, "
                f"measured={point.measured_um}, magnitude={point.signal:.12g} V")
        if result.status != ScanStatus.COMPLETED or len(result.points) != 6:
            raise RuntimeError("Scan unsuccessful: return prohibited")
        saved = load_scan(output)
        if (saved.status != ScanStatus.COMPLETED or len(saved.points) != 6
                or saved.points != result.points or saved.settings != SETTINGS
                or saved.initial_position_um != START):
            raise RuntimeError("Journal verification failed: return prohibited")
        scan_report = "completed; all 6 points and finalized journal verified"
        device.return_authorized = True
        return_report = "started; not yet verified"
        return_to_start(adapter)
        return_report = "PASS: idle, within 1 um of original position"
    except BaseException as error:
        errors.append(f"{type(error).__name__}: {error}")
        traceback.print_exc(file=sys.stdout)
        if return_report == "started; not yet verified":
            return_report = "FAILED; no retry"
        if adapter is not None and device.move_attempts and not adapter.stop_attempted:
            try:
                adapter.stop(timeout_s=2.0)
            except BaseException as stop_error:
                errors.append(f"Protective stop failed: {stop_error}; use independent stop")
        if reader is not None:
            log(f"Latest returned raw DAQ block: {reader.last_samples!r}")
        log("No further positioning commands will be issued")
    finally:
        if analog is not None and analog.taskHandle.value:
            try:
                checked(daq.DAQmxClearTask(analog.taskHandle), "Clear owned DAQ task")
                daq_cleanup = "PASS"
            except BaseException as error:
                daq_cleanup = f"FAILED: {error}"
                errors.append(daq_cleanup)
        if device is not None and device.session >= 0:
            cleanup_errors = []
            try:
                if connection_attempted:
                    checked(device.message("controller.disconnect")[0], "Disconnect stage")
            except BaseException as error:
                cleanup_errors.append(f"Disconnect: {error}")
            finally:
                try:
                    checked(device.close_session(), "CloseSession")
                except BaseException as error:
                    cleanup_errors.append(f"CloseSession: {error}")
            stage_cleanup = "PASS" if not cleanup_errors else repr(cleanup_errors)
            errors.extend(cleanup_errors)
    log(f"Scan: {scan_report}")
    log(f"Return: {return_report}")
    log(f"Stage cleanup: {stage_cleanup}")
    log(f"DAQ cleanup: {daq_cleanup}")
    log(f"Driver-entry move attempts: {device.move_attempts if device else 0}")
    log(f"Protective stop: {adapter.stop_result if adapter else 'not attempted'}")
    log(f"Journal: {output}; footer describes scan only, not return/cleanup")
    log("Operator: disable laser emission manually after this test")
    for error in errors:
        log(f"FAIL: {error}")
    log("OVERALL FAIL" if errors else "OVERALL PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
