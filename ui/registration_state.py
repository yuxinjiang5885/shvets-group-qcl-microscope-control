"""Offline UI lifecycle; no device ownership and no coordinate-transform math.

Archived registration is a demonstration in its recorded frame, never evidence
that the current hardware/sample is registered. Context changes discard approval.
"""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from threading import RLock
from functools import wraps

from experiment.marker_profile_classification import (ClassificationResult, ProfileClass,
                                                       classify_profiles, ProfileGeometry)
from experiment.marker_rotation import RotationFitResult, fit_rotation
from experiment.marker_center_refinement import CenterRefinementResult, refine_marker_center
from experiment.marker_stage_registration import build_stage_registration
from experiment.stage_registration import Orientation, local_to_stage
from experiment.reflection_analysis import EdgeSettings, analyze_scan
from experiment.scan_1d import load_scan
from ui.translation_registration import TranslationEvidence, build_translation_registration


class RegistrationStatus(str, Enum):
    NOT_REGISTERED = 'NOT REGISTERED'
    REGISTERING = 'REGISTERING'
    VALID = 'VALID'
    INVALID = 'INVALID'


class ContextEvent(str, Enum):
    MOVEMENT = 'ordinary_movement'
    FRAME = 'frame_redefinition'
    RECONNECT = 'reconnect_reset'
    SAMPLE = 'sample_replacement'
    GDS = 'gds_replacement'
    MARKER = 'marker_change'
    ORIENTATION = 'orientation_change'
    INPUTS = 'registration_input_change'


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call


@dataclass(frozen=True)
class RegistrationContext:
    gds_path: str = ''
    gds_sha256: str = ''
    marker_id: str = ''
    orientation: Orientation = Orientation.FLIP_X
    frame_id: str = 'archived-module7-frame'
    sample_id: str = 'archived-S37a-sample'
    inputs_id: str = 'archived-module7-journals'


@dataclass(frozen=True)
class RegistrationEvidence:
    """Retain full upstream diagnostics, not just rendered numbers."""
    context: RegistrationContext
    classification: ClassificationResult
    rotation: RotationFitResult
    center: CenterRefinementResult
    source_hashes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TargetPrediction:
    feature_id: str
    label: str
    absolute_gds_um: tuple[float, float]
    marker_local_um: tuple[float, float]
    stage_um: tuple[float, float]


class RegistrationState:
    """One context-bound approval; targets never participate in the fit.

    UI events must synchronize context before review/prediction. A new loaded
    layout also explicitly invalidates, even when it has the same filename.
    No approval is resurrected just because a setting is changed back.
    """
    def __init__(self):
        self.lock = RLock()
        self.context_generation = 0
        self.context = RegistrationContext()
        self.status = RegistrationStatus.NOT_REGISTERED
        self.assignments = None
        self.evidence = None
        self.registration = None
        self.warnings = ()
        self.reasons = ()
        self.prediction = None

    @property
    def registration_mode(self):
        if self.registration is None:
            return None
        return getattr(self.registration, 'registration_mode', 'rotation_calibrated')

    @property
    def rotation_calibrated(self):
        return self.registration is not None and self.registration_mode == 'rotation_calibrated'

    @property
    def approved_registration(self):
        return self.registration

    @_locked
    def invalidate(self, reason, *, context_changed=True):
        if context_changed:
            self.context_generation += 1
        self.registration = None
        self.prediction = None
        self.status = RegistrationStatus.INVALID
        self.reasons = (reason,)
        # Last evidence/warnings remain inspectable, but never usable as approval.

    @_locked
    def set_context(self, context):
        if context != self.context:
            self.context = context
            self.invalidate('registration_context_changed')

    @_locked
    def handle_context_event(self, event, context=None):
        event = ContextEvent(event)
        if event is ContextEvent.MOVEMENT:
            if context is not None and context != self.context:
                raise ValueError('movement_cannot_redefine_context')
            return
        if context is not None:
            self.context = context
        self.invalidate(event.value)

    @_locked
    def begin(self):
        """Legacy offline replay replacement. Candidate runs must not call this.

        LocalizationController retains approval and uses publish_candidate only
        after successful work/cleanup. Existing offline replay behavior is kept.
        """
        self.registration = None
        self.prediction = None
        self.evidence = None
        self.warnings = ()
        self.reasons = ()
        self.status = RegistrationStatus.REGISTERING

    @_locked
    def accept(self, evidence):
        self.begin()
        self.evidence = evidence
        if isinstance(evidence, TranslationEvidence):
            try:
                if evidence.context != self.context or not self.context.marker_id:
                    raise ValueError('evidence_context_mismatch')
                self.registration = build_translation_registration(evidence)
                self.warnings = self.registration.warnings
                self.status = RegistrationStatus.VALID
            except ValueError as error:
                self.invalidate(str(error), context_changed=False)
                raise
            return
        self.warnings = tuple(dict.fromkeys((*evidence.rotation.warnings, *evidence.center.warnings)))
        try:
            if evidence.context != self.context or not self.context.marker_id:
                raise ValueError('evidence_context_mismatch')
            classification = evidence.classification
            if (not classification.sufficient_for_rotation_fit or classification.reasons
                    or classification.usable_final_fits is None):
                raise ValueError('classifier_not_accepted')
            if set(evidence.rotation.used_profile_ids) != set(classification.central_identifiers):
                raise ValueError('central_profile_identity_mismatch')
            registration = build_stage_registration(evidence.rotation, evidence.center)
            if registration.registration.orientation != self.context.orientation:
                raise ValueError('orientation_mismatch')
            self.registration = registration
            self.warnings = registration.warnings
            self.status = RegistrationStatus.VALID
        except ValueError as error:
            self.invalidate(str(error), context_changed=False)
            self.reasons = tuple(dict.fromkeys((*self.reasons, *evidence.classification.reasons,
                                               *evidence.rotation.reasons, *evidence.center.reasons)))
            raise

    @_locked
    def publish_candidate(self, evidence, generation):
        """Validate in isolation then replace atomically; rejection leaves approval.

        Controller owns the full-run/cleanup gate. This method additionally checks
        generation/context and reuses the existing approval checks, without refits.
        """
        if generation != self.context_generation:
            raise ValueError('stale_candidate_generation')
        checked = RegistrationState()
        checked.context = self.context
        checked.accept(evidence)
        self.evidence = checked.evidence
        self.registration = checked.registration
        self.warnings = checked.warnings
        self.reasons = ()
        self.status = RegistrationStatus.VALID
        self.prediction = None

    @_locked
    def targets_changed(self, assignments):
        self.assignments = assignments
        self.prediction = None

    @_locked
    def predict(self, feature_id):
        self.prediction = None
        if self.status is not RegistrationStatus.VALID or self.registration is None:
            raise ValueError('registration_not_valid')
        assignments = self.assignments
        if assignments is None or assignments.marker is None:
            raise ValueError('reference_marker_missing')
        if assignments.marker.feature_id != self.context.marker_id:
            self.invalidate('reference_marker_changed')
            raise ValueError('reference_marker_changed')
        entry = assignments.ms_assignments[feature_id]
        chip = assignments.build_chip_layout()
        pixel = chip.get_ms_pixel(entry.name)
        local = (pixel.center_local_x, pixel.center_local_y)
        stage = local_to_stage(*local, self.registration.registration)
        self.prediction = TargetPrediction(feature_id, entry.name,
            (pixel.center_gds_x, pixel.center_gds_y), local, tuple(stage))
        return self.prediction

    @_locked
    def registered_predictions(self):
        if self.status is not RegistrationStatus.VALID or self.registration is None:
            return {}
        assignments = self.assignments
        if assignments is None or assignments.marker is None:
            return {}
        marker = assignments.marker
        if marker.feature_id != self.context.marker_id:
            self.invalidate('reference_marker_changed')
            return {}
        result = {marker.feature_id: TargetPrediction(marker.feature_id, 'Reference marker',
            (marker.center_x_um, marker.center_y_um), (0., 0.),
            tuple(local_to_stage(0., 0., self.registration.registration)))}
        selected = self.prediction
        try:
            for feature_id in assignments.ms_assignments:
                result[feature_id] = self.predict(feature_id)
        finally:
            self.prediction = selected
        return result


def replay_archived_evidence(root):
    """UI demo orchestration only: reuse every Module 6/7 algorithm unchanged.

    No GDS role is selected here. The caller must manually select the marker
    matching the archived evidence. Provenance includes the actual journal hashes.
    """
    from square_marker_profile_classification_check import JOURNALS
    from square_marker_center_refinement_check import VERTICAL_JOURNAL, INITIAL_HORIZONTAL_JOURNAL

    root = Path(root)
    record = json.loads((root / 'docs/evidence/module7/selection_and_predictions.json').read_text('utf-8'))
    marker = next(row for row in record['selections'] if row['is_reference'])
    context = RegistrationContext(str(Path(record['gds_path']).resolve()),
        record['gds_sha256'], marker['feature_id'])
    filenames = (INITIAL_HORIZONTAL_JOURNAL, VERTICAL_JOURNAL, *JOURNALS)
    scans = {name: load_scan(root / name) for name in filenames}
    settings = EdgeSettings(expected_width_um=500, width_tolerance_um=100)
    horizontal, vertical = scans[INITIAL_HORIZONTAL_JOURNAL], scans[VERTICAL_JOURNAL]
    he, ve = analyze_scan(horizontal, settings), analyze_scan(vertical, settings)
    if horizontal.settings.axis != 'x' or vertical.settings.axis != 'y' or not he.valid or not ve.valid:
        raise ValueError('initial_scan_analysis_failed')
    profiles = []
    for i, name in enumerate(JOURNALS, 1):
        scan = scans[name]
        if scan.settings.axis != 'x':
            raise ValueError('expected_horizontal_scan')
        edge = analyze_scan(scan, settings)
        ys = [p.measured_um[1] for p in scan.points if p.measured_um is not None]
        valid = bool(ys) and edge.valid and len(ys) == len(scan.points) and max(ys)-min(ys) <= 1
        profiles.append(ProfileGeometry(f'P{i}', mean(ys) if ys else float('nan'),
            edge.left_edge_um, edge.right_edge_um, edge.midpoint_um, edge.width_um, valid))
    classification = classify_profiles(profiles, ve.midpoint_um)
    if not classification.sufficient_for_rotation_fit or classification.usable_final_fits is None:
        raise ValueError('classifier_not_accepted: ' + repr(classification.reasons))
    central = tuple(row.profile for row in classification.profiles if row.classification is ProfileClass.CENTRAL)
    rotation = fit_rotation(classification, central)
    center = refine_marker_center(rotation, vertical, initial_center_um=(he.midpoint_um, ve.midpoint_um))
    build_stage_registration(rotation, center)  # Hard upstream gate, no diagnostic-only approval.
    hashes = tuple((name, sha256((root / name).read_bytes()).hexdigest()) for name in filenames)
    return RegistrationEvidence(context, classification, rotation, center, hashes)
