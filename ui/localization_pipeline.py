"""Full localization orchestration over injected services; no hardware factories.

Scan, edge detection and registration remain in unchanged Module 6-7 APIs.
The operational UI supplies no live backend in this milestone.
"""
from dataclasses import dataclass, asdict
from hashlib import sha256
from math import cos, sin, radians, isfinite, hypot
from pathlib import Path
from statistics import mean
import json
import time

from experiment.scan_1d import ScanSettings, StageBounds, ScanStatus, scan_1d, load_scan
from experiment.scan_adapters import NIReflectionReader
from experiment.reflection_analysis import EdgeSettings, analyze_scan
from experiment.marker_profile_classification import (ClassificationSettings, ProfileGeometry,
    ProfileClass, classify_profiles)
from experiment.marker_rotation import fit_rotation
from experiment.marker_center_refinement import CenterRefinementSettings, refine_marker_center
from experiment.marker_stage_registration import build_stage_registration
from experiment.stage_registration import Orientation
from ui.registration_state import RegistrationEvidence


@dataclass(frozen=True)
class DaqSettings:
    channels: tuple[str, str] = ('Dev1/ai0', 'Dev1/ai1')
    voltage_range: tuple[float, float] = (-10., 10.)
    clipping_v: float = 9.9
    samples: int = 32
    rate_hz: int = 100000
    reset: bool = False
    finite: bool = True
    triggered: bool = False

    def __post_init__(self):
        if (self.channels != ('Dev1/ai0', 'Dev1/ai1') or self.voltage_range != (-10., 10.)
                or self.clipping_v != 9.9 or self.samples != 32 or self.rate_hz != 100000
                or self.reset is not False or self.finite is not True or self.triggered is not False):
            raise ValueError('Only validated DAQ configuration is supported')


@dataclass(frozen=True)
class LocalizationSpec:
    rough_start_xy: tuple[float, float]
    bounds: StageBounds  # Operator-reviewed complete approach/scan/return envelope.
    side_um: float = 500.
    scan_margin_um: float = 100.
    step_um: float = 10.
    width_tolerance_um: float = 100.
    profile_count: int = 5
    supported_rotation_deg: float = 5.
    center_uncertainty_um: float = 20.
    boundary_guard_um: float = 10.
    minimum_profiles: int = 3
    required_y_span_um: float = 100.
    resolution_um: float = 1.
    position_tolerance_um: float = 1.
    settling_s: float = .1
    polling_s: float = .01
    movement_timeout_s: float = 5.
    readback_timeout_s: float = 2.
    daq_timeout_s: float = 2.
    stop_timeout_s: float = 2.
    success_only_return: bool = True
    daq: DaqSettings = DaqSettings()

    def __post_init__(self):
        numbers = (*self.rough_start_xy, self.side_um, self.scan_margin_um, self.step_um,
            self.width_tolerance_um, self.supported_rotation_deg, self.center_uncertainty_um,
            self.boundary_guard_um, self.required_y_span_um, self.resolution_um,
            self.position_tolerance_um, self.settling_s, self.polling_s,
            self.movement_timeout_s, self.readback_timeout_s, self.daq_timeout_s, self.stop_timeout_s)
        if len(self.rough_start_xy) != 2 or not all(isfinite(v) for v in numbers):
            raise ValueError('nonfinite_spec')
        if (min(self.side_um, self.scan_margin_um, self.step_um, self.width_tolerance_um,
                self.required_y_span_um, self.polling_s, self.movement_timeout_s,
                self.daq_timeout_s, self.stop_timeout_s) <= 0
                or not 0 <= self.supported_rotation_deg < 45
                or min(self.center_uncertainty_um, self.boundary_guard_um, self.position_tolerance_um) < 0
                or not 0 <= self.settling_s < self.readback_timeout_s
                or self.resolution_um != 1 or type(self.success_only_return) is not bool
                or type(self.profile_count) is not int or type(self.minimum_profiles) is not int
                or self.minimum_profiles < 3 or self.profile_count < self.minimum_profiles
                or self.required_y_span_um < 100):
            raise ValueError('invalid_spec_or_insufficient_production_leverage')
        if not self.bounds.contains(self.rough_start_xy) or any(v != round(v) for v in self.rough_start_xy):
            raise ValueError('rough_start_must_be_exact_integral_and_in_bounds')
        self.scan('x', self.rough_start_xy[0], self.rough_start_xy[1]).positions()
        self.scan('y', self.rough_start_xy[1], self.rough_start_xy[0]).positions()
        plan_profiles(self, self.rough_start_xy)

    def scan(self, axis, center, fixed):
        half = self.side_um / 2 + self.scan_margin_um
        result = ScanSettings(axis, round(center-half), round(center+half), self.step_um,
            round(fixed), self.bounds, movement_timeout_s=self.movement_timeout_s,
            settling_s=self.settling_s, settling_timeout_s=self.readback_timeout_s,
            read_timeout_s=self.daq_timeout_s, stop_timeout_s=self.stop_timeout_s,
            poll_interval_s=self.polling_s, position_tolerance_um=self.position_tolerance_um)
        if any(any(v != round(v) for v in xy) for xy in result.positions()):
            raise ValueError('nonintegral_scan_target')
        return result


def plan_profiles(spec, center):
    # For 0 <= |theta| < 45 degrees, cos(theta)-sin(theta) decreases
    # monotonically. Therefore the interval minimum is at its largest |theta|.
    theta = radians(spec.supported_rotation_deg)
    half = spec.side_um/2*(cos(theta)-sin(theta)) - spec.boundary_guard_um - spec.center_uncertainty_um
    if half <= 0:
        raise ValueError('no_guarded_central_interval')
    # Rounding out of the reviewed interval is not silently accepted or expanded.
    from math import floor
    anchor = round(center[1])
    half_grid = floor((half-abs(anchor-center[1]))/spec.resolution_um)*spec.resolution_um
    ys = tuple(round(anchor-half_grid+2*half_grid*i/(spec.profile_count-1))
               for i in range(spec.profile_count))
    if (len(set(ys)) < spec.minimum_profiles or len(set(ys)) != spec.profile_count
            or max(ys)-min(ys) < spec.required_y_span_um
            or any(abs(y-center[1]) > half for y in ys)):
        raise ValueError('rounded_profile_leverage_or_guard_failure')
    for y in ys:
        spec.scan('x', center[0], y).positions()
    return ys


class BorrowedStageProxy:
    """PriorStageAdapter runs on the reviewed executor, never an arbitrary caller."""
    def __init__(self, bridge, handle, spec, clock):
        self.bridge, self.handle = bridge, handle
        self.adapter = bridge.stage_interface(handle, bounds=spec.bounds,
            polling_s=spec.polling_s, clock=clock)
        self.stop_attempted = False
        self.stop_ok = False

    def _call(self, name, args, timeout_s, cleanup=False):
        return self.adapter._call(name, args, timeout_s, cleanup=cleanup)

    def move_to(self, x, y, *, timeout_s):
        return self._call('move_to', (x, y), timeout_s)

    def get_position(self, *, timeout_s):
        return self._call('get_position', (), timeout_s)

    def is_busy(self, *, timeout_s):
        return self._call('is_busy', (), timeout_s)

    def stop(self, *, timeout_s):
        if not self.bridge.movement_attempted:
            return
        if self.stop_attempted:
            if not self.stop_ok:
                raise RuntimeError('prior_stop_failed_no_retry')
            return
        self.stop_attempted = True
        self._call('stop', (), timeout_s, cleanup=True)
        self.stop_ok = True


class LocalizationPipelineServices:
    """M8.2a service implementation; injected DAQ factory has no live default.

    Factory receives the frozen DAQ settings and must return an owned object
    with acquire_bounded and clear(). Tests supply numerical fakes only.
    """
    def __init__(self, bridge, handle, spec, output_dir, daq_factory, *, clock=time):
        self.bridge, self.handle, self.spec = bridge, handle, spec
        self.clock, self.daq_factory = clock, daq_factory
        self.path = Path(output_dir) / handle.run_id
        self.stage = BorrowedStageProxy(bridge, handle, spec, clock)
        self.task = None
        self.reader = None
        self.journals = []
        self.diagnostics = {}
        self.phase = 'not_started'

    @property
    def movement_attempted(self):
        return self.bridge.movement_attempted

    def prepare(self, settings):
        if settings.context.frame_id != self.spec.bounds.frame_id or not settings.context.marker_id:
            raise ValueError('frame_or_marker_not_confirmed')
        if settings.context.orientation is not Orientation.FLIP_X:
            raise ValueError('existing_Module7_bridge_supports_FLIP_X_only')
        self._start_gate()
        self.path.mkdir()  # Parent must exist; never overwrite prior journals.
        (self.path/'run.json').write_text(json.dumps(dict(run_id=self.handle.run_id,
            context=asdict(settings.context), generation=settings.context_generation,
            spec=asdict(self.spec)), default=lambda v: v.value, indent=2), encoding='utf-8')
        self.task = self.daq_factory(self.spec.daq)
        if self.bridge.daq.task is not self.task or self.bridge.daq.run_id != self.handle.run_id:
            self.bridge.claim_daq(self.handle, self.task, reset=self.spec.daq.reset)
        self.reader = NIReflectionReader(self.task, sample_number=self.spec.daq.samples,
            channel_limits=((-self.spec.daq.clipping_v, self.spec.daq.clipping_v),)*2, clock=self.clock)
        self._start_gate()

    def _start_gate(self):
        timeout = self.spec.readback_timeout_s
        if self.stage.is_busy(timeout_s=timeout):
            raise ValueError('initial_stage_busy')
        if self.stage.get_position(timeout_s=timeout) != self.spec.rough_start_xy:
            raise ValueError('initial_exact_position_mismatch')

    def _phase(self, name, checkpoint, progress, **data):
        checkpoint()
        self.phase = name
        self.diagnostics.update(data)
        progress(dict(phase=name, **data))

    def _scan(self, name, settings, checkpoint, progress):
        self._phase(name, checkpoint, progress, geometry=asdict(settings))
        path = self.path/(name+'.jsonl')
        def cancelled():
            checkpoint()
            return False
        result = scan_1d(settings, self.stage, self.reader, output_path=path,
                         cancelled=cancelled, clock=self.clock)
        checkpoint()
        saved = load_scan(path)
        if (result.status is not ScanStatus.COMPLETED or saved.status is not ScanStatus.COMPLETED
                or result.reasons or saved.reasons or saved.settings != settings
                or saved.points != result.points or len(saved.points) != len(settings.positions())
                or any(p.measured_um is None for p in saved.points)):
            raise ValueError('scan_or_journal_failed:' + name + ':' + repr(result.reasons))
        edge = analyze_scan(saved, EdgeSettings(expected_width_um=self.spec.side_um,
            width_tolerance_um=self.spec.width_tolerance_um))
        if not edge.valid:
            raise ValueError('edge_failed:' + name + ':' + repr(edge.reasons))
        self.journals.append(path)
        progress(dict(profile_completed=name, journal=str(path), edge=asdict(edge)))
        checkpoint()
        return saved, edge

    def work(self, settings, checkpoint, progress):
        x, y = self.spec.rough_start_xy
        progress(dict(rough_start=self.spec.rough_start_xy, profile_count=self.spec.profile_count))
        _, he = self._scan('initial_H', self.spec.scan('x', x, y), checkpoint, progress)
        vertical, ve = self._scan('initial_V', self.spec.scan('y', y, round(he.midpoint_um)), checkpoint, progress)
        initial = (he.midpoint_um, ve.midpoint_um)
        self._phase('planning', checkpoint, progress, initial_center=initial)
        ys = plan_profiles(self.spec, initial)
        rows = []
        for i, measured_y in enumerate(ys, 1):
            scan, edge = self._scan(f'P{i}', self.spec.scan('x', initial[0], measured_y), checkpoint, progress)
            measured = [p.measured_um[1] for p in scan.points]
            if max(measured)-min(measured) > self.spec.position_tolerance_um:
                raise ValueError('profile_measured_Y_unstable')
            rows.append(ProfileGeometry(f'P{i}', mean(measured), edge.left_edge_um,
                edge.right_edge_um, edge.midpoint_um, edge.width_um, edge.valid))
        self._phase('classification', checkpoint, progress)
        classified = classify_profiles(rows, initial[1], ClassificationSettings(side_um=self.spec.side_um))
        if not classified.sufficient_for_rotation_fit or classified.usable_final_fits is None:
            raise ValueError('classification_failed:' + repr(classified.reasons))
        central = tuple(row.profile for row in classified.profiles if row.classification is ProfileClass.CENTRAL)
        self._phase('rotation', checkpoint, progress,
            classification={row.profile.identifier: row.classification.value for row in classified.profiles})
        rotation = fit_rotation(classified, central)
        if not rotation.valid or rotation.accepted_theta_deg is None:
            raise ValueError('rotation_failed:' + repr(rotation.reasons))
        if abs(rotation.accepted_theta_deg) > self.spec.supported_rotation_deg:
            raise ValueError('rotation_outside_reviewed_range')
        self._phase('center', checkpoint, progress, accepted_rotation=rotation.accepted_theta_deg,
                    warnings=rotation.warnings)
        center = refine_marker_center(rotation, vertical,
            CenterRefinementSettings(side_um=self.spec.side_um), initial_center_um=initial)
        if not center.valid:
            raise ValueError('center_failed:' + repr(center.reasons))
        self._phase('registration', checkpoint, progress,
                    refined_center=(center.x_center_stage_um, center.y_center_stage_um))
        build_stage_registration(rotation, center)
        evidence = RegistrationEvidence(settings.context, classified, rotation, center,
            tuple((str(p), sha256(p.read_bytes()).hexdigest()) for p in self.journals))
        if self.spec.success_only_return:
            self._phase('return', checkpoint, progress)
            self._return(checkpoint)
        checkpoint()
        return evidence

    def _return(self, checkpoint):
        target = self.spec.rough_start_xy
        if not self.spec.bounds.contains(target):
            raise ValueError('return_outside_bounds')
        checkpoint()
        deadline = self.clock.monotonic()+self.spec.movement_timeout_s
        self.stage.move_to(*target, timeout_s=self.spec.movement_timeout_s)
        if self.clock.monotonic() >= deadline:
            raise TimeoutError('return_move_exceeded_deadline')
        while self.stage.is_busy(timeout_s=max(1e-9, deadline-self.clock.monotonic())):
            checkpoint()
            if self.clock.monotonic() >= deadline:
                raise TimeoutError('return_motion_timeout')
            self.clock.sleep(self.spec.polling_s)
        deadline = self.clock.monotonic()+self.spec.readback_timeout_s
        idle_since = self.clock.monotonic()
        while True:
            checkpoint()
            if self.clock.monotonic() >= deadline:
                raise TimeoutError('return_settling_timeout')
            if self.stage.is_busy(timeout_s=deadline-self.clock.monotonic()):
                idle_since = None
            else:
                if idle_since is None:
                    idle_since = self.clock.monotonic()
                if self.clock.monotonic()-idle_since >= self.spec.settling_s:
                    break
            self.clock.sleep(self.spec.polling_s)
        if self.clock.monotonic() >= deadline:
            raise TimeoutError('return_readback_timeout')
        actual = self.stage.get_position(timeout_s=max(1e-9, deadline-self.clock.monotonic()))
        checkpoint()
        if not self.spec.bounds.contains(actual) or hypot(actual[0]-target[0], actual[1]-target[1]) > self.spec.position_tolerance_um:
            raise ValueError('return_readback_failed')

    def protective_stop(self):
        self.stage.stop(timeout_s=self.spec.stop_timeout_s)
        return True

    def release_daq(self):
        if self.task is None:
            return True
        try:
            self.task.clear()
        except Exception:
            if self.bridge.daq.run_id == self.handle.run_id:
                self.bridge.release_daq(self.handle, False)
            raise
        if self.bridge.daq.run_id == self.handle.run_id:
            return self.bridge.release_daq(self.handle, True)
        return True

    def confirm_idle(self):
        return not self.stage._call('is_busy', (), self.spec.readback_timeout_s, cleanup=True)
