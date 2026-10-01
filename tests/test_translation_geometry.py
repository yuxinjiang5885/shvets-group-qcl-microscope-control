"""Marker-scaled production geometry; no hardware or alternate edge algorithm."""
from pathlib import Path
import unittest
import gdstk

from experiment.scan_1d import StageBounds
from ui.translation_geometry import production_geometry, production_spec, requested_geometry
from ui.h_only_validation import HOnlySpec
from ui.hv_validation import HVSpec
import test_translation_localization as fixtures


class GeometryTests(unittest.TestCase):
    def test_manual_endpoint_examples(self):
        for step,half,points in ((10,630,127),(20,640,65),(25,625,51),(15,630,85)):
            with self.subTest(step=step):
                mode,requested,actual_step,actual=requested_geometry(500,625,step)
                self.assertEqual((mode,requested,actual_step,actual),('override',625,step,half))
                self.assertEqual(2*actual/step+1,points)

    def test_invalid_overrides(self):
        for half,step in ((0,10),(-1,10),(625,0),(625,-1),(float('nan'),10),
                          (625,float('inf')),(625,2.5),(625,500)):
            with self.subTest(half=half,step=step), self.assertRaises(ValueError):
                requested_geometry(500,half,step)
    def spec(self, side=500, xy=(4200,-26100)):
        return production_spec(xy,StageBounds(-100000,100000,-100000,100000,'test'),side)

    def test_500_defaults_and_exact_endpoints(self):
        self.assertEqual(production_geometry(500),(630,15))
        s=self.spec();h=s.scan();v=s.vertical(4214.8)
        self.assertEqual((h.start_um,h.end_um,h.fixed_um),(3570,4830,-26100))
        self.assertEqual((v.start_um,v.end_um,v.fixed_um),(-26730,-25470,4215))
        for scan in (h,v):
            self.assertEqual(scan.step_um,15)
            self.assertEqual(scan.end_um-scan.start_um,1260)
            self.assertEqual(len(scan.positions()),85)
            axis=0 if scan.axis=='x' else 1
            self.assertEqual(scan.positions()[0][axis],scan.start_um)
            self.assertEqual(scan.positions()[-1][axis],scan.end_um)

    def test_outward_adjustment_integer_and_symmetric(self):
        for side in (20,20.1,39.9,99,123.4,333,501,999.5):
            with self.subTest(side=side):
                half,step=production_geometry(side)
                self.assertGreaterEqual(half,1.25*side)
                self.assertLess(half-1.25*side,step+1e-10)
                self.assertLessEqual(step,min(15,side/20))
                s=self.spec(side,(-13,27))
                for scan in (s.scan(),s.vertical(-12.5)):
                    self.assertTrue(all(v==round(v) for xy in scan.positions() for v in xy))
                    self.assertEqual(len(scan.positions()),2*half//step+1)
                self.assertEqual((s.scan().start_um+s.scan().end_um)/2,-13)
                self.assertEqual((s.vertical(0).start_um+s.vertical(0).end_um)/2,27)

    def test_small_marker_step_and_unrepresentable_rejection(self):
        self.assertEqual(production_geometry(100),(125,5))
        self.assertEqual(production_geometry(20),(25,1))
        for side in (19.9,0,-1,float('nan'),float('inf')):
            with self.subTest(side=side), self.assertRaises(ValueError):production_geometry(side)

    def test_envelope_cannot_expand_at_run_time(self):
        with self.assertRaises(ValueError):
            production_spec((1000,2000),StageBounds(649,1351,1649,2351,'test'),500)
        s=self.spec()
        with self.assertRaises(ValueError):s.vertical(s.scan().end_um+1)

    def test_reference_defaults_unchanged(self):
        bounds=StageBounds(-1000,1000,-1000,1000,'test')
        for cls in (HOnlySpec,HVSpec):
            s=cls((0,0),bounds)
            self.assertEqual((s.scan().start_um,s.scan().end_um,s.step_um),(-350,350,10))
            self.assertEqual(len(s.scan().positions()),71)


class PreviewTests(unittest.TestCase):
    def test_override_preview_execution_and_reset_without_hardware(self):
        c=self.select_fixture_marker()
        c.production_override.setChecked(True)
        c.production_half.setText('625');c.production_step.setText('20')
        c.translation_preview_button.click()
        spec=c.reviewed[0]
        self.assertEqual(spec.production_geometry,('override',625,20))
        self.assertEqual(len(spec.scan().positions()),65)
        self.assertIn('1280',c.result.text())
        self.assertEqual(c.build()[0],spec)
        for field in (c.production_half,c.production_step):
            c.translation_clearance.setChecked(True)
            field.setText('800' if field is c.production_half else '10')
            self.assertIsNone(c.reviewed);self.assertFalse(c.translation_clearance.isChecked())
            c.translation_preview_button.click()
        before=list(self.log);ni=list(self.backend.calls);registration=self.state.registration
        c.production_reset.click()
        self.assertEqual(self.log,before);self.assertEqual(self.backend.calls,ni)
        self.assertIs(self.state.registration,registration)
        self.assertFalse(c.production_override.isChecked())
        self.assertEqual(c.production_half.text(),'625');self.assertEqual(c.production_step.text(),'15')
        self.assertIsNone(c.reviewed)
        self.assertTrue(c.production_half.isReadOnly())

    def test_toggle_invalidates_preview(self):
        c=self.select_fixture_marker();c.translation_preview_button.click()
        c.translation_clearance.setChecked(True)
        c.production_override.setChecked(True)
        self.assertIsNone(c.reviewed);self.assertFalse(c.translation_clearance.isChecked())

    def test_override_run_uses_preview_and_independent_marker_prior(self):
        c=self.select_fixture_marker()
        c.production_override.setChecked(True)
        c.production_half.setText('800');c.production_step.setText('20')
        c.fields['note'].setText('fake parameter study');c.fields['output'].setText(self.tmp.name)
        c.translation_preview_button.click();spec=c.reviewed[0]
        for check in c.checks:check.setChecked(True)
        c.translation_clearance.setChecked(True)
        self.window.auto_relocation.locate_button.click()
        self.pump(lambda:not self.runner.busy)
        self.assertIsNotNone(self.state.registration,self.controller.reasons)
        self.assertEqual(self.runner.services.spec,spec)
        report=self.runner.services.report
        self.assertEqual(report['geometry_mode'],'override')
        self.assertEqual(report['points_per_axis'],81)
        self.assertEqual(report['total_scan_points'],162)
        for axis,anchor in (('initial_H',1000),('initial_V',2000)):
            diag=report['production_candidates'][axis]
            self.assertEqual(diag['expected_dimension_um'],500)
            self.assertEqual(diag['width_tolerance_um'],100)
            self.assertEqual(diag['anchor_um'],anchor)
            self.assertEqual(diag['accepted_candidate_count'],1)
            self.assertGreaterEqual(report['scan_duration_s'][axis],0)
    setUpClass=classmethod(fixtures.TranslationTests.setUpClass.__func__)
    setUp=fixtures.TranslationTests.setUp
    cleanup_window=fixtures.TranslationTests.cleanup_window
    pump=fixtures.TranslationTests.pump
    select_fixture_marker=fixtures.TranslationTests.select_fixture_marker

    def test_preview_geometry_clearance_and_reference_switch(self):
        c=self.select_fixture_marker();c.translation_preview_button.click()
        spec=c.reviewed[0]
        self.assertEqual(spec.step_um,15)
        self.assertEqual((spec.bounds.x_min_um,spec.bounds.x_max_um),(369,1631))
        self.assertEqual((spec.bounds.y_min_um,spec.bounds.y_max_um),(1369,2631))
        for text in ('625','1260','15','85','DYNAMIC','Return target','Clearance bounds'):
            self.assertIn(text,c.result.text())
        c.hv_preview_button.click()
        self.assertEqual(c.reviewed[0].step_um,10)
        self.assertEqual(len(c.reviewed[0].scan().positions()),71)

    def test_selected_GDS_size_not_archived_constant(self):
        c=self.window.h_only_controls
        path=Path(self.tmp.name)/'small.gds'
        lib=gdstk.Library();cell=lib.new_cell('small')
        cell.add(gdstk.rectangle((-100,-100),(100,100)));lib.write_gds(path)
        selection=self.window.auto_relocation.selection
        selection.load_file(path)
        model=selection.layout_model
        selection.select_feature(next(f for f in model.children(model.features()[0]) if f.width_um==200))
        selection.assign_marker()
        c.translation_preview_button.click()
        self.assertIsNotNone(c.reviewed,c.result.text())
        spec=c.reviewed[0]
        self.assertEqual(spec.side_um,200)
        self.assertEqual(spec.step_um,10)
        self.assertEqual(spec.scan().end_um-spec.scan().start_um,500)

    def test_production_end_to_end_85_points_and_publication(self):
        c=self.select_fixture_marker()
        c.fields['note'].setText('fake production');c.fields['output'].setText(self.tmp.name)
        c.translation_preview_button.click()
        for checkbox in c.checks:checkbox.setChecked(True)
        c.translation_clearance.setChecked(True)
        self.window.auto_relocation.locate_button.click()
        self.pump(lambda:not self.runner.busy)
        self.assertIsNotNone(self.state.registration,self.controller.reasons)
        self.assertEqual(self.state.registration.registration_mode,'translation_only')
        self.assertFalse(self.state.registration.rotation_calibrated)
        report=self.runner.services.report
        self.assertEqual((report['points'],report['v_points'],report['step_um']),(85,85,15))
        self.assertEqual(report['actual_span_um'],1260)
        self.assertEqual([p.name for p in self.runner.services.journals],['initial_H.jsonl','initial_V.jsonl'])
        self.assertEqual(report['return_status'],'PASS')
