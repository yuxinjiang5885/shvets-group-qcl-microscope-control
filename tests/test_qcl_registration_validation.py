"""Offline CSV, selected geometry and stage-coordinate overlay tests."""
from dataclasses import replace
from math import dist
from pathlib import Path
import tempfile
import unittest

import gdstk
import numpy as np

from experiment.gds_layout import load_gds
from experiment.layout_assignment import LayoutAssignments
from experiment.stage_registration import StageRegistration, local_to_stage
from experiment.marker_stage_registration import OfflineMarkerRegistration, build_stage_registration
from experiment.marker_rotation import RotationFitResult
from experiment.marker_center_refinement import CenterRefinementResult
from experiment.qcl_registration_validation import (
    load_qcl_image, feature_polygons, predict_selection, plot_overlay,
)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root/'test.csv'
        np.savetxt(self.csv, np.arange(12).reshape(3, 4), delimiter=',')
        lib = gdstk.Library()
        cell = lib.new_cell('root')
        cell.add(gdstk.rectangle((0, 0), (10, 10)),
                 gdstk.Polygon([(20, 0), (24, 0), (20, 4)]),
                 gdstk.rectangle((0, 20), (2, 30)))
        lib.write_gds(self.root/'test.gds')
        self.model = load_gds(self.root/'test.gds')
        features = self.model.children(self.model.features()[0])
        self.marker = next(f for f in features if f.width_um == 10)
        self.a = next(f for f in features if f.width_um == 4)
        self.b = next(f for f in features if f.width_um == 2)
        self.reg = OfflineMarkerRegistration(StageRegistration(100, -200, 0), ('test_warning',))

    def image(self, **kwargs):
        settings = dict(x_origin_um=10., y_origin_um=20., x_pixels=4, y_pixels=3, spacing_um=2.)
        settings.update(kwargs)
        return load_qcl_image(self.csv, **settings)

    def selections(self, targets=True, reverse=False):
        state = LayoutAssignments(self.model)
        state.set_marker(self.marker)
        if targets:
            rows = [('alpha', self.a), ('beta', self.b)]
            for name, f in reversed(rows) if reverse else rows:
                state.add_ms(f, name)
        return state

    def test_coordinate_construction(self):
        image = self.image()
        np.testing.assert_array_equal(image.x_um, [12, 14, 16, 18])
        np.testing.assert_array_equal(image.y_um, [20, 18, 16])

    def test_boundary_not_first_pixel(self):
        self.assertEqual(self.image().extent_um, (11, 19, 15, 21))
        self.assertEqual(self.image().x_um[0], 12)

    def test_y_decreases(self):
        self.assertTrue(np.all(np.diff(self.image().y_um) == -2))

    def test_shape_no_silent_transpose(self):
        with self.assertRaisesRegex(ValueError, 'no reshaping'):
            self.image(x_pixels=3, y_pixels=4)

    def test_signal_no_transpose_or_reversal(self):
        np.testing.assert_array_equal(self.image().signal, np.arange(12).reshape(3, 4))

    def test_marker_origin(self):
        p = predict_selection(self.selections(), self.reg)[0]
        self.assertEqual(p.local_center_um, (0, 0))
        self.assertEqual(p.stage_center_um, (100, -200))

    def test_full_polygon_not_bbox(self):
        p = predict_selection(self.selections(), self.reg)[1]
        self.assertEqual(len(p.gds_polygons_um[0]), 3)
        expected = tuple((100-(x-5), -200+(y-5)) for x, y in p.gds_polygons_um[0])
        self.assertEqual(p.stage_polygons_um[0], expected)

    def test_feature_center(self):
        p = predict_selection(self.selections(), self.reg)[1]
        self.assertEqual(p.gds_center_um, (22, 2))
        self.assertEqual(p.local_center_um, (17, -3))
        self.assertEqual(p.stage_center_um, (83, -203))

    def test_flip_x(self):
        p = predict_selection(self.selections(), self.reg)[1]
        self.assertEqual(p.stage_center_um[0]-100, -p.local_center_um[0])

    def test_positive_rotation(self):
        reg = replace(self.reg, registration=StageRegistration(100, -200, 90))
        p = predict_selection(self.selections(), reg)[1]
        self.assertAlmostEqual(p.stage_center_um[0], 103)
        self.assertAlmostEqual(p.stage_center_um[1], -217)

    def test_multiple_features(self):
        self.assertEqual(len(predict_selection(self.selections(), self.reg)), 3)

    def test_selection_order_independent(self):
        first = {p.feature_id: p for p in predict_selection(self.selections(), self.reg)}
        second = {p.feature_id: p for p in predict_selection(self.selections(reverse=True), self.reg)}
        self.assertEqual(first, second)

    def test_reference_excluded_from_independent_count(self):
        predictions = predict_selection(self.selections(), self.reg)
        self.assertEqual(sum(not p.is_reference for p in predictions), 2)
        self.assertEqual(sum(not p.is_reference for p in predict_selection(self.selections(False), self.reg)), 0)

    def test_upstream_invalid(self):
        with self.assertRaises(ValueError):
            build_stage_registration(RotationFitResult(False, ('rejected',)), CenterRefinementResult(False, ('rejected',)))
        with self.assertRaises(ValueError):
            predict_selection(self.selections(), None)

    def test_nonfinite_rejected(self):
        for v in (float('nan'), float('inf')):
            a = np.ones((3, 4)); a[0, 0] = v
            np.savetxt(self.csv, a, delimiter=',')
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                self.image()

    def test_rigid_distances(self):
        p = predict_selection(self.selections(), self.reg)
        self.assertAlmostEqual(dist(p[1].stage_center_um, p[2].stage_center_um),
                               dist(p[1].gds_center_um, p[2].gds_center_um))

    def test_plot_stage_coordinates(self):
        image = self.image()
        fig = plot_overlay(image, predict_selection(self.selections(), self.reg))
        ax = fig.axes[0]
        raster = ax.images[0]
        self.assertEqual(tuple(raster.get_extent()), image.extent_um)
        self.assertEqual(raster.origin, 'upper')
        self.assertEqual(ax.get_aspect(), 1)
        left, right, bottom, top = raster.get_extent()
        np.testing.assert_allclose(left+(np.arange(4)+.5)*(right-left)/4, image.x_um)
        np.testing.assert_allclose(top-(np.arange(3)+.5)*(top-bottom)/3, image.y_um)
        fig.clear()

    def test_multiple_polygons_and_placement(self):
        lib = gdstk.Library(); cell = lib.new_cell('leaf')
        cell.add(gdstk.rectangle((0, 0), (1, 2)), gdstk.rectangle((3, 0), (4, 2)))
        root = lib.new_cell('parent'); root.add(gdstk.Reference(cell, origin=(10, 20)))
        lib.write_gds(self.root/'multi.gds')
        layout = load_gds(self.root/'multi.gds')
        f = layout.children(layout.features('parent')[0])[0]
        polys = feature_polygons(layout, f)
        self.assertEqual(len(polys), 2)
        self.assertEqual(min(x for p in polys for x, y in p), 10)
        self.assertEqual(min(y for p in polys for x, y in p), 20)

    def test_geometry_budget_fails_not_envelope(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            feature_polygons(self.model, self.marker, max_vertices=2)

    def test_missing_marker(self):
        with self.assertRaisesRegex(ValueError, 'reference'):
            predict_selection(LayoutAssignments(self.model), self.reg)


if __name__ == '__main__':
    unittest.main()
