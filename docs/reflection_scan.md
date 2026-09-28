# Module 6: 1D reflection scans

Author: Yuxin Jiang

Email: yj546@cornell.edu

This module provides step-and-measure acquisition through injected interfaces,
durable offline records, and conservative analysis of a single bright or dark
feature. It does not import instruments, operate a laser, register a chip, infer
marker/MS roles, or integrate with Qt. Separate adapters are documented in
[scan_adapters.md](scan_adapters.md).

## Validation status

Automated tests remain hardware-independent. Separately, operator-run real-hardware
normal-path validation passed: Prior stage readback, controlled +100 um X motion
and return, stationary NI-DAQ acquisition with emission OFF and ON, an integrated
stage + DAQ scan, and horizontal localization of the 500 um gold marker. The
horizontal result was approximately 3959.60/4459.50 um edges, 499.91 um width,
and 4209.55 um midpoint. This does not establish vertical localization.

Hardware fault injection, protective-stop behavior under a real hardware fault,
and native SDK hang interruption/recovery remain unvalidated. Successful normal
operation does not remove the native-call timeout limitation described below.

## API

- `experiment.scan_1d.StageBounds`: permitted X/Y rectangle in micrometers and an
  explicit `frame_id` identifying the current controller-coordinate session.
- `ScanSettings`: axis (`x`/`y`), start/end, positive step magnitude, fixed other
  coordinate, bounds, signal unit, movement/read/stop/settling timeouts, settling
  interval, polling interval, and measured-position tolerance.
- `scan_1d(settings, stage, signal_reader, *, output_path, cancelled=...,
  initial_position_um=None, clock=...) -> ScanResult`.
- `ScanResult`: settings, status (`completed`, `cancelled`, `failed`), points,
  reasons, output path, and initial position/source.
- `ScanPoint`: index, commanded XY, optional measured XY, scalar signal, UNIX
  timestamp in seconds at read completion, and monotonic elapsed seconds.
- `load_scan(path)`: recover a completed or interrupted journal for offline use.
- `experiment.reflection_analysis.analyze_edges(positions_um, signals, settings,
  complete=True)` and `analyze_scan(scan_result, settings,
  use_commanded_positions=False)`: return an `EdgeResult`.
- `EdgeSettings`: minimum contrast/SNR, minimum support, optional expected width
  and tolerance, optional saturation rails, background-consistency threshold.
- `experiment.reflection_synthetic.synthetic_profile(...)`: deterministic bright
  or dark test profiles, with optional rounded transitions and seeded noise.

Invalid acquisition settings become a failed result before movement. Bounds
construction and invalid analysis settings raise `ValueError`. Direct calls to
`ScanSettings.positions()` validate settings and raise on invalid paths.

## Acquisition contract and coordinate frame

The complete requested path is validated before any stage call. Both endpoints
are included, with a shorter final step if needed; decreasing coordinates work
without a negative step. A one-point acquisition is permitted, but is insufficient
for edge analysis. At most 100,000 requested points are accepted.

Before the first move, the stage must be idle, and its starting position must be
inside the permitted rectangle. If initial readback is unavailable, the caller
must explicitly supply `initial_position_um`; there is no implicit origin. Its
source is recorded. Convex rectangular bounds validate the approach and all
segments **provided the adapter moves within the rectangle between each pair of
endpoints**. Bounds are not obstacle avoidance, collision detection, or a substitute
for hardware travel limits. Leave physical margin for positioning/stop error.

`frame_id` is a caller-supplied record, not automatic frame-change detection. The
caller must hold exclusive stage ownership and ensure no homing, coordinate
zeroing, joystick movement, or other scan changes that frame during acquisition.
Rebuild bounds after a coordinate reset. In particular, do not run this beside
the existing snake-scan routine, which temporarily resets stage coordinates.

An injected `Stage` implements:

```python
move_to(x_um, y_um, *, timeout_s)  # command position; return promptly
is_busy(*, timeout_s) -> bool
get_position(*, timeout_s) -> tuple[float, float] | None
stop(*, timeout_s)               # request stop AND confirm idle, or raise
```

Each method must honor its supplied timeout and raise on device errors.
An injected `SignalReader.read(*, timeout_s)` returns one scalar with the configured
signal unit. The caller owns instrument setup, sample averaging/reduction, and
resource cleanup. This module never arms, tunes, enables, or disables a laser.

The movement deadline includes commanding and polling. After idle, acquisition
requires a continuous idle settling interval, bounded by a separate settling
deadline. Readback, if available, must be finite, within bounds, and within the
Euclidean position tolerance. Readback is taken before the detector read; this is
step-and-measure, not synchronized continuous acquisition.

All I/O calls are cooperative and synchronous. Deadlines bound polling and are
checked around adapter calls, but Python cannot preempt a hung vendor DLL. A
future adapter must implement real vendor timeouts or another validated bounded
I/O mechanism; simply wrapping the current driver is insufficient. A late signal
returned by a defective adapter is preserved, then marks the scan failed.

Cancellation is a callback such as `threading.Event.is_set`. It is checked before
device calls, during movement/settling waits, and after each saved point. A
keyboard interrupt also cancels. After any movement attempt, failure/cancellation
requests `stop`; a stop failure is reported as failure. There is no return-to-start
move. Cancellation latency includes the currently executing bounded call plus
stop time (and file I/O). Software cancellation cannot replace a physical stop.

## Offline storage

`output_path` is required; there is no default imaging directory. The parent must
exist. Files are created exclusively, so an existing file is never overwritten.
Failure to open/write the header prevents any movement.

The UTF-8 JSON Lines journal contains:

1. A versioned header with complete scan settings, bounds/frame label, units, and
   start time.
2. Initial position and whether it came from readback or caller assertion.
3. One record per acquired point, flushed and `fsync`ed before the next point.
4. Final status, reasons, and point count.

Scalar NaN/infinity readings are retained as JSON strings (`nan`, `inf`, `-inf`)
and fail the scan. The loader restores them as numeric values. No raw multi-channel
DAQ block is captured by this scalar interface; a future reader should document
its scalar definition and keep any needed raw-channel record separately.

On acquisition failure/cancellation, previous points remain both in the returned
result and on disk. If disk I/O itself fails, acquired points remain in memory;
persistence cannot be guaranteed on a failed disk. The loader preserves intact
records before a truncated tail and marks missing/damaged completion as failed.
It never treats an interrupted scan as complete. A journal with an unreadable
header cannot reconstruct settings and raises instead.

## Edge analysis and limitations

Analysis accepts increasing or decreasing positions but rejects duplicates,
reordering, mismatched lengths, nonfinite data, insufficient samples, and
incomplete acquisitions. `analyze_scan` uses measured positions by default and
rejects missing readback; commanded positions require explicit opt-in and are
identified in the result. It never mixes both sources silently.

The algorithm estimates global low/high levels from the 10th/90th percentile
indices and detects half-height crossings (`signal >= threshold` is high).
Each consecutive crossing pair is a candidate: rising/falling for bright markers,
falling/rising for dark markers. It never bridges intervening crossings. Support
comes from the interior and the immediately adjacent uninterrupted runs, bounded
by neighboring crossings or scan endpoints. All three regions need at least three
samples (configurable upward). Local median contrast, outside-level agreement,
first-difference noise and regional RMS residual reject unsuitable candidates.
Dark markers require high outside support; bright markers require low outside
support. Edge positions are linearly interpolated; midpoint is their average.

More than two crossings require `expected_width_um`; otherwise the conservative
legacy ambiguity rejection remains. Supply the selected GDS feature's expected
scan-direction width, accounting for orientation/intersection geometry in the
caller. The analysis does not load GDS data or infer feature identity. If no
absolute `width_tolerance_um` is supplied, tolerance is 20% of expected width.
Exactly one candidate passing all checks is selected. Multiple passing candidates
remain `ambiguous_edges`; none yields `no_valid_candidate` for multi-pair data.
Single-pair failures retain their existing reason codes. No ranking by strength,
order, or width proximity occurs. Width is a rejection constraint, not evidence
of missing edges or proof of GDS identity.

`EdgeResult.candidates` contains immutable `EdgeCandidate` diagnostics: interpolated
edges, midpoint, width, polarity, `(left, interior, right)` support counts, local
contrast/noise, and all rejection reasons. `crossing_indices` are zero-based left
sample indices in increasing-position order, including for reversed input.
`valid` means the candidate has no rejection reasons. The selected result also
reports `support_counts`. Invalid results never expose a selected midpoint;
candidate midpoints remain diagnostic only. Top-level contrast/noise on failure
describe the global profile; candidate diagnostics provide the local quantities.

For a 500 um marker, for example, use
`EdgeSettings(expected_width_um=500, width_tolerance_um=100)`.
The measured full gold-patch regression selects the approximately 499.91 um bright
pair despite a later partial feature. The separate right-side extension contains
no complete supported 500 um candidate and is rejected. These profiles are frozen
in tests; runtime tests do not require hardware journals or merge scans.

This conservative method targets reasonably sampled plateaus with background on
both sides. Very narrow features (roughly less than 10% occupancy), broad smooth
transitions, strong drift, or sparse scans may be rejected. It does not estimate
rotation, fit arbitrary shapes, or report calibrated statistical uncertainty.
Thresholds are software defaults, not validated QCL-room settings.

Saturation detection requires caller-supplied rails in the scalar signal's units.
A flat-topped feature alone does not establish clipping. If magnitude/averaging
could conceal clipping of an individual DAQ channel, the future reader must check
raw channels and report that failure rather than return a plausible scalar.

Example using synthetic data only:

```python
from experiment.reflection_synthetic import synthetic_profile
from experiment.reflection_analysis import EdgeSettings, analyze_edges

positions = list(range(101))
signals = synthetic_profile(positions, edges_um=(30, 70), transition_um=0.5,
                            noise_std=0.01, seed=42)
result = analyze_edges(positions, signals,
                       EdgeSettings(expected_width_um=40, width_tolerance_um=3))
assert result.valid
print(result.midpoint_um, result.width_um)
```

## Hardware-independent verification

```powershell
python -B -m unittest discover -s tests -p test_reflection_scan.py -v
```

Automated tests use fake devices, a virtual clock, synthetic signals, frozen
measured profiles, and temporary files. They do not access hardware. The suite
also reruns its acquisition/analysis tests in a subprocess that
blocks instrument, DAQ, serial, Qt, and microscope-UI imports. Do not substitute
repository-wide discovery: separate legacy scripts are hardware-oriented.

## Hardware integration boundary

`PriorStageAdapter` and `NIReflectionReader` now wrap existing connected/configured
objects without connecting or issuing commands during construction. Actual device
operations begin when their methods are called, including through `scan_1d`.
See [scan_adapters.md](scan_adapters.md) for contracts, hardware-independent tests, and the
native-call timeout limitation. Before hardware use, verify these assumptions:

- `instruments.hld117.stage.goto` rounds command coordinates to integers; confirm
  units/resolution and set step/tolerance accordingly.
- `busy()` returns strings (`0`, `1`, `2`, `3`); translate deliberately to bool.
- `get_position()` supplies two floats in the current resettable frame. Confirm
  actual readback resolution, sign, repeatability, and controller error behavior.
- `message()` prints nonzero SDK status rather than raising; an adapter must
  surface errors and provide bounded calls. `stop_smoothly()` alone does not
  confirm completion; the adapter must poll idle under the stop deadline.
- `MultiChannelAnalogInput.acquire(sampleNumber)` returns channel/sample arrays,
  uses a fixed 20-second timeout, and does not validate returned sample count.
  The new reader uses `acquire_bounded()` instead, validates raw counts/clipping,
  and defines its scalar reduction. The caller still owns task clearing.
- Detector settling time, physical reflection polarity, clipping rails, and the
  relationship between controller coordinates and safe travel require measurement.

## Supervised hardware-use checklist

The following is setup guidance, not a record of completed validation. In
particular, cancellation/fault exercises below remain unvalidated on hardware.

1. First review the adapters with the operator present. Keep emission off
   for the initial movement check. Confirm the physical stop works, the stage is
   idle, the sample has clearance, and no other code/joystick controls the stage.
   Read and record current XY and the controller frame without homing or zeroing.
2. Agree on a small permitted rectangle around that verified position. A proposed
   first software cap is **current X/Y +/-10 um**, with a line from **current
   axis -5 um to +5 um**, at **1 um steps**, holding the other axis fixed. These
   are conservative test caps, not validated machine-safe limits; reduce them
   if physical clearance requires it. Use an operator-approved low stage speed.
3. With emission off and a fake reader, verify the short X line, its reverse,
   and then Y/reverse, checking measured positions and saved journals. Exercise
   cancellation and confirm idle before proceeding.
4. Only under the room's normal operator-controlled laser procedure, establish a
   stable stationary reflection reading and validate the real reader, raw-channel
   clipping checks, timeout, and settling time. Run one short line with a fresh
   output path. Inspect signals and positions before any repeat.
5. Such a short line may not span both feature edges: expect an incomplete/flat
   analysis result. Expand bounds/span only after a new physical-clearance review
   and explicit operator agreement; never expand automatically to find an edge.
6. To stop, set the cancellation event (or Ctrl+C in a foreground test harness).
   Confirm the adapter requests stop and the controller reports idle. If that
   does not happen promptly, use the verified physical/controller stop and the
   room's laser shutdown procedure. This API does not turn off QCL emission.

The automated test commands above perform no controller connection or laser/DAQ
operation.
