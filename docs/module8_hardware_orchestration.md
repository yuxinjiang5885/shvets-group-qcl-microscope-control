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
Objective creation is guarded; any existing objective widget prevents localization,
so its direct-bound PI/DAQ buttons cannot coexist with an acquired lease.
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
