"""Offline Module 7/5 boundary tests; analytical expectations are independent."""
from dataclasses import replace
from itertools import combinations
from math import cos, sin, tan, radians, dist
import unittest

from experiment.chip_layout import ChipLayout, SquareMarker, MSPixel
from experiment.marker_rotation import RotationFitResult, RotationLineFit
from experiment.marker_center_refinement import CenterRefinementResult
from experiment.marker_stage_registration import build_stage_registration
from experiment.stage_registration import (
    Orientation, StageRegistration, local_to_stage, stage_to_local, transform_chip_layout_to_stage,
)


# GDS bounding-box centers verified from S37a's lower Altug2009 occurrence.
# Names follow the committed manual-assignment example, not fabrication identity.
GDS_CENTERS = ((-498.192, -5100.475), (502.158, -5100.125),
               (-498.192, -4100.475), (501.808, -4100.475))


def inputs(angle=2, translation=(4000., -26000.)):
    line = RotationLineFit(-26000, 4000, -tan(radians(angle)), 0, 0, 0, (0, 0, 0))
    rotation = RotationFitResult(True, (), midpoint_fit=line, theta_mid_deg=angle)
    center = CenterRefinementResult(True, (), x_center_stage_um=translation[0],
        y_center_stage_um=translation[1], accepted_theta_deg=angle, horizontal_midpoint_fit=line)
    return rotation, center


def chip():
    return ChipLayout(SquareMarker(0, -4600, 500, 500),
                      [MSPixel(f'MS_{i}', x, y, 300, 300) for i, (x, y) in enumerate(GDS_CENTERS, 1)])


class IntegrationTests(unittest.TestCase):
    def reg(self, angle=2, translation=(4000., -26000.)):
        return build_stage_registration(*inputs(angle, translation)).registration

    def test_marker_origin(self):
        reg = self.reg()
        self.assertEqual(local_to_stage(0, 0, reg), (4000, -26000))
        self.assertEqual(transform_chip_layout_to_stage(chip(), reg).marker_stage_center, (4000, -26000))

    def test_zero_flip(self):
        self.assertEqual(local_to_stage(10, 20, self.reg(0)), (3990, -25980))

    def test_positive_sign(self):
        reg = self.reg(3, (0, 0))
        x, y = local_to_stage(0, 100, reg)
        self.assertLess(x, 0)
        self.assertGreater(y, 0)
        self.assertAlmostEqual(x/y, -tan(radians(3)))
        # Positive local X is mirrored before CCW rotation: both components negative.
        x, y = local_to_stage(100, 0, reg)
        self.assertLess(x, 0)
        self.assertLess(y, 0)

    def test_negative_sign_symmetry(self):
        plus = local_to_stage(0, 100, self.reg(3, (0, 0)))
        minus = local_to_stage(0, 100, self.reg(-3, (0, 0)))
        self.assertAlmostEqual(plus[0], -minus[0])
        self.assertAlmostEqual(plus[1], minus[1])

    def test_round_trip(self):
        for angle in (-3, 0, 3):
            reg = self.reg(angle)
            for xy in ((0, 0), (500, -500), (-600.2, 400.3)):
                self.assertLess(dist(stage_to_local(*local_to_stage(*xy, reg), reg), xy), 1e-9)

    def test_translation_invariance(self):
        a = local_to_stage(500, 300, self.reg())
        b = local_to_stage(500, 300, self.reg(2, (4012, -26034)))
        self.assertAlmostEqual(b[0]-a[0], 12)
        self.assertAlmostEqual(b[1]-a[1], -34)

    def test_marker_reference_invariance(self):
        layout = chip()
        reg = self.reg()
        snapshot = transform_chip_layout_to_stage(layout, reg)
        for p in layout.ms_pixels:
            manual = (p.center_gds_x-layout.marker.center_gds_x, p.center_gds_y-layout.marker.center_gds_y)
            self.assertEqual(snapshot.ms_stage_centers[p.name], local_to_stage(*manual, reg))

    def test_four_gds_targets_independent_equations(self):
        angle = 2.7
        reg = self.reg(angle)
        snapshot = transform_chip_layout_to_stage(chip(), reg)
        c, s = cos(radians(angle)), sin(radians(angle))
        for i, (gx, gy) in enumerate(GDS_CENTERS, 1):
            lx, ly = gx, gy+4600
            expected = (4000-c*lx-s*ly, -26000-s*lx+c*ly)
            self.assertLess(dist(snapshot.ms_stage_centers[f'MS_{i}'], expected), 1e-9)

    def test_exact_orientation(self):
        self.assertIs(self.reg().orientation, Orientation.FLIP_X)
        self.assertEqual(self.reg().orientation.matrix, ((-1, 0), (0, 1)))

    def test_unit_scale_pairwise_distances(self):
        reg = self.reg()
        layout = chip()
        out = transform_chip_layout_to_stage(layout, reg)
        for a, b in combinations(layout.ms_pixels, 2):
            expected = dist((a.center_local_x, a.center_local_y), (b.center_local_x, b.center_local_y))
            self.assertAlmostEqual(dist(out.ms_stage_centers[a.name], out.ms_stage_centers[b.name]), expected, places=9)

    def test_nonfinite_center(self):
        r, c = inputs()
        for value in (None, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                build_stage_registration(r, replace(c, x_center_stage_um=value))

    def test_invalid_local_inputs(self):
        for value in (float('nan'), float('inf'), None, True):
            with self.assertRaises(ValueError):
                local_to_stage(value, 0, self.reg())
            with self.assertRaises(ValueError):
                stage_to_local(0, value, self.reg())

    def test_failed_rotation(self):
        r, c = inputs()
        with self.assertRaisesRegex(ValueError, 'rotation_not_accepted'):
            build_stage_registration(replace(r, valid=False), c)

    def test_failed_center(self):
        r, c = inputs()
        with self.assertRaisesRegex(ValueError, 'center_not_accepted'):
            build_stage_registration(r, replace(c, valid=False))

    def test_failure_reasons_not_bypassed(self):
        r, c = inputs()
        for bad_r, bad_c in ((replace(r, reasons=('bad',)), c), (r, replace(c, reasons=('bad',)))):
            with self.assertRaises(ValueError):
                build_stage_registration(bad_r, bad_c)

    def test_mismatched_angle_or_fit(self):
        r, c = inputs()
        for bad in (replace(c, accepted_theta_deg=-2), replace(c, horizontal_midpoint_fit=None)):
            with self.assertRaisesRegex(ValueError, 'center_rotation_mismatch'):
                build_stage_registration(r, bad)

    def test_missing_angle(self):
        r, c = inputs()
        with self.assertRaisesRegex(ValueError, 'rotation_not_accepted'):
            build_stage_registration(replace(r, theta_mid_deg=None), c)

    def test_side_angles_ignored(self):
        r, c = inputs()
        self.assertEqual(build_stage_registration(r, c), build_stage_registration(
            replace(r, theta_left_deg=-40, theta_right_deg=40), c))

    def test_warnings_and_physical_status(self):
        r, c = inputs()
        result = build_stage_registration(replace(r, warnings=('side_warning',)),
                                          replace(c, warnings=('side_warning', 'center_warning')))
        self.assertEqual(result.warnings, ('side_warning', 'center_warning'))
        self.assertFalse(result.physically_validated)


class GDSIntegrationTests(unittest.TestCase):
    def test_actual_s37a_selection(self):
        from square_marker_stage_registration_check import DEFAULT_GDS, selected_layout, MARKER_ID, TARGET_IDS
        if not DEFAULT_GDS.is_file():
            self.skipTest('External S37a fixture unavailable; synthetic tests remain portable')
        assignments, layout = selected_layout(DEFAULT_GDS)
        self.assertEqual(assignments.marker.feature_id, MARKER_ID)
        self.assertEqual(tuple(assignments.ms_assignments), TARGET_IDS)
        self.assertEqual((layout.marker.center_gds_x, layout.marker.center_gds_y), (0, -4600))
        self.assertEqual((layout.marker.width, layout.marker.height), (500, 500))
        reg = build_stage_registration(*inputs()).registration
        result = transform_chip_layout_to_stage(layout, reg)
        c, s = cos(radians(2)), sin(radians(2))
        for p, (gx, gy) in zip(layout.ms_pixels, GDS_CENTERS):
            self.assertAlmostEqual(p.center_gds_x, gx)
            self.assertAlmostEqual(p.center_gds_y, gy)
            expected = (4000-c*gx-s*(gy+4600), -26000-s*gx+c*(gy+4600))
            self.assertLess(dist(result.ms_stage_centers[p.name], expected), 1e-9)


if __name__ == '__main__':
    unittest.main()
