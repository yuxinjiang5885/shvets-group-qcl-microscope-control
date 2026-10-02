# Module 8 closeout status

**Current checkpoint: Managed Snake Autofocus V1 normal execution, checked Snake
DAQ, telemetry, PI bounded confirmation and structured diagnostics are HARDWARE
VALIDATED.** Operator-reported single/two-wavelength and Repeat validation is
recorded in the final checkpoint section. Failure finalization and tracing are
software tested; real post-fix failure recovery/close remains pending. Historical
implementation checkpoints below retain their original test counts and limitations.
Unmanaged fallback and uncertain ownership remain blocked. Module 9 is deferred.

**COMPLETE — LIVE VALIDATED.** The operator confirms production Auto Location,
Snake Scan, and Auto Location again in the same Python session work successfully,
including repeated Snake Scan DAQ release attestation. No hardware was executed
by the closeout agent. Earlier pending/retry procedures below are historical.

Live-validated production includes H/V acquisition, size + rough-point identity,
nearby-feature robustness, local 100 um quality, tunable geometry, 15 um default,
canonical FLIP_X normal UI, transactional translation-only registration and
registered GDS predictions. Offline failure/cancel/quarantine tests complement
these successful live workflows; they do not claim every fault was tested live.

**Managed Objective V1 is also COMPLETE — SOFTWARE TESTED AND LIVE HARDWARE
VALIDATED.** See the [2026-10-01 closeout](#managed-objective-scanner-daq-ownership-v1-closeout-2026-10-01)
for the operator-reported live results and freshly rerun regression suite. The
managed window may remain open during localization after verified DAQ release.
Historical sections below describe the legacy/unmanaged widget and earlier
experimental checkpoints: their blanket widget-presence/fresh-session restriction
does not apply to a positively verified RELEASED managed owner. Unknown widgets
and unresolved evidence remain blocked. No Module 9 implementation is included.

Defaults: requested half-span=1.25*S; step=floor(min(15,S/20)); coverage rounds
up to whole steps. S=500 gives requested625, actual630, span1260, step15,
85 points/axis (170 H+V). Manual overrides remain. Local baseline is at most
100 um outside each edge, truncated at nearest crossing; width tolerance100 um,
min_snr6. theta=0, rotation_calibrated=False, FLIP_X(default).

Multi-H/rotation is DEFERRED — OPTIONAL FUTURE CALIBRATION. Module 9 next:
feature selection/guarded movement and physical relocation-accuracy assessment
of the translation-only assumption across the chip. Module 10: feature-centered
Width/Height ROI, preview and existing Snake Scan from its verified top-left.

Cleanup retained all imported diagnostic/calibration modules and regression tests.
Three required runtime journals were copied byte-for-byte to
`tests/fixtures/production_marker/` with documented provenance. Tests now require
those fixtures instead of arbitrary runtime UUID paths. Unused runtime outputs
and unreferenced one-off hardware harnesses were removed. Committed Module 7
profile journals and the 20 um vertical reference remain. localization_runs/ is
ignored for future runtime output. No numerical or hardware policy changes were
made during closeout. Stable UI remains unchanged.

---

# Module 8 M8.2a: fake-service localization orchestration

The M8.2a baseline below is preserved for context. The M8.2b-e experimental
extension and current readiness limits are recorded at the end of this document.

This implements the worker/state architecture requested by the current roadmap
handoff. It does **not** implement operational hardware integration. The roadmap,
stable UI, Module 6-7 algorithms and thresholds remain unchanged. Locate Marker
remains disabled; no fake-start button, scan backend, target motion, laser control,
device initialization or hardware recovery implementation is provided.

## Ownership findings and future boundary

Static inspection of `qcl_scanning_imaging_ui.py`, `ui/stage_windows.py`,
`ui/xbox_controller.py`, `ui/scan_windows.py`, and `experiment/routines.py` shows
that disabling the main button dictionary does not exclude every command source.
Manual stage controls, gamepad and scan workers share the stage object. The stage
SDK uses mutable session/receive-buffer state. Objective/focus routines can also
move hardware and retain a DAQ task. Existing snake/repeat routines call
`set_position`, which redefines coordinates; it is not ordinary stage movement.
Importing/constructing the stable operational window has hardware side effects.

Future integration must use one shared authority for the existing instrument
objects, not open a second Prior/COM3 connection. All competing entry points must
cooperate with the same guards, including gamepad and objective DAQ ownership.
The existing operational UI has **not** been retrofitted with those guards here.
This lease cannot exclude vendor applications or unguarded legacy callers.

## Pure Python contracts

`ui/localization_orchestration.py` contains no Qt or hardware imports.

- `HardwareOwnershipController.can_begin_localization()` returns
  `GuardDecision(allowed, reasons)`; `acquire()` returns a unique immutable
  `LocalizationLease`. One atomic lease covers stage, DAQ, gamepad, legacy scan
  and objective authority. Double acquire, forged/stale release are rejected.
- `set_activity(Activity, active)` models scan, repeat, multiwell, autofocus,
  gamepad, objective DAQ and frame-changing activity. It must receive actual
  lifecycle notifications in a later milestone. A conflict reported while leased
  quarantines ownership even if that conflict is subsequently cleared.
- `release(lease, CleanupOutcome)` requires DAQ release, idle and any required
  stop to be positively confirmed. Failed/uncertain cleanup quarantines ownership.
- `guard(Command)` gives centralized decisions. `dispatch(Command, callback)`
  guards and invokes a short fake/offline callback atomically. A future async job
  must register its activity before the callback returns. Do not put blocking
  native work inside `dispatch`; that would block other controller operations.
- `RunSettings` freezes context, generation and the operator's rough-start
  identity. That identity is **not** a stage readback or clearance check. Future
  acquisition requires separate bounds/readback/clearance validation.
- `LocalizationController.start(settings)` acquires the lease, preserving the
  approved registration. `offer_candidate`, `finish`, `request_cancel`,
  `handle_context_event`, `report_activity`, `snapshot`, `request_close` and
  `can_close` form the controller boundary.

Registration mutation, ownership, start and publication share one reentrant
transaction lock. A supplied ownership controller must be constructed with
`HardwareOwnershipController(registration_state.lock)`; a different lock is
rejected. This avoids a release/publication race and opposing lock orders.
Long fake/service work and cleanup execute outside this lock. Direct mutation of
public state fields is not a supported concurrent API; use controller/state methods.

## Worker and event model

Acquisition state is separate from registration validity and ownership:

```text
IDLE -> RUNNING -> COMPLETE or FAILED
               -> CANCELLING -> CANCELLED or FAILED
terminal -> IDLE -> RUNNING (only for a new authorized run)
```

Ownership independently reports AVAILABLE, LEASED or QUARANTINED. Uncertain
cleanup produces FAILED even when cancellation was requested. Invalid state
transitions raise an explicit error.

`LocateMarkerWorker` is a synchronous core, intended to execute on a worker thread.
Only tests implement its injected `LocalizationServices` protocol: `prepare`,
`work`, `movement_attempted`, `protective_stop`, `release_daq`, `confirm_idle`.
No service implementation for real instruments exists in this milestone.
The worker is single-use and does not run `scan_1d()`.

Events are immutable `WorkerEvent(name, run_id, context_generation, detail)`:
started, progress, phase_changed, warning, failed, cancelled,
registration_completed, finished. A queue retains events even if an observer
raises. Observers must be nonblocking. Stale workers do not call services or
cancel/settle another run. Consumers must use `event_is_current` before updating
the display from queued results, and refresh state from the controller snapshot.

`ui/localization_worker.py` is an optional thin QObject signal adapter. No thread
is created on import or by the panel. A future owner can move it to a QThread,
connect its run slot and consume signals through queued GUI slots. Keep worker
and thread alive through finished/cleanup; never access widgets from core work.
Cancellation calls the Event/controller directly, not a queued worker slot.

## Cancellation and cleanup

`CancellationToken` uses `threading.Event`: `request_cancel`, `is_cancelled`,
`checkpoint` (raises `Cancelled`). The worker checks before preparation, after
preparation, through service checkpoints, before accepting evidence and again
at settlement/publication. A commit lock serializes final publication against a
direct cancellation request; cancellation that happens after commit cannot undo
an already completed transaction.

Cooperative cancellation **cannot interrupt a blocked native SDK call**. The fake
blocked-call test keeps the lease active and close deferred until the call returns.
No concurrent stop is sent into a blocked call, no thread is killed, and no safe
native timeout/recovery is claimed. Real native hangs remain an open hardware risk.

Cleanup is deterministic:

1. On work/QC failure or cancellation, attempt protective stop only if actual
   driver entry was recorded. Preparation failure before entry sends no stop.
2. Release only the run-owned DAQ resource through the service contract.
3. Confirm stage idle.
4. Settle ownership; publish only on confirmed cleanup and all acceptance gates.

All cleanup methods are attempted even if an earlier cleanup method fails. An
unknown movement-entry flag quarantines ownership without guessing and issuing a
stop. Cleanup errors do not trigger exploratory movement, retries, return motion
or disconnection of a borrowed stage. A cleanup failure detected after successful
work quarantines rather than attempting a second cleanup/stop sequence.
Cancellation arriving during cleanup prevents publication; confirmed idle does
not require an additional stop merely because cancellation arrived late.

`request_close()` requests cancellation and defers shutdown while a run is active
or ownership is quarantined. It prevents new runs. This is a policy model only;
the stable UI close handler is untouched. There is no force-close safety claim.

Recovery requires `RecoveryConfirmation` for the quarantined run, explicit idle,
DAQ release, stopped competing activity, verified frame and a nonempty operator
note. Active leases/blockers prevent recovery. These are external attestations,
not automatic checks of physical safety. Recovery never restores approval.

## Transactional registration and context

`RegistrationState.approved_registration` references the existing approved result.
The controller owns a separate `candidate_registration`, run ID and acquisition
state. A start leaves prior approval intact. Candidate QC delegates to existing
Module 7 validation; no regression, threshold or transform is reimplemented.
Successful work, successful QC, confirmed cleanup and matching context/generation
are all required before `publish_candidate` atomically replaces approval.
Failed/cancelled candidates preserve prior approval only while context and
ownership remain trustworthy. Candidate warnings and hard reasons remain separate.

`RegistrationState.context_generation` increments for GDS/marker/orientation,
frame/zero, reconnect/reset, sample and input changes. Explicit events invalidate
even if identity text is unchanged. The controller cancels an active candidate
on such events. Changing text back cannot revive an old generation. Ordinary
movement does not invalidate; target/label changes clear predictions only.
Context changes or uncertain ownership invalidate prior approval immediately.

Legacy `begin()/accept()` still implement destructive archived replay replacement
for backward compatibility. Candidate runs never call them on the approved state;
they validate in an isolated state and publish transactionally. Archived replay
is guarded while localization owns the lease. Old evidence after invalidation
remains diagnostic, never a usable registration.

## UI guards and display

During a lease or quarantine, conflicting categories are blocked: manual/coordinate
motion, gamepad, scan/repeat/imaging/spectrum, multiwell, objective/autofocus,
speed/acceleration, frame/zero, GDS/marker/orientation/sample/input edits and replay.
Target motion is always unavailable. Logs, cached coordinates, progress, QC review
and cancellation remain allowed; a live coordinate query is not a cached read.

The experimental panel displays acquisition state, run ID, ownership, generation,
pending candidate, retained approval, run warnings and failure reasons. It disables
context editing and replay when blocked. It has no fake start controls and Locate
Marker stays disabled. No worker is connected to operational hardware/UI controls.
The whole selection editor is disabled while busy, although target-only changes
in the state model do not invalidate registration.

## Validation and next step

Offline tests cover leases/concurrency, all blockers/guards, quarantine/recovery,
state transitions, cancellation including a blocked synchronous fake call, partial
preparation failure, cleanup order/failures, transactional publication, stale IDs
and generations, warnings/reasons, context events, ordinary movement, target-only
changes, close deferral and blocked device imports. Existing offline replay and
UI tests remain applicable. Tests use fake services and committed journal replay;
the latter is pure file reading and Module 6-7 offline analysis.

Validation result: **350 tests passed** (48 orchestration, 26 offline UI,
20 overlay, 20 registration integration, 32 center refinement, 28 rotation,
31 classifier, 47 reflection scan, 25 adapters, 11 StageRegistration,
11 ChipLayout, 12 layout assignments, 21 GDS layout, 12 GDS preview,
6 GDS assignment). No skips or failures in the final runs. The new core runs
with Qt and instrument imports blocked; the offline UI runs with instrument
imports blocked. Adapter regressions use fake DAQ bindings, not a real SDK.
The stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.

Next: **M8.2b, a supervised single initial-H scan from the experimental UI**, only
after reviewing and implementing shared existing-stage ownership, explicit
run-owned DAQ lifecycle, legacy/gamepad/objective command guards and live frame
events. Wire QThread lifetime/close deferral, exact start and clearance/bounds
gates, and laser-owner policy before any hardware execution is authorized.
The present code cannot certify those operational preconditions. Full Locate
Marker, additional H/V profiles and target motion remain later milestones.

## M8.2b-e extension: injected full pipeline, live execution NOT READY

This review implements the complete numerical/fake workflow and an experimental
ownership bridge. It does not certify a live operational session. Locate Marker
remains disabled; no command launches a live scan. There is no production DAQ
factory, verified Prior owner-thread dispatcher, or single-H-only live action.
The roadmap is unchanged and Module 8 is not marked complete.

### Actual operational objects and lifetimes (static inspection)

| Resource | Object / creation / lifetime / thread |
| --- | --- |
| Prior | `mainWindow.stage`, created by `stageWorker.stage_initialize` on `threadStg`; initializer constructs `stage()` and connects COM3. Session survives initializer deletion/thread exit. GUI, gamepad, scan and objective paths subsequently share it. Main close disconnects it. |
| Stage panel | `stageMotionWindow.stage is mainWindow.stage`; created on GUI thread, constructor sets speed/acceleration and disables joystick. Its `goto`, `set_v`, `set_a`, `joystick`, `run_multiwell` and live `update_readings` are command entry points. |
| Gamepad | `stageMotionWindow.workerG` (`gamepad`) on `threadG`; `request_stop` sets an Event; command loop emits `stopped`, thread quits, `release_gamepad` clears references. `xboxController._monitor_thread` is a daemon; blocking `get_gamepad()` is not proven interruptible. |
| Hardware joystick | `stage.joystick(enable=...)`; toggle widgets are requested state, not independently confirmed physical state. No trustworthy disable confirmation is inferred from a checkbox. |
| Single/sweep/snake/repeat-snake/imaging | Shared `mainWindow.worker`; `threadRun` is reused for `experiment`, `snakeScan`, `repeatSnakeScan`, `imagingScan`. `threadRep` handles repeat experiment; `threadMul` handles repeated acquisition. Threads/workers may be deleted on completion. |
| Multiwell | `stageMotionWindow.workerMW` (`stageMotion`) on `threadMW`, created per run and deleted on completion. `parameters.stage` borrows the same stage. |
| Objective | `mainWindow.pi_scanner_widget`, constructed by `show_pi_scanner_widget` on GUI thread. `daq` is created/configured immediately and retained. Hidden/closed widget is not proof of task release. No reliable task-release signal exists. |
| Autofocus | `pi_scanner_widget.autofocus` operates stage, PI and retained DAQ. Usually GUI callback; snake workflows can reference this same widget. No reliable independent autofocus/motion idle flag exists. Presence blocks localization conservatively. |
| MIRcat | `mainWindow.laser`, constructed by `laserWorker.laser_initialize` on `threadLas`; initializer/thread then exit. Shared with `laserMenu` and acquisition workers. Legacy close disables/disarms it. No localization laser commands added. |
| PI | `mainWindow.pi_scanner.pidevice`, created/connected in main-window construction on GUI thread; shared with objective/scanning workflows, closed by legacy main close. |

Prior calls from multiple legacy threads are evidence of existing usage, **not**
evidence of SDK thread safety. The original creation thread exits; moving the same
session to an arbitrary new thread cannot be declared safe from this code alone.
MIRcat and PI affinity are likewise not established by shared legacy usage.
Objective QWidget access belongs on the GUI thread; legacy cross-thread references
are not reused for localization. These are unknown / require vendor contract or
separately supervised validation, not confirmed-safe hardware behavior.

### Bridge and guards

`OperationalLocalizationBridge(window, controller, executor=..., joystick_disabled=...)`
captures existing references only. It rejects another bridge for the same stage
and a stage window holding a different stage. No stage/session factory exists.
It neither connects, disconnects nor closes the borrowed session during a run.
The stage identity is rechecked on authorized operations.

`blockers()/refresh()/acquire()` adapt `threadRun`, `threadRep`, `threadMul`,
`threadMW`, `threadG/workerG`, objective presence, joystick confirmation, frame
activity and DAQ ownership into structured failures. Observed thread references
are retained even if a newer run replaces a window attribute. Deleted/unreadable
threads are uncertain, not assumed idle. Finished callbacks retain thread identity.

`quiesce_gamepad()` is an explicit pre-lease operation: request stop, bounded wait,
verify the SAME worker/thread finished, then release those references. Timeout,
replacement/stale completion or uncertainty blocks acquisition. It does not stop
the input-monitor daemon and does not disable a hardware joystick implicitly.
The default hardware-joystick confirmation provider returns unknown.

The experimental subclass installs guarded main entry points before base signal
binding. It wraps dynamic stage-panel callbacks and the shared `stage.message`
boundary, including session lifecycle methods. Conflicting callbacks are rejected
before legacy execution; GUI-level rejections are reported rather than raised out
of Qt's event loop. The raw driver boundary still raises for worker callers.
At this historical checkpoint, Objective creation was guarded and any existing
widget prevented localization. Managed V1 now guards the widget's hardware entry
points and permits coexistence only with positively verified resource release;
unmanaged widgets retain the original blocker.
This does not intercept arbitrary external applications or direct `stage.SDK`
calls outside the reviewed command boundary.

Frame hooks include raw position redefine, home/reference, reset/reconnect/session
replacement, communication loss and sample/GDS/marker/orientation/input changes.
They increment generation, invalidate approval and request cancellation. Detected
transport exceptions/nonzero replies conservatively invalidate the frame context.
Ordinary goto/gamepad/return-to-zero movement does not redefine coordinates.
UI diagnostics refresh cached state periodically, without querying instruments.

`execute_stage` delegates only to an injected owner executor, rechecking lease and
identity inside that executor. There is no direct worker-thread fallback. The
numerical tests include a serial executor on a distinct thread. The live wrapper
supplies NO executor: selecting a physically safe thread remains a readiness gate.
Any eventual queued/native implementation must retain in-flight ownership on timeout;
timing out a Future does not prove its native operation stopped.

`DaqOwnership` records a task and run ID; `claim_daq` requires `reset=False` and
rejects conflicts. Only that run can attest release. No objective/legacy task is
cleared or stolen. The injected pipeline factory receives the frozen settings;
it has no real implementation/default here. Partial factory failure that does not
return a task handle remains a live-provider design obligation.

Experimental `closeEvent` requests cancellation and ignores close while leased or
quarantined, preserving borrowed stage lifetime. `continue_localization_close`
allows legacy shutdown only after confirmed settlement. It is tested with an inert
base window; a real worker/thread launch and its automatic finish-to-close binding
are not enabled in the operational wrapper.

### Run specification and phase sequence

`LocalizationSpec` requires an operator-confirmed exact integral rough XY and
an explicit reviewed `StageBounds`/frame. No archived stage coordinates are defaults.
Defaults: side 500 um; background margin 100 um; step 10 um; edge width tolerance
100 um; position tolerance 1 um; five profiles; supported absolute rotation 5 deg;
center uncertainty allowance 20 um; inward guard 10 um; minimum three profiles;
required Y span 100 um; integral-um resolution. Bounds are never expanded.

The initial horizontal interval is rough X +/- (side/2 + margin), fixed rough Y.
The initial vertical interval is rough Y +/- the same half-width, at the rounded
measured H midpoint. Updated geometry is checked against the supplied bounds
before movement. Initial measured position must match the confirmed start exactly,
with idle checks before and after the injected DAQ setup.

DAQ remains X=`Dev1/ai0`, Y=`Dev1/ai1`, +/-10 V range, +/-9.9 V raw clipping,
32 samples/channel, 100000 samples/s/channel, finite/untriggered, reset=False.
Movement timeout 5 s; settling/readback, DAQ and stop timeouts 2 s;
polling 10 ms; continuously idle settling 100 ms. No threshold changes were made
to Module 6-7. Only nominal side geometry is supplied to their settings.

`LocalizationPipelineServices` performs:

1. Exact start/frame/marker/FLIP_X checks; unique run directory and spec manifest.
2. Initial H via `scan_1d`, finalized `load_scan` comparison and `analyze_scan`.
3. Initial V via the same engine and verification; measured initial center.
4. Conservative profile planning and bounded multi-H acquisition.
5. `classify_profiles` with both acceptance gates, then `fit_rotation` with the
   complete CENTRAL set. No fitter-side deletion or alternate subset search.
6. `refine_marker_center` using the accepted rotation and initial V journal.
7. `build_stage_registration`; existing bridge supports FLIP_X only, so other
   orientations fail before acquisition rather than silently changing orientation.
8. Optional success-only return, then M8.2a cleanup and transactional publication.

Planner half-span is `S/2*(cos(T)-sin(T)) - guard - center_uncertainty` for supported
`|theta| <= T < 45 deg`; this is the interval minimum because cos-sin decreases
there. Symmetric positions use an integral center anchor and inward-rounded span.
Count, distinct Y, required leverage, guard containment and all X paths are checked
again after rounding. Failure does not expand bounds or acquire extra profiles.

Every completed profile is reloaded and compared with the in-memory result,
settings and point count; measured coordinates are required. `profile_completed`
is emitted only after finalized journal and edge validation. Each profile has its
own JSONL. The run manifest records context/generation/spec; evidence hashes bind
the seven verified profiles for the default configuration. Partial files survive
failure. Logs/progress include phase, rough start, geometry, initial center,
classification, accepted angle, refined center, warnings and run status.

### Return/publication and failure matrix

Return is configurable, enabled by default, and only follows all analysis gates.
It checks bounds/ownership, motion deadline, continuously idle settling and measured
readback. No reflection is acquired during return. Failure prevents publication.
The candidate replaces approval only after the return (if selected), cleanup,
unchanged generation and ownership checks. No return or retry follows a failure.

| Failure / cancellation | Behavior |
| --- | --- |
| Start/context/lease failure | No motion; no approval; pre-entry failure sends no stop. |
| H/V/profile read, position, edge or journal failure | Stop first-error chain; preserve partial journal; no next profile/return. |
| Planning/classification/rotation/center/registration failure | No rescue profiles/refits; no return/publication. |
| Return failure | No candidate approval; no corrective move/retry. |
| Cancellation during polling/read boundaries or between phases | Cooperative checkpoint abort; blocked native call is not interrupted. |
| Frame/session/communication invalidation | Prior approval invalidated and candidate cancellation requested. |
| Safe failure with unchanged trusted context | Prior approval retained; candidate discarded. |
| Cleanup/stop/idle uncertainty | Quarantine; prior approval unusable; explicit recovery required. |

The Prior message guard records actual goto command entry. The proxy suppresses
stop before entry and latches one stop attempt, avoiding a second stop/retry when
`scan_1d` already attempted protective stop. Cleanup uses the authorized owner
path without bypassing lease checks. Quarantined/lost authority is not permission
to issue concurrent recovery commands. DAQ clear and idle confirmation remain
separate cleanup checks. Candidate diagnostics are not physical accuracy claims.

### Readiness and first supervised H procedure

**NOT READY.** No executable live procedure is authorized/provided yet. Do not run
`--hardware` as a localization test, and do not inject the fake full-pipeline test
entry point into a live session. The first live attempt must be H-only, not this
full H/V/multi-H pipeline.

Concrete remaining gates: establish the Prior SDK owner-thread/session contract;
implement a reviewed dispatcher with in-flight timeout ownership; independently
confirm hardware joystick disabled; confirm objective/DAQ absence or reliable
release; provide a run-owned non-resetting DAQ factory with partial-setup cleanup;
bind worker/thread lifetime, cancellation and deferred close; add an isolated H-only
action and reviewed operator rough-start/clearance/bounds confirmation.

The later H-only procedure must show the actual start, frame and complete envelope,
use the spec/settings above, verify one finalized journal and its edge diagnostics,
return only after success, and stop without automatic return after error. On fault,
inspect partial journal/stop/DAQ/idle outcomes; quarantined ownership cannot be
reused on a button click. Native hangs require an external recovery plan.
Laser ownership must be singular: the operational Python UI already owns MIRcat,
so the vendor GUI cannot be assumed safe to control it concurrently. A reviewed
laser configuration/ownership decision is required before the supervised run.
After a successful single-H test and review, proceed to separately supervised H+V,
then multi-H/full registration. No target motion or imaging integration is included.

Offline validation: 404 tests passed across 17 suites (28 operational bridge,
24 full pipeline, 48 orchestration, 28 UI, and 276 upstream tests). The pipeline
tests execute unchanged scan/analysis/registration APIs over numerical fake
devices, including per-point journals, failure injection and return settling.
No operational hardware window or hardware service was initialized. The stable
UI SHA256 remains `fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.

### Prior dispatcher review (2026-09-30)

Thread contract classification: **B - cross-thread use exists, safety undocumented**.
`instruments/hld117.py:stage` is an ordinary Python object, not a QObject. Its
constructor loads WinDLL, initializes the SDK, creates one session and one shared
`rx` buffer. `message()` calls `PriorScientificSDK_cmd(session, ..., rx)` without
a mutex, thread check or documented affinity. The bundled
`instruments/prior/PriorScientificSDK.h` and `Prior Scientific SDK.docx` do not
state a threading/affinity guarantee. Existing use is evidence of architecture,
not proof that this SDK version supports arbitrary-thread or concurrent access.

| Lifetime / caller | Exact path and execution context |
| --- | --- |
| Construction and COM connection | Main window creates `stageWorker = stageInitializer` and moves it to `threadStg`. `threadStg.started -> stage_initialize()` constructs `stage0`, calls connect/identify on that QThread. |
| Transfer | `stageInstance -> mainWindow.stage_set` stores `self.stage`; stage motion/objective/scan parameters share that object. |
| Initializer shutdown | `stageInitialized` requests `threadStg.quit`, worker deletion; `threadStg.finished` deletes the QThread wrapper. There is no persistent initializer command loop to reuse. |
| GUI commands | `stageMotionWindow` construction configures speed/acceleration/joystick; manual goto, speed/acceleration, joystick and readback callbacks execute on GUI thread. |
| Gamepad | `stageMotionWindow.workerG` (`gamepad`) runs `read` on `threadG`: velocity/relative/goto/readback/stop commands. Its finally block also stops the stage. |
| Python input thread | `ui/xbox_controller.py` starts a daemon monitor that reads input state. Stage commands belong to the gamepad QThread, not this monitor. Stopping the monitor does not prove the command worker has finished. |
| Multiwell | `stageMotionWindow.workerMW` (`stageMotion`) uses shared parameters.stage on `threadMW`; main-window multiple workflow uses `threadMul`. |
| Acquisition | `experiment/routines.py` workers use parameters.stage on main-window `threadRun`/`threadRep` (snake, repeat snake, imaging and related routines). |
| Objective/autofocus | `instruments/pi_scanner.py` autofocus reads/moves/restores the shared stage, normally from GUI callbacks and also called from imaging workers. An existing objective widget remains a blocker. |
| Shutdown | Main-window closeEvent stops gamepad, closes PI, calls stage.disconnect, then laser disable/disarm on GUI thread. It does not explicitly call stage.close_session; the wrapper provides that SDK function separately. Localization never owns either shutdown operation. |

**Execution target:** queued single SDK calls on a QObject constructed in the
main Qt thread. This is the persistent existing GUI command path, not a newly
invented thread for an already-created session. No new session, migration or
connect is attempted. The initializer cannot be targeted after it exits. A
dedicated thread cannot establish affinity merely by receiving the same object.
This main-thread strategy minimizes additional assumptions but does not remove
the undocumented initializer-to-GUI handoff. Live bridge acquisition explicitly
blocks on `Prior_session_execution_contract_unverified` until that contract has
been reviewed. Inert executor injection remains test-only.

`ui/stage_command_dispatcher.py` provides `StageCommandDispatcher.execute`,
`last_ticket`, `unresolved`, `uncertain`, and `shutdown`; `qt_main_thread_target`
provides nonblocking queued submission. A blocking caller on the target thread
is rejected. Authorization uses the exact active handle/lease before submission
and again on execution. Only one ticket may be outstanding; a second command is
rejected instead of issuing overlapping work. Results/exceptions reach the caller.

The bridge's `stage_interface(handle, bounds, polling_s, clock)` exposes
get_position, move_to, is_busy, stop/stop_smoothly and wait_until_idle. It builds
the unchanged PriorStageAdapter over a message-only capability; each SDK message
is dispatched individually. Bounds/readback parsing and polling remain in the
existing adapter on the caller worker, not a long GUI-thread polling loop.
`localization_pipeline.py` no longer constructs an adapter over the raw stage.
The raw stage is retained only at the operational boundary. No numerical
algorithm or threshold changed.

**Timeout semantics:** caller deadline expiry raises NativeCallUncertain, latches
dispatcher uncertainty, quarantines the lease, invalidates registration and
requests candidate cancellation. An expired queued command is skipped; a call
already entered may still be executing. No follow-up read/move/stop or borrowed
session shutdown is permitted, including through legacy guards. Late completion
updates the diagnostic ticket only; it neither clears the latch nor restores
approval. Stop failure also quarantines. Dispatcher shutdown never disconnects;
with unresolved execution it returns False and quarantines instead of pretending
completion. No QThread.terminate, thread kill or second-owner stop exists.

A native hang in the GUI thread can freeze the GUI and delay button/close events.
The waiting worker can still time out if Python scheduling remains available;
this is not an OS/native hard real-time guarantee. No software emergency-stop
claim is made. Recovery requires positive external completion/idle/frame checks
and a separately reviewed dispatcher reconstruction; no reset/recovery button is
implemented. Even an ownership recovery attestation alone cannot unlock the
latched dispatcher/legacy command guard or deferred shutdown.

**Legacy scope:** reviewed stage wrappers ultimately use the intercepted instance
message method; connect/disconnect/close_session and experimental callbacks are
also guarded. No direct stage.SDK calls were found in reviewed operational clients.
External processes, unreviewed direct SDK access or replacing wrappers are outside
this guarantee. No legacy caller was silently rewritten to another thread.
Gamepad handoff still requires producer stop AND command-worker completion,
including its final stop, before leasing; hardware joystick confirmation remains
separate. Objective and acquisition blockers still apply.

**Validation:** 32 dispatcher tests plus the existing 404 tests (436 total) cover
identity/no session lifecycle calls, authorization, serialization, queued/native
timeout, stale commands, stop failures, quarantine, late completion, close and
shutdown, import isolation and the full fake localization pipeline. Qt tests
verify that a fake Prior message executes on the main QObject thread while the
caller is a different thread, and cover queued result/error/timeout delivery.

**PRIOR DISPATCHER READY: NO** for live use: software dispatch is tested, but the
SDK session execution contract remains unsupported by available documentation.
**READY FOR SUPERVISED H-ONLY HARDWARE TEST: NO.** Next obtain authoritative SDK
thread-contract evidence or review an experimental-only lifecycle establishing
construction/connect/use on one persistent thread, without modifying the stable
UI. Then close gamepad/joystick, objective/DAQ, non-resetting live DAQ provider,
worker/cancellation lifetime, laser ownership and isolated H-only launch gates.
No hardware run, target navigation or ROI implementation is part of this task.

### Persistent Prior owner (supersedes the borrowed-session thread blocker)

The experimental startup now uses `ui/persistent_prior_owner.py`. This changes
only `qcl_scanning_imaging_autorelocation_ui.py` and supporting experimental code;
the stable entry point and its module globals remain untouched.

**Injection:** the base constructor has no dependency-injection argument. Its
earliest stage factory lookup is the `stageInitializer` global in `__init__`.
`constructor_with_proxy` binds the same constructor code/defaults/`__class__`
closure to a private copy of its globals, substituting only this initializer.
No shared module monkey patch and no copied UI implementation are used. Startup
rejects an incompatible constructor before creating an owner. The replacement
initializer only emits the already-connected proxy through the existing signals.
Its temporary QThread remains a delivery mechanism, never a native session owner.
The original constructor/global lookup remains intact for the old entry point.

The persistent owner starts before inherited startup. Model/COM configuration is
read from the inherited constructor's configuration, not a second connection.
The owner creates the driver, initializes SDK/session, connects and identifies on
one persistent QThread. A context rejects a second owner; start/connect are
single-use. `mainWindow.stage`, stageMotionWindow, gamepad, scan parameters and
objective paths receive the same proxy identity through normal base wiring.
The real factory imports/constructs Prior only inside the owner thread. Default
offline UI never calls it. Real experimental startup still has inherited
MIRcat/PI and stage-configuration side effects and has NOT been executed here.

**Compatibility:** synchronous copied returns and keyword arguments are preserved
for message, busy, get_position/get_speed/get_acc, goto, identify, joystick,
move_at_velocity/move_rel/reference, set_acc/set_position/set_speed, stop_smoothly,
encoder_res, arm_trigger, make_snakes and wait_until_ready. Configuration lists
speeds/steps/accs and defaultSpeed/defaultAcc/realHw are copied data, not raw state.
Reviewed clients do not mutate those attributes or require SDK/session/rx handles.
Position/integer formatting remains in the existing driver. Connect is explicitly
rejected after startup. Disconnect invokes the owner's full cleanup; close_session
cannot close a live session independently. Normal driver return types are retained;
SDK failures now raise RuntimeError rather than being silently discarded. Error
text crosses threads, not tracebacks retaining raw driver objects.

`piScanner_widget` has a standalone fallback that creates a stage when no instance
is supplied. Reviewed operational callers pass the existing stage; the experimental
flow must continue to pass the proxy and must never use that fallback. Existing
objective/DAQ ownership remains a localization blocker.

**One physical execution queue:** GUI/gamepad/scan/localization -> shared proxy ->
persistent owner QThread -> raw driver. A bounded caller lock serializes legacy
callers; StageCommandDispatcher supplies queued-call result/timeout bookkeeping.
Localization's existing dispatcher remains an authorization/lease layer in the
calling worker, with an inline capability call to the proxy, not a second Qt
execution target. Localization timeouts propagate to the owner's call deadline.
The old main-thread target remains only for its isolated tests/inert fixtures.
All raw methods, including their nested SDK calls, run on the owner thread.
The raw message boundary checks SDK status even for legacy methods that discard
their return values. Raw objects/handles are never returned by proxy APIs.

**Guards:** guarding only proxy.message would miss SDK calls made inside raw goto
or joystick. The bridge therefore guards every proxy invocation as well as existing
experimental callbacks. Localization authority is checked in the calling thread;
legacy commands are rejected while leased before reaching the owner queue. Frame
redefinitions invalidate context; ordinary goto does not. The proxy cannot bypass
global owner uncertainty. No new gamepad implementation or acquisition algorithm
is introduced.

**Timeout:** waiting for the caller-serialization lock can time out without
submitting any native call. Once submitted, expiry latches native uncertainty;
no new raw call, concurrent stop or disconnect is allowed. Late completion never
clears it automatically. The owner notifies the bridge to quarantine an active
localization lease and invalidate registration. The raw object/thread remain
retained after timeout, including failed startup. No terminate/kill capability or
automatic retry/recovery exists. Default legacy-call timeout is 5 s; localization
supplies its reviewed timeout. A long native wait may therefore now fail closed
where legacy code previously waited indefinitely.

**Shutdown:** reject close during localization/unresolved cleanup; defer while
legacy acquisition workers remain active. The inherited close handler stops and
joins the gamepad command worker before its stage disconnect call. That call is
intercepted by the proxy: disconnect, checked CloseSession and raw destruction all
occur on the owner thread, then quit/wait ends that QThread. Only confirmed cleanup
allows application shutdown. Failure leaves close unaccepted and the owner retained.
No raw session is disconnected from the GUI thread. Initialization errors that
returned normally permit owner-thread partial cleanup; unresolved startup does not.
Cleanup itself is bounded and cannot be treated as successful after a timeout.

**Validation:** 41 new fake-owner tests plus 436 regression tests, 477 total.
Thread-recording fakes verify construction, connect, identify, operations,
disconnect, CloseSession and destruction on the same persistent thread; tests
exercise GUI/worker callers, competing callers, failure/timeout/late completion,
proxy guards, localization, isolated startup globals and exactly one factory call.
No real Prior/DAQ/MIRcat/PI, COM3, gamepad control or `--hardware` run occurred.
Stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.

**PERSISTENT PRIOR OWNER READY: YES** means internally consistent and fake-tested,
not hardware validated. The raw session no longer depends on undocumented migration
between initializer/GUI/worker threads. **READY FOR SUPERVISED H-ONLY HARDWARE TEST:
NO.** Next validate deterministic gamepad command-worker plus hardware-joystick
handoff over this proxy with inert tests. Objective/DAQ ownership, the real
non-resetting DAQ provider, live worker/cancel binding, laser ownership, rough-start
coverage and isolated H-only launch remain gates. The finalized Module 8-10 product
workflow is unchanged; no target-motion or ROI implementation is included.

## Isolated H-only live gates (2026-09-30)

This section supersedes the earlier readiness verdicts, which describe preceding
milestones. **READY FOR SUPERVISED H-ONLY HARDWARE TEST: YES**, subject to the
prerequisites below. This means implementation plus inert/fake validation, NOT
successful real hardware operation. Full live Locate Marker remains disabled.
No hardware was initialized or commanded during this work.

Validation: **534 offline/inert tests passed** (477 prior tests plus 57 new tests:
33 H-only/handoff, 13 owned-DAQ, 11 Qt worker/close tests). NI tests execute the
existing bounded-read method with injected DAQmx bindings, including setup/start/
read/stop/clear failures. Qt end-to-end tests use a persistent fake Prior owner,
fake DAQ and unchanged numerical APIs. Full-suite command:
`python -B -m unittest discover -s tests -v`. Stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.

### Handoff and ownership

`ui/h_only_validation.py` provides immutable `HOnlySpec`, explicit
`OperatorConfirmation`, `InputHandoff`, and single-H services. The existing
gamepad command worker receives `request_stop`; its exact QThread must finish
within 3 seconds, remain the same worker/thread pair, report not running and
finished, and then be released. Timeout, stale completion, missing worker/thread
or a still-active worker blocks acquisition. No assumption is made that the
separate gamepad input-monitor daemon has been joined. It no longer has a command
consumer after that worker exits. Synchronous owner calls mean there are no
uncompleted commands from a successfully joined command worker.

Next, the existing shared stage proxy disables the hardware joystick. The Prior
wrapper uses `controller.stage.joyxyz.off/on`; no state readback is exposed.
`StageProxy.joystick_state` records only the last successfully acknowledged
software command. Unknown state or failed disable blocks H-only. The owner checks
the underlying SDK status even though the legacy wrapper discards it. This is
**command acknowledgement, not independent physical joystick-state verification**.
Only after handoff does the bridge grant the localization lease. Re-read idle/XY
under that lease before and after DAQ setup; error above 1 um Euclidean aborts.

After stop/DAQ cleanup/idle are confirmed and frame generation is unchanged,
restore the previously acknowledged hardware joystick state through the authorized
proxy. Restoration failure quarantines. Uncertain cleanup never re-enables inputs.
The gamepad worker is intentionally NOT restarted automatically: a held stick
could otherwise produce immediate motion. Its existing control becomes available
for deliberate operator restart after safe cleanup. A failed preflight/handoff
may leave inputs disabled; it does not guess a restore state or retry.

### Objective and legacy DAQ blockers

This paragraph records the pre-managed H-only checkpoint. The Managed Objective
V1 closeout below supersedes its blanket widget-presence restriction; verified
managed release and source-specific Snake release are now supported.

Actual legacy QThread/callback activity, gamepad ownership, frame operation and
DAQ ownership remain blockers. An existing `pi_scanner_widget`, even hidden,
blocks H-only because it retains a DAQ task without a checked release signal.
Explicit autofocus/objective-motion/objective-DAQ/unknown-ownership flags also
block. Do not steal/clear that task. A new legacy acquisition launched through the
experimental wrapper latches `legacy_daq_cleanup_unverified`: legacy completion
and unchecked `clear_task()` do not attest cleanup. H-only requires a fresh UI
session after such activity. This restriction affects H-only eligibility, not the
stable UI or availability of normal legacy scans when no localization lease exists.
External processes cannot be excluded by an in-process lease; operator confirmation
requires that they are closed.

### Owned NI task

`ui/localization_daq.py` defers the real NI import and creation until a lease is
granted. An injectable backend permits tests without loading vendor libraries.
The provider reuses `MultiChannelAnalogInput(reset=False)` and its validated
`acquire_bounded`; `NIReflectionReader` retains all signal/sample/clipping logic.
Checked configuration: Dev1/ai0 lock-in X, Dev1/ai1 lock-in Y, input +/-10 V,
clipping at +/-9.9 V, 32 samples/channel, 100 kS/s, finite and untriggered. No
reset, objective-task reuse or second run owner is allowed.

The run claims the task before native configuration. Failure after CreateTask,
either channel or timing attempts one checked clear of its own handle. Cleanup
failure retains uncertain ownership and quarantines; it is not retried. Acquisition
uses a 2-second bounded read and the existing start/read/stop logic. Read timeout,
short count, clipping and SDK errors stop the chain. Task clear occurs exactly once
when possible; repeated calls do not issue another native clear. A hung SDK call
cannot be force-interrupted: retain the worker/resources and defer shutdown until
completion is known. Stop/clear errors remain separate from the scan failure.

### Laser policy

The hardware experimental UI uses its inherited, single Python MIRcat object.
The vendor GUI and other Python laser controllers must be closed. H-only neither
connects another laser nor arms, tunes or enables emission. The operator uses
existing controls and explicitly confirms physical emission ON, wavenumber and
SR865A settings. Cached armed/tuned flags are supporting gates. The legacy
`enable()` does not refresh `isEmitting`, and `get_wavelength()` drops validity/unit
information; therefore this is NOT presented as fresh SDK emission/wavelength
verification. The result retains that limitation as a warning. Tune/enable/settings
mutations are guarded during the lease. Operator disable/disarm remains available
and requests cancellation; no automatic emission change is performed by H-only.

### Worker, UI and publication boundary

`ui/h_only_controls.py` owns a persistent runner reference and one QObject worker
on a QThread per run. It connects progress/results by run ID and context generation.
The cancellation Event is set directly; it does not depend on a queued worker slot.
Duplicate starts are rejected. Worker objects stay alive until completion, with
deleteLater/quit and GUI-thread final reporting. No terminate/forced deletion is used.
Close requests cancel and defer until worker exit, DAQ cleanup, input restoration,
lease settlement and owner-thread Prior shutdown. Native uncertainty or quarantine
prevents a fake-successful close, even after late native completion.

The separate **Run H-Only Validation** action lives under Auto Location in the
hardware experimental UI. Full **Locate Marker** stays disabled. `RunSettings`
purpose `h_only` explicitly forbids candidate registration publication. This path
does only initial H, finalized journal verification, existing width-guided analysis,
and verified success-only return. No V scan, profiles, fitting, feature movement,
ROI or Snake Scan is called. An existing approved registration is not replaced;
frame/hardware integrity failures still invalidate it through the normal lifecycle.

Preview the envelope before enabling Run; any edited scan input clears the review
and confirmations. The reviewed spec/context/generation must still match at launch.
Confirmed rough XY must be integer stage coordinates in the selected live frame;
archived frame/sample/input identities are rejected. Selected marker comes from
manual GDS assignments; nominal side comes from its square geometry. The full
horizontal path and return must fit operator-entered bounds before any movement.
Default 500 um side, 100 um margin and 10 um step produce X0-350 -> X0+350 at Y0,
71 points. This development envelope does not guarantee both edges from every
possible point on a square. Choose a roughly central point for the first test;
insufficient edge support fails closed without expansion or retry.

The report separates run/analysis, return, protective stop, DAQ clear, idle check,
input restoration, terminal state and quarantine. It records requested/measured
ranges, count, edges/midpoint/width, expected width, contrast/noise/support/candidate
diagnostics, run/context IDs and warnings. Evidence is written under
`localization_runs/<run-id>/`: `run.json`, `operator_confirmation.json`,
`initial_H.jsonl`, `h_only_result.json`. Partial journals are retained. Failure
before setup may produce no journal; an unconfirmed shutdown may not yet have a
final report. Report-write errors are displayed rather than hidden.

### Failure / recovery matrix

| Condition | Action |
|---|---|
| Missing context, confirmation, reviewed envelope, bounds or laser setup | No launch |
| Gamepad timeout/stale completion or unknown joystick | No lease/DAQ/scan; keep uncertain sources blocked |
| Objective widget or legacy DAQ release unknown | Block; require clean session after independently verified cleanup |
| Start changed >1 um or busy | Abort before motion; clean only owned resources |
| Scan/read/journal/edge/width failure | First-error stop; no retry and no return |
| Cancel | Cooperative checkpoints; protective stop only after actual move entry; no return |
| Return failure | Run fails; no registration publication |
| DAQ/stop/idle/restore failure or frame change | Quarantine/invalidity; do not silently restore motion sources |
| Native call unresolved | No concurrent stop/disconnect; retain owner/worker; close remains deferred |

Recovery is operator-supervised, not an automatic reset button. Retain errors and
journals, use independently reviewed read-only/idle/session checks after the native
call is known to have returned, and re-establish frame/XY/clearance before any new
motion. Never start a second UI/COM owner to recover a still-running session.

### First supervised H-only procedure (NOT executed)

1. Close the stable UI, MIRcat vendor GUI, standalone acquisition scripts and other
   stage/DAQ/laser owners. Confirm normal instrument wiring and safe startup settings.
   Launch `python .\qcl_scanning_imaging_autorelocation_ui.py --hardware` only when
   separately authorized. This explicitly starts inherited Prior/MIRcat/PI hardware;
   it has never been run against hardware by this task.
2. Use a fresh session: do not open the objective/autofocus widget or run any legacy
   Single/Snake/imaging/repeat/multiwell acquisition before H-only.
3. In Auto Location load GDS and manually select the square gold marker/desired
   targets. Enter non-archived, current frame, sample and inputs identities. Do not
   replay archived registration as a substitute for live frame confirmation.
4. Establish 1500 cm^-1 and physical emission ON using existing Python laser controls;
   SR865A 20 mV, 300 us, Advanced 24 dB. Confirm the actual physical/settings state.
   H-only will not tune or enable the laser. Vendor GUI remains closed.
5. Use the existing stage/gamepad controls to reach a roughly central point on the
   selected marker. Release sticks. Preview reads fresh XY; do not enter archived
   coordinates. Enter the operator note and desired margin/step. Leave proposed
   clearance bounds enabled, or enter explicit reviewed limits in manual mode.
   Neither mode establishes physical clearance automatically.
6. For side 500, margin 100, step 10, review X0-350 through X0+350 at Y0 (71 points).
   Bounds must contain every point and start/return; for example X0 +/-351 and
   Y0 +/-1 are a narrow envelope only if the operator has verified their clearance.
   Press **Preview H Envelope**, review it, then check all four confirmations.
   Editing any field requires a new preview and fresh confirmations.
7. Press **Run H-Only Validation** once. Expect gamepad worker stop/confirmation,
   joystick-off acknowledgement, lease acquisition, idle/start re-read, independent
   NI task setup, a second start check, exactly one H scan and edge analysis.
   Timeouts: move 5 s; readback/settling, DAQ and protective stop 2 s; polling 10 ms;
   continuously idle settling 100 ms; position tolerance 1 um. Width analysis uses
   nominal 500 +/-100 um without assuming polarity. NI settings are listed above.
8. Inspect progress and run diagnostics. Success requires 71/71 points, finalized
   journal, unique valid edges, verified return to confirmed start, confirmed cleanup
   and input restore. Hardware joystick returns to its prior acknowledged state;
   manually restart the existing gamepad only when safe. H-only publishes no registration.
9. Cancel for an unexpected path, signal/position problem or operator concern. Do
   not expect return after cancel/failure. Emission-off remains available. Inspect
   separate primary and cleanup errors; do not retry a quarantined/unresolved session.
10. Stop after this one profile and review the saved evidence. Do not test V, full
    Locate Marker, target moves, ROI or Snake Scan. After a successful reviewed H-only
    run, prepare the separately supervised initial H+V milestone.

### H-envelope preview and tab usability correction

Operator-reported preparation reached GDS selection and confirmations, but Preview
failed before motion. The former `HOnlyControls.build()` evaluated
`float(self.fields['x'].text())` while rough X was initialized to an empty string.
Rough Y and four bounds were also initially blank. Preview did not read the stage.

Preview now reads fresh XY through the existing persistent proxy with a 2-second
call timeout; it does not stop the gamepad, change joystick state, create DAQ,
change laser state or move. Release the gamepad before preview. Every preview
captures a new immutable spec/context/generation and clears prior confirmations.
Run still re-reads idle/XY after ownership acquisition and DAQ setup, enforcing
the existing 1 um tolerance. No acquisition/ownership/numerical policy changed.

| Value | Source |
|---|---|
| Rough X/Y | Fresh proxy readback on Preview; displayed read-only |
| Marker width/height and expected width | Operator-selected square GDS marker geometry |
| Margin and step | Validated defaults 100 um / 10 um; labeled operator-editable configuration |
| Width tolerance | Existing HOnlySpec default 100 um |
| Position tolerance | Existing HOnlySpec fixed validated value 1 um |
| Clearance bounds | Default proposed H envelope plus 1 um padding, explicitly operator-confirmed; optional manual current-frame limits |
| Physical clearance / laser / lock-in / note | Explicit operator confirmation/input |

Proposed bounds are not discovered mechanical limits or proof of sample/objective
clearance. Legacy travel extent does not establish absolute limits in a redefined
controller frame. Preview labels the proposal accordingly. Uncheck the proposal
option to enter reviewed bounds explicitly; empty/invalid/nonfinite values receive
field-specific errors before numeric conversion. For side 500, defaults give
X0-350 to X0+350 at Y0, 71 points and return to X0/Y0. Enter note/settings before
preview, then review the diagnostics and confirm clearance/settings before Run.

Auto Location now has a widget-resizable vertical scroll wrapper in both entry
paths. Registration and assignment buttons reflow into shorter rows, while the
GDS canvas keeps a 300-pixel minimum height. The shared GDS widget implementation
and stable operational UI are untouched. A local `AutoLocationPanel` stylesheet
overrides inherited legacy dark container rules with neutral backgrounds and dark
text, including disabled and selected states. The GDS scene retains its dark
canvas. No application-wide stylesheet or palette changes are made.

Tests exercise empty-field reproduction, fresh readback, missing/unavailable
values, unchanged gamepad/DAQ state, scrolling at 1280x720 and contrasting palettes.
The offscreen Qt environment lacks system fonts; screenshot inspection loaded
Segoe UI only into the temporary inspection process, not production UI code.


## First supervised live H-only validation: PASSED

Operator-reported live run `495ebff7920b4d1296f5e9680afdd2a5` is also recorded in
`localization_runs/495ebff7920b4d1296f5e9680afdd2a5/initial_H.jsonl` and its local
`h_only_result.json`. These existing local evidence files were read, not modified.
Requested and measured X: 3830 to 4530 um, fixed Y -26100 um; 71/71 points.
Reported edges: 3966.049 and 4463.602 um; midpoint 4214.825 um; width 497.554 um
(expected 500 um). Edge analysis VALID, return PASS, DAQ cleanup PASS, ownership
AVAILABLE, H-only complete; registration published False. Rounded figures here
are evidence summaries, not production defaults or claims of physical accuracy.

The normal live path demonstrated the persistent owner/proxy, input handoff,
run-owned NI provider, journaled scan, analysis, return and cleanup. It does not
validate hardware fault injection or native-call interruption. Known warnings:
`joystick_command_ack_only` and
`laser_operator_confirmation_not_fresh_SDK_readback` remain explicit limitations.
Full live Locate Marker remains disabled. This is not full Module 8 validation.

## Next supervised development gate: H+V (implementation and inert validation)

`ui/hv_validation.py` extends the existing H-only spec/services; the shared Qt
runner, handoff, NI provider, scanner, edge analysis, return and cleanup are reused.
`RunSettings.purpose='hv'` is explicitly non-publishing, like `h_only`. A successful
run never calls classification, rotation, center refinement or StageRegistration.

Sequence: operator preview/confirmation -> exclusive ownership and existing input
handoff -> fresh idle/start checks before and after DAQ setup -> initial H ->
finalized-journal verification/unique width-guided edges -> dynamic V plan ->
initial V -> finalized-journal verification/unique width-guided edges -> initial
(H midpoint, V midpoint) estimate -> verified success-only return -> owned DAQ,
idle and input-restore cleanup. Both scans call unchanged `scan_1d()` and
`analyze_scan()`. H-only still performs exactly one scan.

For nominal side 500, margin 100, step 10 and fresh rough start (X0,Y0):

- H: X0-350 to X0+350 at Y0, increasing X, 71 points.
- V: Y0-350 to Y0+350, increasing numeric Y (including negative coordinates),
  71 points. Fixed X is nearest integer H midpoint, ties-to-even, never truncation.
  The result reports the floating midpoint, chosen integer X and signed delta.
- V X is unknown before H. The operator reviews the rounding policy and the full
  possible rectangle, not an invented exact V X. Prevalidation checks both extreme
  V lines at the H endpoints. Dynamic V X must stay inside this reviewed H range;
  every V target is checked again before motion.
- Proposed clearance bounds: X0 +/-351 and Y0 +/-351, including tolerance padding.
  These are not measured mechanical limits. The entire rectangle, diagonal
  reposition/approach and return require actual operator clearance approval.
- A roughly central starting point is recommended. This fixed envelope does not
  guarantee edge coverage from an arbitrary point near a marker corner. Missing
  edges fail closed; no automatic extension, retry or extra profile is allowed.

**Separate authorization:** Preview H+V Envelope clears old H-only confirmations.
Run H+V requires all original confirmations plus an explicit BOTH X/Y full-2D
clearance checkbox. Field/context changes require a fresh review. The shared runner
prevents overlapping H/H+V runs, and both sets of controls lock during acquisition.

Each run retains `initial_H.jsonl` and `initial_V.jsonl` separately under its unique
run directory. `hv_result.json` and UI run diagnostics include requested/measured
ranges, counts, both edge analyses (contrast/noise/candidate details), dynamic V X,
initial center, warnings, return/cleanup/ownership and completion status. Partial
journals remain after failure. No StageRegistration is published.

Cancellation checkpoints exist after each verified journal, before V reposition,
during scan polling, and before/during return. H failure prevents V; either-axis
failure/cancel prevents automatic return. Failed return prevents success. Cleanup
failure or uncertain native execution quarantines; no concurrent stop, forced thread
termination, automatic reset or second session is introduced. Deferred close uses
the same runner/owner lifecycle as H-only.

### Exact next supervised H+V procedure (not executed by this implementation task)

1. Close other stage/DAQ owners, the stable UI, standalone scripts and MIRcat vendor
   GUI. Start a fresh `python .\qcl_scanning_imaging_autorelocation_ui.py --hardware`
   session only for the separately supervised test. Do not open objective/autofocus
   or perform legacy acquisition first; uncertain legacy DAQ ownership blocks launch.
2. Python is sole MIRcat owner. Establish and physically confirm emission/settings
   using existing controls: 1500 cm^-1; SR865A 20 mV, 300 us, Advanced 24 dB.
   H+V does not tune or enable emission. Acknowledgements/operator confirmation
   still do not constitute fresh independent hardware telemetry.
3. Manually select the square gold reference marker, enter current frame/sample/input
   identities, and use existing gamepad/stage controls to reach a roughly central
   point. Release sticks. Set margin 100, step 10, operator note and output directory.
4. Press **Preview H+V Envelope**. Review fresh XY, H endpoints/count, dynamic V X
   rounding policy, V Y endpoints/count, return target and the full clearance
   rectangle. Inspect physical clearance; then check all four original confirmations
   and the separate BOTH X/Y checkbox. Do not reuse remembered coordinates.
5. Press **Run H+V Validation** once. Expect handoff and owned DAQ setup, exactly
   71 H points, then 71 V points at rounded H midpoint X, then return only on success.
   NI: ai0 X/ai1 Y, +/-10 V, clipping +/-9.9 V, 32 samples/channel at 100 kS/s,
   finite untriggered, reset=False. Position tolerance 1 um; polling 10 ms,
   continuous idle settling 100 ms; movement 5 s; readback/settling, DAQ and stop 2 s.
6. Accept only finalized H/V journals, valid unique edges/width within 500 +/-100 um,
   plausible initial center, return PASS, DAQ/idle/restore cleanup PASS, ownership
   AVAILABLE, `hv_complete=True`, and registration_published=False. Review warnings.
7. Cancel on unexpected behavior. Cancellation is cooperative, with no failure return;
   native calls cannot be forcibly interrupted. After failure retain evidence and
   current position, inspect reasons, and do not retry until independent idle/frame/
   cleanup/clearance checks resolve the cause. Uncertain execution remains quarantined;
   never open another stage session or force-disconnect an unresolved owner.
8. Do not test multi-H, rotation, refined center, full Locate Marker, target movement,
   ROI or Snake Scan. After H+V evidence is reviewed, separately prepare supervised
   planned multi-H acquisition/classification. Module 8 is still in progress.

Offline validation for this H+V implementation: **575 tests passed** (542 baseline
plus 33 new H+V orchestration/Qt tests). Stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
No hardware was initialized or commanded during implementation/testing.
Readiness is for a separately supervised H+V test, not a completed live H+V result.


## First supervised live H+V validation: PASSED

Run `8493cabf1df6424fa2bee5e25e5d8396` completed on real hardware, as reported by
the operator and recorded in the local `hv_result.json`. Existing evidence was
read only; runtime journals are not altered by this implementation.

| Quantity | Result (um unless noted) |
| --- | --- |
| H requested X / fixed Y / count | 3830 to 4530 / -26100 / 71 |
| H left / right | 3965.934549550488 / 4463.664592482027 |
| H midpoint / width | 4214.799571016258 / 497.7300429315387 |
| V chosen integer X / rounding delta | 4215 / +0.200428983742313 |
| V requested Y / count | -26450 to -25750 / 71 |
| V lower / upper | -26346.34241019074 / -25857.20103169517 |
| V midpoint / height | -26101.771720942954 / 489.14137849556937 |
| Initial H/V center | (4214.799571016258, -26101.771720942954) |

Both analyses VALID; return PASS; cleanup PASS; ownership AVAILABLE;
`hv_complete=True`, registration_published=False. The operator also reported
H completion. Journals are `localization_runs/8493cabf1df6424fa2bee5e25e5d8396/initial_H.jsonl`
and `initial_V.jsonl` in the same directory. Known warnings remain
`joystick_command_ack_only` and `laser_operator_confirmation_not_fresh_SDK_readback`.
This validates normal H+V acquisition, not rotation, full Locate Marker, fault
injection or calibrated physical accuracy. The values above are evidence, never
production defaults.

## Supervised multi-H acquisition and classification

`ui/multi_h_validation.py` reuses `HVServices.acquire_initial_center`, the shared
Qt runner, persistent owner/handoff/DAQ/cleanup, and unchanged Module 6 scanner and
Module 7 classifier. `purpose='multi_h'` is explicitly non-publishing. Existing
H-only and H+V actions stay separate. Full live Locate Marker stays disabled.

The existing `LocalizationSpec` / `plan_profiles` supply profile planning and scan
geometry. Defaults: side 500 um, supported rotation +/-5 degrees, center allowance
20 um, inward guard 10 um, 5 profiles, minimum 3 accepted and minimum 100 um span,
integer-um resolution. The planner computes
`Amax = S/2*(cos(theta_max)-sin(theta_max)) - guard - allowance` for this supported
small-angle branch. For the defaults this is approximately 197.26 um. Rounded
profiles are symmetric about the rounded measured V midpoint, with rechecked
central margin, distinct Y, count, leverage and full path bounds. At an integer
preview center their offsets are (-197,-98,0,98,197) um (394 um span); these are
computed outcomes, not hardcoded historical offsets. Final positions depend on
actual H/V measurements. Profile X scans are centered on the initial H midpoint,
with the existing planner's integer rounding; Y positions use the V midpoint.

**Envelope:** let L=S/2+margin. Because initial center estimates are not known
before acquisition, require the conservative clearance rectangle
`X0 +/- (2L+1)` and `Y0 +/- (L+S/2+1)`; for defaults X0 +/-701, Y0 +/-601 um.
This deliberately covers possible recentering, approach, diagonal reposition and
return, rather than guessing the live center in the preview. It is not a claim of
mechanical limits or physical clearance. Manual bounds must contain this envelope;
the complete measured-center-derived profile plan is checked again before profile
1 moves. An inadequate plan fails closed, without expansion or additional profiles.

**Acquisition and classification:** initial H/V must both have finalized journals
and valid unique edges. Then acquire exactly the planned profile count, each using
unchanged scan_1d, independent journal finalization/readback verification and edge
analysis. Journals: initial_H.jsonl, initial_V.jsonl, profile_H_01.jsonl through
profile_H_05.jsonl in one unique run directory. Hardware/acquisition/position/journal
failures abort at once. Completed profiles with invalid optical edges are retained
as edge_valid=False and passed to the classifier, not deleted. Measured Y mean and
spread are recorded; unstable measured-Y profiles are marked unusable, not trimmed.
All planned profiles reach one call to the existing classify_profiles. Its settings
are unchanged (only nominal side supplied), and it alone assigns CENTRAL,
CORNER_AFFECTED, INCONSISTENT or INVALID. No alternate subset or replacement scan.

Report each profile's requested/measured Y, edges/midpoint/width, contrast/noise,
edge diagnostics, classification/reasons and journal path. Also report CENTRAL IDs,
count, accepted measured-Y span, other IDs, classifier reasons,
sufficient_for_rotation_fit and usable_final_fits availability. The classifier API
has no separate warnings field; this is recorded as empty, while upstream hardware
warnings remain. Classifier provisional/QC fit angles are not displayed as accepted
production rotation. Success requires classifier sufficiency and usable fits, plus
the run's minimum accepted count/span. Only then attempt return. No production
rotation fit, center refinement or StageRegistration call occurs.

**Lifecycle:** checkpoints after H/V, before planning, before/during/after every
profile, before classification and return. No automatic return after scan, journal,
classifier failure or cancellation; partial evidence remains. Return failure fails
the run. Cleanup/stop/idle/restore uncertainty quarantines. Native calls cannot be
forcibly interrupted. Results are saved as multi_h_result.json; successful cleanup
adds multi_h_complete=True and registration_published=False. READY FOR ROTATION FIT
means classifier/leverage eligibility only, not production rotation QC approval.

### Next supervised multi-H procedure (not executed in this task)

1. Close stable UI, MIRcat vendor GUI, standalone stage/DAQ scripts and other hardware
   owners. Launch `python .\qcl_scanning_imaging_autorelocation_ui.py --hardware`
   in a fresh session. Do not first open objective/autofocus or run legacy acquisition.
2. Python remains sole MIRcat owner. Establish/physically confirm 1500 cm^-1 and
   emission ON; SR865A 20 mV, 300 us, Advanced 24 dB. The action does not enable/tune
   emission. Existing acknowledgement/operator-confirmation warnings still apply.
3. Load GDS, manually select the square gold marker, enter current frame/sample/input
   identities, and use existing gamepad/stage controls to reach a roughly central
   point. Release sticks. Set margin100, step10 and operator note/output directory.
4. Press **Preview Multi-H Envelope**. Review fresh XY, initial H/V paths, dynamic
   V X, approximate five-profile Y positions/span, recentered profile X policy,
   full clearance rectangle and original-start return target. Verify the ENTIRE
   rectangle physically. An old H/H+V clearance does not authorize this envelope.
5. Check the original four confirmations and the separate **Multi-H** full-sequence
   clearance checkbox; press **Run Multi-H Validation** once. Expect initial H and V
   (71 points each), then five H profiles (normally 71 each) centered from those
   measurements, followed by classification. Inspect progress index/total and rows.
   DAQ/timings unchanged: ai0/ai1, +/-10 V, clipping9.9 V, 32 samples/channel at
   100 kS/s, finite untriggered reset=False; tolerance1 um, polling10 ms, idle100 ms,
   movement5 s, readback/settling/DAQ/stop2 s.
6. Accept only verified journals for all seven scans, classifier sufficiency with
   usable fits, >=3 CENTRAL and >=100 um accepted span, successful return/cleanup,
   ownership AVAILABLE, multi_h_complete=True and registration_published=False.
   Inspect every rejected/other row and retained warning; do not manually trim.
7. Cancel for unexpected behavior. There is no failure/cancel return, retry or
   replacement profile. Retain journals/current position; resolve error/idle/frame/
   cleanup/clearance under supervision before retry. An unresolved native call is
   not cancelled by timeout; never force-close it or open a second owner.
8. Do not run production rotation/refinement, full Locate Marker, target navigation,
   ROI or Snake Scan. After reviewing successful multi-H/classifier evidence,
   separately prepare the production rotation stage of live validation.

Multi-H implementation validation: **615 offline/fake tests passed**, including
40 new multi-H orchestration/Qt tests and all H-only/H+V regressions. Stable UI
SHA256 remains `fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
No hardware was initialized in this implementation task. Ready for a separately
supervised multi-H test; no multi-H live result is claimed.


## First supervised Multi-H live attempt: failed safely, diagnosis pending

Operator reports `ValueError: existing_Module7_bridge_supports_FLIP_X_only` while
Auto Location displayed FLIP_X. Reported outcomes: initial H completed, no multi-H
profiles acquired, no automatic return, cleanup PASS, input restore
RESTORE_SUCCESS_GAMEPAD_MANUAL_RESTART, ownership AVAILABLE,
registration_published=False and multi_h_complete=False. Treat this as a reported
software integration failure, not evidence of hardware failure. No retry was run
as part of the software investigation.

The exact orientation representation cause is **not yet established**. In commit
50a8db4, the sole raise is LocalizationPipelineServices.prepare(), before initial H
and DAQ creation. The selector stores the string 'flip_x', but sync_context()
converts it to experiment.stage_registration.Orientation.FLIP_X before RunSettings.
An inert actual-widget check confirms that canonical identity survives this path.
All H/H+V/Multi-H actions share the same prepare gate; planning has no orientation
argument or conversion. A naive JSON-to-RegistrationContext reload retains a string,
but that reload is not used by this live path. It is not a confirmed explanation.

The operator subsequently identified run `792e5087c2f74bab8a0d16316920964d`
and explicitly confirmed initial H completed before the displayed failure. This
live timing evidence is retained; the current-source order does not explain it.
The exact reported directory
`C:\Users\Discovery\GitHub\Projects\experiments\_147\localization_runs\792e5087c2f74bab8a0d16316920964d`
was searched and is absent. The working repository/CWD is
`C:\Users\Discovery\GitHub\Projects\experiments_147`; its `localization_runs`
contains only the earlier H and H+V runs. Absence here does not disprove the live
diagnostics. The failed process's traceback and orientation identity remain unknown.

The supervised caller trace is HOnlyControls.start -> HOnlyRunner.start ->
LocateMarkerQtWorker -> LocateMarkerWorker.run -> MultiHServices.prepare ->
HVServices.prepare -> HOnlyServices.prepare -> LocalizationPipelineServices.prepare.
Each superclass receives the same RunSettings/context. Only after prepare returns
does MultiHServices.work call acquire_initial_center (H then V), plan, profiles,
and classifier. There is no post-H prepare call in this checkout. InputHandoff.prepare
is a separate gamepad/joystick operation. Planned H journal path/count fields are
populated before acquisition, so those fields alone do not establish scan timing.

An inert experimental-window regression exercises constructor_with_proxy, manual
GDS selection, UI orientation changes, the real Qt runner, H/V acquisition and
planning. It observes prepare once, then H, V, plan. The private globals are a
shallow copy retaining module/class identity. Received and expected Orientation
classes are identical, with equality=True and identity=True. A deliberately injected
duplicate str-enum demonstrates equality=True/identity=False and safe rejection;
it is a diagnostic fault fixture, not a reproduced cause in the operational path.

Read-only orientation-gate diagnostics now capture repr/value, type/module/source,
class/module IDs, equality/identity, loaded Orientation modules, run ID, phase,
verified journals and initial-H file existence. These are included in the UI report
and failure reason. If prepare fails before creating a run directory, the report is
saved exclusively as `<output>/<run-id>_prepare_diagnostics.json`; no scan journal
is invented or overwritten. No conversion or change from identity to equality was
applied. Retry remains blocked pending identification of the live discrepancy.
Validation: 618 offline/fake tests passed; stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
No hardware was initialized, and no files were staged or committed.
Full live Locate Marker remains disabled; production rotation/refinement pending.

## Runtime provenance and no-motion Multi-H Preflight

The next diagnostic action is **Run Multi-H Preflight (no hardware calls)** in
Auto Location's supervised development section. This is not Preview Multi-H
Envelope and not Run Multi-H Validation. The action needs no scan preview,
clearance checkbox, emission confirmation, or stage readback. It snapshots the
current UI context/generation, uses the same RunSettings builder as the runner,
and calls the exact extracted pure context/orientation gate used by prepare.
The `is Orientation.FLIP_X` gate is unchanged. If a cached preview is available,
its rough coordinate/frame is included; otherwise rough start is explicitly absent.
The result is diagnostic validity only, never scan readiness or registration.

It does not construct acquisition services, stop gamepad, disable joystick,
request a lease, read/move/stop stage, create DAQ, touch laser, write journals,
or publish registration. It displays selectable JSON and changes no registration
state. Do not retry scanning on the strength of a successful preflight.

Provenance includes executable, resolved CWD/repository root, read-only bounded
`git rev-parse HEAD`, ordered sys.path and candidate repo files; loaded module
names, IDs, resolved paths and disk SHA256; and loaded function code hashes for
prepare, the shared gate, MultiH prepare/work, and worker run. Disk hashes describe
current files, not necessarily the source used by an older running process.
Marshalled runtime-code hashes identify loaded code (within matching Python/path
environments). Duplicate logical imports and alternate sys.path copies are listed,
not silently normalized. Orientation diagnostics inspect the actual gate's enum
reference, including equality versus identity, repr/str/value and class/module IDs.

Supervised-run reports now include in-memory phase breadcrumbs with run ID,
sequence, wall/monotonic timestamps and thread identity. Events cover runner start,
handoff, settings creation, ownership, prepare enter/exit, work, H/V enter/complete,
planner, profile entry, classifier, return and cleanup. Pre-lease events receive
the acquired run ID when bound. Settings creation actually precedes acquisition;
the trace records that order. Reports persist on normal completion/failure, including
pre-prepare failure diagnostics. These are not crash-durable per-event journals.

Artifact audit: the corrected path is
`C:\Users\Discovery\GitHub\Projects\experiments_147\localization_runs\792e5087c2f74bab8a0d16316920964d`.
It is absent too. Current production code creates the output parent, exclusively
creates a run directory, and scan_1d opens each journal exclusively. Cleanup closes
resources/streams, never deletes/moves run directories or journals. No production
temporary-directory deletion, failed-candidate pruning, or localization_runs purge
was found in the experimental entry point, UI modules or scanner. Test temporary
directories belong only to fixtures. A post-H analysis failure test confirms H
journal and final failure report retention. No deletion bug was found or fixed;
the missing historical artifact is not reconstructed and its absence remains unexplained.

Operator diagnostic procedure (not executed here): close the prior experimental
process safely; use the intended Python environment from the repository root and
launch `python .\qcl_scanning_imaging_autorelocation_ui.py --hardware` only under
the existing supervised startup policy (sole Python MIRcat owner, vendor GUI and
other conflicting hardware applications closed). Startup itself initializes normal
operational hardware; only the preflight action is hardware-call-free. Load GDS,
manually select the reference marker and verify current frame/orientation. Do not
enable emission or position the stage for this diagnostic. Press only **Run Multi-H
Preflight (no hardware calls)**. Copy the selectable JSON to the review record,
including executable/CWD/HEAD, all paths/hashes, enum identity and reasons. Stop
there; do not press any envelope preview or scan-validation button. An already
running older process cannot gain this action without a controlled restart.

Validation: **626 offline/fake tests passed** (eight new preflight/provenance tests).
The experimental constructor path verifies zero preflight device calls, canonical
module identity, duplicate/wrong-gate diagnostics, alternate sys.path detection,
ordered threaded breadcrumbs and failed-scan evidence retention. Stable UI hash
is unchanged. **READY TO RUN NO-MOTION MULTI-H PREFLIGHT ON HARDWARE UI: YES**;
Multi-H scan retry remains blocked pending review of actual-process evidence.

## MVP scope update: production H/V translation-only Locate Marker

This decision supersedes earlier requirements to calibrate rotation before Module 8
completion. The operator reports multi-H acquisition completed, but classification
was brittle for current live data. No thresholds are retuned here. Multi-H,
classifier, rotation, refined center and provenance/preflight remain optional
Development / Diagnostics tools; their unresolved calibration issues do not block
the translation-only MVP. The live H-only and H+V evidence above is preserved.

Production now reuses HVServices.acquire_initial_center unchanged: confirmed rough
point, handoff/lease/DAQ, initial H with finalized journal/valid edges, nearest-integer
(ties-to-even) V X, initial V with finalized journal/valid edges. The anchor is
(H midpoint, V midpoint); no second H, profiles, classifier, rotation fit or center
refinement is called. TranslationServices builds the existing Module 5
StageRegistration(anchor_x, anchor_y, 0, FLIP_X), verifies success-only return, then
offers typed TranslationEvidence to the existing worker/controller. Only confirmed
cleanup and unchanged context/generation permit atomic publication. A safe failed
candidate retains prior approval; frame changes or uncertain cleanup invalidate it.

Approved metadata: registration_mode=translation_only, rotation_calibrated=False,
assumed_theta_deg=0.0, scale=1, shear=none. Display: VALID — TRANSLATION ONLY;
rotation assumed 0° — not calibrated. Warning rotation_assumed_zero_not_calibrated
remains visible with joystick_command_ack_only and
laser_operator_confirmation_not_fresh_SDK_readback. No angle uncertainty is invented.
Target error grows with distance if true chip rotation is nonzero. Physical target
accuracy remains unmeasured; later Module 9 validation determines sufficiency.

The registered preview keeps its explicit GDS coordinate frame and annotates the
manually selected marker/target centers with approved stage XY. Predictions use
the existing marker-local ChipLayout and local_to_stage, never screen coordinates.
Single-clicking an assigned feature displays its prediction; no click or double-click
moves hardware. Scene annotations clear on invalidation. No Module 9 or ROI work.

Primary controls are now Locate Marker, Preview Locate Marker Envelope (H+V),
current identities and confirmations. H-only/H+V/multi-H validation, no-motion
preflight and archived replay remain in a collapsed Development / Diagnostics
section. Diagnostic instrumentation was retained, not removed. Default --hardware
does not enable production Locate Marker. A future explicitly supervised test can
opt in using --supervised-translation-only; this flag is rejected without --hardware.
This task executes neither flag against hardware.

### First translation-only Locate Marker procedure (not executed)

1. Close competing stage/DAQ software and the MIRcat vendor GUI. Use the normal
   supervised startup/clearance precautions and sole Python MIRcat ownership.
2. From the repository and intended Python environment run:
   `python .\qcl_scanning_imaging_autorelocation_ui.py --hardware --supervised-translation-only`.
   This explicitly enables the later supervised production test; normal startup
   remains gated. Startup initializes operational instruments as before.
3. Load GDS, manually select the square gold reference and desired features. Set
   current non-archived frame/sample/input identities and FLIP_X. Use the existing
   gamepad to put the beam roughly on the selected marker. No new gamepad exists.
4. Establish laser emission/settings using the operational Python owner: 1500 cm^-1
   for the validated setup, SR865A 20 mV, 300 us, Advanced 24 dB. Confirm physical
   emission/wiring; cached SDK flags are not fresh emission/settings verification.
5. Press Preview Locate Marker Envelope (H+V). For a 500 um marker with 100 um
   margin, inspect Xrough +/-350 um at Yrough and Yrough +/-350 um at dynamic
   V X=round(valid H midpoint). Step 10 um, 71 points/axis. The whole rectangle,
   approaches and return must have physical clearance and permitted stage bounds.
   An arbitrary point near the marker edge may not capture both edges: no auto retry.
6. Enter operator note and journal directory; confirm current frame/full clearance,
   laser emission, sole software ownership, lock-in setup, and the distinct Locate
   Marker both-axis clearance checkbox. Press Locate Marker once.
7. Expect input handoff, H then V, original rough-start return, cleanup, ownership
   AVAILABLE, then VALID — TRANSLATION ONLY. Inspect measured H/V center, assumed
   angle, retained warnings, separate initial_H/initial_V journals and
   translation_only_result.json. The selected reference maps to the measured center;
   selected feature centers show predicted stage XY without motion.
8. Cancel uses the existing cooperative path; failure/cancellation causes no retry
   or automatic return and no new approval. Preserve journals/result. With uncertain
   native/DAQ cleanup, leave motion sources disabled and follow existing supervised
   quarantine recovery; never force-terminate the owner or open a second session.
9. Stop after reviewing publication and predictions. Do not test target movement,
   ROI/Snake Scan, multi-H fallback or calibration. After successful review, plan
   Module 9 guarded feature-center motion and physical target accuracy checks.

Offline implementation validation: **648 tests passed**, including 22 new
translation-only tests and retained H/H+V, multi-H, diagnostics and Module 5-7
regressions. Tests exercise the actual experimental constructor with inert
Prior/NI, production button/preview, transaction failures, context invalidation,
warning metadata and registered predictions. Stable UI SHA256 remains
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
**READY FOR SUPERVISED TRANSLATION-ONLY LOCATE MARKER TEST: YES**. This is
software readiness only; no production Locate Marker hardware run occurred in
this task. Module 8 remains incomplete until that separate live test is reviewed.

### Fresh-session legacy DAQ attestation investigation

The subsequent operator report is a genuinely restarted experimental session
blocked before acquisition by
`legacy_DAQ_release_not_attested_fresh_session_required`. No legacy acquisition
or objective widget was reportedly used. That live transition has **not** been
reproduced from the reviewed startup source; do not attribute it to operator
activity without evidence. This investigation supersedes the earlier readiness
claim for that unresolved blocker.

The exact emitter is `OperationalLocalizationBridge.blockers()`, consumed by
`InputHandoff.prepare()` before input handoff, lease or localization DAQ creation.
Previously the bridge initialized `legacy_daq_cleanup_unverified=False`.
The experimental wrapper set it True on entry to six legacy acquisition
callbacks, with no verified-release path. There is no reviewed startup assignment
to True. Calling the actual stable `run_experiment()` with an unarmed laser
reproduces a separate defect: it returns without creating a worker/task, but the
old wrapper still permanently marked the session dirty.

Startup ownership audit (static inspection only):

- `mainWindow.__init__` constructs `piScanner`, a PI controller object, not an NI
  task. Ordinary scan tabs, parameters, menus and controls are non-owning.
- `show_pi_scanner_widget()` lazily constructs `piScanner_widget`; its constructor
  calls `_setup_daq()` and configures an NI task. Hidden is not equivalent to
  released. Widget visibility/finished-thread signals do not attest NI cleanup.
- Single/sweep, repeat, multiwell, snake/repeat-snake and imaging acquisition
  callbacks create QThreads before running their task-creating workers. None of
  those acquisition workers is started by the reviewed window constructor.
- NI task creation occurs in the NI wrapper's configure methods, not because an
  acquisition parameter object or an NI wrapper module merely exists.

The experimental fix tracks session-scoped acquisition evidence. `never_acquired`
is clean without needing a release event. Reviewed legacy callbacks are marked
uncertain immediately before their QThread factory executes; early returns are
clean. A private globals copy intercepts only this factory. The stable source hash
and compiled callback code must match the audited source; unknown/changed callbacks
are conservatively marked at entry. The stable UI and its globals are unchanged.
Objective-widget entry is marked before construction, including partial failures.

Each transition records a session ID, source and token. Blocked diagnostics include
pending sources; no-motion preflight includes the full safe ledger snapshot. A
positive release requires a token-bound owner verifier and no active/unknown
owner. There is no operator "clear clean" override. Current legacy workers have
no such verified cleanup signal, so potentially acquired tasks remain blocked
even when workers finish. Restart creates a new session ledger; it does not claim
to clear another process's hardware tasks. All other ownership gates still apply.

New inert regression coverage includes fresh production H/V, actual stable
early-return callback through the experimental wrapper, worker creation, active
and uncertain ownership, owner-bound release, stale tokens, non-owning PI versus
NI-owning objective widgets, and session restart. No real hardware was run.
Validation: **663 offline tests passed**, including 15 focused attestation tests;
`git diff --check` passed and the stable UI SHA256 remains unchanged.

**READY TO RETRY PRODUCTION LOCATE MARKER: NO** for claiming the reported live
blocker resolved: the callback-free live dirty transition remains unidentified.
The no-task callback defect is fixed, and fresh inert production H/V passes.
Next evidence needed is the pending-source/session provenance if the reported
fresh-session denial recurs; do not bypass the blocker or infer NI cleanup from
an idle UI. This task does not authorize or execute a hardware retry.

### Marker-scaled production sampling update

The operator subsequently reports successful live production H -> V -> center,
theta=0 -> return -> cleanup -> VALID TRANSLATION ONLY publication and registered
predictions. That success used reference sampling. The new sampling described
below has not been executed on hardware in this implementation task.

`ui/translation_geometry.py` centralizes production settings and constructs the
existing immutable `HVSpec`. Side S comes from the manually selected square's
GDS geometry, not an archived constant. The selection model accepts arbitrary
positive square sizes; production rejects S<20 um because 1 um stage resolution
cannot satisfy S/20 sampling.

- Requested half-span: 1.25*S.
- Integral step: floor(min(25 um, S/20)); never rounded upward for small markers.
- Actual half-span: ceil(requested half-span / step)*step. Endpoints expand
  symmetrically, never shrink; point count = 2*actual half-span/step+1.
- H is centered on confirmed rough X at rough Y. V is centered on rough Y at
  the nearest-integer measured H midpoint X (unchanged ties-to-even policy).
- S=500 um gives +/-625 um, 25 um step, 51 points/axis, 102 scan positions total.
  Around (4200,-26100), H is 3575..4825 and V is -26725..-25475 um.
- Proposed clearance bounds include the full new rectangle plus existing 1 um
  tolerance padding. They are not detected travel limits. Inadequate manually
  entered bounds fail before motion. No runtime expansion beyond approved bounds.

Production ignores the labeled development/reference margin/step fields.
Development H-only/H+V retains +/-350 um, 10 um / 71-point defaults for S=500 um.
Preview and run diagnostics report actual span, step and count. Edge analysis,
expected width/tolerance, measured-coordinate interpolation, return/cleanup and
translation-only publication rules are unchanged.

Move to a point clearly on the selected marker; exact centering is not required.
Failure to capture a unique valid edge pair remains fail-closed, without retry.
25 um is a speed/coverage default and may reduce edge/center precision; no
quantitative physical accuracy is claimed. 10 um remains validated reference
sampling. Module 9 physical target tests will assess adequacy.

For the next separately supervised test, follow the production procedure above
but inspect the NEW larger envelope and 25 um / 51-point settings before
confirming full 2D clearance. Retain sole Python MIRcat ownership, all laser,
lock-in, frame confirmations and cancellation/failure precautions. Expect only
H then V, return, cleanup and translation-only publication. Do not test target
motion, ROI, multi-H or rotation calibration. This update ran no real hardware.

### Tunable production geometry and rough-anchor candidate policy

Production Scan Settings exposes automatic/override, requested half-span and
integral step, calculated actual span/counts and Reset to Automatic Defaults.
Automatic remains 1.25*S and floor(min(25,S/20)); for 500 um, 625/25 gives 51
points. Override expands half-span using ceil(requested/step)*step: 625/10 ->
630 and 127 points; 625/20 -> 640 and 65; 625/25 -> 625 and 51. Requests must
be finite/positive, step integral, have at least nine samples, and leave background
extent beyond half the marker width. Endpoints remain integral, symmetric and
within previewed clearance. No runtime expansion/retry. Parameter/marker changes
clear preview and confirmation. Reset is software-only, leaving registration
unchanged. H/H+V development reference defaults remain unchanged.

TranslationServices retains scanner/journal verification and generic analysis,
then inspects ALL evaluated candidates even on generic selection failure. Require
selected square width/height +/-100 um, inclusive containment of rough X (H) or
rough Y (V), and ALL generic quality checks. Exactly one eligible candidate
succeeds; zero returns no_anchor_matching_marker_candidate and multiple returns
multiple_anchor_matching_marker_candidates. No ranking, nearest-center choice,
interpolation duplication, or signal-QC waiver is allowed.

Result metadata includes mode/requested/actual geometry, per-axis/total planned
point counts, measured centers/widths, candidate QC/anchor/size decisions, per-axis
acquisition/verification/analysis duration, and elapsed service time through DAQ
cleanup. The latter excludes pre-service input handoff and is labeled accordingly.

Offline runtime journal analysis:
localization_runs/402745357b0c4b769431c2ccc138617c/initial_H.jsonl reports generic
no_valid_candidate with three candidates. The only width/anchor match at X=4200
has edges 3957.3193222053806 and 4469.514230851912 um, width
512.1949086465311 um and midpoint 4213.416776528646 um. Support counts (16,20,7)
pass, but contrast 3.5223249947828847 / noise 0.6584503951182552 gives SNR about
5.35, below 6. It remains rejected as noisy_signal. Other candidate widths are
168.2038384247653 and 75.66729779712023 um and fail the marker-size/anchor prior.

Successful recovery of this journal conflicts with preserving generic quality
rules. No threshold was changed to force acceptance. READY TO TEST TUNABLE
ANCHOR-AWARE PRODUCTION LOCATE MARKER: NO until that specific conflict is reviewed.
Synthetic nearby-feature selection and fake publication pass, but do not show
that the real failed scan passes. No hardware/target motion/ROI/rotation work.

### Production local-baseline quality (supersedes the prior SNR blocker)

Marker identity and signal quality are separate: first require exactly one
GDS-dimension/rough-anchor match, even if generic wide-region quality rejected it.
Multiple identity matches fail before quality; never rank or try another candidate.
Then use fixed LOCAL_BACKGROUND_WIDTH_UM=100, independent of marker size, range
or step. For interpolated edges L/R, nominal substrate is [L-100,L) and
(R,R+100]. Clip at the nearest previous/next detected crossing, without interpreting
neighbor semantics. The marker interior remains bounded by L/R.

Membership uses sorted measured coordinates. Exclude BOTH measured samples of
every threshold crossing bracket from all three quality regions, including marker
interior, deterministically removing transition samples without changing edge
interpolation or selected coordinates. Never add distant samples. Each background
side and the interior require at least three usable points. Specific failures are
insufficient_local_baseline_support_left/right and insufficient_local_marker_support.
Finite-data/saturation protection remains. Empty/short windows fail before statistics.

The existing contrast, median-level, first-difference/residual noise and background
consistency mathematics were factored into evaluate_region_quality, used unchanged
by generic candidates and production-local regions. min_snr=6, min_contrast=0.01,
baseline difference fraction=0.25, min_region_points=3 and width tolerance=100 um
are unchanged. Distant structures outside these windows cannot affect this
selected candidate's local quality; generic global crossing generation is unchanged.

Failed 25 um journal 402745357b0c4b769431c2ccc138617c, offline:
- Edges 3957.3193222053806 / 4469.514230851912 um unchanged; midpoint
  4213.416776528646 um, width 512.1949086465311 um; anchor 4200 contained.
- Left requested/actual interval [3857.3193222053806,3957.3193222053806).
  Usable X: 3875,3900,3925 (3 points).
- Right requested/actual interval (4469.514230851912,4569.514230851912].
  Usable X: 4500,4525,4550 (3 points). Interior support: 18.
- Previous crossing: none; next: 4637.718069276677 um. Neither window needs
  crossing truncation in this journal; both are clipped to the physical 100 um cap.
- Region medians: 2.5700674295092263 / 5.8664625156860435 /
  2.542400197667672. Contrast 3.3102287020975947; noise 0.010177181514993016;
  SNR 325.25986661640735. Baseline difference 0.027667231841554507 is below
  allowed 0.8275571755243987. Identity TRUE, local quality PASS, reasons empty.

Historical comparisons, unchanged journals: 8493cabf1df6424fa2bee5e25e5d8396
10 um initial H passes (support 9/48/6, SNR 130.06913185834898); initial V passes
(9/47/9, SNR 47.104465741482336). The committed 20 um vertical marker journal
9392a56a0a0e4517b9b897398376ee3b passes (4/23/4, SNR 22.667713670082446).
Available samples may cover less than a nominal window; no extrapolation occurs.

Diagnostics retain generic wide-region reasons for comparison, separately report
marker_identity_match / marker_quality_pass, and persist local intervals, neighbors,
support/coordinates, region medians, contrast/noise/SNR and final reasons.
Geometry/overrides, ownership, H/V center, theta=0, return/cleanup/publication and
registered predictions are unchanged. High local SNR is not calibrated center accuracy.

Next supervised procedure: existing --hardware --supervised-translation-only
startup with sole Python MIRcat ownership and no competing DAQ/stage software;
select the square marker, establish frame/sample/laser/lock-in confirmations,
position clearly on marker, leave production automatic defaults, preview full
2D envelope (500 um: +/-625, step25,51 points), confirm clearance, Locate Marker
once. Inspect H/V local identity/quality, separate journals, return and cleanup
before accepting publication. Failure/cancel causes no retry/automatic return;
uncertain cleanup follows existing quarantine. No target motion/ROI/rotation test.
This procedure is not executed as part of implementation.

## Production defaults and repeated Snake Scan reuse

Production translation-only Auto Location has now been live validated successfully
(operator report). This update is implementation/offline validation only.

Automatic requested step is floor(min(15 um, S/20)); the small-marker resolution
check is retained. Requested half-span is 1.25*S; actual half-span rounds upward
to a whole number of steps. For S=500 um: requested half-span 625, step 15,
actual half-span 630, span 1260, 85 positions/axis and 170 nominal H+V positions.
The UI distinguishes requested from actual coverage. Manual integral overrides
remain available; 10 um remains a finer reference. Development H/H+V defaults,
marker identity, local 100 um quality, thresholds and theta=0 are unchanged.

Normal startup displays Orientation: FLIP_X (default), with canonical
experiment.stage_registration.Orientation.FLIP_X. Alternate controls are hidden.
The optional --developer-mode flag exposes the existing selector and its context
invalidation behavior. A normal launch does not inherit hidden alternative state.

### Snake Scan acquisition and release evidence

The old worker_creation:run_snake_scan evidence had no positive release verifier:
thread completion alone could not clear it. The experimental acquisition boundary
now instruments run_snake_scan and repeat_snake_scan using private function globals
and a worker subclass. Neither stable UI nor experiment/routines.py is changed;
the existing scan engine executes unchanged. Other legacy sources retain their
independent conservative blockers.

Each worker has a unique acquisition token in the existing LegacyDaqEvidence.
CREATED is not proof of NI acquisition. MultiAI construction creates a wrapper;
configure_triggered enters NI task creation and marks ACQUIRED. start_task marks
ACTIVE. The wrapper observes the existing read_line, stop_task and clear_task.
Each task belongs to that worker's token, including successive pattern tasks.
The experimental wrapper forbids reset=True.

Normal completion already stops/clears tasks. A worker-finally path handles any
remaining owned task on the acquisition thread, then records worker completion.
A GUI-thread receiver observes actual QThread completion. RELEASE_CONFIRMED
requires both completions, all owned tasks cleared, and no uncertain NI operation.
A started task must have successful stop and clear returns. A wrapper that never
entered configuration needs no NI release. Creating a worker that exits without
acquiring a task does not permanently poison the session.

Release applies only to the exact token. It cannot release another objective,
legacy or uncertain source. Completed history is bounded to 32 entries; unresolved
sources are never pruned. Diagnostics expose lifecycle state, task count, worker/
thread completion, active acquisition IDs, pending/active sources, last completed
source and timestamped release attestation, plus production blockers.

A Python-level failure or cooperative unwind can release ownership after verified
cleanup. The existing Snake engine has no newly added cancellation mechanism:
no claim is made that a blocking driver call can be cancelled. An unresolved call
keeps the worker and ownership pending. NI setup/read/stop/clear exceptions retain
uncertainty even if subsequent cleanup returns; they require existing fresh-session
or quarantine recovery. No thread termination, concurrent stop, blind reset or
clear-all attestation is introduced. Failure does not emit the legacy success
signal that would falsely claim laser emission was disabled; error diagnostics
explicitly leave laser state unconfirmed.

Managed V1 rejects Snake/Repeat worker-origin autofocus and fallback Objective
construction before those unsupported paths access Objective hardware. Ordinary
Snake scans must leave Autofocus on Imaging disabled. A managed RELEASED window
may exist; unknown widgets and independent Objective/DAQ uncertainty still block
localization. A scan-task release cannot clear another owner's evidence.

DAQ usage itself does not invalidate registration. However the existing Snake
engine calls set_position to redefine and later restore coordinates. Those frame
changes continue to invalidate registration through the shared proxy; do not reuse
an old approval across them. Ordinary movement alone remains non-invalidating.

### Offline verification and next supervised check

719 offline/fake tests pass. Focused tests exercise 20 consecutive successful
acquisitions with empty pending/active sources after every release; 45 releases
verify bounded history. They cover never-acquired workers, active/uncertain tasks,
source isolation, NI failures, safe Python-exception cleanup, the actual compiled
stable callback with inert factories, Qt thread completion, and no false success
signal on failure. Stable UI SHA256 remains
fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab.

Next supervised test (not executed here): launch experimental UI with --hardware
--supervised-translation-only, without --developer-mode. Close competing stage/NI
applications and the MIRcat vendor GUI; Python remains sole MIRcat software owner.
Use the already approved laser/lock-in and clearance procedure. Select the marker,
position clearly on it, and preview automatic 15 um geometry before Auto Location.
After a successful registration, run one small previously reviewed ordinary Snake
Scan with autofocus disabled. Wait for worker/thread completion and refresh DAQ
diagnostics: release confirmed, no pending/active sources, no cleanup uncertainty,
ownership available. Re-establish laser state (normal Snake disables emission),
review coordinate-frame identity, reposition on marker, re-preview and reconfirm
Auto Location. Repeat two more scans and then longer sequences only after review.
An active scan must block localization. Any uncertain cleanup stops the sequence;
do not bypass attestation or retry hardware automatically. No target-motion, ROI,
rotation or new scan engine work is part of this check.

## Managed Objective Scanner DAQ Ownership V1 closeout (2026-10-01)

**COMPLETE — SOFTWARE TESTED AND LIVE HARDWARE VALIDATED.**

Provenance: the operator supplied the live QCL outcomes and diagnostic fields in
the checkpoint request. They are recorded as operator-reported hardware validation,
not hardware execution by the closeout agent. No new run UUIDs, raw journals or
screenshots were supplied for this closeout; none are invented or added as artifacts.
The agent inspected the implementation and reran the software-only suite below.

### Implemented boundary

Only the new `qcl_scanning_imaging_autorelocation_ui.py` uses the managed adapter.
The old `qcl_scanning_imaging_ui.py`, `instruments/pi_scanner.py`,
`instruments/ni_daq.py`, other hardware drivers and `experiment/routines.py` are
unchanged. Hash constants are unchanged. The explicit zero-argument
`show_pi_scanner_widget(self)` adapter preserves the Qt connection contract:
`QAction.triggered(bool)` cannot leak its Boolean into the legacy zero-argument
method. Live opening and close/reopen produced no TypeError or UI exit.

`ui/managed_objective_widget.py` overrides DAQ setup before inherited connections
are established. Opening initializes the UI and guarded non-DAQ position state,
but does not create a native NI task. It reuses the managed widget on reopen.
`ui/objective_daq_lifecycle.py` reserves Objective activity through the existing
bridge/controller lock and uses an operation-scoped task on Dev1/ai0 and Dev1/ai1
(10 samples/channel, 10 kHz, no reset). Acquire Signal, Move To's post-motion
read, and GUI Autofocus use this lifecycle. PI/stage position and motion methods
are also guarded. Autofocus remains synchronous; its reads share one task within
that operation, and cleanup clears it before release is attested.

State is RELEASED -> ACTIVE -> RELEASING -> RELEASED, or UNCERTAIN after an
unverified failure. Operation generation/token, task identity, creation/clear
evidence, execution state and errors are recorded. Stop/clear are checked, cleanup
does not wait while holding the admission lock, and release is owner-bound through
LegacyDaqEvidence. The adapter retains hardware/helper failures even if the legacy
callback catches them. Historical ownerless records are never silently cleared.
Localization admission is atomic against Objective reservation. Unknown widgets
remain blocked; managed ACTIVE, RELEASING and UNCERTAIN owners cannot localize.
Verified localization cleanup and worker completion restore Objective availability;
quarantine does not. Diagnostics distinguish window visibility from resource state.

### Operator-reported live validation

| Sequence | Observed result |
| --- | --- |
| Open Objective Scanner | managed=true, window=OPEN, state=RELEASED, verified_released=true, native_creation_attempted=false, native_task_created=false, uncertain=false, blockers=[] |
| Leave Objective open -> Locate Marker | H and V completed; registration published; DAQ cleanup and idle cleanup passed; localization COMPLETE; ownership AVAILABLE |
| Acquire Signal -> Locate Marker | operation=acquire_signal; native creation attempted/created=true; clear_confirmed=true; RELEASED and verified_released=true; execution_in_flight=false; uncertain=false; errors=[]; attestation released=true; later localization succeeded without restart |
| Move To -> Locate Marker | operation=move_to; native task created and clear confirmed; verified RELEASED, no uncertainty/errors; repeated moves had separate valid generations/tokens; later localization succeeded without restart |
| Autofocus -> Locate Marker | Normal completion; operation=autofocus; verified RELEASED; autofocus_state=inactive; execution_in_flight=false; native task created and clear confirmed; uncertain=false; errors=[]; later localization succeeded without restart |
| Locate Marker -> Objective controls | Window stayed visible; Acquire Signal, Move To, Acquire Position, Autofocus and stage/objective movement controls disabled during localization; after completion controls returned and Acquire Signal cleared successfully, with RELEASED/AVAILABLE state |
| Close/reopen -> Locate Marker | managed=true, OPEN, verified RELEASED, uncertain=false, blockers=[]; no new DAQ transition merely from reopening; prior release evidence retained; later localization succeeded |

Autofocus on Imaging remained disabled: it is unsupported in V1, rather than an
action automatically re-enabled after localization. Disabled controls were not
bypassed on real hardware to force conflicts. Software tests cover direct-method
denial, admission races and injected failures. Successful live sequences do not
claim live coverage of every timeout, cleanup failure or quarantine path.

### Software closeout verification

Fresh closeout run: **252 passed, 0 failed**. Offscreen Qt; an import finder rejected
`instruments`, `PyDAQmx`, `pipython`, `inputs`, `serial`,
`qcl_scanning_imaging_ui` and `experiment.routines`. Tests compile selected legacy
class/method source with inert dependencies instead of importing hardware modules.
No stage, laser, PI or NI device was initialized or operated by this run.

Exact test modules:

- `test_auto_relocation_ui`
- `test_operational_localization_bridge`
- `test_legacy_daq_attestation`
- `test_localization_daq`
- `test_hardware_ownership_diagnostics`
- `test_snake_daq_lifecycle`
- `test_objective_daq_lifecycle`
- `test_managed_objective_widget`
- `test_h_only_controls`
- `test_h_only_validation`
- `test_auto_relocation_orchestration`

Coverage includes real offscreen Qt action payloads, native task non-creation on
open, operation-scoped acquisition, partial construction, start/read/stop/clear
failures, checked PI/stage waits, owner-bound release, admission races, no lock held
across cleanup waits, localization handback/quarantine, stale/unmanaged evidence,
worker autofocus rejection and close/reopen reuse. Test exception hooks/fake
hardware are confined to test fixtures, not production bypasses.

Protected legacy/driver/scan/registration files have no diff. Legacy UI SHA-256:
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
`git diff --check` passes. This checkpoint contains source, tests and these existing
documents only, with no generated localization runs or hardware-test artifacts.

### Accepted limitations and next module

- No forced autofocus cancellation; V1 waits for normal completion and rejects
  localization while Objective activity is active or uncertain.
- No automatic autofocus restart after localization. Restart is manual.
- Snake/Repeat worker-origin autofocus and fallback Objective construction remain
  unsupported and fail-closed; this closeout does not redesign those workers.
- Unmanaged widgets and unresolved cleanup/ownership evidence still require the
  existing recovery/fresh-session policy. Mere managed opening, clean operations
  and reopening no longer require restarting the UI.
- Production registration remains translation-only, theta=0,
  rotation_calibrated=False. Rotation and quantitative relocation calibration are
  deferred; successful cleanup is not a physical target-accuracy measurement.
- Current authoritative numbering: Module 8 is production Locate Marker;
  Module 9 is registered feature selection/guarded target movement; Module 10 is
  feature-centered ROI/existing Snake Scan integration. Modules 9 and 10 remain
  NOT STARTED. `target_motion_not_implemented` remains enforced. The next
  discussion plans Module 9; no target/MS movement is enabled by this checkpoint.

## Checked Snake Imaging DAQ Release V1

**Status: HARDWARE VALIDATED THROUGH SNAKE IMAGING.**

This prerequisite strengthens experimental Snake/Repeat imaging-task evidence.
At that prerequisite checkpoint it did not implement Managed Snake Autofocus,
a parent Snake reservation, or Module 9. The subsequent section records the
managed autofocus implementation; unmanaged Objective fallback remains blocked.

### Native contract and implementation boundary

Installed PyDAQmx 1.4.6 `DAQmxFunctions.catch_error_default` was inspected as text,
without importing the hardware package. It raises on negative native status,
warns on positive status, and returns the numeric status. The legacy DAQ methods
discard those returns. The earlier simulated -1 discrepancy did not demonstrate
a live hardware fault, but exposed insufficient independent release evidence.

`ui/checked_snake_daq.py` verifies the constructor and relevant legacy method code
against the repository source without importing it. It executes private copies
of the reviewed methods with checked native bindings. No global monkey patch,
driver edit, second native clear, or reset is used. Trigger configuration, data
shape, timing, channel order and legacy method sequencing are retained.

Each native call must return an integer zero; exceptions, nonzero statuses,
booleans, None and other unknown outcomes fail closed. Read completion also
requires the requested sample count. The installed wrapper's positive warnings
are rejected conservatively. Factory code that differs from the reviewed source
is rejected before construction.

Evidence includes a per-task generation UUID and actual native handle value,
creation attempt/creation flags, verified configure/start/read/stop/clear flags,
clear attempt, uncertainty and retained operation errors. A task cannot be
reconfigured, cleared twice, retried after clear, or cleared from another thread
or after its handle changes. Generation is separate from native handle identity;
neither a Python object id nor a reused native handle alone is release authority.

### Cleanup and attestation

Stop and clear are independently attempted. Stop failure does not skip clear;
an attempted stop or clear is not automatically retried. Partial configuration
retains the created handle for cleanup. A failed create with no trustworthy
handle remains uncertain. A wrapper never configured has no native task and is
reported as never created, not as a fictitious successful clear.

`TrackedSnakeTask.cleared` is set only after explicit checked native clear.
Worker and thread completion remain necessary; every created task must have
verified clear and no unresolved uncertainty. Child or parent autofocus
handoff is not added here. Historical ownerless evidence remains untouched.

Acquisition failure and resource release are distinct: successful clear can
resolve task uncertainty after a read/start/stop failure, but retained errors
still mark the operation failed. The failure path does not emit legacy success
or claim laser-off. Unknown/failed clear prohibits release attestation. This
supersedes the older Snake policy that retained DAQ uncertainty after every
native acquisition error even when cleanup could be proven.

### Software validation

Targeted checked-adapter/Snake tests passed before the broader run. Final broader
regression: **266 passed, 0 failed**, offscreen Qt, `python -B`, with imports of
instruments, PyDAQmx, pipython, serial, inputs, the legacy UI and
`experiment.routines` explicitly blocked. Fake native bindings execute extracted
legacy class code without executing any hardware imports or module initialization.

Coverage includes the exact native clear -1 regression, exceptions and unknown
statuses, partial creation, short reads, independent stop/clear cleanup, task
identity/generation isolation, stale attestation, multiple-task release gates,
worker/thread completion and existing Objective/localization/UI regressions.
No hardware commands were run. Legacy source and legacy UI hash remain unchanged.

## Managed Snake Autofocus V1

**Status: HARDWARE VALIDATED — NORMAL EXECUTION PATH.**

### Execution and ownership

`SnakeAutofocusSettings` is frozen and validated on the GUI thread before the
reviewed launch callback executes. Target X/Y, sweep offsets/step, PI limits,
timeouts and readback tolerances cannot change during the run. The worker uses
local scanner/target adapters, not QWidget objects. The actual legacy Snake and
Repeat scan bodies still determine autofocus timing once per wavelength per
pattern/repetition; the existing private factory redirects only their hardware
references. Unmanaged Objective construction remains a hard error.

`SnakeWorkflow` reserves `Activity.SNAKE_WORKFLOW` atomically in the existing
controller, before worker hardware execution. It is not an independent hardware
lock or a nested localization lease. Parent token, generation, worker identity,
phase, cancellation and cleanup evidence are retained in the existing ledger.
Only the admitted launch callback and subsequently bound worker may execute
their permitted calls. Manual Objective, localization and competing workflows
remain denied, including between DAQ tasks. Module 9 remains blocked.

The phases are PREPARE, AUTOFOCUS, IMAGING, CLEANUP, COMPLETE and UNCERTAIN.
An Objective child has its own operation generation and attestation, tied to
the current parent and worker. It reuses `ObjectiveOperation` and `ObjectiveTask`
without changing the live-validated manual Objective lifecycle. Child release
never releases the parent. Stale/foreign authority and late completion are rejected.

### DAQ and movement sequence

Previous imaging task checked clear -> AUTOFOCUS -> Objective ACTIVE -> one lazy
finite DAQ task for the sweep -> final PI best-position verification -> stage
entry-position restoration/readback -> Objective clear/child attestation ->
IMAGING -> next checked Snake imaging task. The parent remains reserved throughout.
The checked imaging-DAQ prerequisite is retained without weakening its status,
identity, no-retry or release rules.

The service computes focus coordinates from frozen absolute target minus the
known pattern origin and checks the legacy adapter's local target against that
calculation. It does not temporarily edit GUI fields. PI stays at the best focus;
the stage returns to its entry position. Current explicit defaults are stage
readback tolerance 1 um, PI tolerance 0.1 um, movement timeout 10 s and DAQ read
timeout 20 s. These require supervised acceptance, not an accuracy claim. PI
transport timeout is bounded per call and the previous setting is restored;
stage calls use the existing persistent owner and its execution timeout.

### Failure, cancellation and completion

Structured outcomes distinguish invalid settings, cancellation, DAQ configure/
start/read/stop/clear failures, PI move/wait/readback failures, no valid focus,
stage move/restore/readback failures and uncertainty. Only successful autofocus
with verified child cleanup and stage restoration permits imaging. A failed
operation can retain verified DAQ release without becoming a successful scan.
Unverified stage/PI state or task cleanup retains the parent reservation.

Cancel Snake workflow in the Objective window requests cooperative cancellation.
Checks occur at phase boundaries, between sweep points, after reads, before
restoration and before imaging. Calls already in progress return under their
bounded contracts; no thread is terminated and no autofocus is restarted.
Safe cleanup can restore known coordinate labels after confirmed idle, without
commanding an extra physical return move. Unknown native stage execution prevents
competing restoration. Frame changes retain existing registration invalidation.

The existing laser-disable algorithm is retained through a private checked SDK
view: emission query/off statuses and final off readback must be verified.
Failure does not claim laser-off. Legacy success emission is buffered until
worker cleanup; the parent reservation persists until Qt thread completion and
final ledger verification. Controls remain guarded until verified parent release.

Diagnostics separate Objective window visibility and Objective RELEASED from
the continuing Snake reservation. They include parent phase/token/generation,
worker identity, cancellation, imaging tasks, Objective child state/identity/
clear evidence, autofocus result and stage/laser cleanup evidence.

### Validation and next step

Final software-only regression: **296 passed, 0 failed** across checked Snake
DAQ, Snake lifecycle, new autofocus service/worker tests, legacy DAQ attestation,
localization DAQ/bridge/orchestration, managed Objective widget/lifecycle,
experimental UI, ownership diagnostics and H-only controls/validation. Qt was
offscreen, bytecode suppressed and real hardware imports explicitly blocked.
Actual Snake and Repeat method bodies were compiled against inert devices and
in-memory output stubs. Tests cover four autofocus operations for two wavelengths
and two patterns/repetitions, preserved output/timestamps, cancellation without
imaging, child/parent authority, stale completion, failure cleanup and admission
races. Existing manual Objective and zero-argument callback regressions pass.

No physical hardware was run. Legacy UI/routines/instrument drivers and hash
constants are unchanged. Checked-DAQ prerequisite work remains preserved.
Module 9 is NOT STARTED. No commit or push accompanies this implementation.

Supervised validation should start with one short wavelength/pattern, confirm
focus/return/best-PI position and DAQ phase ordering, then test two wavelengths
and Repeat counts. Confirm controls remain disabled through task-free gaps and
return only after completion; then manually acquire signal and run Locate Marker
without restart. Check close/reopen and invalid-parameter rejection. Keep native
fault injection, stale tokens and programmatic conflict tests software-only.

### Managed Snake Autofocus Telemetry

Status: **HARDWARE VALIDATED**.

The service already acquired each sweep point; this addition exposes those values
without another acquisition or hardware query. Immutable point events cross the
worker QObject signal through an explicit queued connection to the GUI-thread
Objective receiver and its existing `append_text_signal` rendering path.
Messages identify requested wavelength/units/QCL, not verified physical wavelength.
The selected measurement is retained as `AutofocusResult.best_signal` alongside
`best_position`. Final success is displayed only after stage restoration, PI
verification and checked Objective cleanup. Failures retain their actual outcome.

Telemetry is non-authoritative and subscriber failures are isolated and logged.
No ownership, DAQ handoff or autofocus success rules changed. No worker QWidget
access was introduced. Parent token/generation filters reject obsolete runs;
ordered events from the latest completed parent may drain until a newer run or
manual operation supersedes them. Hidden/reopened widgets reuse the receiver;
replaced widgets ignore delivery and Qt disconnects deleted receivers.

Regression: **303 passed, 0 failed**, with offscreen Qt, `-B` and explicit hardware
import blocking. Coverage includes known signal magnitudes, best-signal pairing,
cleanup-before-result, callback failure isolation, GUI-thread queued delivery,
stale/hidden/deleted receivers, one/two-wavelength Snake and Repeat attribution,
no-autofocus behavior and existing manual Objective/localization regressions.
Legacy files and UI hash remain unchanged. No hardware, commit or push was run.
Module 9 remains NOT STARTED. Supervised validation should observe start, sweep
and final best-signal messages for one and two wavelengths, then Repeat; confirm
unchanged imaging/ownership and manually Acquire Signal afterward.

### Snake Failure Finalization / Recovery

Status: **SOFTWARE IMPLEMENTED AND SOFTWARE TESTED; NORMAL SUCCESS PATH HARDWARE
VALIDATED; REAL POST-FIX FAILURE RECOVERY HARDWARE VALIDATION PENDING**.

Workflow outcome and worker activity are now separate from retained reservation
and hardware safety. A failed completed Snake reports FAILED and worker_active
false; unresolved PI, frame, DAQ or native safety still retains quarantine and
blocks conflicting operations. The existing PI-failure quarantine policy is not
relaxed. Failures with fully verified cleanup under existing policy can release
without claiming scan success. DAQ scope attestation is independent of parent
safety, so a cleared task is not relabeled uncertain solely for a PI mismatch.

Finalization explicitly authorizes only stage idle/readback, coordinate-label
restoration/readback and existing laser-off cleanup. It does not globally bypass
uncertainty or permit new movement/acquisition. Native stage uncertainty prevents
frame operations. Independent cleanup failures are retained without overwriting
the root autofocus failure; child physical restoration does not substitute for
parent coordinate-frame verification. Diagnostics expose the independent evidence.

PI mismatches retain machine-readable phase (sweep_point/final_best), sweep index,
target_um, actual_um, delta_um, tolerance_um, timeout_s, elapsed_s, wait_result,
on_target_poll_count and position_read_count. PI tolerance remains 0.1 um; MOV,
qONT polling and one immediate qPOS retain their previous acceptance behavior.
That checkpoint added no settling, retry or hardware read for diagnostics. Its
single-qPOS acceptance rule is superseded by the bounded confirmation below.

Cancel is disabled after completion; later close requests do not convert FAILED
to cancellation. Running close requests cancellation and retries after thread
finalization. Completed quarantine uses a separate new-UI close path: log the
snapshot, stop gamepad through its existing bounded path, shut down the known
Prior owner or retire its uncertain delivery thread without native disconnect,
stop GUI timers and close. It skips legacy unbounded PI/laser shutdown calls and
does not attest uncertain DAQ, PI, laser or frame release. The experimental Prior
owner retains uncertainty evidence when retiring; this is process exit, not
in-session recovery. A native call still executing can still defer exit: it is
never force-terminated or treated as released. Completed, quiescent quarantine
no longer requires force exit merely because its parent record exists.

Validation: **392 passed, 0 failed** with offscreen Qt, bytecode suppression and
explicit hardware-import blocking. Tests cover exact final/sweep PI deltas,
primary/secondary error separation, real QThread failure completion and heartbeat,
frame restoration and failures, DAQ scope release versus parent quarantine,
admission/control policy, safe/uncertain close, idle owner retirement and an
in-flight fake native call that cannot be terminated. Existing Snake, Repeat,
telemetry, checked DAQ, Objective, localization and stage-owner regressions pass.
Protected legacy source/hash are unchanged. No hardware was run; no commit/push.
Module 9 remains NOT STARTED.

Supervised next step: run a normal short Snake/autofocus. If a PI mismatch occurs
naturally, capture phase/target/actual/delta/tolerance, confirm terminal FAILED
with responsive GUI, retained safety blockers where required and normal bounded
close. Do not deliberately induce PI or DAQ faults.

### PI bounded readback confirmation / Snake failure and shutdown tracing

PI bounded readback confirmation and structured diagnostics:
**HARDWARE VALIDATED**.

Managed Snake pi_move now follows one MOV and the existing qONT wait with a
400 ms observation window. qPOS polls are separated by up to 10 ms and acceptance
requires two consecutive absolute errors <= 0.1 um. An out-of-tolerance sample
resets the consecutive count. This applies to sweep_point and final_best phases.
The PI adapter caps each read transport timeout to the remaining confirmation
budget (milliseconds, rounded down); no read starts with less than 1 ms left.
Late transport results cannot pass. There is no second MOV, larger tolerance,
unconditional settling delay or autofocus selection/spacing change. Persistent
mismatch and qPOS exceptions retain PI_READBACK_FAILURE and checked cleanup.

Structured success/failure diagnostics include target, last/final actual, signed
final delta, minimum absolute delta seen, phase/index, tolerance, window, elapsed
times, on-target polls, attempted position reads, required/observed consecutive
count and the confirmation samples. Successful final-best diagnostics remain in
AutofocusResult.pi_diagnostics. No diagnostic query adds another hardware read.

Snake failure/shutdown tracing:
**SOFTWARE IMPLEMENTED AND SOFTWARE TESTED; HARDWARE SUCCESS-PATH TRACING
OBSERVED; FAILURE/CLOSE HARDWARE VALIDATION PENDING**.

Cached breadcrumbs use sequence, wall/monotonic timestamps, thread and parent
identity, phase, outcome, worker/thread activity, retained-parent and safety state.
They cover autofocus failure, child release, DAQ/stage/frame/laser cleanup,
worker completion and thread quit/finished, parent finalization, controls and close.
Close traces identify cancellation/deferral reasons and brackets around gamepad,
Prior and legacy shutdown. Completed quarantine records legacy_shutdown_skipped,
never a false legacy completion. close_accepted is recorded after acceptance.

The latest 512 events are exposed through the existing Snake diagnostics. Live
hardware-mode startup also enables an asynchronous diagnostic writer beneath the
startup directory: localization_runs/snake_trace_<session>.jsonl. The absolute path,
queue-drop count and errors appear in trace_journal. This ignored runtime directory
is not source data. The queue is bounded at 2048 entries and producers never wait
for file I/O. The writer flushes each JSON line; disk failures/full queues remain
diagnostic only. Offline/inert windows do not automatically create journals.
Persistence is best-effort: queued tail events may be lost on process termination.
After restart, inspect the prior session journal rather than the new session's
empty state. No trace is release evidence or a hardware safety decision.

Validation: **407 passed, 0 failed**, offscreen Qt, -B and explicit hardware-import
blocking. Deterministic fake-clock tests cover a 0.111828 um initial mismatch that
settles, persistent mismatch, transient crossings, qONT timeout, qPOS exceptions,
deadline/transport budgets, phase attribution and exactly one MOV. Actual QThread
failure tests verify heartbeat, breadcrumbs, disabled conflicting controls and
completed-quarantine close without false attestation. Async journal success,
disk errors and full queues are tested in temporary directories. Existing Snake,
Repeat, telemetry, ownership, checked DAQ, Objective and localization tests pass.
Protected legacy files/hash are unchanged; no hardware, commit or push was run.
Module 9 remains NOT STARTED.

Manual next step: run a normal short Snake/autofocus, inspect successful confirmation
diagnostics, and if mismatch occurs naturally capture the sequence and failure/close
breadcrumbs. Confirm responsive GUI and bounded normal close while preserving
quarantine where required. Do not deliberately induce DAQ faults.

## Managed Snake checkpoint: supervised hardware validation closeout

This section records the operator's completed real-QCL validation report. The
checkpoint agent only inspected code/docs and ran software tests; it did not run
hardware. Earlier implementation sections retain historical regression counts
and validation plans. The following status supersedes their pending normal-path
validation statements, but does not claim post-fix failure/close hardware recovery.

| Component | Current validation status |
|---|---|
| Managed Objective Scanner V1 | HARDWARE VALIDATED |
| Checked Snake Imaging DAQ Release V1 | HARDWARE VALIDATED THROUGH SNAKE IMAGING |
| Managed Snake Autofocus V1 | HARDWARE VALIDATED — NORMAL EXECUTION PATH |
| Autofocus telemetry | HARDWARE VALIDATED |
| PI bounded confirmation and structured diagnostics | HARDWARE VALIDATED |
| Failure finalization model | SOFTWARE IMPLEMENTED AND SOFTWARE TESTED; normal success hardware validated; real post-fix failure recovery pending |
| Failure/shutdown tracing | SOFTWARE IMPLEMENTED AND SOFTWARE TESTED; hardware success-path tracing observed; failure/close hardware validation pending |

Managed Objective validation covers open, Acquire Signal, Move To, manual
Autofocus, Objective operations followed by Locate Marker, ownership-based control
disabling during localization/Snake, control restoration and close/reopen.
Operation-scoped DAQ ownership and verified release work in the NEW UI without
legacy UI, routines or instrument-driver changes.

Validated managed order: frozen GUI settings -> Snake worker -> parent reservation
-> wavelength tune -> Objective child autofocus -> verified Objective release ->
checked imaging DAQ -> verified imaging cleanup -> next wavelength/pattern ->
final cleanup/release. Autofocus occurs once per wavelength per pattern/repetition.
Workers do not directly read QWidget state. Queued telemetry reports requested
wavelength, QCL, PI position, signal, best PI position and best signal. Requested
wavelength remains context, not independent wavelength metrology.

Single-wavelength Snake + Autofocus: **PASS**. Final phase COMPLETE, workflow
SUCCESS, worker/native execution inactive, hardware VERIFIED_RELEASED, Objective
and imaging DAQ released, stage verified, frame restored, laser verified and
worker/thread finished. A confirmation example had target approximately
52.956856 um and consecutive deltas -0.031112 and -0.011184 um: both passed.

Two-wavelength Snake (1500 and 1600 cm^-1): **PASS**. One autofocus preceded imaging
at each wavelength, yielding two Objective child releases and two checked imaging
tasks. Complete cleanup ended SUCCESS / VERIFIED_RELEASED. Best focus was about
52.96 um at 1500 cm^-1 and 54.96 um at 1600 cm^-1. The repeatable approximately
2 um offset is an observation in this tested configuration, not a general
physical conclusion about wavelength and focus.

Repeat Snake, two wavelengths x two patterns: **PASS**. Workflow type
repeat_snake_scan produced four managed autofocus operations and four imaging
DAQ tasks. All child operations released cleanly; all imaging configure/start/
read/stop/clear checks passed, with no operation failures. Final workflow SUCCESS,
hardware VERIFIED_RELEASED, worker inactive, thread finished, parent reservation
released and controls restored. Best-focus readings were approximately:

| Requested wavelength | First focus (um) | Repeated focus (um) |
|---|---:|---:|
| 1500 cm^-1 | 52.948 | 52.944 |
| 1600 cm^-1 | 54.945 | 54.941 |

These values demonstrate good repeatability in this validation run. They are
not a calibrated accuracy claim or evidence of arbitrary hardware fault testing.

PI confirmation retains the 0.1 um tolerance and one MOV. After qONT=true, qPOS
is observed for at most 400 ms with 10 ms polling and two consecutive in-tolerance
reads required. Persistent mismatch still fails closed as PI_READBACK_FAILURE.
The motivating real final_best failure was target 52.973608 um, actual 53.085436 um,
delta 0.111828 um, tolerance 0.1 um, qONT true and one immediate qPOS. The previous
rule failed only 0.011828 um beyond tolerance; bounded observation addresses a
potential transient without increasing tolerance or re-commanding movement.
Structured diagnostics expose phase/sweep index, target, actual/final actual,
delta/minimum absolute error, tolerance, timeout/window, elapsed time, qONT/qPOS
counts, consecutive count and samples; sweep_point and final_best are distinct.

Failure finalization keeps workflow RUNNING/SUCCESS/FAILED/CANCELLED separate from
hardware VERIFIED_RELEASED/UNCERTAIN/QUARANTINED and worker/native execution.
Terminal failure need not appear worker-active merely to retain quarantine.
Normal success is now hardware validated; a persistent post-fix PI failure was
not deliberately reproduced. **Real failure recovery/close remains pending a
natural failure**, and no arbitrary DAQ fault injection is claimed hardware tested.

Success-path breadcrumbs were observed. Failure/close breadcrumbs and best-effort
JSONL journals under localization_runs are diagnostic, non-authoritative and
excluded from Git; forced termination may lose queued tail events. Software tests
cover failure/quarantine/close without substituting for real hardware validation.

Current roadmap numbering: Module 6 reflection acquisition/edge analysis remains
complete; Module 8 production Locate Marker is implemented and previously hardware
validated. Module 9 guarded target movement is **NOT STARTED — DEFERRED**. Further
Module 9 development requires a new explicit instruction.

Final checkpoint software validation: **407 targeted tests passed**, followed by
**847 full-discovery tests passed; 0 failures, 0 errors, 0 skips**. Both runs used
offscreen Qt, Python -B, PYTHONDONTWRITEBYTECODE and explicit hardware-import
blocking. The full run follows the repository's unittest discovery convention.
Protected legacy UI/routines/instrument code is unchanged. Legacy UI SHA-256:
`fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab`.
Existing /localization_runs/ ignore policy already excludes runtime traces/data;
.gitignore needs no change. Only intentional source, tests and these existing
documentation files are included in the checkpoint.
