"""Stationary, emission-ON NIReflectionReader hardware validation.

Operator enables and confirms hardware emission using the QCL UI before running.
Keep stage stationary. Do not open Objective Scanner or run UI acquisitions/scans.
No other DAQ users may acquire. Manually disable emission after success or failure.
No stage, laser, PI, or SR865A control; no device reset or retries. Values are DAQ volts,
not sensitivity-scaled optical signals. SR865A sensitivity: operator reports 20 mV.
Native Start/Stop/Clear calls cannot be interrupted by the read timeout.
"""

import sys
import time
import traceback

import numpy as np
from instruments import ni_daq as daq
from experiment.scan_adapters import NIReflectionReader


CHANNELS = [b"Dev1/ai0", b"Dev1/ai1"]
SAMPLES = 32
RATE = 100_000
READS = 10
INTERVAL = 0.25
TIMEOUT = 2.0
CLIP = 9.9
OFF_MEAN = 0.00166299400265


def log(message):
    print(message, flush=True)


def checked(status, operation):
    # Some PyDAQmx versions return None after their own error checking.
    log(f"{operation}: status={status!r}")
    if status is not None and status != 0:
        raise RuntimeError(f"{operation} returned DAQmx status {status}")


def configure_owned_task(device):
    # Same finite, internal-clock setup as configure(32, 100000), with checked
    # statuses. The object retains the handle even if later configuration fails.
    checked(daq.DAQmxCreateTask("", daq.byref(device.taskHandle)), "CreateTask")
    if not device.taskHandle.value:
        raise RuntimeError("CreateTask returned no valid task handle")
    for channel in CHANNELS:
        checked(daq.DAQmxCreateAIVoltageChan(
            device.taskHandle, channel, "", daq.DAQmx_Val_Cfg_Default,
            -10.0, 10.0, daq.DAQmx_Val_Volts, None),
            f"CreateAIVoltageChan({channel!r})")
    checked(daq.DAQmxCfgSampClkTiming(
        device.taskHandle, "", RATE, daq.DAQmx_Val_Rising,
        daq.DAQmx_Val_FiniteSamps, SAMPLES), "CfgSampClkTiming")


def describe(label, values, *, ddof):
    values = np.asarray(values, dtype=float)
    log(f"{label}: min={values.min():.12g}, max={values.max():.12g}, "
        f"mean={values.mean():.12g}, std={values.std(ddof=ddof):.12g}, "
        f"peak-to-peak={np.ptp(values):.12g} V (std ddof={ddof})")


def inspect_block(samples, magnitude):
    if samples is None:
        log("Raw shape/statistics/finite/clipping: unavailable; no block returned")
        log("Independent magnitude/reduction agreement: unavailable")
        raise RuntimeError("Reader has no returned raw block")
    raw = np.asarray(samples, dtype=float)
    log(f"Raw array shape: {raw.shape}")
    finite = bool(np.isfinite(raw).all())
    clipping_ok = finite and bool((np.abs(raw) < CLIP).all())
    log(f"All samples finite: {finite}; clipping checks pass: {clipping_ok}")
    if raw.shape != (2, SAMPLES):
        raise RuntimeError(f"Wrong sample dimensions: {raw.shape}")
    describe("X", raw[0], ddof=0)
    describe("Y", raw[1], ddof=0)
    independent = float(np.mean(np.hypot(raw[0], raw[1])))
    agreement = (magnitude is not None and np.isfinite(magnitude)
                 and np.isclose(magnitude, independent, rtol=1e-12, atol=1e-12))
    log(f"Independent mean(hypot(X,Y)): {independent:.12g} V")
    log(f"Reduction agreement: {bool(agreement)}")
    if not finite:
        raise RuntimeError("Non-finite raw samples")
    if not clipping_ok:
        raise RuntimeError("Raw sample at or beyond +/-9.9 V")
    if not agreement:
        raise RuntimeError("Reader/independent reduction missing or mismatched")
    return float(raw[0].mean()), float(raw[1].mean())


def main():
    device = None
    reader = None
    errors = []
    magnitudes, x_means, y_means = [], [], []
    log("Stationary emission-ON DAQ test; emission is operator-confirmed, not queried")
    log("UI may control laser only: no Objective Scanner or UI acquisitions/scans")
    log("No stage, laser, PI, or SR865A control; operator must disable emission afterward")
    log("ON/OFF ratio is not an SNR; subtracting mean magnitudes is not a "
        "calibrated optical background correction")
    log("X=Dev1/ai0; Y=Dev1/ai1; input +/-10 V; clipping threshold +/-9.9 V")
    log("32 samples/channel; requested rate=100000 samples/s/channel; "
        "finite internal clock; default terminal mode; no trigger; reset=False")
    log("10 reads; 0.25 s between reads; 2 s timeout/read")
    try:
        device = daq.MultiChannelAnalogInput(
            CHANNELS, limit=(-10.0, 10.0), reset=False)
        configure_owned_task(device)
        reader = NIReflectionReader(
            device, sample_number=SAMPLES,
            channel_limits=((-CLIP, CLIP), (-CLIP, CLIP)),
            x_channel=0, y_channel=1)
        for index in range(READS):
            log(f"Read {index + 1}/{READS}")
            started = time.monotonic()
            try:
                magnitude = reader.read(timeout_s=TIMEOUT)
            except BaseException:
                log(f"Acquisition elapsed: {time.monotonic() - started:.6f} s")
                log("NIReflectionReader magnitude: unavailable (read raised)")
                try:
                    inspect_block(reader.last_samples, None)
                except Exception as diagnostic_error:
                    log(f"Block diagnostics: {diagnostic_error}")
                raise
            elapsed = time.monotonic() - started
            log(f"Acquisition elapsed: {elapsed:.6f} s")
            log(f"NIReflectionReader magnitude: {magnitude:.12g} V")
            x_mean, y_mean = inspect_block(reader.last_samples, magnitude)
            magnitudes.append(magnitude)
            x_means.append(x_mean)
            y_means.append(y_mean)
            if index + 1 < READS:
                time.sleep(INTERVAL)
    except BaseException as error:
        errors.append(f"{type(error).__name__}: {error}")
        log("FAILURE: stopping without retry")
        traceback.print_exc(file=sys.stdout)
        if reader is not None:
            log(f"Latest returned raw block (None if unavailable): {reader.last_samples!r}")
    finally:
        # This handle starts null and is assigned only by this script's CreateTask.
        # Also clears a partially configured task; never clears/resets other tasks.
        if device is not None and device.taskHandle.value:
            try:
                checked(daq.DAQmxClearTask(device.taskHandle), "ClearTask(owned)")
            except BaseException as error:
                errors.append(f"Cleanup failed: {type(error).__name__}: {error}")
                traceback.print_exc(file=sys.stdout)

    log("Operator: manually disable emission now; this script cannot switch it off")
    log(f"Validated reads: {len(magnitudes)}/{READS}")
    if len(magnitudes) == READS:
        describe("ON block magnitudes", magnitudes, ddof=1)
        on_mean = float(np.mean(magnitudes))
        log(f"ON mean magnitude: {on_mean:.12g} V")
        log(f"ON sample standard deviation: {np.std(magnitudes, ddof=1):.12g} V")
        log(f"ON peak-to-peak variation: {np.ptp(magnitudes):.12g} V")
        log(f"OFF baseline mean: {OFF_MEAN:.12g} V")
        log(f"ON/OFF mean ratio: {on_mean / OFF_MEAN:.12g} (not an SNR)")
        log(f"ON minus OFF mean magnitude: {on_mean - OFF_MEAN:.12g} V")
        log("Subtracting mean magnitudes is not a calibrated optical background correction")
        describe("X block means", x_means, ddof=1)
        describe("Y block means", y_means, ddof=1)
    else:
        log(f"Partial magnitudes (V): {magnitudes!r}")
        log(f"Partial X block means (V): {x_means!r}")
        log(f"Partial Y block means (V): {y_means!r}")
    if errors:
        for error in errors:
            log(f"FAIL: {error}")
        return 1
    log("PASS: 10 stationary ON reads validated and owned task cleared; emission not verified by script")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
