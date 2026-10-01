"""Unique marker identity followed by local quality using unchanged thresholds."""
from dataclasses import replace, asdict
from math import isfinite

from experiment.reflection_analysis import EdgeResult, EdgeSettings
from ui.production_marker_quality import local_marker_quality


def select_marker_candidate(generic, expected_dimension, tolerance, anchor, *, scan=None, settings=None):
    if not all(isfinite(v) for v in (expected_dimension,tolerance,anchor)) or expected_dimension<=0 or tolerance<0:
        raise ValueError('invalid_marker_selection_context')
    rows=[];accepted=[]
    for candidate in generic.candidates:
        width_ok=abs(candidate.width_um-expected_dimension)<=tolerance
        anchor_ok=candidate.left_edge_um<=anchor<=candidate.right_edge_um
        # Keep wide-region quality for comparison, separate from identity.
        quality=tuple(r for r in candidate.reasons if r!='width_mismatch')
        selected=width_ok and anchor_ok
        rows.append(dict(**asdict(candidate),width_matches=width_ok,anchor_contained=anchor_ok,
                         quality_failures=quality,quality_source='generic wide-region diagnostic',
                         identity_eligible=selected,identity_selected=False))
        if selected:accepted.append(candidate)
    diagnostics=dict(expected_dimension_um=expected_dimension,width_tolerance_um=tolerance,
        anchor_um=anchor,generic_valid=generic.valid,generic_reasons=generic.reasons,
        candidates=rows,identity_candidate_count=len(accepted),accepted_candidate_count=0,
        marker_identity_match=len(accepted)==1,marker_quality_pass=False)
    if len(accepted)!=1:
        reason='no_anchor_matching_marker_candidate' if not accepted else 'multiple_anchor_matching_marker_candidates'
        return replace(generic,valid=False,reasons=(reason,),left_edge_um=None,right_edge_um=None,
                       midpoint_um=None,width_um=None),diagnostics
    c=accepted[0]
    for row in rows:
        row['identity_selected']=row['identity_eligible']
    if scan is not None:
        settings=settings or EdgeSettings(expected_width_um=expected_dimension,width_tolerance_um=tolerance)
        local=local_marker_quality(scan,c,generic.candidates,settings)
        diagnostics['local_quality']=local
        quality=local['reasons']
        contrast=local.get('contrast');noise=local.get('noise');counts=local['support_counts']
    else:
        # Candidate-only callers lack measured samples for local reassessment.
        quality=tuple(r for r in c.reasons if r!='width_mismatch')
        contrast,noise,counts=c.contrast,c.noise,c.support_counts
    diagnostics['marker_quality_pass']=not quality
    if quality:
        return replace(generic,valid=False,reasons=quality,left_edge_um=None,right_edge_um=None,
                       midpoint_um=None,width_um=None),diagnostics
    diagnostics['accepted_candidate_count']=1
    return EdgeResult(True,left_edge_um=c.left_edge_um,right_edge_um=c.right_edge_um,
        midpoint_um=c.midpoint_um,width_um=c.width_um,contrast=contrast,noise=noise,
        polarity=c.polarity,position_source=generic.position_source,candidates=generic.candidates,
        support_counts=counts),diagnostics
