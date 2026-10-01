"""Supervised H/V/profiles/classification only; no production rotation or publication."""
from dataclasses import dataclass, fields, asdict
from statistics import mean

from experiment.marker_profile_classification import (
    ClassificationSettings, ProfileGeometry, ProfileClass, classify_profiles,
)
from ui.runtime_provenance import breadcrumb
from ui.hv_validation import HVSpec, HVConfirmation, HVServices
from ui.localization_pipeline import LocalizationSpec, plan_profiles


def clearance_rectangle(rough, side, margin):
    """Conservative possible paths, not physical travel limits or clearance proof.

    Initial midpoints may lie anywhere inside their initial scan ranges. Later
    X scans extend one further half-scan about measured X. The planner's Y
    half-span is always < S/2. One um covers rounding and one readback padding.
    """
    half = side/2 + margin
    x, y = rough
    return (x-2*half-1, x+2*half+1, y-half-side/2-1, y+half+side/2+1)


@dataclass(frozen=True)
class MultiHSpec(HVSpec):
    profile_count: int = 5
    supported_rotation_deg: float = 5.
    center_uncertainty_um: float = 20.
    boundary_guard_um: float = 10.
    minimum_profiles: int = 3
    required_y_span_um: float = 100.
    resolution_um: float = 1.

    def __post_init__(self):
        super().__post_init__()
        self.planning_spec()  # Reuse existing numerical/planning validation.
        xmin, xmax, ymin, ymax = clearance_rectangle(
            self.rough_start_xy, self.side_um, self.scan_margin_um)
        if not all(self.bounds.contains((x,y)) for x in (xmin,xmax) for y in (ymin,ymax)):
            raise ValueError('multi_H_full_possible_envelope_outside_clearance')

    def planning_spec(self):
        return LocalizationSpec(**{f.name:getattr(self,f.name)
            for f in fields(LocalizationSpec) if hasattr(self,f.name)})

    def plan(self, center):
        planning = self.planning_spec()
        ys = plan_profiles(planning, center)
        scans = tuple(planning.scan('x', center[0], y) for y in ys)
        for scan in scans:
            scan.positions()  # Recheck complete final measured-center-derived paths.
        return ys, scans


@dataclass(frozen=True)
class MultiHConfirmation(HVConfirmation):
    multi_profile_clearance: bool = False

    def validate(self, context, laser):
        super().validate(context, laser)
        if self.multi_profile_clearance is not True:
            raise ValueError('multi_H_requires_separate_full_sequence_clearance')


class MultiHServices(HVServices):
    def prepare(self, settings):
        if (not isinstance(self.spec, MultiHSpec)
                or not isinstance(self.confirmation, MultiHConfirmation)
                or settings.purpose != 'multi_h'):
            raise ValueError('multi_H_spec_confirmation_and_purpose_required')
        super().prepare(settings)

    def work(self, settings, checkpoint, progress):
        center = self.acquire_initial_center(checkpoint, progress)
        self._phase('profile_planning', checkpoint, progress)
        breadcrumb(self, 'planner_enter')
        ys, scans = self.spec.plan(center)
        self.report.update(planned_profile_y=ys, profile_count=len(ys), profiles=[])
        progress(dict(initial_center=center, planned_profile_y=ys,
                      profile_geometry=[asdict(s) for s in scans]))
        rows = []
        for index, scan_settings in enumerate(scans, 1):
            checkpoint()
            name = f'profile_H_{index:02d}'
            progress(dict(profile_index=index, profile_total=len(scans)))
            # Completed acquisition with invalid optical edges is classifier input,
            # not an acquisition failure. Never remove, replace or retry a profile.
            scan, edge = self._scan(name, scan_settings, checkpoint, progress,
                                   require_valid_edges=False)
            measured_y = [p.measured_um[1] for p in scan.points]
            stable = max(measured_y)-min(measured_y) <= self.spec.position_tolerance_um
            row = ProfileGeometry(name, mean(measured_y), edge.left_edge_um,
                edge.right_edge_um, edge.midpoint_um, edge.width_um, edge.valid and stable)
            rows.append(row)
            diagnostic = dict(index=index, identifier=name, fixed_y=scan_settings.fixed_um,
                measured_y=row.measured_y_um, measured_y_range=(min(measured_y),max(measured_y)),
                left=edge.left_edge_um, right=edge.right_edge_um, midpoint=edge.midpoint_um,
                width=edge.width_um, contrast=edge.contrast, noise=edge.noise,
                edge_valid=edge.valid, edge_reasons=edge.reasons, measured_y_stable=stable,
                journal=str(self.journals[-1]), edge_diagnostics=asdict(edge))
            self.report['profiles'].append(diagnostic)
            progress(dict(profile_result=diagnostic))
            checkpoint()
        self._phase('profile_classification', checkpoint, progress)
        breadcrumb(self, 'classifier_enter')
        classified = classify_profiles(tuple(rows), center[1],
            ClassificationSettings(side_um=self.spec.side_um))
        by_id = {row.profile.identifier:row for row in classified.profiles}
        for diagnostic in self.report['profiles']:
            row = by_id[diagnostic['identifier']]
            diagnostic.update(classification=row.classification.value,
                              classification_reasons=row.reasons)
        accepted = [r.profile for r in classified.profiles if r.classification is ProfileClass.CENTRAL]
        span = max(p.measured_y_um for p in accepted)-min(p.measured_y_um for p in accepted) if accepted else 0.
        reasons = list(classified.reasons)
        if len(accepted) < self.spec.minimum_profiles:
            reasons.append('insufficient_accepted_profile_count')
        if span < self.spec.required_y_span_um:
            reasons.append('insufficient_accepted_Y_span')
        ready = (classified.sufficient_for_rotation_fit and classified.usable_final_fits is not None
                 and not reasons)
        if not ready and not reasons:
            reasons.append('classifier_not_sufficient')
        self.report.update(central_ids=classified.central_identifiers, central_count=len(accepted),
            accepted_y_span_um=span,
            other_profile_ids=tuple(r.profile.identifier for r in classified.profiles
                                   if r.classification is not ProfileClass.CENTRAL),
            sufficient_for_rotation_fit=classified.sufficient_for_rotation_fit,
            usable_final_fits_available=classified.usable_final_fits is not None,
            classifier_reasons=classified.reasons,
            classifier_warnings=(),  # Current classifier has reasons, no warning field.
            supervised_reasons=tuple(reasons), ready_for_rotation_fit=ready,
            production_rotation_executed=False, registration_published=False)
        # Do not expose classifier provisional/QC slopes as accepted rotation.
        progress(dict(classification_report=self.report.copy()))
        checkpoint()
        if not ready:
            raise ValueError('multi_H_classification_failed:'+repr(tuple(reasons)))
        self._phase('success_only_return', checkpoint, progress)
        self.report['return_status'] = 'FAILED_OR_INCOMPLETE'
        self._return(checkpoint)
        self.report['return_status'] = 'PASS'
        return self.report.copy()
