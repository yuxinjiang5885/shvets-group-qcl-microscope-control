"""Production sampling policy; uses the existing immutable H/V run spec."""
from math import ceil, floor, isfinite

from ui.hv_validation import HVSpec

SEARCH_HALF_SPAN_MARKER_FACTOR = 1.25
PRODUCTION_STEP_MAX_UM = 15
PRODUCTION_STEP_MARKER_FRACTION = 1 / 20


def production_geometry(side_um):
    """Return (actual half-span, integral step), expanding symmetrically outward.

    Stage resolution is 1 um. Reject markers whose requested step is below it;
    never round step upward and silently undersample a small marker.
    """
    if not isfinite(side_um) or side_um <= 0:
        raise ValueError('invalid_production_marker_size')
    step = floor(min(PRODUCTION_STEP_MAX_UM, side_um * PRODUCTION_STEP_MARKER_FRACTION))
    if step < 1:
        raise ValueError('marker_too_small_for_integer_stage_sampling')
    half = ceil(SEARCH_HALF_SPAN_MARKER_FACTOR * side_um / step) * step
    return half, step


def requested_geometry(side_um, half_span=None, step_um=None):
    if half_span is None and step_um is None:
        half, step = production_geometry(side_um)
        return 'automatic', SEARCH_HALF_SPAN_MARKER_FACTOR*side_um, step, half
    if (half_span is None or step_um is None or not all(isfinite(v) for v in (half_span,step_um))
            or half_span <= 0 or step_um <= 0 or step_um != round(step_um)):
        raise ValueError('invalid_production_override_integral_step_required')
    half = ceil(half_span/step_um)*step_um
    if 2*half/step_um+1 < 9:
        raise ValueError('insufficient_samples_for_edge_analysis')
    if half <= side_um/2:
        raise ValueError('production_range_requires_background_beyond_marker_half_width')
    return 'override', half_span, step_um, half


def production_spec(rough_start_xy, bounds, side_um, *, half_span=None, step_um=None):
    mode, requested, step, half = requested_geometry(side_um,half_span,step_um)
    return HVSpec(rough_start_xy, bounds, side_um=side_um,
                  scan_margin_um=half-side_um/2, step_um=step,
                  production_geometry=(mode,requested,step))
