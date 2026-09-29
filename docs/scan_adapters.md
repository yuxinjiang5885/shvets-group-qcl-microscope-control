# Module 6 adapters for existing devices

Author: Yuxin Jiang

Email: yj546@cornell.edu

`experiment.scan_adapters` imports no instrument modules and makes no device calls
on import or construction. It accepts already connected/configured objects owned
by the caller. There is no connection helper, UI entry point, laser control, or
automatic configuration.

## Validation status

Automated tests remain hardware-independent and use fake devices. Separately,
operator-run real-hardware normal-path validation passed: Prior stage readback,
controlled +100 um X motion and return, stationary NI-DAQ acquisition with emission
OFF and ON, an integrated stage + DAQ scan, and horizontal localization of the
500 um gold marker, followed by vertical single-profile localization. Stage
return/readback and owned-resource cleanup passed in
these supervised tests.

Hardware fault injection, protective-stop behavior under a real hardware fault,
and native SDK hang interruption/recovery remain unvalidated. These normal-path
results do not establish recovery safety or hard bounds on native calls.
The later lower-bar Y scan exercised real position-mismatch rejection and saved
68 points plus a failed footer. Its software stop path has only partial evidence;
the journal does not independently verify physical stopping or cleanup.
See [final Module 6 evidence and limitations](module6_hardware_validation.md).

## Stage

`PriorStageAdapter(existing_stage, bounds=stage_bounds)` implements the Module 6
`move_to`, `is_busy`, `get_position`, and `stop` interface using the existing
`stage.message(command)` method. It checks its returned SDK status instead of
using high-level methods that discard errors. Nonzero statuses, malformed replies,
and nonfinite positions raise exceptions. Busy strings `0` through `3` are mapped
explicitly to booleans.

Targets must be integral micrometers, matching the existing driver's command
format. Fractional requests are rejected rather than rounded. Choose integral
start/end/fixed coordinates and step sizes for the entire scan, including its final
endpoint. Pass the same `StageBounds` to `ScanSettings` and the adapter. Targets
and current approach positions must lie within those bounds; the stage must be
idle before a move. Bounds are a caller-verified rectangle in the unchanged current
controller frame, not absolute physical limits or obstacle avoidance.

`stop()` sends `controller.stop.smoothly` and polls until idle, sharing one
deadline across the request and polling. SDK failures or late replies latch
movement off. Stop remains available after a fault. An operator must inspect the
physical state and coordinate frame before reconstructing a faulted adapter.
No home, zero, speed, acceleration, joystick, trigger, or QCL commands are issued.
The caller must establish exclusive stage ownership and appropriate speed before
scanning. Simultaneous callers are unsupported; the legacy stage has a shared
SDK reply buffer.

## DAQ

`NIReflectionReader(existing_analog_input, sample_number=N,
channel_limits=((low_x, high_x), (low_y, high_y)))` implements `read(timeout_s=...)`.
The object must already be configured for the correct channel order, sample count,
sample rate, voltage range, terminal configuration, and untriggered acquisition.
Optional `x_channel` and `y_channel` select the lock-in channels explicitly.
Every configured input requires a clipping interval, including unused channels.
Use limits reflecting the tighter of DAQ rails and detector/lock-in output rails,
with an appropriate experimentally verified margin.

The new `MultiChannelAnalogInput.acquire_bounded(sampleNumber, timeout_s=...)`
method in `instruments/ni_daq.py` starts the existing task, supplies the remaining
time budget to `DAQmxReadAnalogF64`, verifies the actual samples-read count, and
attempts to stop the task even after start/read errors. Nonzero returned DAQmx
statuses, including warnings, are rejected conservatively; raised PyDAQmx errors
are also propagated. If both acquisition and stop fail, both errors are reported.
Legacy `acquire`, `acquire_fast`, and configuration methods are unchanged.

The reader checks returned channel/sample dimensions, finiteness, and clipping on
each raw sample before reduction. The scalar is **mean(hypot(X_i, Y_i)) in volts**,
matching the imaging step-scan convention, not hypot(mean(X), mean(Y)). Configure
`ScanSettings.signal_unit='V'`. `last_samples` retains the latest returned block,
including blocks rejected by the reader, for inspection; it is not a raw-data
journal. If the low-level acquisition itself raises, no block is returned.
The scan's earlier scalar points remain preserved by Module 6.

After a reader error it is faulted and refuses further reads. The caller owns task
clearing and recovery; the adapter never resets a device or clears a task it does
not own. The hardware harness must clear its owned task and check cleanup errors
after exclusive ownership has been established. No DAQ task is created here.

## Timeout limitation: not a hard real-time adapter

The supplied `PriorScientificSDK.h` exposes no timeout argument for
`PriorScientificSDK_cmd`; the existing `message()` blocks inside this call.
Deadlines bound polling and are checked before/after returned SDK calls, but
**cannot preempt a hung native call**. The NI read has a real timeout parameter;
NI StartTask/StopTask have no timeout parameter and cleanup can exceed the budget.
These concrete adapters therefore cannot guarantee the strict bounded-call contract
in `scan_1d.Stage` under a stalled native driver. This limitation is not hidden by
a background thread: there are no abandoned workers that could issue late moves.

Cancellation is acted on between calls. A blocked call can delay cancellation and
software stop indefinitely. Before hardware use, verify actual controller/DAQ
response and timeout behavior with the operator present and a working independent
stop. For a guaranteed bound under DLL hangs, further transport/vendor support or
carefully designed isolation and independent stop hardware is needed. Even killing
a worker cannot undo an already accepted physical move.

## Automated tests (fake devices only)

```powershell
python -B -m unittest discover -s tests -p test_scan_adapters.py -v
python -B -m unittest discover -s tests -p test_reflection_scan.py -v
```

Adapter tests use fake `message()` and analog-input objects. Tests of the actual
`acquire_bounded` implementation extract only that method's AST from the source
file and bind fake DAQ functions, a virtual clock, and in-memory NumPy buffers.
They do not import `instruments.ni_daq` or load PyDAQmx. A subprocess reruns these
tests while blocking instrument, DAQ, serial, Qt, and microscope-UI imports.
Coverage includes mappings, rejected replies/targets, shared stop deadlines,
late returns, clipping, incomplete reads, error cleanup, and scan integration.
This does not test native driver ABI, installation, physical timing, or wiring.

## Hardware-use checks

These are setup/revalidation checks, not a list of completed hardware tests.

1. Confirm actual stage model, units, signs, integral command resolution, readback
   accuracy, and SDK reply/status formats. Verify smooth stop reaches idle and
   test the independent physical/controller stop before emission is enabled.
2. Establish current XY without homing/zeroing; choose safe bounds and a low
   speed/acceleration. Ensure no other UI, gamepad, joystick, or scan owns the
   controller. Confirm the approach path and sample/objective clearance.
3. Verify command latency and timeout/error behavior. Do not deliberately remove
   connections while moving. Confirm the operator can stop independently of Python.
4. Verify DAQ channel mapping to lock-in X/Y, terminal configuration, voltage
   ranges, sample count/rate, untriggered mode, and output clipping rails. Check
   this installed PyDAQmx version's status/exception behavior and task cleanup.
5. Measure detector settling, noise, and reflection polarity. Choose read timeout
   longer than sample_count/sample_rate plus overhead, and verify the default
   settling interval is adequate rather than assuming it is calibrated.
6. With emission off, first check very short stage travel with a fake reader;
   then stationary detector acquisition under normal room laser procedures;
   only then try the supervised short scan described in `reflection_scan.md`.

Neither adapter changes QCL emission. The operator/harness must follow the room's
laser shutdown procedure separately.
