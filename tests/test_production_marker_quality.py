"""Physical local quality windows, generic-QC invariance and journal regression."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
import test_translation_localization as fixtures

from experiment.reflection_analysis import analyze_edges, analyze_scan, EdgeSettings
from experiment.scan_1d import load_scan
from ui.production_marker_selection import select_marker_candidate

SETTINGS=EdgeSettings(expected_width_um=500,width_tolerance_um=100)


def synthetic(step=10, extra=(), change=None):
    x=list(range(-400,901,step))
    y=[4. if 0<=v<=500 or any(a<=v<=b for a,b in extra) else 1. for v in x]
    if change:y=[change(v,z,i) for i,(v,z) in enumerate(zip(x,y))]
    scan=SimpleNamespace(settings=SimpleNamespace(axis='x'),
        points=[SimpleNamespace(measured_um=(v,0),signal=z) for v,z in zip(x,y)])
    g=analyze_edges(x,y,SETTINGS)
    return scan,g


def selected(scan,g):
    return select_marker_candidate(g,500,100,250,scan=scan)


class LocalQualityTests(unittest.TestCase):
    def test_clean_marker_and_physical_windows_each_step(self):
        for step in (10,15,20,25):
            with self.subTest(step=step):
                scan,g=synthetic(step);r,d=selected(scan,g)
                self.assertTrue(r.valid,d)
                q=d['local_quality'];self.assertEqual(q['nominal_background_width_um'],100)
                self.assertGreaterEqual(min(q['support_counts']),3)
                for interval in q['requested_intervals']:self.assertAlmostEqual(interval[1]-interval[0],100)
                for coords,interval in zip((q['used_measured_coordinates'][0],q['used_measured_coordinates'][2]),q['actual_intervals']):
                    self.assertTrue(all(interval[0]<=v<=interval[1] for v in coords))

    def test_distant_crosses_and_variance_excluded(self):
        base=selected(*synthetic())[1]['local_quality']
        scan,g=synthetic(extra=((-300,-230),(730,800)),
            change=lambda x,z,i:z+(.4*(-1)**i if x<-150 or x>650 else 0))
        r,d=selected(scan,g);self.assertTrue(r.valid,d)
        for field in ('region_medians','contrast','noise','support_counts'):
            self.assertEqual(base[field],d['local_quality'][field])

    def test_nearest_crossing_truncation_with_support(self):
        scan,g=synthetic(extra=((570,650),))
        r,d=selected(scan,g);self.assertTrue(r.valid,d)
        q=d['local_quality']
        self.assertEqual(q['actual_intervals'][1][1],q['nearest_next_crossing'])
        self.assertLess(q['actual_intervals'][1][1],q['requested_intervals'][1][1])
        self.assertTrue(all(x<560 for x in q['used_measured_coordinates'][2]))

    def test_truncation_insufficient_support_fails_identity_stays_selected(self):
        scan,g=synthetic(extra=((530,650),))
        r,d=selected(scan,g)
        self.assertTrue(d['marker_identity_match']);self.assertFalse(d['marker_quality_pass'])
        self.assertIn('insufficient_local_baseline_support_right',r.reasons)

    def test_left_truncation(self):
        scan,g=synthetic(extra=((-140,-40),))
        r,d=selected(scan,g);q=d['local_quality']
        self.assertEqual(q['actual_intervals'][0][0],q['nearest_previous_crossing'])
        self.assertIn('insufficient_local_baseline_support_left',r.reasons)

    def test_noisy_local_substrate_still_rejected(self):
        scan,g=synthetic(change=lambda x,z,i:z+1.4*(-1)**i if -100<=x<0 or 500<x<=600 else z)
        r,d=selected(scan,g)
        self.assertTrue(d['marker_identity_match'],d)
        self.assertFalse(r.valid);self.assertIn('noisy_signal',r.reasons)

    def test_local_background_mismatch_rejected(self):
        scan,g=synthetic(change=lambda x,z,i:2 if x>500 else z)
        r,d=selected(scan,g)
        self.assertTrue(d['marker_identity_match'],d)
        self.assertIn('inconsistent_background',r.reasons)

    def test_measured_coordinates_not_index_determine_support(self):
        scan,g=synthetic();r,d=selected(scan,g)
        first=d['local_quality']['used_measured_coordinates'][0][0]
        points=[SimpleNamespace(measured_um=(p.measured_um[0]-.2 if p.measured_um[0]==first else p.measured_um[0],0),signal=p.signal) for p in scan.points]
        # Move a used point beyond the physical lower window while retaining
        # crossing brackets; generic candidate is unchanged.
        index=next(i for i,p in enumerate(points) if p.measured_um[0]==first-.2)
        points[index].measured_um=(d['local_quality']['actual_intervals'][0][0]-1,0)
        r2,d2=selected(SimpleNamespace(settings=scan.settings,points=points),g)
        self.assertEqual(d2['local_quality']['support_counts'][0],d['local_quality']['support_counts'][0]-1)

    def test_ambiguity_precedes_quality(self):
        scan,g=synthetic();c=g.candidates[0]
        g=replace(g,candidates=(c,replace(c,reasons=('noisy_signal',))))
        r,d=selected(scan,g)
        self.assertEqual(r.reasons,('multiple_anchor_matching_marker_candidates',))
        self.assertNotIn('local_quality',d)

    def test_saturation_still_rejected(self):
        scan,g=synthetic()
        r,d=select_marker_candidate(g,500,100,250,scan=scan,
            settings=replace(SETTINGS,saturation_high=3.9))
        self.assertIn('saturated_signal',r.reasons)

    def test_real_failed_and_historical_journals(self):
        root=Path(__file__).resolve().parents[1]
        paths=['tests/fixtures/production_marker/wide_25um_H.jsonl',
               'tests/fixtures/production_marker/reference_10um_H.jsonl',
               'tests/fixtures/production_marker/reference_10um_V.jsonl',
               'vertical_marker_scan_9392a56a0a0e4517b9b897398376ee3b.jsonl']
        for path in paths:
            with self.subTest(path=path):
                scan=load_scan(root/path);g=analyze_scan(scan,SETTINGS)
                anchor=4200 if 'wide_25um' in path else g.midpoint_um
                r,d=select_marker_candidate(g,500,100,anchor,scan=scan)
                self.assertTrue(r.valid,d);self.assertGreaterEqual(d['local_quality']['snr'],6)
                self.assertEqual(r.left_edge_um,next(c.left_edge_um for c in g.candidates if c.left_edge_um<=anchor<=c.right_edge_um))
                if 'wide_25um' in path:
                    self.assertFalse(g.valid)
                    self.assertEqual(d['local_quality']['support_counts'],(3,18,3))
                    self.assertAlmostEqual(d['local_quality']['snr'],325.25986661640735)


class PublicationTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.TranslationTests.setUpClass.__func__)
    setUp=fixtures.TranslationTests.setUp
    cleanup_window=fixtures.TranslationTests.cleanup_window
    pump=fixtures.TranslationTests.pump
    run_production=fixtures.TranslationTests.run_production

    def test_local_quality_failure_never_publishes_or_returns(self):
        original=self.backend.read
        def read(*args):
            result=original(*args)
            x,y=self.observed.position
            if 650<=x<750 or 1250<x<=1350:
                args[4][0,:]=2.4 if round(x/10)%2 else .2
            return result
        self.backend.read=read
        self.run_production()
        report=self.runner.services.report
        self.assertIsNone(self.state.registration)
        self.assertTrue(report['production_candidates']['initial_H']['marker_identity_match'])
        self.assertFalse(report['production_candidates']['initial_H']['marker_quality_pass'])
        self.assertNotEqual(report['return_status'],'PASS')
