# QCL GDS-Based Metasurface Localization — Module Plan

This is the authoritative module roadmap. Review and update it before starting a
module, declaring a module complete, or committing completed module work.
Module 8-10 workflow design reviewed on 2026-09-30; earlier module evidence retains its recorded dates. Completion is scoped to the
exit criteria below; it does not imply universal hardware reliability.

## Project goal

Start from a GDS layout and an approximately located physical chip, identify and
register a selected gold marker using reflection scans, establish the transform
from GDS-local to physical-stage coordinates, let the user select metasurface
pixels, safely move to their physical locations, and integrate registration with
the QCL imaging workflow.

## Architecture principles

- Users select marker/MS semantics manually where appropriate. Geometry extraction
  and presentation must not unnecessarily guess feature roles.
- Hardware access stays behind adapters. Algorithms remain independently testable
  without hardware; hardware operations fail closed.
- Prefer measured coordinates over commanded coordinates.
- Registration carries explicit coordinate-frame and orientation assumptions.
  Current operator-confirmed orientation is `FLIP_X`; scale is 1 and shear absent.
- Module 5 maps `stage = translation + rotation * orientation * local`, with
  positive rotation counterclockwise after orientation. Local origin is the
  selected marker center; units are micrometers.
- Registration QC precedes automatic MS movement. Bounds require operator-verified
  clearance and are not obstacle avoidance.
- Module 6 supervised development used Python QCL UI closed with vendor MIRcat
  control. Integrated Module 8-10 operation must instead establish singular laser
  ownership and exclusive shared stage/DAQ ownership; do not assume both laser
  controllers may coexist. No unreviewed hardware runs.
- Journals prove acquisition facts, not laser settings, return, cleanup or physical
  stopping effectiveness. Preserve the provenance distinctions in the evidence.

## Module overview

| Module | Name | Responsibility | Status | Primary outputs | Depends on |
| --- | --- | --- | --- | --- | --- |
| 1 | Chip-local geometry model | Geometry and local coordinates | COMPLETE | ChipLayout | None |
| 2 | GDS parsing / feature extraction | Read geometry and identities | COMPLETE | GDSLayout, selectable features | None; feeds 1 through 4 |
| 3 | Interactive GDS preview | Inspect geometry and hierarchy | COMPLETE | Preview and selection | 2 |
| 4 | Manual marker / MS selection | User-defined semantics | COMPLETE | Assignments, ChipLayout | 1–3 |
| 5 | GDS-local to stage transform | Orientation, rotation, translation | COMPLETE AT ALGORITHM LEVEL | StageRegistration, StageLayout | 1, 4 |
| 6 | 1D reflection scan and single-scan edge analysis | Adapters, scans, journals, edges | COMPLETE / HARDWARE VALIDATED within documented limits | ScanResult, EdgeResult | Hardware adapters; geometry supplies width prior |
| 7 | Automatic square-marker registration | Multi-profile classification, fitting, QC | COMPLETE within documented validation limits | Offline center/angle; qualitative overlay agreement | 4–6 |
| 8 | Auto Location / Locate Marker | Automatic localization and registered preview | COMPLETE / LIVE VALIDATED | UI with QC/invalidation | 3–7 |
| 9 | Registered feature navigation | Click prediction / guarded center motion | NOT STARTED | Target prediction and motion/readback outcome | 5–8 |
| 10 | Scanning ROI / Snake Scan MVP | Width/Height ROI to existing Snake Scan | NOT STARTED | ROI/start preview and guarded scan | 8–9 |

## Detailed modules

### Module 1 — Chip-local geometry model

**Purpose** Represent chip/GDS geometry with a marker-relative origin.

**Inputs** Named MS geometry and a square marker, in GDS micrometers.

**Outputs** SquareMarker, MSPixel and ChipLayout; local centers by subtraction.

**Key files** `experiment/chip_layout.py`; `tests/test_chip_layout.py`.

**Dependencies** None of the later modules; hardware-independent.

**Completed work** Geometry validation, marker origin, local-coordinate updates,
lookup, unique names and summaries.

**Remaining work** None within this scope; callers must recalculate after edits.

**Validation / tests** Existing tests cover geometry, invalid input, lookup,
duplicates, updates and summaries. Not rerun during this documentation task.

**Exit criteria** Valid layouts preserve GDS geometry and produce explicit local
coordinates without hardware or stage-frame assumptions. Met at module scope.

**Relevant commits** `d1e626439c9842c6fb5acaf42b6bb7c26a8a4859`.

### Module 2 — GDS parsing / feature extraction

**Purpose** Extract geometry without inferring marker/MS roles.

**Inputs** GDS file and selected root/hierarchy traversal.

**Outputs** Unit-normalized GDSLayout and deterministic selectable feature IDs.

**Key files** `experiment/gds_layout.py`, `inspect_gds_features.py`,
`requirements-gds.txt`, `docs/gds_layout.md`, `tests/test_gds_layout.py`.

**Dependencies** gdstk; no hardware modules.

**Completed work** Hierarchy, transformed instances, arrays/pagination, bounds,
units, metadata and input validation.

**Remaining work** None within this scope. External S37a fixture availability is
environment-specific; geometry does not establish fabrication success.

**Validation / tests** Synthetic transform/identity tests and optional S37a
integration test exist; not rerun for this wrap-up.

**Exit criteria** Stable geometry and identities in explicit frames, without
semantic guesses. Met at module scope.

**Relevant commits** `905836a89b53d9a39dc6f2b2fe19985c9c4c50ec`.

### Module 3 — Interactive GDS preview

**Purpose** Display extracted geometry for inspection and selection.

**Inputs** Module 2 layout and user navigation.

**Outputs** Geometry view, hierarchy navigation and selected feature information.

**Key files** `ui/gds_preview.py`, `ui/gds_preview_scene.py`,
`preview_gds_layout.py`, `docs/gds_preview.md`, `tests/test_gds_preview.py`.

**Dependencies** Module 2, PyQt6.

**Completed work** Pan/zoom, roots, selection/overlap cycling, hierarchy and
explicit array instances; standalone hardware-independent preview.

**Remaining work** Main microscope integration belongs to Module 8.

**Validation / tests** Existing UI/geometry and import-isolation tests; not rerun
here. Manual behavior and limitations are described in the preview documentation.

**Exit criteria** User can inspect/select identifiable geometry without microscope
initialization. Met for the standalone preview.

**Relevant commits** `1647f397e47e69a814e38072b01d20cd1850e43e`.

### Module 4 — Manual marker / MS selection

**Purpose** Let the user assign semantic roles to selected physical occurrences.

**Inputs** Module 2 feature identities and user marker/MS choices.

**Outputs** LayoutAssignments and fresh ChipLayout snapshots with local offsets.

**Key files** `experiment/layout_assignment.py`, `ui/gds_assignment.py`,
`docs/gds_assignment.md`, `tests/test_layout_assignment.py`,
`tests/test_gds_assignment.py`.

**Dependencies** Modules 1–3.

**Completed work** Assignment/removal, renaming, role/conflict validation, marker
replacement confirmation, table/overlays and invalidation of local coordinates.

**Remaining work** Saved assignment/registration lifecycle is not established;
interactive assignments are session state, not inferred from test examples.

**Validation / tests** Existing backend/UI and optional S37a workflow tests;
not rerun during this wrap-up.

**Exit criteria** Manual roles consistently produce valid local geometry and
reject conflicting frames/assignments. Met for session-based assignment.

**Relevant commits** `eace06fe32c21b22344208e28524a4a7ae06a9ab`.

### Module 5 — GDS-local to stage transform

**Purpose** Apply supplied registration parameters mathematically.

**Inputs** Marker stage center, orientation, rotation angle and chip-local points.

**Outputs** StageRegistration, forward/inverse points and StageLayout.

**Key files** `experiment/stage_registration.py`, `docs/stage_registration.md`,
`tests/test_stage_registration.py`.

**Dependencies** Module 1 geometry; Module 4 supplies assigned layouts.

**Completed work** Eight explicit orientations, default FLIP_X, rotation then
translation, inverse mapping, validation and immutable layout snapshots.

**Remaining work** Physical calibration/QC depends on Module 7; no parameter
fitting, hardware movement, arbitrary scaling or shear is implemented here.

**Validation / tests** Analytic mappings, round trips and historical numerical
regressions exist; they do not prove current-sample registration. Not rerun here.

**Exit criteria** Correct forward/inverse math with explicit frames and unchanged
inputs. Met at algorithm level; physical validation remains downstream.

**Relevant commits** `ff7379a4989b1434d0ba203050a0266f4c8fd918`.

### Module 6 — 1D reflection scan and single-scan edge analysis

**Purpose** Bounded real-device scans, durable partial data and conservative
single-profile edge selection.

**Inputs** ScanSettings, safe StageBounds, stage/reader adapters, output journal
and optional expected feature width.

**Outputs** Per-point journal, ScanResult, measured edges/midpoint/width/polarity
and support/contrast/noise/candidate diagnostics.

**Key files** `experiment/scan_1d.py`, `experiment/scan_adapters.py`,
`instruments/ni_daq.py`, `experiment/reflection_analysis.py`,
`experiment/reflection_synthetic.py`, `tests/test_reflection_scan.py`,
`tests/test_scan_adapters.py`, `docs/reflection_scan.md`, `docs/scan_adapters.md`,
`docs/module6_hardware_validation.md`, `vertical_marker_scan_check.py`.
The evidence document links archived journals and earlier supervised harnesses.

**Dependencies** Existing Prior/NI drivers behind adapters; geometry supplies the
width prior. Pure analysis and fake-device tests require no hardware.

**Completed work** Movement/idle/settling/readback/acquisition loop; flushed
per-point journals and recovery; bounded NI reads; validation and failure stops;
bright/dark consecutive-pair analysis, local QC and uniqueness-only width guidance.
Real normal-path readback, motion, OFF/ON DAQ, vendor-GUI ownership, integration,
horizontal and vertical single-profile localization passed under supervision.

**Remaining work** Deliberate hardware fault injection, physical stop effectiveness
under actual faults and native SDK hang interruption/recovery remain unvalidated.
The 2 um Y mismatch cause remains unresolved; tolerance stays 1 um. These explicit
limitations do not become guarantees merely because Module 6 is closed.

**Validation / tests** Wrap-up commands, both hardware-independent:

```powershell
python -B -m unittest discover -s tests -p test_reflection_scan.py -v
python -B -m unittest discover -s tests -p test_scan_adapters.py -v
```

47 + 25 tests passed. Vertical journal reanalysis reproduced the recorded edges.
See the evidence document for journal facts versus operator reports and partial
failure-path evidence. No hardware commands were issued during this wrap-up.

**Exit criteria** Supervised bounded single scans persist/reload data and return
unique edges or explicit failure; fake-device regressions pass; hardware evidence
and limitations are recorded. Met within the documented scope.

**Relevant commits**

- `29707b7dc09513b83999b50fd23ad73cb9453d07` — core implementation/tests/docs.
- `f06ce11c070b26d505a250044fa66070c597de43` — supervised harnesses.
- `3bf04f401f3c40d204c96f0be426d02c63c0d3f6` — horizontal evidence.
- `cd743c9489128b66c16c20dcfbbf8c191175ec7b` — final vertical evidence and status;
  pushed to `yuxin/feature/gds-layout-registration`.

### Module 7 — Automatic square-marker registration

**Purpose** Rough marker position -> initial H/V center -> multiple horizontal
profiles -> CENTRAL / CORNER_AFFECTED / INCONSISTENT / INVALID classification ->
rotation fit -> rotation-corrected center refinement -> QC -> (x_center,y_center,theta).

**Inputs** Selected square geometry, measured profiles and explicit Module 5 frame,
orientation and unit-scale assumptions.

**Outputs** Accepted offline StageRegistration, residuals, uncertainty/limitations
and diagnostics; qualitative QCL-image physical overlay agreement. Quantitative
physical localization accuracy is **NOT CALIBRATED**.

**Key files** `experiment/marker_profile_classification.py`,
`tests/test_marker_profile_classification.py`,
`square_marker_profile_classification_check.py`; the five original profile
journals listed explicitly in the evaluator are preserved as offline evidence.
The five repetitive one-off profile hardware harnesses were removed at Module 8
closeout; the committed journals and offline evaluators remain available.
Production rotation: `experiment/marker_rotation.py`,
`tests/test_marker_rotation.py`, `square_marker_rotation_fit_check.py`.
Center refinement: `experiment/marker_center_refinement.py`,
`tests/test_marker_center_refinement.py`, `square_marker_center_refinement_check.py`.
Stage integration: `experiment/marker_stage_registration.py`,
`tests/test_marker_stage_registration_integration.py`,
`square_marker_stage_registration_check.py`.
Overlay validation: `experiment/qcl_registration_validation.py`,
`ui/gds_validation_selection.py`, `square_marker_qcl_overlay_check.py`,
`tests/test_qcl_registration_validation.py`.
Permanent evidence: [overlay validation note](evidence/module7/qcl_overlay_validation.md),
PNG overlay and selection/prediction JSON in `docs/evidence/module7/`.

**Dependencies** Modules 4–6.

**Completed work** Automatic horizontal-profile classification:
**COMPLETE / OFFLINE VALIDATED**. Module 7 is **COMPLETE within documented validation limits**.
Initial horizontal/vertical scans and five horizontal profiles were collected.
Validated states are CENTRAL / CORNER_AFFECTED / INCONSISTENT / INVALID.
The classifier uses one deterministic seed, midpoint-based provisional rotation,
geometric central/corner boundaries and guard, robust width screening, and separate
edge/midpoint residual screening. Final count/distinct-Y/Y-span and seed-support
gates fail closed; `usable_final_fits` is None after any failed set-level QC.
There is no iterative trimming, alternate-seed search or historical-angle dependence.
Provisional rotation and QC lines are not production registration outputs.

Production marker rotation fitting: **COMPLETE / OFFLINE VALIDATED**.
It requires successful classifier set-level QC and exactly the complete accepted
CENTRAL geometry. It fits left/right/midpoint lines once using measured Y and
the accepted Y mean as reference. The sole accepted rotation is
`theta_mid = -degrees(atan(dx_mid/dy))`, consistent with Module 5.
Slope standard errors, propagated midpoint angular statistical SE, RMS/max
residuals, per-profile residuals and width statistics are reported.
`accepted_theta_deg` equals `theta_mid_deg` only when valid; it is None on any
hard QC failure. Warnings are separate from failure reasons. No profile deletion,
subset search, iterative trimming, angle averaging or historical-angle dependence.

Rotation-corrected marker-center refinement: **COMPLETE / OFFLINE VALIDATED**.
It requires a valid production rotation and its `accepted_theta_deg`, reuses the
approved horizontal midpoint fit without reselection/refitting, and reanalyzes
the committed vertical journal using measured X. The center is the algebraic
intersection of horizontal and vertical centerline constraints. Measured-X
stability, vertical chord height, central-region guard and constraint-substitution
checks fail closed: both output center coordinates are None on hard failure.
Angle-fit sensitivity is reported; no hardware or StageRegistration is invoked.

StageRegistration integration: **COMPLETE / OFFLINE VALIDATED**.
The QC bridge requires valid, matching rotation and center results, preserves
upstream warnings, and delegates transformation to the existing Module 5 API.
It uses the refined center and accepted midpoint angle with FLIP_X, unit scale,
and no shear. No transform mathematics is duplicated and no hardware is accessed.
Marker-local origin mapping, transform sign, inverse and distance invariants pass.
Actual GDS target coordinates are predicted offline; upstream warnings are preserved.

QCL-image physical overlay validation: **QUALITATIVE PASS**.
The operator-reviewed overlay shows the reference marker aligned with the measured
QCL structure and independently selected gold bars/crosses in the correct general
predicted locations. Quadrant/orientation behavior, FLIP_X, scale and gross
translation are physically consistent; no large sign/orientation failure is visible.
Marker identity and validation-feature identities were operator selected; software
does not infer marker/bar/cross semantics. Labels are `L=1.05`, `empty`, `P=1.5`,
`P=1.6`, `Cross_left`, `Cross_right`; cross selections are individual polygons,
not automatically grouped full crosses. Full selected polygons are transformed
without image-based refitting/optimization or hardware motion.

**Validation limits and future precision work**

Quantitative physical localization accuracy: **NOT CALIBRATED**. Manual observed
feature centers and observed-minus-predicted errors were not measured.
A small systematic angular/positional mismatch remains visible in the overlay.
Possible contributors include rotation estimation, marker geometry, optical edge
bias, scan-coordinate convention and drift. The cause has not been quantitatively
isolated; the mismatch is not attributed definitely to rotation.
The overlay deliberately reproduces the normal QCL snake-scan UI display convention,
which differs from acquisition/trigger coordinates; it is not a coordinate calibration.

Future precision work may include improved rotation estimation, more horizontal
profiles, quantitative clicked/observed feature centers, scan-coordinate calibration,
and drift/systematic-error characterization. These are future improvements, not
blockers for moving to Module 8.

The current physical sample does not contain the intended GDS MS pixels, so those
MS coordinates cannot be directly physically validated on this sample. The qualitative
overlay uses separately operator-selected visible gold structures; it does not
establish the fabrication status or suitability of all other GDS features.

Thresholds remain provisional screening thresholds, not experimentally calibrated
production uncertainty limits. Do not fit toward the historical angle. Bar-based
rotation was abandoned. No automatic targeting follows from classification.
Production rotation defaults are provisional engineering QC thresholds, not
calibrated physical uncertainty limits: side disagreement warns above 0.25 deg
and fails above 1.0 deg; minimum 3 profiles, 2 distinct measured Y values and
100 um Y span; maximum RMS residual 1 um, absolute residual 2 um (each line),
and width peak-to-peak 5 um. Equality at both angular limits is accepted.

Center-refinement defaults remain provisional engineering QC settings: square
side 500 um, maximum measured-X spread 1 um, maximum vertical chord-height error
20 um, inward boundary guard 10 um, constraint residual tolerance 1e-6 um,
edge-analysis width tolerance 100 um and angle/slope consistency tolerance 1e-12.
Exact guarded-boundary equality is rejected. These are not calibrated physical
uncertainty limits; constraint residuals check algebra, not physical accuracy.

**Validation / tests** Module 7 closeout rerun passed 20 overlay, 20 integration,
32 center, 28 rotation, 31 classifier, 47 reflection-scan, 25 adapter,
11 StageRegistration, 11 ChipLayout, 12 layout-assignment and 21 GDS-layout tests:
258 hardware-independent tests, including available actual S37a fixture checks.
Run each with `python -B -m unittest discover -s tests -p <filename> -v`, using
`test_marker_stage_registration_integration.py`, `test_stage_registration.py`,
`test_chip_layout.py`, `test_layout_assignment.py`, `test_gds_layout.py`,
`test_marker_center_refinement.py`, `test_marker_rotation.py`,
`test_marker_profile_classification.py`, `test_reflection_scan.py` and
`test_scan_adapters.py` and `test_qcl_registration_validation.py`.
The overlay evaluator replayed the archived manual selection successfully; see
the permanent evidence note for its command and external CSV/GDS prerequisites.
`python -B square_marker_profile_classification_check.py`
reloads all five journals and reruns single-scan analysis before classification.
Profiles 1–4 are CENTRAL; Profile 5 is INCONSISTENT (width, left-edge and midpoint
residual failures). Four accepted profiles have four distinct Y coordinates and
240 um accepted Y span; `sufficient_for_rotation_fit = True`.

`python -B square_marker_rotation_fit_check.py` reloads the same committed journals,
reruns single-scan analysis and classification, and fits only P1-P4. It reproduces:

| Rotation quantity | Result |
| --- | --- |
| Left-side angle | -0.08049369300446074 deg |
| Right-side angle | +0.34448525843138883 deg |
| Effective midpoint rotation / accepted rotation | +0.13199759820576185 deg |
| Midpoint regression statistical SE | 0.047127211112961795 deg |
| Side-angle disagreement | 0.4249789514358496 deg |
| Warning | left_right_angle_disagreement_warning |
| Hard-failure reasons | () |
| Valid | True |

The midpoint line defines the effective rigid-body marker rotation used for
registration; it does not assert perfectly parallel physical gold edges.
Side disagreement is retained as a QC warning with no physical cause assigned.
Statistical SE is regression-only, conditional on the selected profiles and OLS
assumptions, not calibrated physical uncertainty. It excludes stage calibration,
Y error, optical edge bias, drift and classification-selection effects.

`python -B square_marker_center_refinement_check.py` replays the complete offline
chain: P1-P5 journals -> single-scan analysis -> classifier -> production rotation
-> vertical scan analysis -> center refinement, without bypassing upstream QC.
The tracked vertical evidence is
`vertical_marker_scan_9392a56a0a0e4517b9b897398376ee3b.jsonl`.

| Center-refinement quantity | Verified result |
| --- | --- |
| Refined stage X | 4214.965309833208 um |
| Refined stage Y | -26111.10204224153 um |
| Effective midpoint rotation | +0.13199759820576185 deg |
| Orientation / scale / shear assumptions | FLIP_X / 1 / none |
| Vertical measured X mean / spread | 4210 / 0 um |
| Lower / upper Y edge | -26359.297926319337 / -25862.929036293222 um |
| Vertical midpoint | -26111.11348130628 um |
| Measured / expected vertical chord height | 496.36889002611497 / 500.0013268681278 um |
| Chord-height error | -3.6324368420128508 um |
| Offset from center / guarded central limit | 4.965309833208266 / 239.42338890381313 um |
| Horizontal / vertical constraint residual | -5.838385330747542e-14 / -1.3091524392327969e-12 um |
| Warning | left_right_angle_disagreement_warning |
| Hard-failure reasons / valid | () / True |

This estimate is integrated into Module 5 StageRegistration and has qualitative
overlay agreement, not calibrated physical accuracy. P1-P4 are CENTRAL; P5 remains INCONSISTENT.
The side-angle warning is retained without assigning it a physical cause.

`python -B square_marker_stage_registration_check.py` replays the accepted Module 7
chain, resolves the reviewed occurrence IDs from actual S37a geometry, and uses
LayoutAssignments/ChipLayout to compute marker-local offsets. The lower marker
reference is GDS (0,-4600) um, under Arra / Altug2009 / instance:0.
The local origin maps exactly to stage (4214.965309833208,-26111.10204224153) um.
Accepted rotation is +0.13199759820576185 deg; FLIP_X / scale 1 / shear none.

The verified transform is `stage = translation + R(theta) B local`, with
`B(x,y)=(-x,y)`. Thus stage X = center X - cos(theta)*local X - sin(theta)*local Y,
and stage Y = center Y - sin(theta)*local X + cos(theta)*local Y.
The midpoint-line slope is -tan(theta), so the Module 7 angle passes directly
into Module 5 with no sign reversal. Inverse and distance invariants pass:
origin error 0 um; maximum round-trip error 1.8225386545374702e-12 um;
maximum pairwise-distance discrepancy 2.5011104298755527e-12 um.

**OFFLINE PREDICTION ONLY** (all coordinates in um):

| Example name | Absolute GDS XY | Marker-local XY | Predicted stage XY |
| --- | --- | --- | --- |
| MS_1 | (-498.192,-5100.475) | (-498.192,-500.475) | (4714.308977,-26610.427984) |
| MS_2 | (502.158,-5100.125) | (502.158,-500.125) | (3713.960826,-26612.382582) |
| MS_3 | (-498.192,-4100.475) | (-498.192,499.525) | (4712.005187,-25610.430638) |
| MS_4 | (501.808,-4100.475) | (501.808,499.525) | (3712.007840,-25612.734428) |

Names follow the committed assignment example/order, not intrinsic GDS semantics
or unsaved interactive state. Full feature IDs and paths are printed by the
evaluator. These physical positions are not validated. The upstream warning
`left_right_angle_disagreement_warning` is retained; hard-failure reasons are ().
The external GDS file remains a prerequisite for replaying this evaluator.

The original center reconstructed from committed horizontal and vertical journals
is (4209.550599411898, -26111.11348130628) um. The refined-minus-original
correction is (+5.414710421310701, +0.011439064750448) um, total
5.4147225043258755 um. This is **not purely a rotation correction**: it also
replaces the original single coarse horizontal scan estimate with the later
multi-profile midpoint regression. Do not attribute the full 5.4 um to rotation.

Angle-fit sensitivity only, holding the measured line anchor and vertical
constraint fixed: theta minus one statistical SE gives delta X +0.032823165 um,
delta Y -0.004035486 um; theta plus one SE gives delta X -0.032829759 um,
delta Y +0.003981485 um. This is not full center uncertainty or calibrated physical
uncertainty. Midpoint slope/intercept covariance and vertical-edge uncertainty
are not fully propagated; stage calibration, optical edge bias,
classification-selection uncertainty and drift/systematics are not included.

Each preserved P1-P5 journal records 71 completed points, measured and commanded XY,
scalar reflection, bounds, scan timing settings and completion status. All saved
command/readback pairs agree exactly. The journals do not record raw DAQ samples,
laser/lock-in telemetry, physical clearance, acquisition-time code revision,
post-scan return or cleanup. Classification is reproducible offline; those other
hardware facts require separate operator evidence. Quantitative registration
accuracy remains uncalibrated. Interpolated edge digits are not physical accuracy.

**Exit criteria: SATISFIED within documented validation limits.**

- Robust single-scan acquisition/edge analysis is available from Module 6.
- Marker profile classification fails closed.
- Production midpoint rotation and refined marker center are available.
- StageRegistration transform is verified and actual GDS predictions are generated.
- QCL overlay gives qualitative physical agreement.
- Warnings and limitations are preserved.
- No quantitative or micron-level physical localization accuracy is claimed.

**Relevant commits** Classifier milestone:
`0675a29861f30df44bbfdf042eea5301d2ab054e` —
`feat(registration): add horizontal profile classification`.
Rotation milestone: `031d6468403c5711f9eec90a9ab9d6078829b285` —
`feat(registration): add production marker rotation fitting`.
Center milestone: `3166ce66c9c646c75e02b57f0caa0ae887b92e05` —
`feat(registration): add marker center refinement`.
Stage-integration milestone:
`cc88978be45f72c4fa73569cce43b2963b8df8ab` —
`feat(registration): integrate marker registration with stage transform`.
Closeout milestone: `feat(registration): complete Module 7 validation workflow`.
Record its resulting hash in the next roadmap update; this document is part of that commit.

### Module 8 - Auto Location MVP: H/V translation-only Locate Marker

**Status: COMPLETE — LIVE VALIDATED.** Operator-confirmed production and repeated
Snake Scan -> Auto Location reuse in the same Python session passed. Earlier
implementation checkpoints below are historical; this closeout status supersedes
their pending-test wording.

**Purpose** Provide an **Auto Location** main tab alongside Single, Snake scan,
and Scanning imaging in `qcl_scanning_imaging_autorelocation_ui.py`. Preserve
existing operational behavior through the experimental subclass/supporting modules;
`qcl_scanning_imaging_ui.py` must remain byte-identical. The experimental operational
tab is labeled Auto Location, with approved stage-center annotations on the GDS preview.

**Inputs** Loaded GDS, one operator-selected square gold reference marker,
manually selected desired features/MS pixels, orientation/frame/sample identity,
operator-confirmed rough stage position, nominal marker size and reviewed bounds.
Software must not infer marker/MS/bar/cross semantics. Reuse the existing GDS
preview and assignment model, and the existing gamepad/stage controls; do not add
a second gamepad implementation within Auto Location.

**Normal operator workflow** Load GDS -> select marker and targets -> use existing
stage/gamepad controls to put the beam at a rough point on the selected marker ->
confirm rough start and scan envelope -> press **Locate Marker**. The automatic
chain is rough point -> initial H -> initial V -> measured H/V marker center ->
theta=0 translation-only StageRegistration -> registered feature preview.
Intermediate scans normally require no manual execution. A rough point need not
be the center: scan-envelope planning must accommodate the declared rough-start
uncertainty or reject inadequate coverage before motion, without an unreviewed
whole-chip search. Development H-only/H+V validation gates are not the final UX.

**Outputs** A context-bound, approved translation-only registration and registered GDS preview.
For every selected feature show predicted stage center, with registration state,
marker center, rotation, orientation, warnings and separate hard failures. All
predictions delegate to StageRegistration. Selection alone is not motion.
The production mode is `translation_only`, `rotation_calibrated=False`,
`assumed_theta_deg=0.0`, orientation FLIP_X, scale=1, no shear. Rotation is an
explicit assumption, never presented as measured or assigned fake uncertainty.
Nonzero chip rotation causes target error to increase with marker distance;
no quantitative physical accuracy is claimed. Module 9 target tests will assess
whether this MVP approximation is sufficient.

**Key files** `qcl_scanning_imaging_autorelocation_ui.py`,
`ui/auto_relocation_widget.py`, `ui/registration_state.py`,
`ui/localization_orchestration.py`, `ui/localization_worker.py`,
`ui/operational_localization_bridge.py`, `ui/localization_pipeline.py`,
`ui/gds_assignment.py`; corresponding offline UI/orchestration/bridge/pipeline tests.
See [shell milestone](module8_ui_milestone.md) and
[ownership/pipeline design](module8_hardware_orchestration.md).

**Dependencies** Modules 3-6 manual selection, transform and scan/analysis APIs,
plus the live-validated H/V ownership path. Module 7 calibration remains optional.

**Current status** Offline shell/lifecycle: **COMPLETE / OFFLINE VALIDATED /
MANUALLY REVIEWED**. M8.2a ownership/worker/cancellation framework:
**COMPLETE / OFFLINE VALIDATED**. Fast-track M8.2b-M8.2e pipeline and experimental
bridge are offline tested; the production H/V subset and repeated Snake Scan reuse
are now live validated. Full rotation calibration remains optional/deferred.
The first supervised live H-only validation **PASSED** (run
`495ebff7920b4d1296f5e9680afdd2a5`, 71/71 points, valid edges, return and cleanup
PASS, ownership AVAILABLE, no registration published). The first supervised live
H+V validation **PASSED**, run `8493cabf1df6424fa2bee5e25e5d8396`: both analyses
valid, return/cleanup PASS, ownership AVAILABLE, no registration published.
The operator subsequently reports successful multi-H acquisition, with classifier
acceptance too brittle for the current live data. This is useful experimental
evidence, not a Module 8 MVP blocker; no classifier thresholds are changed.
The earlier runtime/orientation investigation and preflight remain documented
under optional development tooling. Production H/V translation-only integration
and fake tests are implemented; the operator reports successful live H/V,
return, cleanup, translation-only publication and registered predictions using
reference sampling. Default hardware startup keeps Locate Marker disabled; a separately
supervised test requires explicit `--supervised-translation-only` opt-in.

**Production sampling policy** Selected square side S determines requested
half-span = 1.25*S. Step = floor(min(15 um, S/20)) in integer micrometres;
S < 20 um fails closed at the current 1 um stage resolution. Actual half-span
rounds outward to a whole step, symmetrically about confirmed rough XY.
For S=500 um: requested +/-625 um, actual +/-630 um, 15 um step,
85 points/axis (170 H+V positions). Manual integral steps including 10/20/25 remain.
V X remains the rounded measured H midpoint. Preview/confirmation covers the
larger 2D rectangle and return; no automatic extension/retry is allowed.
Development H-only/H+V retains 10 um validated reference sampling. The new
production default is 15 um; physical center precision still requires assessment.
Physical localization accuracy remains uncalibrated and will be assessed in
Module 9 target tests. Move to a point clearly on the selected marker; exact
centering is not required, but capture of both edges is not guaranteed.

**Remaining work** No required Module 8 MVP work remains. The operator confirms
15 um production Auto Location and repeated Snake Scan -> Auto Location reuse
in one session are live validated. Module 9 physical feature relocation is next.
No multi-H/classifier gate is
required for production.
Retain blockers for unmanaged Objective widgets and unresolved DAQ evidence, and
sole-Python laser ownership. Managed Objective V1 permits a visible window after
verified operation-scoped release; ordinary opening/use no longer requires restart.
Joystick acknowledgement is not independent readback; laser state/settings still
require operator confirmation. Marker-scaled coverage is not proof of coverage from any
marker point: failure to capture both edges fails closed without retries or an
expanded search. No Module 9/10 implementation here.

**Tunable production sampling and anchor prior:** Production Scan Settings now
allows explicit half-span/step override, calculated points, and reset to the
marker-scaled automatic defaults. Changes require new preview and clearance
confirmation. Production inspects every generic evaluated candidate using selected
square width/height +/-100 um and inclusive containment of rough X (H) / rough Y
(V); exactly one QC-valid match is required. Generic noise, contrast, support and
background checks remain unchanged; geometry overrides never change marker priors.

Production quality now uses maximum 100 um substrate windows immediately outside
the uniquely identified marker, truncated at the nearest intervening crossings.
Both samples of every threshold-transition bracket are excluded from substrate
and interior quality regions; measured coordinates determine membership. Each
region still requires at least three samples. Shared generic quality calculations
retain min_snr=6, contrast, baseline-consistency and all other thresholds.
Generic Module 6 selection semantics and wide-region outputs remain unchanged.
Identity ambiguity fails before quality; no ranking or fallback candidates.

The wide-scan failure 402745357b0c4b769431c2ccc138617c still fails generic wide
SNR (5.35), but passes production local quality offline (SNR 325.26, background
support 3/3). Historical 10 um H/V scans also pass. The prior local-quality blocker
is resolved offline and the resulting production local-quality path is live validated.
No hardware was run during implementation. 15 um
is now the production default; 10 um is the finer reference.
Module 9 physical target tests will assess accuracy. Rotation remains deferred.

Normal production displays FLIP_X (default), backed by the canonical enum; only
--developer-mode exposes alternative orientation selection. Fresh normal startup
cannot inherit a developer alternative. The stable UI is unchanged.

Experimental Snake/repeat-Snake DAQ tasks now have source-specific cleanup
attestation. Configure marks potential NI acquisition; release requires all owned
tasks positively cleared (started tasks also stopped), worker unwind and thread
completion. Never-acquired workers release without a fictitious NI cleanup event.
Active scans or any uncertain NI call/cleanup remain blocking. Completed history
is bounded to 32; confirmed scans do not accumulate pending blockers. DAQ use
alone does not invalidate registration, but the existing Snake Scan explicitly
calls set_position to redefine coordinates; preserve that frame invalidation.

**Optional Rotation Calibration / Future Enhancement** Multi-H planning and
acquisition, profile classification, midpoint rotation, rotation-corrected center,
second-H refinement if later evidence justifies it, and quantitative localization
calibration are retained/deferred. They do not block this MVP. H-only, H+V,
multi-H, preflight/provenance and archived replay remain secondary tools under
Development / Diagnostics; the normal workflow does not require them.

**Safety/lifecycle contract** One stage-command owner and one DAQ-task owner;
share the persistent Prior owner's proxy, never create a second COM3 owner. Block legacy
workers/gamepad during localization; cooperative cancellation, no native-call
interruption claim, no retry/return after failure, partial journals retained,
uncertain cleanup quarantined. Publish candidate registration only after full QC,
verified success-only return when configured, cleanup and unchanged context.
GDS/marker/orientation/frame/sample/input changes invalidate registration and cancel
an active candidate. Ordinary motion does not. Target selection changes predictions,
not the registration. Warnings remain visible even when VALID; archived replay is
not automatically a live approved registration.

**Validation / exit criteria** Offline ownership, invalidation, failure/cancel,
journal and publication tests pass; the stable UI is unchanged; manual selection,
registered preview and warning display work; the operator selects marker/features,
clicks Locate Marker after preview/confirmation, H/V run automatically, and the
translation-only registration is published only after return/cleanup. Selected
feature centers appear in the GDS preview. This chain is operator-confirmed live validated within the documented limits.
**Exit criteria: SATISFIED. Module 8 COMPLETE — LIVE VALIDATED.** Target movement belongs to Module 9; ROI scan
launch belongs to Module 10. Quantitative calibration and improved rotation are
future precision work, not blockers for this core workflow.

**Relevant commits** Offline shell:
`75a1c885ec37d1bea59f97e2a01e0b25d9bac485`.
M8.2a: `b1fb1213ebcebf677eb9bfc49d21a3d7b5cb54d2`.

#### Managed Objective Scanner DAQ Ownership V1 closeout (2026-10-01)

**Status: COMPLETE — SOFTWARE TESTED AND LIVE HARDWARE VALIDATED.** This is a
Module 8 ownership/workflow prerequisite closeout, not Module 9 implementation.
The operator supplied the live results; the closeout agent reran software tests
only. Full behavior/evidence and validation limits are recorded in
[Managed Objective V1 validation](module8_hardware_orchestration.md#managed-objective-scanner-daq-ownership-v1-closeout-2026-10-01).

- The explicit zero-argument Objective action adapter fixes the Qt Boolean-payload
  regression. Opening and close/reopen passed live with no TypeError or UI exit.
- Opening the managed window creates no native NI task: managed=true, OPEN,
  RELEASED, verified_released=true, native_creation_attempted=false,
  native_task_created=false, uncertain=false, blockers=[].
- Acquire Signal, Move To (including repeated generations/tokens), and normal
  Autofocus completion each confirmed task clear and owner-bound release, followed
  by successful Locate Marker without restarting the UI.
- With Objective Scanner left open, H/V localization completed, registration was
  published, DAQ/idle cleanup passed, and ownership returned to AVAILABLE.
- During localization, Objective hardware controls were disabled. After verified
  cleanup they became usable again; a subsequent Acquire Signal cleared normally.
  Close/reopen created no new DAQ transition, retained release evidence, and a
  subsequent Locate Marker succeeded. Programmatic denial is software-tested;
  disabled controls were not bypassed on hardware.
- Lifecycle: RELEASED -> ACTIVE -> RELEASING -> RELEASED, or UNCERTAIN on
  unverified failure. Unmanaged widgets, unresolved historical evidence and
  uncertain cleanup still fail closed. Window visibility is not DAQ activity.

Closeout regression: **252 passed, 0 failed**, offscreen Qt with hardware imports
explicitly blocked. The legacy UI, instrument/driver code, scan engine and hash
constants are unchanged. Legacy UI SHA-256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.

Accepted limits: no forced autofocus cancellation or automatic restart;
Snake/Repeat worker-origin autofocus/fallback Objective creation remains
unsupported and fail-closed. Rotation remains deferred (production theta=0).
Module 9 guarded target/MS movement and Module 10 ROI integration remain
NOT STARTED. The next discussion is Module 9 architecture, not automatic enablement.

### Module 9 - Feature Selection and Guarded Move

**Purpose** Select a registered feature and safely move to its predicted center.
**Status** NEXT PLANNING MODULE — implementation not started. **Dependencies** Modules 5-8.

**Inputs** Valid context-bound registration, manually assigned target, current
stage readback, permitted bounds and operator-verified approach clearance.
**Outputs** Selected feature/predicted XY and explicit motion/readback outcome.

**Interaction** Single click selects and shows predicted stage XY without motion.
Double click requests motion to that feature center; a **Move to Selected Feature**
button may remain. Both use the same guarded action, never independent motion code.
Selection and double-click events must not issue duplicate commands. Prediction
uses existing StageRegistration; no transform reimplementation.

**Remaining work** Add navigation interaction and guarded target-motion service.
Require valid current registration/target/bounds and exclusive ownership at command
execution, block gamepad/legacy conflicts, verify idle/readback and preserve
cancellation/quarantine/frame-invalidation behavior. Ordinary movement preserves
registration. Stale or failed registration cannot authorize movement.

**Validation / exit criteria** Fake tests cover selection versus movement, duplicate
clicks, stale context, bounds, conflicts, cancellation and failed readback/cleanup.
Supervised navigation on an operator-confirmed physically present feature passes
with explicit outcome and documented limitations. Controller readback agreement is
not quantitative optical localization accuracy. The current sample lacks intended
MS pixels; choose a present landmark or suitable sample for physical checks.
Physical relocation-accuracy validation must assess whether translation-only
registration with assumed theta=0 is sufficiently accurate across the relevant
chip region. Quantitative calibration remains future work; record observed
relocation errors and practical limitations without assuming micron accuracy. No automatic multi-target batch movement/imaging.

**Key reuse** `experiment/stage_registration.py`, `experiment/scan_adapters.py`,
experimental ownership and registration-state modules. No stable-UI edits.
**Relevant commits** None for registered target motion.

### Module 10 - Scanning ROI and existing Snake Scan MVP

**Purpose** After feature navigation, define a Width/Height ROI around the selected
feature, preview it and launch the existing Snake Scan from its top-left start.
**Status** NOT STARTED. **Dependencies** Modules 8-9 and existing Snake Scan.

**Inputs** Valid registration/selected feature, its predicted stage center, positive
ROI width/height, resolution and existing scan settings, permitted stage bounds.
**Outputs** A stage-axis-aligned rectangular ROI, center/start overlays, validated
legacy scan parameters and traceable results. The center is the predicted feature
center, not the current stage position. Do not require the stage to remain there.

**UI** Add **Scanning ROI**, Width, Height, **Preview ROI**, and **Start Snake Scan**.
Show the rectangle, selected center and intended start directly in the registered
preview. If displayed in GDS coordinates, use the existing inverse StageRegistration
for the stage-aligned ROI vertices; do not rotate the acquisition grid with the GDS.

**Legacy coordinate contract - inspected source, not a new scan engine**

- `qcl_scanning_imaging_ui.py:run_snake_scan` supplies
  `xParameters=[xOrig,xPixelRes,xPixelNums]` and equivalent Y parameters.
  Positive integer resolutions/counts are required; `construct_snakescan_pattern`
  delegates to `stage.make_snakes` with `M=xPixelNums`, `N=yPixelNums//2`.
- `instruments/hld117.py:make_snakes` calls `(X0,Y0)` the top-left start.
  For block i it uses `Y0-2*i*dY`, `Y0-(2*i+1)*dY`, and
  `X1=X0+xIndent+M*dX`: forward +X, successive rows -Y, alternating return.
  Use this acquisition convention, not the visual screen's inverted axes.
- `experiment/routines.py:snakeScan.scan` moves to absolute `(xOrig,yOrig)`,
  redefines that location as `(0,0)`, executes local paths, and restores the
  original coordinate labels on normal completion. Start is not required to equal
  the stage's current location. Temporary zeroing is a real frame change, not goto.
- Forward trigger indent, backward return drift and local path origins affect
  actual acquisition/motion bounds. The normal UI display uses inclusive linspace
  coordinates and adds trigger indent to both displayed origins; these differ
  from the actual path/trigger convention. Do not silently treat them as identical.
  The raster-direction selector does not itself make this engine a rotated/Y-fast
  grid; MVP uses the inspected X-fast path only.

**Remaining conversion work** Implement a small tested parameter adapter and invoke
this same Snake Scan engine through the experimental ownership boundary. Define
Width/Height as the requested stage ROI extent; explicitly resolve pixel-count,
endpoint and resolution semantics against the legacy path and triggers. Reject or
show requested versus realizable extents before acceptance; never silently truncate
odd Y counts (`//2`), round origins or change ROI coverage. Distinguish requested
ROI, sampled locations/display extent and full motion envelope (indent, drift,
approach, return). Derive the absolute top-left from that tested convention and
preview the exact start that will be commanded. Do not introduce a competing scan.

**Enablement gates** Valid current registration, selected target, finite positive
ROI, approved integer parameter conversion, ROI and complete motion envelope within
permitted bounds, and no acquisition/ownership conflict. Recheck at launch and
invalidate ROI/predictions when registration context changes. Target or size/settings
changes require a fresh conversion/preview, not re-registration. Moving elsewhere
in the same frame does not invalidate the ROI; Snake Scan approaches its start.

**Frame/ownership integration gate** Reusing legacy code is not permission to bypass
zero-change invalidation. Before enabling launch, review an experimental frame-aware
adapter around its temporary local frame, preserve an immutable approved scan
snapshot, and verify restoration before any subsequent registered navigation.
Until restoration is confirmed, registration must be unavailable for navigation;
unexpected redefine/reset or uncertain failure invalidates/quarantines it. Do not
suppress raw frame hooks without an explicit tested coordinate contract. Review
legacy laser/DAQ/autofocus ownership, cancellation and exception cleanup as part of
reuse; keep stable UI unchanged and do not copy the scan engine.

**Validation / exit criteria** Tests compare converted starts, directions, counts,
resolutions, triggers and full bounds with the actual legacy implementation,
including rounding/even-row, stale-context and failure cases. Preview matches the
accepted conversion; guarded reuse and coordinate restoration are fake-tested,
then one ROI Snake Scan is separately supervised and results/provenance recorded.
No micron-level accuracy claim is required or implied. Rotated grids, automatic
multi-target batch imaging, quantitative calibration and improved rotation are
future enhancements, not MVP blockers.

**Key reuse** `qcl_scanning_imaging_autorelocation_ui.py`, supporting experimental
UI modules, `ui/scan_windows.py`, `experiment/routines.py`,
`instruments/hld117.py` (static reference; no hardware needed for design review).
**Relevant commits** None for registration-aware ROI launch.

## Before starting a new module

- [ ] Review this document.
- [ ] Confirm previous-module exit criteria.
- [ ] Confirm repository branch and clean/understood working tree.
- [ ] Identify module inputs/outputs.
- [ ] Identify files expected to be created/modified.
- [ ] Define unit/synthetic tests before hardware integration.
- [ ] Define hardware validation separately where applicable.
- [ ] Confirm what is explicitly out of scope.

## Before committing a completed module

- [ ] Review this document.
- [ ] Confirm module exit criteria.
- [ ] Run relevant regression tests.
- [ ] Run/document required hardware validation.
- [ ] Review git diff and exclude next-module work.
- [ ] Update this module's status and remaining work.
- [ ] Record important limitations.
- [ ] Commit with a module-specific message.
- [ ] Push and record the commit hash here.

Record completed module hashes in subsequent roadmap updates; a commit cannot
contain its own final hash. Do not amend completed history just to add that hash.

## Current handoff

Module 6 complete. Module 7 complete within documented validation limits.
Module 8 COMPLETE — LIVE VALIDATED (operator-confirmed).

Production: manual GDS marker/target selection -> existing gamepad positioning
clearly on marker -> envelope preview/confirmations -> H -> size/anchor identity
and local 100 um quality -> V -> measured center -> theta=0 translation-only
StageRegistration -> registered feature predictions. FLIP_X is the production
default; rotation_calibrated=False. Manual geometry override remains available.
For a 500 um square: requested half-span 625, actual 630, step15, span1260,
85 points/axis. Width tolerance100 um and min_snr6 remain unchanged.

Live validated: production H/V and transactional publication, nearby-feature
robustness, size/anchor selection, local quality, tunable geometry, 15 um default,
normal FLIP_X display, and repeated Snake Scan -> Auto Location in one session
with positive source-specific DAQ release. Active/uncertain ownership still blocks.
Offline tests additionally exercise failure/cancel/quarantine and stale context.

Managed Objective Scanner DAQ Ownership V1 is COMPLETE — SOFTWARE TESTED AND
LIVE HARDWARE VALIDATED. Opening creates no native DAQ task; Acquire Signal,
Move To, Autofocus and close/reopen each permit subsequent Locate Marker after
verified release without restart. The window stays open, hardware controls are
disabled during localization, and controls return after verified cleanup. The
zero-argument Qt callback fix is also live validated. Old UI/instrument code is
unchanged. Unsupported worker autofocus and uncertain ownership remain blocked.

Multi-H / rotation calibration: DEFERRED — OPTIONAL FUTURE CALIBRATION.
No quantitative physical relocation accuracy is claimed by Module 8.

Next discussion: plan Module 9 — Feature Selection and Guarded Move; no target
motion implementation is included in this checkpoint. Single click selects
and shows predicted XY; double click or explicit Move requests one guarded move.
Physically validate whether theta=0 translation-only predictions are sufficiently
accurate across the relevant chip region. Do not duplicate StageRegistration.

Module 10 remains Width/Height feature-centered ROI -> preview -> verified
top-left start -> reuse existing Snake Scan. No Module 9/10 implementation is
included in this closeout. Historical harnesses and unused runtime output were
removed; required journals survive as committed evidence or explicit test fixtures.
