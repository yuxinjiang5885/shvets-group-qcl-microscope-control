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

**Remaining work**

1. Production rotation fitting from accepted CENTRAL profiles.
2. Rotation uncertainty / residual QC.
3. Rotation-corrected center refinement using the vertical scan.
4. Final marker registration QC.
5. Physical validation of StageRegistration predictions.

Thresholds remain provisional screening thresholds, not experimentally calibrated
production uncertainty limits. Do not fit toward the historical angle. Bar-based
rotation was abandoned. No automatic targeting follows from classification.

**Validation / tests** Milestone rerun passed 31 classifier tests,
47 reflection-scan tests and 25 adapter tests: 103 hardware-independent tests.
Run each with `python -B -m unittest discover -s tests -p <filename> -v`, using
`test_marker_profile_classification.py`, `test_reflection_scan.py` and
`test_scan_adapters.py`. `python -B square_marker_profile_classification_check.py`
reloads all five journals and reruns single-scan analysis before classification.
Profiles 1–4 are CENTRAL; Profile 5 is INCONSISTENT (width, left-edge and midpoint
residual failures). Four accepted profiles have four distinct Y coordinates and
240 um accepted Y span; `sufficient_for_rotation_fit = True`.

Each preserved journal records 71 completed points, measured and commanded XY,
scalar reflection, bounds, scan timing settings and completion status. All saved
command/readback pairs agree exactly. The journals do not record raw DAQ samples,
laser/lock-in telemetry, physical clearance, acquisition-time code revision,
post-scan return or cleanup. Classification is reproducible offline; those other
hardware facts require separate operator evidence. Final registration validation
tests still need definition. Interpolated edge digits are not physical accuracy.

**Exit criteria** Independently tested classification and fitting reject ambiguous
or inconsistent data; sufficient accepted profiles support consistent side slopes;
center/angle and residual QC pass supervised validation. Not yet met.

**Relevant commits** Classifier milestone: `feat(registration): add horizontal
profile classification`. Record its resulting hash in the next roadmap update;
this document is part of that commit.

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
Module 7 classifier is complete and offline validated; Module 7 remains in progress.
Next task: implement production rotation fitting using only accepted CENTRAL
profiles and requiring successful set-level classification QC. Final rotation,
uncertainty, rotation-corrected center refinement and registration are not complete.

Profiles 1–5 journals are preserved Module 7 classifier evidence; their repetitive
hardware harnesses remain untracked. Lower-bar exploratory files remain local abandoned
experiments; the Y-repeatability harness has no reported execution results and
remains local diagnostic work.
No experiment files were deleted, and this roadmap authorizes no hardware motion.
