# Module 6 hardware-validation milestone

This record separates operator reports, saved acquisition evidence, offline
analysis, and automated tests. Hardware tests were supervised and run manually;
preparing this document did not issue hardware commands. Module 6 is complete for
bounded single-profile scanning and analysis, with supervised horizontal and
vertical normal-path validation on this setup. Multi-profile registration is
Module 7 and is not established by this milestone.

Related implementation: `29707b7dc09513b83999b50fd23ad73cb9453d07`.
Preserved validation harnesses: `f06ce11c070b26d505a250044fa66070c597de43`.
These are preservation references, not acquisition-time revisions recorded by the
journals. See [scan contracts](reflection_scan.md) and [adapters](scan_adapters.md).

## Operator-established conditions

For the emission-ON measurements, the operator reported:

- Daylight Solutions MIRcat wavenumber: 1500 cm^-1.
- SR865A sensitivity: 20 mV; time constant: 300 us; filter: Advanced 24 dB.
- Lock-in X/Y analog outputs: +/-10 V full scale.
- DAQ X: Dev1/ai0; Y: Dev1/ai1; input range: +/-10 V.
- Raw near-rail rejection: abs(sample) >= 9.9 V.
- 32 samples/channel at 100000 samples/s/channel, finite untriggered acquisition,
  reset=False, 2 s read timeout, using NIReflectionReader/acquire_bounded().
- Stationary checks: 10 reads with 0.25 s between reads.

These settings come from operator reports and preserved harness configuration,
not independent instrument-setting telemetry in the journals. Magnitudes are
DAQ-output volts, not sensitivity-scaled or calibrated optical power.

For integrated scans, the Python QCL UI was closed and the standalone MIRcat GUI
owned laser control. The operator confirmed horizontal sample/objective clearance.
The harnesses did not control the laser, objective or SR865A, home/zero the stage,
or change stage speed/acceleration.

## Operator-reported validation sequence

| Validation | Reported result |
| --- | --- |
| Prior read-only check | COM3 connection, idle checks and position (4918, -23417) um passed; disconnect and CloseSession returned 0; no movement. |
| Controlled stage motion | X moved from 4918 to 5018 um and back, Y=-23417 um; exact readback and busy transitions 1 to 0; cleanup passed. |
| Stationary emission OFF | 10/10 reads passed; mean 0.00166299400265 V, block-magnitude sample std approximately 0.000139186 V, peak-to-peak 0.000397246 V. |
| Stationary emission ON | 10/10 reads passed; mean 0.565619617484 V, sample std 0.000485733976 V, peak-to-peak 0.001475928777 V; X mean approximately 0.563407 V, Y mean approximately -0.049973 V. |
| Standalone MIRcat GUI ownership | Python QCL UI closed; vendor GUI maintained emission while Python owned DAQ. 10/10 reads passed; mean 0.549735089588 V, std 0.001172135655 V, peak-to-peak 0.003474390751 V. |
| Six-point integration | All moves/reads and journal verification passed; return to (4918, -23417) um and stage/DAQ cleanup passed; protective stop not needed; OVERALL PASS. |
| Full horizontal gold scan | 40-point scan completed and returned to (4240, -26100) um. Original offline analysis returned ambiguous_edges despite a clear central plateau. |
| Right-side extension | Diagnostic scan characterized the additional right-side feature; its saved journal records 19 completed points. GDS inspection was reported to show additional real gold structures. |

For stationary checks, the operator reported finite raw samples, no clipping,
agreement between reader output and independent mean(hypot(X,Y)), and successful
owned-task cleanup. ON/OFF mean ratio was approximately 340.12 for the first ON
check. This ratio is not an SNR; subtracting mean magnitudes is not a calibrated
optical background correction. No stationary raw data files are included here.

## Preserved journal evidence

The following original journals are preserved without content changes:

- [Six-point integration](../integrated_scan_f3981a48b9254b4b90956c86573d1896.jsonl)
- [Full gold-patch scan](../gold_patch_scan_d3ea06d804ae4d36ae39f23e1aa1f0f4.jsonl)
- [Right-side extension](../right_side_extension_992fc9673b0042ed912ef6303e29984a.jsonl)

| Journal | Initial readback (um) | X range / step (um) | Fixed Y (um) | Points |
| --- | --- | --- | --- | --- |
| Integration | (4918, -23417) | 4918 to 5018 / 20 | -23417 | 6 |
| Gold patch | (4240, -26100) | 3850 to 4630 / 20 | -26100 | 40 |
| Extension | (4240, -26100) | 4430 to 4790 / 20 | -26100 | 19 |

Inspection confirms each footer records completed status, empty reasons, and the
listed point count. Every saved commanded XY matches its measured XY exactly.
Each journal includes schema version, scan axis/range/step, bounds/frame label,
units, initial position/source, per-point index/command/readback/scalar magnitude,
UNIX timestamps, elapsed times, and completion status. Shared settings are 100 ms
continuous-idle settling, 10 ms polling, 5 s movement timeout, 2 s settling/read/
stop timeouts, and 1 um position tolerance.

Bounds recorded are X [4917,5019], Y [-23418,-23416] for integration;
X [3849,4631], Y [-26101,-26099] for gold; and X [4239,4791],
Y [-26101,-26099] for the extension (including the approach from X=4240).

The journals do NOT record raw X/Y arrays, channel configuration, sample rate/count,
clipping checks, lock-in settings, laser telemetry/emission confirmation, physical
clearance, device serial numbers, calibration, SDK versions, operator identity,
GDS file/hash/selected feature, acquisition-time code revision, or analysis settings
and results. Frame labels are caller labels, not independently verified registration.
Timestamps are computer-clock values, not independently certified timing.
Completed status covers the scan engine, not the subsequent return, disconnect,
session closure or DAQ cleanup. Those outcomes require operator/console evidence;
they cannot be inferred from the journal footer. No fault/stop trace is saved.

## Width-guided offline analysis

Offline reanalysis of the separate journals uses measured coordinates and
`EdgeSettings(expected_width_um=500, width_tolerance_um=100)`, with other defaults
from the core commit. The expected width is a configurable input representing the
operator-selected GDS marker, not a hard-coded measured coordinate. Journals are
not combined. Analysis results below are derived from the saved scalar profiles;
they are not fields originally recorded in those files.

The full gold profile contains three threshold crossings, at approximately
3959.60, 4459.50 and 4629.99 um. The original exactly-two-crossings rule therefore
returned `ambiguous_edges`. Its final elevated point belongs to the beginning of
another reflective feature, supported by the extension and operator GDS review;
it is not treated as random noise.

Updated analysis considers consecutive crossing pairs, applies local support,
contrast/noise/background and width checks, and selects only a unique valid pair.
It does not rank by contrast, order or proximity to expected width. Both bright
and dark candidates are supported; multiple valid candidates remain ambiguous.

The full scan uniquely selects the central bright marker:

| Quantity | Result |
| --- | --- |
| Left edge | 3959.5972266309154 um |
| Right edge | 4459.50397219288 um |
| Width | 499.90674556196427 um |
| Midpoint | 4209.550599411898 um |
| Polarity | bright |
| Support (left / interior / right) | 6 / 25 / 8 samples |
| Local contrast | 3.0445613598332244 V |
| Local noise estimate | 0.036782654674743766 V |
| Crossing indices (zero-based left sample indices) | 5 / 30 |

The other full-scan candidate is dark, 4459.50397219288 to 4629.986406877892 um,
width 170.48243468501187 um, support 25/8/1. It is rejected for
`insufficient_edge_support`, `inconsistent_background`, and `width_mismatch`.

The extension contains crossings at 4460.802899473227, 4628.474327077877,
and 4719.301236459739 um. Its bright neighboring feature spans approximately
4628-4719 um (width 90.8269093818617 um; support 8/5/4) and fails the 500 um
width constraint. Its dark pair spans the first two crossings (width
167.6714276046505 um; support 2/8/5) and fails support and width checks.
The extension therefore returns `no_valid_candidate` for the selected 500 um
marker. This is compatible with a real neighboring feature of different width.
Interpolated digits are reproducibility values, not a claim of submicrometer
physical accuracy or calibrated statistical uncertainty.

## Automated tests and remaining validation

Before the core commit, 47 reflection-scan tests and 25 adapter tests passed.
These tests use fake devices, synthetic/frozen measured profiles, temporary files
and import guards; they do not operate hardware. Frozen regression profiles do
not depend on these journal filenames at runtime. Offline reanalysis during this
document's preparation reproduced the results above without hardware access.

Successful supervised normal operation does not validate:

- Real hardware fault injection.
- Protective-stop behavior during an actual hardware fault.
- Native SDK hang interruption/recovery; synchronous native calls can outlast
  Python deadlines and cannot be preempted by the current adapters.

Full 2D registration and general behavior across other settings/samples remain
outside this milestone.

The three named journals are intentionally tracked evidence. Narrow root-level
ignore patterns exclude future generated journals of these scan families by
default; there is no blanket JSONL ignore rule.

## Final vertical single-profile validation

The unchanged [vertical harness](../vertical_marker_scan_check.py) and
[original journal](../vertical_marker_scan_9392a56a0a0e4517b9b897398376ee3b.jsonl)
extend the preserved evidence to a Y-axis scan. The journal records initial
position (4240, -26100) um, fixed X=4210 um, Y=-26450 to -25750 um at 20 um
spacing, and 36 completed points with no footer reasons. Bounds are
X [4209,4241], Y [-26451,-25749] um. The same timing, tolerance and DAQ settings
were used by the harness. The operator reported successful finalized-journal
verification, return to (4240,-26100), stage cleanup and DAQ cleanup.
As with the other journals, return and cleanup are not encoded in its footer.

Offline reanalysis with expected width 500 um and tolerance 100 um reproduces:

| Quantity | Result |
| --- | --- |
| Lower-Y edge | -26359.297926319337 um |
| Higher-Y edge | -25862.929036293222 um |
| Height | 496.36889002611497 um |
| Y midpoint | -26111.11348130628 um |
| Polarity | bright |
| Support | 5 / 25 / 6 |
| Contrast | 2.8337787738458022 V |
| Noise estimate | 0.17511529707396248 V |
| Crossing indices | 4 / 29 |

There is one valid candidate and no rejection reasons. The combined initial
horizontal/vertical center estimate is (4209.550599411898,-26111.11348130628) um;
this is not a rotation-corrected registration or a calibrated accuracy claim.

## Real position-mismatch failure: partial validation

The abandoned lower-bar rotation experiment provides useful failure evidence.
The local, uncommitted journal
`lower_bar_y_75aa8b468f6441db966efed8a6277fe0.jsonl` records 68 completed points
and a failed footer: `ValueError: Measured position differs from commanded position`.
The last two saved Y readbacks are -26532 and -26527 um for commands -26531 and
-26526 um. The operator reported the next command -26521 um read back -26519 um,
exceeding the unchanged 1 um Euclidean tolerance. That rejected readback is not
itself a saved point. The failed acquisition stopped without an automatic return.

The reviewed engine attempts protective stop after a movement-related failure;
this footer contains no stop-failure reason. That is evidence of the software
failure path, not an independent physical stop trace. The journal does not record
the smooth-stop command/reply, idle transition, return, or cleanup. Physical
stopping effectiveness during an actual controller fault is therefore unvalidated.
No successful repeatability diagnostic has been reported; the origin of the 2 um
error remains unresolved. No production tolerance was relaxed.

## Final status and scope boundary

- **Validated:** supervised Prior HLD117 normal communication and X motion;
  stationary OFF/ON DAQ; vendor GUI ownership; integrated scans; horizontal and
  vertical single-profile localization; width-guided unique feature selection.
  Successful return and cleanup are operator-reported for the successful tests.
- **Partially validated:** real position-mismatch rejection with retained partial
  data and failed footer; software protective-stop path without physical stop
  telemetry or a separately archived console trace.
- **Not validated:** deliberate hardware fault injection, protective-stop
  effectiveness under an actual hardware fault, native SDK hang interruption/
  recovery, and general accuracy/repeatability beyond these supervised trials.

The final wrap-up reran the hardware-independent `test_reflection_scan.py`
(47 tests) and `test_scan_adapters.py` (25 tests). Exact commands are documented
in [scan adapters](scan_adapters.md). No hardware harness was executed.
Square-marker rotation Profiles 1-5, automatic profile classification, production
rotation fitting and refined registration belong to Module 7, not this commit.
