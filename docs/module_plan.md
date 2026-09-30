# QCL GDS-Based Metasurface Localization — Module Plan

This is the authoritative module roadmap. Review and update it before starting a
module, declaring a module complete, or committing completed module work.
Status reviewed against the repository on 2026-09-29. Completion is scoped to the
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
- Supervised acquisition uses exclusive stage/DAQ ownership: Python QCL UI closed,
  vendor MIRcat GUI controlling emission independently. No unreviewed hardware runs.
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
| 7 | Automatic square-marker registration | Multi-profile classification, fitting, QC | IN PROGRESS; paused for this wrap-up | Validated center and angle | 4–6 |
| 8 | Registration UI integration | Workflow and registration lifecycle | NOT STARTED | UI with QC/invalidation | 3–7 |
| 9 | Move to selected MS and physical validation | Safe registered targeting | NOT STARTED | Verified target/readback/residual | 5–8 |
| 10 | ROI / QCL imaging integration | Registered geometry to imaging | NOT STARTED | ROIs and imaging workflow | 8–9 |

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

**Outputs** Planned: accepted registration, residuals, uncertainty/limitations and
diagnostics; no production registration is currently complete.

**Key files** `experiment/marker_profile_classification.py`,
`tests/test_marker_profile_classification.py`,
`square_marker_profile_classification_check.py`; the five original profile
journals listed explicitly in the evaluator are preserved as offline evidence.
The five repetitive `square_marker_rotation_profile_*_check.py` hardware harnesses
remain local/untracked and are not required to replay classification.
Production rotation: `experiment/marker_rotation.py`,
`tests/test_marker_rotation.py`, `square_marker_rotation_fit_check.py`.
Center refinement: `experiment/marker_center_refinement.py`,
`tests/test_marker_center_refinement.py`, `square_marker_center_refinement_check.py`.

**Dependencies** Modules 4–6.

**Completed work** Automatic horizontal-profile classification:
**COMPLETE / OFFLINE VALIDATED**. Module 7 as a whole remains **IN PROGRESS**.
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

**Remaining work**

1. Assemble final marker registration result.
2. Integrate accepted center + rotation with Module 5 StageRegistration.
3. Predict selected MS stage coordinates.
4. Physically validate predicted MS positions (requires fabricated targets;
   current-sample MS pixels are absent, as recorded in Module 9).
5. Finalize Module 7 registration QC / exit criteria.

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

**Validation / tests** Center-refinement milestone rerun passed 32 center tests,
28 rotation tests,
31 classifier tests, 47 reflection-scan tests and 25 adapter tests:
163 hardware-independent tests.
Run each with `python -B -m unittest discover -s tests -p <filename> -v`, using
`test_marker_center_refinement.py`, `test_marker_rotation.py`,
`test_marker_profile_classification.py`, `test_reflection_scan.py` and
`test_scan_adapters.py`. `python -B square_marker_profile_classification_check.py`
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

This is an offline registration estimate, not yet a production StageRegistration
or physical targeting validation. P1-P4 are CENTRAL; P5 remains INCONSISTENT.
The side-angle warning is retained without assigning it a physical cause.

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
hardware facts require separate operator evidence. Final registration validation
tests still need definition. Interpolated edge digits are not physical accuracy.

**Exit criteria** Independently tested classification and fitting reject ambiguous
or inconsistent data; sufficient accepted profiles pass rotation hard QC with
side-quality warnings preserved;
center/angle and residual QC pass supervised validation. Not yet met.

**Relevant commits** Classifier milestone:
`0675a29861f30df44bbfdf042eea5301d2ab054e` —
`feat(registration): add horizontal profile classification`.
Rotation milestone: `031d6468403c5711f9eec90a9ab9d6078829b285` —
`feat(registration): add production marker rotation fitting`.
Center milestone: `feat(registration): add marker center refinement`.
Record its resulting hash in the next roadmap update; this document is part of
that commit.

### Module 8 — Registration UI integration

**Purpose** Expose localization and registration with visible QC and lifecycle.

**Inputs** Assignments and Module 7 registration/results.

**Outputs** Planned workflow, QC display and invalidation state.

**Key files** No dedicated implementation. Existing integration candidates:
`ui/gds_assignment.py`, `qcl_scanning_imaging_ui.py`; design Needs review.

**Dependencies** Modules 3–7.

**Completed work** None for registration UI; preview/assignment already exist.

**Remaining work** Ownership, cancellation, UI threading, persistence and
invalidation on frame/assignment changes; implementation design Needs review.

**Validation / tests** New registration UI tests and supervised integration planned;
no dedicated test filenames established.

**Exit criteria** UI safely manages registration state and prevents stale/failed
registration use. Detailed acceptance criteria Needs review.

**Relevant commits** None.

### Module 9 — Move to selected MS and physical validation

**Purpose** Transform selected targets and verify safe physical localization.

**Inputs** Accepted registration, assigned MS feature, current readback and clearance.

**Outputs** Planned bounded target motion, readback and physical residual evidence.

**Key files** No dedicated implementation; reuse candidates
`experiment/stage_registration.py`, `experiment/scan_adapters.py`.

**Dependencies** Modules 5–8.

**Completed work** None for registered automatic MS targeting.

**Remaining work** QC gates, movement workflow and independent physical validation.
Operator reports the current sample's MS pixels were not fabricated; gold remains.
Absent MS pixels must not be used as physical validation targets. Suitable sample
or separately identified fabricated landmark strategy Needs review.

**Validation / tests** Planned fake-stage tests plus separately authorized hardware
validation; no dedicated implementation/test files yet.

**Exit criteria** Safe bounded motion and independently measured localization
residuals meet reviewed criteria on fabricated targets. Not met.

**Relevant commits** None.

### Module 10 — ROI / QCL imaging integration

**Purpose** Connect registered geometry to QCL imaging ROIs and acquisition.

**Inputs** Valid registration, selected MS geometry and imaging settings.

**Outputs** Planned registered ROIs and traceable imaging results.

**Key files** No dedicated registration-aware implementation. Existing integration
candidates `qcl_scanning_imaging_ui.py`, `ui/scan_windows.py`,
`experiment/routines.py`; detailed design Needs review.

**Dependencies** Modules 8–9 and existing imaging controls.

**Completed work** Existing QCL imaging predates this module; registered ROI
integration has not started.

**Remaining work** ROI generation, bounds/ownership, registration invalidation,
acquisition provenance and UI integration.

**Validation / tests** Planned geometry/unit tests, simulated integration and
separately supervised imaging. Dedicated tests Needs review.

**Exit criteria** Accepted registration produces safe, correct imaging ROIs with
traceable results and failure handling. Detailed thresholds Needs review.

**Relevant commits** None for this integration.

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

Module 6 is complete within its documented hardware-validation limits.
Module 7 profile classification is complete and offline validated.
Module 7 production rotation fitting is complete and offline validated.
Module 7 center refinement is complete and offline validated.
Module 7 as a whole remains in progress.
Next task: integrate the accepted marker center and midpoint rotation with
Module 5 StageRegistration, without moving hardware yet, and verify
predicted coordinates offline before physical validation.

Profiles 1–5 journals are preserved Module 7 classifier evidence; their repetitive
hardware harnesses remain untracked. Lower-bar exploratory files remain local abandoned
experiments; the Y-repeatability harness has no reported execution results and
remains local diagnostic work.
No experiment files were deleted, and this roadmap authorizes no hardware motion.
