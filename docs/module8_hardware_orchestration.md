# Module 8 M8.2a: fake-service localization orchestration

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
