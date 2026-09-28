"""Conservative offline edge-pair analysis, independent of hardware and semantics.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Analyze a single bright or dark plateau bracketed by measured background. This is
not a general shape fitter; uncertain profiles return reasons and no center.
"""

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import median

from experiment.scan_1d import ScanResult, ScanStatus


@dataclass(frozen=True)
class EdgeSettings:
    min_contrast: float = 0.01
    min_snr: float = 6.0
    min_region_points: int = 3
    expected_width_um: float | None = None
    width_tolerance_um: float | None = None
    saturation_low: float | None = None
    saturation_high: float | None = None
    max_baseline_difference_fraction: float = 0.25

    def __post_init__(self):
        for name in ("min_contrast", "min_snr", "max_baseline_difference_fraction"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if isinstance(self.min_region_points, bool) or not isinstance(self.min_region_points, int) or self.min_region_points < 3:
            raise ValueError("min_region_points must be an integer >= 3")
        if self.expected_width_um is not None:
            if not isfinite(self.expected_width_um) or self.expected_width_um <= 0:
                raise ValueError("expected_width_um must be finite and positive")
        if self.width_tolerance_um is not None:
            if self.expected_width_um is None or not isfinite(self.width_tolerance_um) or self.width_tolerance_um < 0:
                raise ValueError("Width tolerance requires expected width and must be nonnegative")
        for value in (self.saturation_low, self.saturation_high):
            if value is not None and not isfinite(value):
                raise ValueError("Saturation limits must be finite")
        if self.saturation_low is not None and self.saturation_high is not None:
            if self.saturation_low >= self.saturation_high:
                raise ValueError("Saturation limits must be ordered")


@dataclass(frozen=True)
class EdgeCandidate:
    """One consecutive crossing pair; indices refer to increasing positions."""

    crossing_indices: tuple[int, int]
    left_edge_um: float
    right_edge_um: float
    width_um: float
    midpoint_um: float
    polarity: str
    support_counts: tuple[int, int, int]
    contrast: float
    noise: float
    reasons: tuple[str, ...]

    @property
    def valid(self):
        return not self.reasons


@dataclass(frozen=True)
class EdgeResult:
    valid: bool
    reasons: tuple[str, ...] = ()
    left_edge_um: float | None = None
    right_edge_um: float | None = None
    midpoint_um: float | None = None
    width_um: float | None = None
    contrast: float | None = None
    noise: float | None = None
    polarity: str | None = None
    position_source: str = "provided"
    candidates: tuple[EdgeCandidate, ...] = ()
    support_counts: tuple[int, int, int] | None = None


def _evaluate_candidate(x, y, above, crossings, k, threshold, settings):
    first, second = crossings[k:k + 2]
    start = 0 if k == 0 else crossings[k - 1] + 1
    end = len(y) if k + 2 == len(crossings) else crossings[k + 2] + 1
    regions = (y[start:first + 1], y[first + 1:second + 1], y[second + 1:end])
    counts = tuple(map(len, regions))
    levels = tuple(map(median, regions))
    baseline = (levels[0] + levels[2]) / 2
    contrast = abs(levels[1] - baseline)
    local = y[start:end]
    noise = median(abs(b - a) for a, b in zip(local, local[1:])) / 0.9538725524
    residual = sqrt(sum((v - level) ** 2 for region, level in zip(regions, levels)
                        for v in region) / len(local))
    noise = max(noise, residual)
    polarity = "bright" if above[first + 1] else "dark"
    reasons = []
    if any(count < settings.min_region_points for count in counts):
        reasons.append("insufficient_edge_support")
    if contrast < settings.min_contrast or contrast <= 0:
        reasons.append("flat_or_low_contrast")
    if ((polarity == "bright" and levels[1] <= max(levels[0], levels[2]))
            or (polarity == "dark" and levels[1] >= min(levels[0], levels[2]))):
        reasons.append("invalid_polarity")
    if abs(levels[0] - levels[2]) > settings.max_baseline_difference_fraction * contrast:
        reasons.append("inconsistent_background")
    if noise > 0 and contrast / noise < settings.min_snr:
        reasons.append("noisy_signal")

    def crossing(i):
        return x[i] + (threshold - y[i]) * (x[i + 1] - x[i]) / (y[i + 1] - y[i])

    left, right = crossing(first), crossing(second)
    width = right - left
    if settings.expected_width_um is not None:
        tolerance = settings.width_tolerance_um
        if tolerance is None:
            tolerance = 0.2 * settings.expected_width_um
        if abs(width - settings.expected_width_um) > tolerance:
            reasons.append("width_mismatch")
    return EdgeCandidate((first, second), left, right, width, (left + right) / 2,
                         polarity, counts, contrast, noise, tuple(reasons))


def analyze_edges(positions_um, signals, settings: EdgeSettings = EdgeSettings(), *,
                  complete: bool = True) -> EdgeResult:
    """Select a unique supported half-height edge pair in monotonic samples.

    Uses global 10th/90th percentile levels and local uninterrupted support runs.
    Multiple crossings require an expected width; only consecutive pairs qualify.
    No ranking, merging across crossings, or interpolation across missing data.
    Expected width is a QC constraint, not evidence of a missing edge. Contrast/noise have
    the input signal's units; position, width, and midpoint are in um.
    """
    def fail(reason, **diagnostics):
        return EdgeResult(False, (reason,), **diagnostics)

    if not complete:
        return fail("incomplete_scan")
    try:
        x, y = list(map(float, positions_um)), list(map(float, signals))
    except (TypeError, ValueError, OverflowError):
        return fail("invalid_data")
    if len(x) != len(y):
        return fail("length_mismatch")
    if not all(isfinite(value) for value in x + y):
        return fail("nonfinite_data")
    minimum = settings.min_region_points
    if len(x) < minimum * 3:
        return fail("insufficient_samples")
    differences = [b - a for a, b in zip(x, x[1:])]
    if all(d < 0 for d in differences):
        x.reverse()
        y.reverse()
    elif not all(d > 0 for d in differences):
        return fail("nonmonotonic_positions")
    if any((settings.saturation_low is not None and value <= settings.saturation_low)
           or (settings.saturation_high is not None and value >= settings.saturation_high) for value in y):
        return fail("saturated_signal")
    ordered = sorted(y)
    low = ordered[int((len(y) - 1) * 0.1)]
    high = ordered[int((len(y) - 1) * 0.9)]
    contrast = high - low
    # Robust estimate for independent Gaussian sample noise from first differences.
    noise = median(abs(b - a) for a, b in zip(y, y[1:])) / 0.9538725524
    diagnostics = {"contrast": contrast, "noise": noise}
    if contrast < settings.min_contrast or contrast <= 0:
        return fail("flat_or_low_contrast", **diagnostics)
    threshold = (low + high) / 2
    above = [value >= threshold for value in y]
    crossings = [i for i in range(len(y) - 1) if above[i] != above[i + 1]]
    # Preserve legacy early noise rejection for single-feature/no-prior use.
    # Width-guided multi-feature decisions must use candidate-local noise only.
    if (len(crossings) <= 2 or settings.expected_width_um is None) and noise > 0 and contrast / noise < settings.min_snr:
        return fail("noisy_signal", **diagnostics)
    if len(crossings) > 2 and settings.expected_width_um is None:
        return fail("ambiguous_edges", **diagnostics)
    if len(crossings) < 2:
        return fail("incomplete_feature", **diagnostics)
    candidates = tuple(_evaluate_candidate(x, y, above, crossings, k, threshold, settings)
                       for k in range(len(crossings) - 1))
    accepted = [candidate for candidate in candidates if candidate.valid]
    if len(accepted) > 1:
        return fail("ambiguous_edges", candidates=candidates, **diagnostics)
    if not accepted:
        # Keep the existing single-pair failure code, with full local diagnostics.
        reason = candidates[0].reasons[0] if len(candidates) == 1 else "no_valid_candidate"
        return fail(reason, candidates=candidates, **diagnostics)
    selected = accepted[0]
    return EdgeResult(True, left_edge_um=selected.left_edge_um,
                      right_edge_um=selected.right_edge_um,
                      midpoint_um=selected.midpoint_um, width_um=selected.width_um,
                      polarity=selected.polarity, contrast=selected.contrast,
                      noise=selected.noise, candidates=candidates,
                      support_counts=selected.support_counts)


def analyze_scan(scan: ScanResult, settings: EdgeSettings = EdgeSettings(), *,
                 use_commanded_positions: bool = False) -> EdgeResult:
    """Require complete acquisition; use readback unless caller opts into commands.

    Never silently mix measured and commanded positions in one spatial profile.
    """
    from dataclasses import replace

    if scan.status != ScanStatus.COMPLETED:
        return EdgeResult(False, ("incomplete_scan",))
    if len(scan.points) != len(scan.settings.positions()):
        return EdgeResult(False, ("incomplete_scan",))
    if not use_commanded_positions and any(point.measured_um is None for point in scan.points):
        return EdgeResult(False, ("missing_position_readback",))
    axis = 0 if scan.settings.axis == "x" else 1
    positions = [(p.commanded_um if use_commanded_positions else p.measured_um)[axis] for p in scan.points]
    result = analyze_edges(positions, [p.signal for p in scan.points], settings)
    return replace(result, position_source="commanded" if use_commanded_positions else "measured")
