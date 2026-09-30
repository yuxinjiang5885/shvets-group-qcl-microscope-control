"""Offline intersection of horizontal/vertical square-center lines.

No horizontal reselection or regression. Coordinates remain in the measured
stage frame (Module 5 angle convention); no registration object is created.
Angle-fit sensitivity is not calibrated physical uncertainty: it omits slope/
intercept covariance, vertical-edge uncertainty, stage calibration, optical
bias, classification selection, drift and systematic effects.
"""
from dataclasses import dataclass
from math import cos, sin, tan, radians, fsum, hypot, isfinite

from experiment.marker_rotation import RotationFitResult, RotationLineFit
from experiment.reflection_analysis import EdgeResult, EdgeSettings, analyze_scan
from experiment.scan_1d import ScanResult, ScanStatus


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


@dataclass(frozen=True)
class CenterRefinementSettings:
    """Provisional engineering QC, not calibrated physical uncertainty.

    1 um X stability follows the acquisition readback budget. Chord error 20 um
    is a 4% square-size allowance; the 10 um guard conservatively excludes
    corner transitions. 1e-6 um checks algebra/geometry consistency only.
    Edge extraction retains the reviewed 500 +/-100 um default search window.
    """
    side_um: float = 500.0
    max_vertical_x_spread_um: float = 1.0
    max_chord_height_error_um: float = 20.0
    boundary_guard_um: float = 10.0
    constraint_tolerance_um: float = 1e-6
    edge_width_tolerance_um: float = 100.0
    slope_consistency_tolerance: float = 1e-12

    def __post_init__(self):
        for name, value in vars(self).items():
            if not _finite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.boundary_guard_um >= self.side_um / 2:
            raise ValueError('Guard must be smaller than half the side')


@dataclass(frozen=True)
class AngleSensitivity:
    """Fixed (a_mid, y_ref, x_v, y_v); line pivots about (a_mid, y_ref).

    This deliberately changes slope with angle, not the measured line anchor.
    It is NOT a covariance-aware propagation or a QC-approved alternate fit.
    """
    theta_deg: float
    delta_x_um: float
    delta_y_um: float


@dataclass(frozen=True)
class CenterRefinementResult:
    """Center fields are None on every hard failure; QC diagnostics remain."""
    valid: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    x_center_stage_um: float | None = None
    y_center_stage_um: float | None = None
    accepted_theta_deg: float | None = None
    horizontal_midpoint_fit: RotationLineFit | None = None
    horizontal_reference_y_um: float | None = None
    vertical_scan_x_um: float | None = None
    vertical_scan_x_min_um: float | None = None
    vertical_scan_x_max_um: float | None = None
    vertical_scan_x_spread_um: float | None = None
    vertical_edges: EdgeResult | None = None
    vertical_lower_edge_um: float | None = None
    vertical_upper_edge_um: float | None = None
    vertical_midpoint_um: float | None = None
    vertical_chord_height_um: float | None = None
    expected_vertical_chord_height_um: float | None = None
    chord_height_error_um: float | None = None
    vertical_offset_from_center_um: float | None = None
    vertical_central_half_width_um: float | None = None
    vertical_outer_half_width_um: float | None = None
    guarded_vertical_half_width_um: float | None = None
    horizontal_constraint_residual_um: float | None = None
    vertical_constraint_residual_um: float | None = None
    initial_center_um: tuple[float, float] | None = None
    center_correction_from_initial_x_um: float | None = None
    center_correction_from_initial_y_um: float | None = None
    total_correction_um: float | None = None
    angle_minus_se: AngleSensitivity | None = None
    angle_plus_se: AngleSensitivity | None = None


def _intersection(a, y_ref, x_v, y_v, theta):
    # [1,t; -t,1] [xc,yc] = [K,L], det=1+t*t,
    # K=a+t*y_ref, L=y_v-t*x_v. These are the measured square-center lines.
    # Solve translated about (a,y_ref) to avoid large K/L cancellation:
    t = tan(radians(theta))
    dy = ((y_v-y_ref) - t*(x_v-a)) / (1+t*t)
    return a-t*dy, y_ref+dy


def refine_marker_center(rotation_result: RotationFitResult,
                         vertical_profile: ScanResult,
                         settings=CenterRefinementSettings(), *,
                         initial_center_um=None) -> CenterRefinementResult:
    """Consume approved midpoint rotation and reanalyze a complete measured Y scan.

    No replacement-angle argument. Initial center is optional comparison-only,
    never used to solve or select the center. Point ordering is preserved for
    edge detection (monotonic forward/reverse accepted, shuffled rejected).
    Exact guarded boundary is excluded. Other maximum limits accept equality.
    """
    r = rotation_result
    data = {'warnings': r.warnings}

    def fail(*reasons):
        return CenterRefinementResult(False, tuple(reasons), **data)

    if r.valid is not True or r.reasons or r.diagnostic_only:
        return fail('rotation_not_accepted')
    theta, fit, se = r.accepted_theta_deg, r.midpoint_fit, r.theta_mid_standard_error_deg
    if not _finite(theta):
        return fail('missing_or_invalid_accepted_angle')
    if fit is None or not all(_finite(v) for v in vars(fit).values() if not isinstance(v, tuple)):
        return fail('missing_or_invalid_midpoint_fit')
    if not _finite(se) or se < 0:
        return fail('invalid_angle_standard_error')
    if abs(theta) >= 45:
        return fail('outside_small_angle_branch')
    t = tan(radians(theta))
    if abs(fit.slope+t) > settings.slope_consistency_tolerance:
        return fail('midpoint_angle_slope_mismatch')
    data.update(accepted_theta_deg=theta, horizontal_midpoint_fit=fit,
                horizontal_reference_y_um=fit.y_ref_um)
    if initial_center_um is not None:
        if (not isinstance(initial_center_um, (tuple, list)) or len(initial_center_um) != 2
                or not all(_finite(v) for v in initial_center_um)):
            return fail('invalid_initial_center')
        data['initial_center_um'] = tuple(initial_center_um)
    scan = vertical_profile
    if scan.settings.axis != 'y':
        return fail('not_vertical_scan')
    if scan.status != ScanStatus.COMPLETED or scan.reasons:
        return fail('incomplete_vertical_scan')
    if not scan.points or any(p.measured_um is None or len(p.measured_um) != 2
                             or not all(_finite(v) for v in p.measured_um) for p in scan.points):
        return fail('invalid_vertical_readback')
    xs = [p.measured_um[0] for p in scan.points]
    x_v = fsum(xs)/len(xs)
    spread = max(xs)-min(xs)
    data.update(vertical_scan_x_um=x_v, vertical_scan_x_min_um=min(xs),
                vertical_scan_x_max_um=max(xs), vertical_scan_x_spread_um=spread)
    if spread > settings.max_vertical_x_spread_um:
        return fail('vertical_x_spread_exceeded')
    edges = analyze_scan(scan, EdgeSettings(expected_width_um=settings.side_um,
                                          width_tolerance_um=settings.edge_width_tolerance_um))
    data['vertical_edges'] = edges
    if not edges.valid or edges.reasons or edges.position_source != 'measured':
        return fail('invalid_vertical_edges', *edges.reasons)
    lo, hi, y_v, height = edges.left_edge_um, edges.right_edge_um, edges.midpoint_um, edges.width_um
    if (not all(_finite(v) for v in (lo, hi, y_v, height)) or hi <= lo
            or abs(height-(hi-lo)) > settings.constraint_tolerance_um
            or abs(y_v-(lo+hi)/2) > settings.constraint_tolerance_um):
        return fail('invalid_vertical_edge_geometry')
    data.update(vertical_lower_edge_um=lo, vertical_upper_edge_um=hi,
                vertical_midpoint_um=y_v, vertical_chord_height_um=height)
    xc, yc = _intersection(fit.intercept_um, fit.y_ref_um, x_v, y_v, theta)
    c, s = abs(cos(radians(theta))), abs(sin(radians(theta)))
    central, outer = settings.side_um/2*(c-s), settings.side_um/2*(c+s)
    guard = central-settings.boundary_guard_um
    expected = settings.side_um/c
    # Substitution residuals are algebra sanity checks, not independent evidence.
    hr = (xc-fit.intercept_um)+t*(yc-fit.y_ref_um)
    vr = (yc-y_v)-t*(xc-x_v)
    dx = abs(x_v-xc)
    data.update(expected_vertical_chord_height_um=expected, chord_height_error_um=height-expected,
                vertical_offset_from_center_um=dx, vertical_central_half_width_um=central,
                vertical_outer_half_width_um=outer, guarded_vertical_half_width_um=guard,
                horizontal_constraint_residual_um=hr, vertical_constraint_residual_um=vr)
    reasons = []
    if not all(isfinite(v) for v in (xc, yc, hr, vr, dx, height-expected)):
        reasons.append('nonfinite_center_solution')
    if abs(height-expected) > settings.max_chord_height_error_um:
        reasons.append('vertical_chord_height_mismatch')
    if dx >= guard:
        reasons.append('vertical_scan_not_safely_central')
    if max(abs(hr), abs(vr)) > settings.constraint_tolerance_um:
        reasons.append('constraint_residual_exceeded')
    if reasons:
        return fail(*reasons)
    # Hold line anchor and measured vertical constraint fixed, not both a fixed
    # slope and an inconsistent perturbed angle. No covariance is exposed upstream.
    if abs(theta-se) >= 45 or abs(theta+se) >= 45:
        return fail('angle_sensitivity_outside_branch')
    for name, angle in (('angle_minus_se', theta-se), ('angle_plus_se', theta+se)):
        px, py = _intersection(fit.intercept_um, fit.y_ref_um, x_v, y_v, angle)
        data[name] = AngleSensitivity(angle, px-xc, py-yc)
    if initial_center_um is not None:
        dx0, dy0 = xc-initial_center_um[0], yc-initial_center_um[1]
        data.update(center_correction_from_initial_x_um=dx0,
                    center_correction_from_initial_y_um=dy0, total_correction_um=hypot(dx0, dy0))
    return CenterRefinementResult(True, (), x_center_stage_um=xc, y_center_stage_um=yc, **data)
