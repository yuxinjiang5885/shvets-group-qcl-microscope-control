"""Physical local support for an already uniquely identified marker."""
from math import isfinite
from experiment.reflection_analysis import evaluate_region_quality

LOCAL_BACKGROUND_WIDTH_UM = 100.


def local_marker_quality(scan, candidate, candidates, settings):
    axis=0 if scan.settings.axis=='x' else 1
    points=sorted(scan.points,key=lambda p:p.measured_um[axis])
    x=[p.measured_um[axis] for p in points];y=[p.signal for p in points]
    # Generic candidates expose all consecutive crossing pairs, including failures.
    crossings={}
    for c in candidates:
        crossings[c.crossing_indices[0]]=c.left_edge_um
        crossings[c.crossing_indices[1]]=c.right_edge_um
    first,second=candidate.crossing_indices
    previous=max((v for i,v in crossings.items() if i<first),default=None)
    following=min((v for i,v in crossings.items() if i>second),default=None)
    left,right=candidate.left_edge_um,candidate.right_edge_um
    nominal=((left-LOCAL_BACKGROUND_WIDTH_UM,left),(right,right+LOCAL_BACKGROUND_WIDTH_UM))
    actual=((max(nominal[0][0],previous) if previous is not None else nominal[0][0],left),
            (right,min(nominal[1][1],following) if following is not None else nominal[1][1]))
    # Exclude both measured samples bracketing ANY detected crossing, on both
    # plateau and substrate sides. No step-derived counts or distant substitutes.
    excluded={j for i in crossings for j in (i,i+1)}
    indices=([i for i,v in enumerate(x) if actual[0][0]<=v<left and i not in excluded],
             [i for i,v in enumerate(x) if left<=v<=right and i not in excluded],
             [i for i,v in enumerate(x) if right<v<=actual[1][1] and i not in excluded])
    regions=[[y[i] for i in ids] for ids in indices]
    counts=tuple(map(len,regions));reasons=[]
    for name,n in zip(('left','interior','right'),counts):
        if n<settings.min_region_points:
            reasons.append('insufficient_local_baseline_support_'+name if name!='interior' else 'insufficient_local_marker_support')
    if any(not isfinite(v) for v in x+y):reasons.append('nonfinite_data')
    # Preserve whole-scan saturation protection, independent of local support.
    if any((settings.saturation_low is not None and v<=settings.saturation_low) or
           (settings.saturation_high is not None and v>=settings.saturation_high) for v in y):
        reasons.append('saturated_signal')
    diagnostics=dict(nominal_background_width_um=LOCAL_BACKGROUND_WIDTH_UM,
        requested_intervals=nominal,actual_intervals=actual,
        nearest_previous_crossing=previous,nearest_next_crossing=following,
        support_counts=counts,used_measured_coordinates=[[x[i] for i in ids] for ids in indices],
        transition_rule='Exclude both bracket samples at every crossing from all three regions')
    if not reasons:
        _,levels,contrast,noise,quality=evaluate_region_quality(regions,candidate.polarity,settings)
        reasons.extend(quality)
        diagnostics.update(region_medians=levels,contrast=contrast,noise=noise,
            snr=contrast/noise if noise>0 else None,zero_noise=noise==0,
            baseline_difference=abs(levels[0]-levels[2]),
            baseline_difference_limit=settings.max_baseline_difference_fraction*contrast)
    diagnostics.update(reasons=tuple(reasons),marker_quality_pass=not reasons)
    return diagnostics
