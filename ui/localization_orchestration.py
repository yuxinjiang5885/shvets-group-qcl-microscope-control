"""M8.2a orchestration contracts only: no devices, scans, Qt, laser or motion.

Ownership covers cooperating callers in this process. It is not a hardware lock
against vendor applications or unguarded legacy code. No real backend is supplied.
"""
from ui.runtime_provenance import breadcrumb
from ui.translation_registration import TranslationEvidence
from dataclasses import dataclass
from enum import Enum
from queue import SimpleQueue
from threading import Event, RLock
from typing import Protocol
from uuid import uuid4

from ui.registration_state import (RegistrationContext, RegistrationEvidence, RegistrationState,
    ClassificationResult, RotationFitResult, CenterRefinementResult)


class OwnershipError(RuntimeError):
    pass


class Cancelled(Exception):
    pass


class CancellationToken:
    """Cooperative only. Cannot interrupt a blocked native SDK call."""
    def __init__(self):
        self._event = Event()
        self.commit_lock = RLock()

    def request_cancel(self):
        with self.commit_lock:
            self._event.set()

    def is_cancelled(self):
        return self._event.is_set()

    def checkpoint(self):
        if self.is_cancelled():
            raise Cancelled('cancellation_requested')


class Activity(str, Enum):
    SCAN = 'existing_scan'
    REPEAT = 'repeat_scan'
    MULTIWELL = 'multiwell'
    AUTOFOCUS = 'autofocus'
    GAMEPAD = 'gamepad'
    OBJECTIVE_DAQ = 'objective_daq'
    FRAME_CHANGE = 'frame_change'


class Command(str, Enum):
    MANUAL_MOVE = 'manual_move'
    COORDINATE_MOVE = 'coordinate_move'
    GAMEPAD = 'gamepad'
    SNAKE_SCAN = 'snake_scan'
    REPEAT_SCAN = 'repeat_scan'
    IMAGING = 'imaging'
    SPECTRUM = 'spectrum_sweep'
    MULTIWELL = 'multiwell'
    OBJECTIVE_MOVE = 'objective_move'
    AUTOFOCUS = 'autofocus'
    SPEED_ACCELERATION = 'speed_acceleration'
    FRAME_CHANGE = 'zero_frame_change'
    GDS_CHANGE = 'gds_change'
    MARKER_CHANGE = 'marker_change'
    ORIENTATION_CHANGE = 'orientation_change'
    SAMPLE_CHANGE = 'sample_change'
    INPUT_CHANGE = 'input_change'
    REPLAY = 'archived_registration_replacement'
    TARGET_MOTION = 'target_motion'
    LOGS = 'logs'
    CACHED_COORDINATES = 'cached_coordinates'
    PROGRESS = 'progress'
    QC_REVIEW = 'qc_review'
    CANCEL = 'cancel'


READ_ONLY = frozenset((Command.LOGS, Command.CACHED_COORDINATES, Command.PROGRESS,
                       Command.QC_REVIEW, Command.CANCEL))


class OwnershipStatus(str, Enum):
    AVAILABLE = 'AVAILABLE'
    LEASED = 'LEASED'
    QUARANTINED = 'QUARANTINED'


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalizationLease:
    run_id: str
    # One atomic lease covers all competing authorities, not independent locks.
    authorities: tuple[str, ...] = ('stage', 'daq', 'gamepad', 'legacy_scan', 'objective')


@dataclass(frozen=True)
class CleanupOutcome:
    daq_released: bool
    stage_idle: bool
    stop_confirmed: bool = True
    reasons: tuple[str, ...] = ()

    @property
    def confirmed(self):
        return (self.daq_released is True and self.stage_idle is True
                and self.stop_confirmed is True and not self.reasons)


@dataclass(frozen=True)
class RecoveryConfirmation:
    run_id: str
    stage_idle: bool
    daq_released: bool
    competing_activity_stopped: bool
    frame_verified: bool
    operator_note: str


class HardwareOwnershipController:
    """Atomic lease/blocker registry; callers must report activities honestly.

    A late conflicting activity quarantines ownership; it cannot be dismissed by
    a successful cleanup report. Recovery is an explicit external attestation,
    not an automatic hardware-safety check, and never restores registration.
    """
    def __init__(self, transaction_lock=None):
        self._lock = transaction_lock or RLock()
        self._active = None
        self._activities = set()
        self.status = OwnershipStatus.AVAILABLE
        self.reasons = ()
        self.quarantined_run_id = None

    def set_activity(self, activity, active):
        activity = Activity(activity)
        with self._lock:
            if active:
                self._activities.add(activity)
                if self._active is not None:
                    self.status = OwnershipStatus.QUARANTINED
                    self.quarantined_run_id = self._active.run_id
                    self.reasons = tuple(dict.fromkeys((*self.reasons, 'conflicting_activity:' + activity.value)))
            else:
                self._activities.discard(activity)

    def can_begin_localization(self):
        with self._lock:
            reasons = tuple('activity:' + a.value for a in sorted(self._activities, key=lambda a: a.value))
            if self._active is not None:
                reasons += ('lease_active',)
            if self.status is OwnershipStatus.QUARANTINED:
                reasons += ('ownership_quarantined',)
            return GuardDecision(not reasons, reasons)

    def acquire(self):
        with self._lock:
            decision = self.can_begin_localization()
            if not decision.allowed:
                raise OwnershipError('; '.join(decision.reasons))
            self._active = LocalizationLease(uuid4().hex)
            self.status = OwnershipStatus.LEASED
            return self._active

    def assert_authority(self, lease):
        with self._lock:
            if self._active is not lease or self.status is not OwnershipStatus.LEASED:
                raise OwnershipError('lease_not_authorized')

    def quarantine(self, lease, reason):
        """Latch native execution uncertainty without releasing its owner."""
        with self._lock:
            if self._active is not lease:
                raise OwnershipError('stale_quarantine_request')
            self.status = OwnershipStatus.QUARANTINED
            self.quarantined_run_id = lease.run_id
            self.reasons = tuple(dict.fromkeys((*self.reasons, reason)))

    def release(self, lease, cleanup):
        with self._lock:
            if self._active is not lease:
                raise OwnershipError('stale_lease_release')
            self._active = None
            if not cleanup.confirmed or self.status is OwnershipStatus.QUARANTINED:
                self.status = OwnershipStatus.QUARANTINED
                self.quarantined_run_id = lease.run_id
                self.reasons = tuple(dict.fromkeys((*self.reasons, *cleanup.reasons, 'cleanup_or_ownership_unconfirmed')))
            else:
                self.status = OwnershipStatus.AVAILABLE
                self.reasons = ()

    def acknowledge_recovery(self, confirmation):
        with self._lock:
            if self.status is not OwnershipStatus.QUARANTINED or self._active is not None:
                raise OwnershipError('recovery_not_ready')
            if (confirmation.run_id != self.quarantined_run_id or self._activities
                    or not confirmation.operator_note.strip()
                    or any(value is not True for value in (confirmation.stage_idle,
                        confirmation.daq_released, confirmation.competing_activity_stopped,
                        confirmation.frame_verified))):
                raise OwnershipError('recovery_not_confirmed')
            self.status = OwnershipStatus.AVAILABLE
            self.reasons = ()
            self.quarantined_run_id = None

    def guard(self, command):
        try:
            command = Command(command)
        except ValueError:
            return GuardDecision(False, ('unknown_command',))
        with self._lock:
            if command in READ_ONLY:
                return GuardDecision(True)
            if command is Command.TARGET_MOTION:
                return GuardDecision(False, ('target_motion_not_implemented',))
            return self.can_begin_localization()

    def dispatch(self, command, action):
        """Guard + invocation under the same lock; action is fake/offline here.

        Future long-lived external jobs must register activity before returning.
        This function does not cancel work that bypasses this controller.
        """
        with self._lock:
            decision = self.guard(command)
            if not decision.allowed:
                raise OwnershipError('; '.join(decision.reasons))
            return action()


class AcquisitionState(str, Enum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'
    CANCELLING = 'CANCELLING'
    CANCELLED = 'CANCELLED'
    FAILED = 'FAILED'
    COMPLETE = 'COMPLETE'


class RunStateMachine:
    def __init__(self):
        self.state = AcquisitionState.IDLE

    def transition(self, target):
        target = AcquisitionState(target)
        allowed = {
            AcquisitionState.IDLE: {AcquisitionState.RUNNING},
            AcquisitionState.RUNNING: {AcquisitionState.CANCELLING, AcquisitionState.FAILED, AcquisitionState.COMPLETE},
            AcquisitionState.CANCELLING: {AcquisitionState.CANCELLED, AcquisitionState.FAILED},
            AcquisitionState.CANCELLED: {AcquisitionState.IDLE},
            AcquisitionState.FAILED: {AcquisitionState.IDLE},
            AcquisitionState.COMPLETE: {AcquisitionState.IDLE},
        }
        if target not in allowed[self.state]:
            raise ValueError(f'invalid_transition:{self.state.value}->{target.value}')
        self.state = target


@dataclass(frozen=True)
class RunSettings:
    context: RegistrationContext
    context_generation: int
    expected_rough_start_id: str
    purpose: str = 'registration'

    def __post_init__(self):
        if (type(self.context_generation) is not int or self.context_generation < 0
                or not self.expected_rough_start_id.strip()
                or self.purpose not in ('registration', 'translation_only', 'h_only', 'hv', 'multi_h')):
            raise ValueError('invalid_run_settings')


@dataclass(frozen=True)
class RunHandle:
    settings: RunSettings
    lease: LocalizationLease
    cancellation: CancellationToken

    @property
    def run_id(self):
        return self.lease.run_id


@dataclass(frozen=True)
class WorkerEvent:
    name: str
    run_id: str
    context_generation: int
    detail: object = None


class LocalizationController:
    """Serializes publication against context changes using RegistrationState.lock.

    Worker thread may run work/cleanup; GUI may cancel/change context. Widgets
    consume snapshots/events only. No UI/hardware lifecycle is started here.
    """
    def __init__(self, registration_state, ownership=None):
        self.registration = registration_state
        self.ownership = ownership or HardwareOwnershipController(registration_state.lock)
        if self.ownership._lock is not registration_state.lock:
            raise ValueError('ownership_requires_registration_transaction_lock')
        self.machine = RunStateMachine()
        self.active = None
        self.last_run_id = None
        self.candidate_registration = None
        self.warnings = ()
        self.reasons = ()
        self.shutdown_requested = False

    def start(self, settings, cancellation=None):
        with self.registration.lock:
            if self.shutdown_requested or self.active is not None:
                raise OwnershipError('run_or_shutdown_active')
            if (settings.context_generation != self.registration.context_generation
                    or settings.context != self.registration.context):
                raise ValueError('stale_run_context')
            lease = self.ownership.acquire()
            if self.machine.state is not AcquisitionState.IDLE:
                self.machine.transition(AcquisitionState.IDLE)
            self.machine.transition(AcquisitionState.RUNNING)
            self.active = RunHandle(settings, lease, cancellation or CancellationToken())
            self.last_run_id = lease.run_id
            self.candidate_registration = None
            self.warnings, self.reasons = (), ()
            return self.active

    def request_cancel(self, handle=None):
        with self.registration.lock:
            if self.active is None or (handle is not None and handle is not self.active):
                return False
            self.active.cancellation.request_cancel()
            if self.machine.state is AcquisitionState.RUNNING:
                self.machine.transition(AcquisitionState.CANCELLING)
            return True

    def context_updated(self):
        with self.registration.lock:
            if self.active and self.active.settings.context_generation != self.registration.context_generation:
                self.request_cancel()

    def handle_context_event(self, event, context=None):
        with self.registration.lock:
            self.registration.handle_context_event(event, context)
            self.context_updated()

    def report_activity(self, activity, active):
        with self.registration.lock:
            self.ownership.set_activity(activity, active)
            if self.ownership.status is OwnershipStatus.QUARANTINED:
                self.registration.invalidate('ownership_conflict')
                self.request_cancel()

    def checkpoint(self, handle):
        with self.registration.lock:
            if handle is not self.active:
                raise Cancelled('stale_run')
            self.context_updated()
            handle.cancellation.checkpoint()
            self.ownership.assert_authority(handle.lease)

    def offer_candidate(self, handle, evidence):
        with self.registration.lock:
            self.checkpoint(handle)
            if handle.settings.purpose in ('h_only', 'hv', 'multi_h'):
                raise ValueError('H_only_cannot_publish_registration')
            if handle.settings.purpose == 'translation_only':
                if not isinstance(evidence, TranslationEvidence) or evidence.run_id != handle.run_id:
                    raise ValueError('malformed_translation_candidate')
            elif (not isinstance(evidence, RegistrationEvidence)
                    or not isinstance(evidence.classification, ClassificationResult)
                    or not isinstance(evidence.rotation, RotationFitResult)
                    or not isinstance(evidence.center, CenterRefinementResult)):
                raise ValueError('malformed_candidate')
            self.candidate_registration = evidence
            # Validate without touching the approved state. A QC failure follows
            # the normal failure/cleanup path; publication validates again.
            scratch = RegistrationState()
            scratch.context = self.registration.context
            scratch.accept(evidence)

    def finish(self, handle, *, succeeded, cleanup, reasons=()):
        """Only the active run can settle its lease or publish. Stale results ignored."""
        with self.registration.lock, handle.cancellation.commit_lock:
            if handle is not self.active:
                return False
            self.context_updated()
            self.reasons = tuple(reasons)
            candidate = self.candidate_registration
            if isinstance(candidate, TranslationEvidence):
                self.warnings = tuple(dict.fromkeys((*candidate.warnings, 'rotation_assumed_zero_not_calibrated')))
            elif candidate is not None:
                self.warnings = tuple(dict.fromkeys((*candidate.rotation.warnings, *candidate.center.warnings)))
                self.reasons += (*candidate.classification.reasons,
                                 *candidate.rotation.reasons, *candidate.center.reasons)
            # Settlement comes before approval. Quarantine overrides cancellation.
            self.ownership.release(handle.lease, cleanup)
            if self.ownership.status is OwnershipStatus.QUARANTINED:
                self.registration.invalidate('ownership_uncertain')
                self.reasons += self.ownership.reasons
                target = AcquisitionState.FAILED
            elif handle.cancellation.is_cancelled():
                if self.machine.state is AcquisitionState.RUNNING:
                    self.machine.transition(AcquisitionState.CANCELLING)
                self.reasons += ('cancelled',)
                target = AcquisitionState.CANCELLED
            elif succeeded is True and handle.settings.purpose in ('h_only', 'hv', 'multi_h'):
                target = AcquisitionState.COMPLETE  # Never publishes registration.
            elif succeeded is not True or candidate is None:
                self.reasons += ('candidate_run_failed',)
                target = AcquisitionState.FAILED
            else:
                try:
                    self.registration.publish_candidate(candidate, handle.settings.context_generation)
                    target = AcquisitionState.COMPLETE
                except Exception as error:
                    self.reasons += (str(error),)
                    if isinstance(candidate, RegistrationEvidence):
                        self.reasons += (*candidate.classification.reasons,
                                         *candidate.rotation.reasons, *candidate.center.reasons)
                    target = AcquisitionState.FAILED
            self.machine.transition(target)
            self.candidate_registration = None
            self.active = None
            return target is AcquisitionState.COMPLETE

    def event_is_current(self, event):
        with self.registration.lock:
            return (event.run_id == self.last_run_id
                    and event.context_generation == self.registration.context_generation)

    def request_close(self):
        with self.registration.lock:
            self.shutdown_requested = True
            self.request_cancel()
            return self.can_close()

    def can_close(self):
        with self.registration.lock:
            return self.active is None and self.ownership.status is not OwnershipStatus.QUARANTINED

    def snapshot(self):
        with self.registration.lock:
            return dict(acquisition=self.machine.state.value, run_id=self.last_run_id,
                ownership=self.ownership.status.value, candidate_pending=self.candidate_registration is not None,
                approved_retained=self.registration.registration is not None,
                generation=self.registration.context_generation, warnings=self.warnings,
                reasons=self.reasons + self.ownership.reasons)


class LocalizationServices(Protocol):
    """Only tests provide an implementation in M8.2a; no scan backend exists."""
    movement_attempted: bool

    def prepare(self, settings: RunSettings): ...
    def work(self, settings: RunSettings, checkpoint, progress) -> RegistrationEvidence: ...
    def protective_stop(self) -> bool: ...
    def release_daq(self) -> bool: ...
    def confirm_idle(self) -> bool: ...


class LocateMarkerWorker:
    """Synchronous core runnable on a future thread; no widgets/native calls here.

    Cleanup order: protective stop if failed/cancelled after movement entry,
    owned DAQ release, idle confirmation, lease settlement, optional publication.
    A blocked injected call keeps ownership active until it returns. No retry,
    return motion, disconnect, thread termination or native-call interruption.
    """
    def __init__(self, controller, handle, services):
        self.controller, self.handle, self.services = controller, handle, services
        self.events = SimpleQueue()
        self.delivery_errors = []
        self._ran = False

    def run(self, notify=None):
        if self._ran:
            raise RuntimeError('worker_already_run')
        self._ran = True

        def emit(name, detail=None):
            event = WorkerEvent(name, self.handle.run_id, self.handle.settings.context_generation, detail)
            self.events.put(event)
            if notify:
                try:
                    notify(event)
                except Exception as error:
                    self.delivery_errors.append(str(error))  # Observer failure cannot skip cleanup.

        def progress(value):
            emit('progress', value)
            if isinstance(value, dict):
                if 'warnings' in value:
                    with self.controller.registration.lock:
                        self.controller.warnings = tuple(dict.fromkeys(
                            (*self.controller.warnings, *value['warnings'])))
                    for warning in value['warnings']:
                        emit('warning', warning)
                if 'phase' in value:
                    emit('phase_changed', value['phase'])
                if 'profile_completed' in value:
                    emit('profile_completed', value)

        touched = False
        succeeded = False
        reasons = ()
        emit('started')
        if self.controller.active is not self.handle:
            emit('failed', ('stale_run',))
            emit('finished', 'STALE')
            return
        try:
            self.controller.checkpoint(self.handle)
            emit('phase_changed', 'prepare')
            touched = True  # prepare can fail after acquiring a partial resource.
            breadcrumb(self.services, 'services_prepare_enter')
            self.services.prepare(self.handle.settings)
            self.controller.checkpoint(self.handle)
            emit('phase_changed', 'candidate_work')
            breadcrumb(self.services, 'services_work_enter')
            candidate = self.services.work(self.handle.settings,
                lambda: self.controller.checkpoint(self.handle), progress)
            if self.handle.settings.purpose in ('h_only', 'hv', 'multi_h'):
                progress({self.handle.settings.purpose + '_result': candidate})
            else:
                self.controller.offer_candidate(self.handle, candidate)
            succeeded = True
        except Cancelled as error:
            self.controller.request_cancel(self.handle)
            reasons = (str(error),)
        except Exception as error:
            reasons = (f'{type(error).__name__}: {error}',)
        finally:
            breadcrumb(self.services, 'cleanup_enter')
            emit('phase_changed', 'cleanup')
            failures = []

            def checked(name):
                try:
                    if getattr(self.services, name)() is not True:
                        raise RuntimeError('not_confirmed')
                    return True
                except Exception as error:
                    failures.append(f'{name}: {error}')
                    return False

            stop = True
            if touched and (not succeeded or self.handle.cancellation.is_cancelled()):
                try:
                    attempted = self.services.movement_attempted
                    if type(attempted) is not bool:
                        raise ValueError('movement_attempt_unknown')
                except Exception as error:
                    # Never guess that a move occurred and issue a stop. Missing
                    # entry tracking instead makes ownership unconfirmed.
                    attempted = False
                    stop = False
                    failures.append(f'movement_tracking: {error}')
                if attempted:
                    stop = checked('protective_stop')
            daq = checked('release_daq') if touched else True
            idle = checked('confirm_idle') if touched else True
            if hasattr(self.services, 'restore_inputs'):
                if daq and idle and stop and self.controller.ownership.status is OwnershipStatus.LEASED:
                    checked('restore_inputs')
                else:
                    failures.append('input_restore_withheld_unsafe_cleanup')
            cleanup = CleanupOutcome(daq, idle, stop, tuple(failures))
            # Snapshot terminal output atomically: an observer/new GUI action
            # may start another run as soon as this lease has been settled.
            with self.controller.registration.lock:
                accepted = self.controller.finish(self.handle, succeeded=succeeded, cleanup=cleanup, reasons=reasons)
                warnings = self.controller.warnings
                final_reasons = self.controller.reasons
                state = self.controller.machine.state
                registration = self.controller.registration.registration
            for warning in warnings:
                emit('warning', warning)
            if accepted and self.handle.settings.purpose in ('h_only', 'hv', 'multi_h'):
                emit('progress', {self.handle.settings.purpose + '_complete': True, 'cleanup': 'PASS', 'registration_published': False})
            elif accepted:
                emit('registration_completed', registration)
            elif state is AcquisitionState.CANCELLED:
                emit('cancelled', final_reasons)
            else:
                emit('failed', final_reasons)
            emit('finished', state.value)
