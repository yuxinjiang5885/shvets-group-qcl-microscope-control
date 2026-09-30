"""Supervised H+V only, reusing H handoff, acquisition and cleanup machinery."""
from dataclasses import dataclass, replace, asdict
from math import isfinite
from statistics import mean

from ui.h_only_validation import HOnlySpec, HOnlyServices, OperatorConfirmation


@dataclass(frozen=True)
class HVSpec(HOnlySpec):
    """Review the entire rectangle before H; dynamic V X stays within H range.

    Prior requires integer micrometres. Nearest integer, ties-to-even (Python
    round), is explicit and symmetric for negative coordinates; never truncate.
    Rectangular bounds cover approach/reposition/return, including diagonal moves.
    """
    def __post_init__(self):
        super().__post_init__()
        horizontal = self.scan()
        for x in (horizontal.start_um, horizontal.end_um):
            self.vertical(x).positions()

    def vertical(self, midpoint):
        if not isfinite(midpoint):
            raise ValueError('nonfinite_H_midpoint')
        h = self.scan()
        x = round(midpoint)
        if not h.start_um <= x <= h.end_um:
            raise ValueError('V_X_outside_reviewed_H_envelope')
        half = self.side_um / 2 + self.scan_margin_um
        y = self.rough_start_xy[1]
        result = replace(h, axis='y', start_um=y-half, end_um=y+half, fixed_um=x)
        if any(any(v != round(v) for v in xy) for xy in result.positions()):
            raise ValueError('V_targets_must_match_integer_stage_resolution')
        return result


@dataclass(frozen=True)
class HVConfirmation(OperatorConfirmation):
    both_axes_clearance: bool = False

    def validate(self, context, laser):
        super().validate(context, laser)
        if self.both_axes_clearance is not True:
            raise ValueError('H_plus_V_requires_separate_both_axes_clearance_confirmation')


class HVServices(HOnlyServices):
    def prepare(self, settings):
        if not isinstance(self.spec, HVSpec) or not isinstance(self.confirmation, HVConfirmation):
            raise ValueError('H_plus_V_spec_and_confirmation_required')
        super().prepare(settings)

    def work(self, settings, checkpoint, progress):
        _, h = self.acquire_horizontal(checkpoint, progress)
        checkpoint()  # Verified H journal; no V movement before this gate.
        vsettings = self.spec.vertical(h.midpoint_um)
        self.report.update(chosen_v_x=vsettings.fixed_um,
                           v_x_rounding_delta=vsettings.fixed_um-h.midpoint_um,
                           vertical_journal=str(self.path/'initial_V.jsonl'),
                           requested_y=(vsettings.start_um, vsettings.end_um),
                           expected_v_points=len(vsettings.positions()))
        self._phase('before_vertical', checkpoint, progress,
                    chosen_v_x=vsettings.fixed_um,
                    rounding_delta=vsettings.fixed_um-h.midpoint_um)
        vertical, edge = self._scan('initial_V', vsettings, checkpoint, progress)
        checkpoint()
        xs = [p.measured_um[0] for p in vertical.points]
        ys = [p.measured_um[1] for p in vertical.points]
        self.report.update(v_measured_x_mean=mean(xs), v_measured_x_range=(min(xs), max(xs)),
            v_measured_y=(min(ys), max(ys)), v_points=len(ys),
            lower=edge.left_edge_um, upper=edge.right_edge_um,
            v_midpoint=edge.midpoint_um, height=edge.width_um,
            vertical_edge_diagnostics=asdict(edge),
            initial_center=(h.midpoint_um, edge.midpoint_um),
            center_interpretation='initial H/V estimate only; not rotation corrected')
        self._phase('success_only_return', checkpoint, progress)
        self.report['return_status'] = 'FAILED_OR_INCOMPLETE'
        self._return(checkpoint)
        self.report['return_status'] = 'PASS'
        return self.report.copy()
