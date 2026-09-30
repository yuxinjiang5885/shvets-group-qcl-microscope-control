# Module 8 first UI milestone: architecture and review

The authoritative roadmap records this milestone's closeout. Module 8 exposes localization and
registration with visible QC/lifecycle, consumes manual assignments and Module 7
results, and depends on Modules 3-7. Its outputs are registration state, QC display,
and invalidation behavior. Its exit criterion is safe management of registration
with no stale/failed result use; detailed acceptance criteria, hardware ownership,
cancellation, threading, persistence and supervised validation remain future work.
This milestone covers offline registration UI only. It does not complete Module 8.
Module 9 target motion and Module 10 imaging/ROI integration are out of scope.

## Existing operational UI: static inspection

`qcl_scanning_imaging_ui.mainWindow(QMainWindow)` is started by its `__main__`
block (`QApplication`, `mainWindow`, `app.exec`). `make_gui()` builds a central
QWidget/QGridLayout containing `self.tabs`: Single, Snake scan, Scanning imaging
(Legacy). It calls `show()` during construction. Actions/Laser/Multiple/Stage/
Objective/Options/Help menus and separate laser settings, stage motion, multiple
acquisition and objective windows remain owned by the original class.

Qt signals connect buttons, actions, fields and worker signals directly to bound
methods/lambdas (`clicked`, `triggered`, `returnPressed`, `textChanged`). Controls
are also held in dictionaries such as `btn`, `inputField` and scan dropdowns.
Runtime state resides on the main window, parameter objects in
`experiment/auxiliary.py`, scan browsers, workers and instrument objects. Defaults
come from `experiment/defaults.py`; acquisition code writes experiment data/logs.
There is no shared registration lifecycle/persistence object in that window.

Stage coordinates come from `stage.get_position()` into `displayed_coordinates`;
stageMotionWindow forwards updates to the main status bar and snake browser.
The stage window has XY readouts, a stage plot and separate speed/acceleration
controls. QCL arm/tune/emission and scan actions call the existing laser/routine
methods; NI tasks are created by acquisition routines, not the registration panel.

Inspected helper/import paths include `experiment.auxiliary`, `defaults`, `routines`,
`ui.laser_windows`, `stage_windows`, `scan_windows`, `plot_widgets`,
`xbox_controller`, `instruments.mircat`, `hld117`, `ni_daq`, `pi_scanner`, and the
PI module's import of `standalone_stage_ui_h117`. None was started for this review.

| Phase | Side effects found |
| --- | --- |
| Import old UI | Imports acquisition/instrument modules; MIRcat `CDLL` loads its SDK immediately; NI imports PyDAQmx bindings; matplotlib configuration and module paths change. Not a hardware-independent import. |
| Main window construction | Starts laser initializer thread (`laser()` connects/queries MIRcat), Prior initializer thread (SDK initialization/session, COM connection, identify), modal startup dialogs, stage readback, PI USB connection/query/startup. |
| Stage window construction | Sets default acceleration and speed, disables hardware joystick, initializes readings/plot. |
| Gamepad selection | `goto_gamepad` starts a Qt worker; `xboxController()` starts its monitoring thread. Not started merely by constructing the stage window. |
| Objective Scanner action | Constructs `piScanner_widget`, creates/configures NI DAQ and reads positions; main construction already connected PI. |
| Acquisition actions | Existing routines create/configure/start DAQ tasks and control hardware. |
| Close original window | Stops gamepad, closes PI connection, disconnects stage, disables/disarms laser. |

The original class has no offline constructor or dependency-injection hook. Its
`self.tabs` is a clean extension point; no index/count-dependent callback was found
that assumes exactly three tabs. Calling its constructor in an offline test is unsafe.

## Reuse decision and entry points

No copy and no modification of the stable UI. The new entry point supplies:

- A hardware-independent default host for `AutoRelocationWidget`.
- `operational_window_class()` creates a subclass of the existing main window
  only on an explicit hardware path. It calls `super().__init__()` unchanged, then
  adds the same panel as one tab. Existing controls/callbacks/cleanup are inherited.
- A fake base can be injected into the factory to test extension without importing
  the legacy UI. This verifies the extension contract, not actual instrument behavior.

```powershell
# Existing operational entry point, unchanged; has existing hardware side effects:
python .\qcl_scanning_imaging_ui.py
# New entry point: safe offline panel by default (also accepts --offline):
python .\qcl_scanning_imaging_autorelocation_ui.py
# Full experimental legacy window + panel; NOT executed in this milestone:
python .\qcl_scanning_imaging_autorelocation_ui.py --hardware
```

This explicit mode split is necessary to keep the new entry point importable and
usable offline. The default shell does not fake instrument controls. The full
subclass path inherits their real startup behavior and requires a later supervised
hardware review. Opening the panel itself has no device side effects.

## Reused APIs

| API | UI inputs and outputs | Boundary |
| --- | --- | --- |
| `GDSLayoutPreviewWidget.load_file/set_layout`, `selection_changed` | GDS model -> generic selectable geometry/IDs/paths | Offline Qt |
| `GDSAssignmentWidget`, `chip_layout_changed` | Operator assigns/renames marker and targets -> LayoutAssignments and ChipLayout snapshots | Offline Qt; embedded unchanged |
| `LayoutAssignments.set_marker/add_ms/remove/rename_ms/build_chip_layout` | Manual identities -> validated marker-relative geometry | Pure offline |
| `scan_1d(ScanSettings, stage, signal_reader, output_path=..., cancelled=...)` | Bounds, timing, caller-owned devices -> journaled ScanResult | Hardware-facing when given real devices; NOT wired |
| `PriorStageAdapter(..., bounds=...)` | Existing controller -> move_to/is_busy/get_position/stop protocol | No import/construction device calls; method calls touch hardware; NOT wired |
| `NIReflectionReader(..., sample_number=..., channel_limits=...)` | Existing configured DAQ -> checked scalar reflection, last_samples | read calls acquire_bounded; NOT wired |
| `load_scan(path)` | Journal -> ScanResult | Pure offline |
| `analyze_scan(scan, EdgeSettings)` | Single profile -> EdgeResult with edges/candidates/QC | Pure offline |
| `classify_profiles(ProfileGeometry rows, initial Y, settings)` | Profiles -> ClassificationResult, CENTRAL IDs, sufficient flag, usable_final_fits | Pure offline |
| `fit_rotation(classification, complete CENTRAL rows, settings)` | Approved profiles -> RotationFitResult, accepted_theta_deg, warnings/reasons | Pure offline |
| `refine_marker_center(rotation, vertical ScanResult, settings, initial_center_um=...)` | Accepted angle/fit and vertical evidence -> CenterRefinementResult | Pure offline |
| `build_stage_registration(rotation, center)` | Matching accepted results -> OfflineMarkerRegistration wrapping Module 5 StageRegistration | Pure offline |
| `local_to_stage(x, y, registration)` | ChipLayout local target -> stage prediction | Pure offline; only transform implementation used |

The UI never classifies marker/bar/cross semantics. Existing editable labels and
full IDs remain in LayoutAssignments/table tooltips; predictions show the full ID.
The internal MS container is reused for user-selected targets, including non-MS
features. No second semantic or transformation system is introduced.

## State, provenance and invalidation

`RegistrationState` stores context, assignments, full evidence results, approved
registration, warnings, reasons and the last target prediction. States are
NOT REGISTERED, REGISTERING, VALID, INVALID. VALID here means archived offline QC
approval, not current hardware or physical accuracy certification.

`RegistrationContext` binds GDS path/hash, marker ID, orientation, frame/zero identity,
sample identity and registration-input identity. GDS reload, marker replacement/
removal, orientation, frame/zero, sample or input edits discard approval/prediction.
Changing a setting back does not revive approval. Targets/labels can change without
invalidating marker registration; they clear only the target prediction.

`RegistrationEvidence` retains ClassificationResult, RotationFitResult and
CenterRefinementResult plus journal hashes. `accept` requires classifier approval,
the complete CENTRAL identifier set, matching context and the existing Module 7
bridge's rotation/center QC. Failed results cannot produce a usable transform.
Warnings and hard failures have separate visible labels; a valid result can warn.
Invalidated prior evidence remains diagnostic only. State is session-local; no
registration persistence format or live hardware/frame event hook is claimed yet.

Archived demo replay uses committed source filenames and algorithms, reconstructs
the initial center from journals, and obtains the final center/angle programmatically.
It does not read constant predicted coordinates as an approval. The operator must
first select the matching GDS marker manually; wrong marker/hash/context fails closed.
Archived results cannot be relabeled into a new sample/frame through the panel.

## Panel and first-milestone limits

The panel provides GDS/manual assignment, orientation/frame/sample/input identities,
registration/QC values, full diagnostic review and selected-target prediction.
Locate Marker is disabled. Replay archived Module 7 registration is explicitly
offline; there is no scan connection, move button or automatic return/motion logic.
The retained side-angle warning and uncalibrated physical accuracy are visible.

The fixed seven-journal demonstration replay is synchronous and short. Arbitrary
large replay/acquisition needs a future worker/cancellation design with context
generation checks before results are accepted. Future hardware integration must
handle exclusive stage/DAQ ownership, busy/cancel/stop/cleanup, and frame/sample
changes before enabling live registration. External edits to source files are not
watched; the panel binds the loaded layout and replayed journal snapshots.

Validation uses offscreen Qt, blocked instrument imports, a fake legacy base,
synthetic manual geometry and the existing archived evidence. Actual operational
window startup and instrument behavior are deliberately not tested here.
Next Module 8 step: design
the hardware acquisition worker/ownership/cancellation and live-frame invalidation
contract before connecting Locate Marker. No target motion is authorized by this work.

## Milestone validation result

298 tests passed: 22 new UI/lifecycle tests; 258 existing Module 5-7/layout/overlay
tests; 12 GDS preview and 6 GDS assignment GUI tests. Real archived-selection
injection and evidence replay displayed VALID with the retained
`left_right_angle_disagreement_warning`, center
(4214.965309833208, -26111.10204224153) um and rotation
+0.13199759820576185 deg. Operator-labelled P=1.6 predicted
(3538.5603696740036, -26612.386667895684) um through Module 5. These are offline
replay results, not new physical validation or a declaration of the live frame.

The stable UI remains byte-identical, SHA256
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
Existing algorithms, QC thresholds, journals and QCL CSV are unchanged.
Operator manual review confirmed GDS loading, manual marker/target selection,
archived replay becoming VALID, retained warnings, offline prediction and correct
invalidation behavior. Offline UI shell / lifecycle is COMPLETE / OFFLINE VALIDATED /
MANUALLY REVIEWED. Operational hardware integration is NOT YET IMPLEMENTED.
The six-file offline milestone includes the roadmap update and is prepared for
`feat(ui): add auto-relocation UI shell`; no Locate Marker worker is included.
