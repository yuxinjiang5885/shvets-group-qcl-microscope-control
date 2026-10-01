"""Production priors never waive generic candidate quality failures."""
from dataclasses import replace
from pathlib import Path
import unittest

from experiment.reflection_analysis import EdgeCandidate, EdgeResult, EdgeSettings, analyze_edges, analyze_scan
from experiment.scan_1d import load_scan
from ui.production_marker_selection import select_marker_candidate


def candidate(left=0,right=500,reasons=()):
    return EdgeCandidate((3,23),left,right,right-left,(left+right)/2,'bright',
                         (4,20,4),3.,.01,reasons)


class SelectionTests(unittest.TestCase):
    def select(self, candidates, anchor=250):
        return select_marker_candidate(EdgeResult(False,('no_valid_candidate',),candidates=tuple(candidates)),500,100,anchor)

    def test_unique_size_anchor_candidate(self):
        result,diag=self.select([candidate(-200,-150),candidate(),candidate(700,1200)])
        self.assertTrue(result.valid);self.assertEqual(result.midpoint_um,250)
        self.assertEqual(diag['accepted_candidate_count'],1)

    def test_width_and_anchor_boundaries(self):
        for width,valid in ((399,False),(400,True),(500,True),(600,True),(601,False)):
            for anchor in (0,width):
                with self.subTest(width=width,anchor=anchor):
                    self.assertEqual(self.select([candidate(0,width)],anchor)[0].valid,valid)

    def test_no_match_and_ambiguity_fail_closed(self):
        result,_=self.select([candidate(700,1200)])
        self.assertEqual(result.reasons,('no_anchor_matching_marker_candidate',))
        result,_=self.select([candidate(),candidate(100,600)])
        self.assertEqual(result.reasons,('multiple_anchor_matching_marker_candidates',))
        self.assertIsNone(result.midpoint_um)

    def test_signal_quality_reasons_never_waived(self):
        for reason in ('noisy_signal','insufficient_edge_support','inconsistent_background','flat_or_low_contrast','invalid_polarity'):
            with self.subTest(reason=reason):
                result,diag=self.select([candidate(reasons=(reason,))])
                self.assertFalse(result.valid)
                self.assertEqual(diag['candidates'][0]['quality_failures'],(reason,))

    def test_generic_ambiguity_resolved_by_anchor_without_modifying_generic(self):
        x=list(range(-300,1401,10));y=[4 if 0<=v<=500 or 800<=v<=1300 else 1 for v in x]
        generic=analyze_edges(x,y,EdgeSettings(expected_width_um=500,width_tolerance_um=100))
        self.assertFalse(generic.valid)
        selected,_=select_marker_candidate(generic,500,100,250)
        self.assertTrue(selected.valid)
        self.assertFalse(generic.valid)

    def test_nearby_crosses_one_or_both_sides(self):
        for features in (((-250,-180),(0,500),(700,770)),((0,500),(700,770))):
            x=list(range(-400,951,10));y=[4 if any(a<=v<=b for a,b in features) else 1 for v in x]
            generic=analyze_edges(x,y,EdgeSettings(expected_width_um=500,width_tolerance_um=100))
            selected,diag=select_marker_candidate(generic,500,100,200)
            self.assertTrue(selected.valid,diag)
            self.assertAlmostEqual(selected.midpoint_um,250)

    def test_failed_real_journal_retains_noisy_signal_rejection(self):
        path=Path(__file__).resolve().parents[1]/'tests/fixtures/production_marker/wide_25um_H.jsonl'
        generic=analyze_scan(load_scan(path),EdgeSettings(expected_width_um=500,width_tolerance_um=100))
        result,diag=select_marker_candidate(generic,500,100,4200)
        self.assertEqual(generic.reasons,('no_valid_candidate',))
        matching=[c for c in diag['candidates'] if c['width_matches'] and c['anchor_contained']]
        self.assertEqual(len(matching),1)
        self.assertEqual(matching[0]['quality_failures'],('noisy_signal',))
        self.assertAlmostEqual(matching[0]['midpoint_um'],4213.416776528646)
        self.assertFalse(result.valid)
