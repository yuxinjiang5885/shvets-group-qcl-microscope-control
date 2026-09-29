"""Offline square-profile classification; no acquisition or registration fitting.

Seed: nearest measured Y values (ties by identifier), never selected by angle.
One fixed rejection pass uses seed residuals and the geometric-central width MAD.
Final OLS checks can invalidate the remaining set, but never iteratively trim it.
Final QC requires retained original seed support and sufficient accepted Y leverage.
Angles use the small-angle branch |theta| < 45 degrees and theta = -atan(dx/dy).
Seed parallelism limit is max(configured slope limit, 2*residual_floor/Y_span):
the short seed has less slope leverage than the final central set. Seed width
spread and residual checks use fixed floors so seed corruption cannot inflate MAD.
Accepted-row residuals reference final central OLS; excluded-row residuals reference
the seed OLS, preserving the evidence for rejection. No final angle is derived.
Thresholds are screening defaults, not calibrated measurement uncertainties.
"""
from dataclasses import dataclass, replace
from enum import Enum
from math import atan, cos, sin, degrees, isfinite
from statistics import median


class ProfileClass(str, Enum):
    CENTRAL = "CENTRAL"
    CORNER_AFFECTED = "CORNER_AFFECTED"
    INCONSISTENT = "INCONSISTENT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ProfileGeometry:
    identifier: str
    measured_y_um: float
    left_edge_um: float | None
    right_edge_um: float | None
    midpoint_um: float | None
    width_um: float | None
    edge_valid: bool


@dataclass(frozen=True)
class ClassificationSettings:
    """Provisional screening thresholds, not calibrated production uncertainty.

    minimum_y_span_um applies to both the seed and screened CENTRAL set.
    """
    side_um: float = 500.0
    minimum_profiles: int = 3
    boundary_guard_um: float = 10.0
    width_floor_um: float = 5.0
    residual_floor_um: float = 3.0
    mad_multiplier: float = 3.0
    max_slope_disagreement: float = 0.01
    seed_width_model_tolerance_um: float = 15.0
    minimum_y_span_um: float = 40.0
    geometry_tolerance_um: float = 1e-6

    def __post_init__(self):
        if isinstance(self.minimum_profiles, bool) or not isinstance(self.minimum_profiles, int) or self.minimum_profiles < 3:
            raise ValueError("minimum_profiles must be an integer >= 3")
        for key, value in vars(self).items():
            if key != "minimum_profiles" and (isinstance(value, bool) or not isfinite(value) or value <= 0):
                raise ValueError(f"{key} must be finite and positive")
        if self.boundary_guard_um >= self.side_um / 2:
            raise ValueError("Guard must be smaller than half the side")


@dataclass(frozen=True)
class LineFit:
    y_ref_um: float
    intercept_um: float
    slope: float

    def at(self, y):
        return self.intercept_um + self.slope * (y - self.y_ref_um)


@dataclass(frozen=True)
class ClassifiedProfile:
    profile: ProfileGeometry
    classification: ProfileClass
    reasons: tuple[str, ...]
    width_deviation_um: float | None = None
    geometric_dy_um: float | None = None
    central_half_height_um: float | None = None
    left_residual_um: float | None = None
    right_residual_um: float | None = None
    midpoint_residual_um: float | None = None


@dataclass(frozen=True)
class ClassificationResult:
    """Per-profile screening diagnostics plus an explicit set-level approval.

    CENTRAL rows alone do not approve a dataset: seed-support/leverage gates can
    still fail. usable_final_fits is None on every failure. Successful fits are
    left/right/midpoint QC lines, not a production registration or final angle.
    """
    profiles: tuple[ClassifiedProfile, ...]
    provisional_rotation_deg: float | None
    provisional_slope: float | None
    central_y_interval_um: tuple[float, float] | None
    guarded_central_y_interval_um: tuple[float, float] | None
    outer_half_height_um: float | None
    sufficient_for_rotation_fit: bool
    reasons: tuple[str, ...]
    seed_identifiers: tuple[str, ...] = ()
    width_plateau_um: float | None = None
    width_limit_um: float | None = None
    residual_limits_um: tuple[float, ...] = ()
    usable_final_fits: tuple[LineFit, ...] | None = None
    slope_disagreement: float | None = None

    def identifiers(self, classification):
        return tuple(r.profile.identifier for r in self.profiles if r.classification == classification)

    @property
    def central_identifiers(self):
        return self.identifiers(ProfileClass.CENTRAL)

    @property
    def corner_affected_identifiers(self):
        return self.identifiers(ProfileClass.CORNER_AFFECTED)

    @property
    def inconsistent_identifiers(self):
        return self.identifiers(ProfileClass.INCONSISTENT)

    @property
    def invalid_identifiers(self):
        return self.identifiers(ProfileClass.INVALID)


FIELDS = ("left_edge_um", "right_edge_um", "midpoint_um")


def _fit(profiles, field, y_ref):
    ys = [p.measured_y_um - y_ref for p in profiles]
    xs = [getattr(p, field) for p in profiles]
    ym, xm = sum(ys) / len(ys), sum(xs) / len(xs)
    denominator = sum((y - ym) ** 2 for y in ys)
    if denominator == 0:
        raise ValueError("No Y leverage")
    slope = sum((y - ym) * (x - xm) for y, x in zip(ys, xs)) / denominator
    return LineFit(y_ref, xm - slope * ym, slope)


def _limit(values, floor, multiplier):
    center = median(values)
    return max(floor, multiplier * 1.4826 * median(abs(v - center) for v in values))


def classify_profiles(profiles, y_center_initial_um, settings=ClassificationSettings()):
    """Return conservative classifications, never a production registration angle.

    Invalid records are excluded before seed selection. Outside-footprint valid
    edge claims are INCONSISTENT, not evidence of a corner. Guard-band records
    are CORNER_AFFECTED with an explicit boundary reason.
    """
    if not isfinite(y_center_initial_um):
        raise ValueError("Initial center must be finite")
    profiles = tuple(profiles)
    ids = [p.identifier for p in profiles]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Identifiers must be unique nonempty strings")
    profiles = tuple(sorted(profiles, key=lambda p: p.identifier))
    rows, usable = {}, []
    for p in profiles:
        values = (p.measured_y_um, p.left_edge_um, p.right_edge_um, p.midpoint_um, p.width_um)
        finite = all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in values)
        valid = p.edge_valid is True and finite
        if valid:
            valid = (p.right_edge_um > p.left_edge_um and
                     abs(p.width_um - (p.right_edge_um - p.left_edge_um)) <= settings.geometry_tolerance_um and
                     abs(p.midpoint_um - (p.left_edge_um + p.right_edge_um) / 2) <= settings.geometry_tolerance_um)
        dy = abs(p.measured_y_um - y_center_initial_um) if isinstance(p.measured_y_um, (float, int)) and isfinite(p.measured_y_um) else None
        rows[p.identifier] = ClassifiedProfile(p, ProfileClass.INVALID, ("invalid_edge_geometry",), geometric_dy_um=dy)
        if valid:
            usable.append(p)
    seed = sorted(usable, key=lambda p: (abs(p.measured_y_um-y_center_initial_um), p.identifier))[:settings.minimum_profiles]
    seed_ids = tuple(p.identifier for p in seed)

    def fail_seed(reason):
        for p in usable:
            rows[p.identifier] = replace(rows[p.identifier], classification=ProfileClass.INCONSISTENT,
                                         reasons=(reason,))
        return ClassificationResult(tuple(rows.values()), None, None, None, None, None,
                                    False, (reason,), seed_ids)

    if len(seed) < settings.minimum_profiles:
        return fail_seed("insufficient_seed")
    if max(p.measured_y_um for p in seed) - min(p.measured_y_um for p in seed) < settings.minimum_y_span_um:
        return fail_seed("insufficient_seed_y_span")
    fits = tuple(_fit(seed, f, y_center_initial_um) for f in FIELDS)
    theta = -atan(fits[2].slope)
    if abs(theta) >= 0.7853981633974483:
        return fail_seed("outside_small_angle_branch")
    half = settings.side_um / 2 * (abs(cos(theta)) - abs(sin(theta)))
    outer = settings.side_um / 2 * (abs(cos(theta)) + abs(sin(theta)))
    seed_width = median(p.width_um for p in seed)
    seed_residuals = tuple([getattr(p, f) - fit.at(p.measured_y_um) for p in seed]
                          for f, fit in zip(FIELDS, fits))
    if (any(abs(p.measured_y_um-y_center_initial_um) >= half-settings.boundary_guard_um for p in seed) or
        max(abs(p.width_um-seed_width) for p in seed) > settings.width_floor_um or
        abs(seed_width-settings.side_um/abs(cos(theta))) > settings.seed_width_model_tolerance_um or
        abs(fits[0].slope-fits[1].slope) > max(settings.max_slope_disagreement,
            2 * settings.residual_floor_um / (max(p.measured_y_um for p in seed)-min(p.measured_y_um for p in seed))) or
        any(max(map(abs, r)) > settings.residual_floor_um for r in seed_residuals)):
        return fail_seed("inconsistent_seed")
    central = [p for p in usable if abs(p.measured_y_um-y_center_initial_um) < half-settings.boundary_guard_um]
    plateau = median(p.width_um for p in central)
    width_limit = _limit([p.width_um for p in central], settings.width_floor_um, settings.mad_multiplier)
    limits = tuple(_limit(r, settings.residual_floor_um, settings.mad_multiplier) for r in seed_residuals)
    for p in usable:
        dy = abs(p.measured_y_um-y_center_initial_um)
        residuals = tuple(getattr(p, f)-fit.at(p.measured_y_um) for f, fit in zip(FIELDS, fits))
        reasons = []
        if dy >= outer:
            kind, reasons = ProfileClass.INCONSISTENT, ["outside_square_footprint"]
        elif dy >= half-settings.boundary_guard_um:
            kind, reasons = ProfileClass.CORNER_AFFECTED, ["corner_boundary_guard" if dy < half else "corner_region"]
        else:
            if abs(p.width_um-plateau) > width_limit:
                reasons.append("width_plateau_outlier")
            for name, residual, limit in zip(FIELDS, residuals, limits):
                if abs(residual) > limit:
                    reasons.append(name + "_seed_residual_outlier")
            kind = ProfileClass.INCONSISTENT if reasons else ProfileClass.CENTRAL
        rows[p.identifier] = ClassifiedProfile(p, kind, tuple(reasons), p.width_um-plateau, dy, half, *residuals)
    accepted = [r.profile for r in rows.values() if r.classification == ProfileClass.CENTRAL]
    final_fits, disagreement, reasons = None, None, []
    if len(accepted) < settings.minimum_profiles:
        reasons.append("insufficient_central_profiles")
    accepted_ys = {p.measured_y_um for p in accepted}
    if len(accepted_ys) < 2:
        reasons.append("insufficient_distinct_y")
    final_span = max(accepted_ys) - min(accepted_ys) if accepted_ys else 0.0
    if final_span < settings.minimum_y_span_um:
        reasons.append("insufficient_final_y_span")
    # The seed contains exactly minimum_profiles records: losing any member
    # invalidates its support. Never replace it with a better-looking group.
    accepted_ids = {p.identifier for p in accepted}
    if not set(seed_ids).issubset(accepted_ids):
        reasons.append("seed_support_lost")
    # Accumulate all gate diagnostics before deciding; no final regression runs
    # on a deficient set, including identical-Y survivors after screening.
    if not reasons:
        final_fits = tuple(_fit(accepted, f, y_center_initial_um) for f in FIELDS)
        disagreement = abs(final_fits[0].slope-final_fits[1].slope)
        final_residuals = {p.identifier: tuple(getattr(p, f)-fit.at(p.measured_y_um)
                           for f, fit in zip(FIELDS, final_fits)) for p in accepted}
        # No second trimming pass: reject the set if the final model fails QC.
        failed = disagreement > settings.max_slope_disagreement or any(
            abs(r) > limit for values in final_residuals.values() for r, limit in zip(values, limits))
        for p in accepted:
            r = rows[p.identifier]
            rows[p.identifier] = replace(r, left_residual_um=final_residuals[p.identifier][0],
                right_residual_um=final_residuals[p.identifier][1], midpoint_residual_um=final_residuals[p.identifier][2],
                classification=ProfileClass.INCONSISTENT if failed else ProfileClass.CENTRAL,
                reasons=("final_central_model_inconsistent",) if failed else ())
        if failed:
            reasons.append("final_central_model_inconsistent")
            # Retain residuals/disagreement, but expose no rejected fit objects.
            final_fits = None
    return ClassificationResult(tuple(rows.values()), degrees(theta), fits[2].slope,
        (y_center_initial_um-half, y_center_initial_um+half),
        (y_center_initial_um-half+settings.boundary_guard_um, y_center_initial_um+half-settings.boundary_guard_um),
        outer, not reasons, tuple(reasons), seed_ids, plateau, width_limit, limits, final_fits, disagreement)
