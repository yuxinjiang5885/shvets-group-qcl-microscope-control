"""Offline rotation from the complete classifier-approved CENTRAL set.

No trimming or subset search. Angles/lines on invalid results are diagnostics
only; accepted_theta_deg is the production output and is None on every failure.
OLS standard errors assume independent, equal-variance X errors and exact Y.
They exclude stage calibration, edge bias, Y error, drift and selection effects.
The midpoint line defines the effective rigid-body marker rotation for this
registration workflow, even when sides are mildly nonparallel. Fabrication
geometry, edge roughness, optical edge bias or noise may contribute; a side
disagreement warning identifies none of these causes. It only reports that
independent side angles differ beyond the nominal parallelism threshold.
"""
from dataclasses import dataclass
from math import atan, degrees, fsum, isfinite, sqrt
from statistics import stdev

from experiment.marker_profile_classification import (
    ClassificationResult, ProfileClass, ProfileGeometry,
)


@dataclass(frozen=True)
class RotationSettings:
    """Independent, provisional production-QC defaults; not calibrated uncertainty.

    100 um requires a longer baseline than classifier screening (40 um).
    Side parallelism warns above 0.25 deg and fails above 1.0 deg. The 1/2 um
    residual limits and 5 um width variation are conservative engineering
    acceptance budgets, not measured accuracy or statistical confidence limits.
    Each residual limit applies independently to left, right and midpoint.
    """
    minimum_profiles: int = 3
    minimum_y_span_um: float = 100.0
    warning_left_right_angle_disagreement_deg: float = 0.25
    hard_max_left_right_angle_disagreement_deg: float = 1.0
    max_rms_residual_um: float = 1.0
    max_abs_residual_um: float = 2.0
    max_width_peak_to_peak_um: float | None = 5.0
    geometry_tolerance_um: float = 1e-6

    def __post_init__(self):
        if (type(self.minimum_profiles) is not int or self.minimum_profiles < 3):
            raise ValueError('minimum_profiles must be an integer >= 3')
        for name, value in vars(self).items():
            if name == 'minimum_profiles':
                continue
            if name == 'max_width_peak_to_peak_um' and value is None:
                continue
            if not _finite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.warning_left_right_angle_disagreement_deg > self.hard_max_left_right_angle_disagreement_deg:
            raise ValueError('Side warning threshold must not exceed hard limit')


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


@dataclass(frozen=True)
class RotationLineFit:
    y_ref_um: float
    intercept_um: float
    slope: float
    slope_standard_error: float
    rms_residual_um: float
    max_abs_residual_um: float
    residuals_um: tuple[float, ...]  # Same order as used_profile_ids.


@dataclass(frozen=True)
class RotationProfileDiagnostic:
    identifier: str
    measured_y_um: float
    width_um: float
    left_residual_um: float
    right_residual_um: float
    midpoint_residual_um: float


@dataclass(frozen=True)
class RotationFitResult:
    """Only accepted_theta_deg is usable; reasons invalidate, warnings do not.

    Side fits remain diagnostics even on valid results. Warnings may coexist
    with hard failures, and never override those failures.
    """
    valid: bool
    reasons: tuple[str, ...]
    used_profile_ids: tuple[str, ...] = ()
    used_profile_count: int = 0
    measured_y_span_um: float | None = None
    left_fit: RotationLineFit | None = None
    right_fit: RotationLineFit | None = None
    midpoint_fit: RotationLineFit | None = None
    theta_left_deg: float | None = None
    theta_right_deg: float | None = None
    theta_mid_deg: float | None = None
    theta_mid_standard_error_deg: float | None = None
    left_right_angle_disagreement_deg: float | None = None
    width_mean_um: float | None = None
    width_std_um: float | None = None  # Sample standard deviation (ddof=1).
    width_min_um: float | None = None
    width_max_um: float | None = None
    width_peak_to_peak_um: float | None = None
    per_profile: tuple[RotationProfileDiagnostic, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def accepted_theta_deg(self):
        return self.theta_mid_deg if self.valid else None

    @property
    def diagnostic_only(self):
        return not self.valid

    @property
    def left_rms_residual_um(self):
        return self.left_fit.rms_residual_um if self.left_fit else None

    @property
    def right_rms_residual_um(self):
        return self.right_fit.rms_residual_um if self.right_fit else None

    @property
    def midpoint_rms_residual_um(self):
        return self.midpoint_fit.rms_residual_um if self.midpoint_fit else None

    @property
    def left_max_abs_residual_um(self):
        return self.left_fit.max_abs_residual_um if self.left_fit else None

    @property
    def right_max_abs_residual_um(self):
        return self.right_fit.max_abs_residual_um if self.right_fit else None

    @property
    def midpoint_max_abs_residual_um(self):
        return self.midpoint_fit.max_abs_residual_um if self.midpoint_fit else None


def _fit_line(xs, ys):
    # Center both coordinates before products; fsum limits cancellation.
    n = len(xs)
    y_ref, x_ref = fsum(ys) / n, fsum(xs) / n
    dy = [y - y_ref for y in ys]
    dx = [x - x_ref for x in xs]
    dy_mean, dx_mean = fsum(dy) / n, fsum(dx) / n
    s_yy = fsum((y-dy_mean)**2 for y in dy)
    slope = fsum((y-dy_mean)*(x-dx_mean) for x, y in zip(dx, dy)) / s_yy
    offset = dx_mean - slope * dy_mean
    residuals = tuple(x - (offset + slope*y) for x, y in zip(dx, dy))
    sse = fsum(r*r for r in residuals)
    return RotationLineFit(y_ref, x_ref + offset, slope,
                           sqrt(sse / (n-2) / s_yy), sqrt(sse/n),
                           max(map(abs, residuals)), residuals)


def fit_rotation(classification: ClassificationResult,
                 central_profiles: tuple[ProfileGeometry, ...],
                 settings=RotationSettings()) -> RotationFitResult:
    """Fit exactly the complete accepted set, never a caller-chosen subset.

    Caller supplies the classifier result and all its CENTRAL ProfileGeometry
    records. Equality with those records protects against stale/altered inputs.
    This is an API consistency gate, not authentication of fabricated results.
    Classifier QC lines are checked for availability, but not reused as the
    production regression: the new reference is the accepted measured-Y mean.
    """
    reasons = []
    if classification.sufficient_for_rotation_fit is not True:
        reasons.append('classifier_not_sufficient')
    if classification.usable_final_fits is None:
        reasons.append('classifier_fits_unavailable')
    elif len(classification.usable_final_fits) != 3:
        reasons.append('invalid_classifier_fits')
    if classification.reasons:
        reasons.append('classifier_has_failure_reasons')
    if reasons:
        return RotationFitResult(False, tuple(reasons))
    profiles = tuple(central_profiles)
    ids = [p.identifier for p in profiles]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        return RotationFitResult(False, ('invalid_profile_identifiers',))
    rows = classification.profiles
    if len({r.profile.identifier for r in rows}) != len(rows):
        return RotationFitResult(False, ('invalid_classifier_identifiers',))
    expected = {r.profile.identifier: r.profile for r in rows
                if r.classification is ProfileClass.CENTRAL}
    if set(ids) != set(expected) or any(p != expected[p.identifier] for p in profiles):
        return RotationFitResult(False, ('central_set_mismatch',))
    if any(r.reasons for r in rows if r.classification is ProfileClass.CENTRAL):
        return RotationFitResult(False, ('central_profile_has_failure_reasons',))
    for p in profiles:
        values = (p.measured_y_um, p.left_edge_um, p.right_edge_um, p.midpoint_um, p.width_um)
        if (p.edge_valid is not True or not all(_finite(v) for v in values)
                or p.right_edge_um <= p.left_edge_um
                or abs(p.width_um-(p.right_edge_um-p.left_edge_um)) > settings.geometry_tolerance_um
                or abs(p.midpoint_um-(p.left_edge_um+p.right_edge_um)/2) > settings.geometry_tolerance_um):
            return RotationFitResult(False, ('invalid_profile_geometry',))
    profiles = tuple(sorted(profiles, key=lambda p: (p.measured_y_um, p.identifier)))
    ids = tuple(p.identifier for p in profiles)
    ys = tuple(p.measured_y_um for p in profiles)
    span = max(ys)-min(ys) if ys else 0.0
    if len(profiles) < settings.minimum_profiles:
        reasons.append('insufficient_central_profiles')
    if len(set(ys)) < 2:
        reasons.append('insufficient_distinct_y')
    if span < settings.minimum_y_span_um:
        reasons.append('insufficient_y_span')
    if reasons:
        return RotationFitResult(False, tuple(reasons), ids, len(ids), span)
    try:
        fits = tuple(_fit_line(tuple(getattr(p, field) for p in profiles), ys)
                     for field in ('left_edge_um', 'right_edge_um', 'midpoint_um'))
        widths = tuple(p.width_um for p in profiles)
        width_mean, width_std = fsum(widths)/len(widths), stdev(widths)
        if not all(isfinite(v) for f in fits for v in
                   (f.y_ref_um, f.intercept_um, f.slope, f.slope_standard_error,
                    f.rms_residual_um, f.max_abs_residual_um, *f.residuals_um)):
            raise ArithmeticError('Nonfinite fit')
        if not all(isfinite(v) for v in (span, width_mean, width_std)):
            raise ArithmeticError('Nonfinite summary')
    except (ArithmeticError, ValueError):
        return RotationFitResult(False, ('numerical_fit_failure',), ids, len(ids), span)
    angles = tuple(-degrees(atan(f.slope)) for f in fits)
    angular_se = degrees(fits[2].slope_standard_error / (1 + fits[2].slope**2))
    disagreement = abs(angles[0]-angles[1])
    # Preserve the classifier's side-identification branch; never reinterpret
    # an accepted set as a different pair of square sides.
    if any(abs(a) >= 45 for a in angles):
        reasons.append('outside_small_angle_branch')
    warnings = []
    # Equality is accepted at both boundaries. Above the hard limit, retain
    # the side warning as well as the distinct hard-failure reason.
    if disagreement > settings.warning_left_right_angle_disagreement_deg:
        warnings.append('left_right_angle_disagreement_warning')
    if disagreement > settings.hard_max_left_right_angle_disagreement_deg:
        reasons.append('excessive_left_right_angle_disagreement')
    for name, fit in zip(('left', 'right', 'midpoint'), fits):
        if fit.rms_residual_um > settings.max_rms_residual_um:
            reasons.append(name + '_rms_residual_exceeded')
        if fit.max_abs_residual_um > settings.max_abs_residual_um:
            reasons.append(name + '_max_residual_exceeded')
    width_range = max(widths)-min(widths)
    if settings.max_width_peak_to_peak_um is not None and width_range > settings.max_width_peak_to_peak_um:
        reasons.append('width_variation_exceeded')
    diagnostics = tuple(RotationProfileDiagnostic(
        p.identifier, p.measured_y_um, p.width_um,
        *(f.residuals_um[i] for f in fits)) for i, p in enumerate(profiles))
    return RotationFitResult(
        valid=not reasons, reasons=tuple(reasons), used_profile_ids=ids,
        used_profile_count=len(ids), measured_y_span_um=span,
        left_fit=fits[0], right_fit=fits[1], midpoint_fit=fits[2],
        theta_left_deg=angles[0], theta_right_deg=angles[1], theta_mid_deg=angles[2],
        theta_mid_standard_error_deg=angular_se,
        left_right_angle_disagreement_deg=disagreement, width_mean_um=width_mean,
        width_std_um=width_std, width_min_um=min(widths), width_max_um=max(widths),
        width_peak_to_peak_um=width_range, per_profile=diagnostics,
        warnings=tuple(warnings))
