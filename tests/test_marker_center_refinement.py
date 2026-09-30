"""Synthetic offline center geometry and fail-closed boundary tests."""
from dataclasses import replace
from math import cos, radians, tan
from random import Random
import unittest
from unittest.mock import patch

from experiment.marker_profile_classification import ProfileGeometry, classify_profiles
from experiment.marker_rotation import fit_rotation
from experiment.marker_center_refinement import CenterRefinementSettings, refine_marker_center
from experiment.reflection_analysis import EdgeResult
from experiment.scan_1d import ScanSettings, StageBounds, ScanPoint, ScanResult, ScanStatus


def rotation(angle=2, center=(1000., -2000.)):
    cx, cy = center
    t = tan(radians(angle))
    width = 500/cos(radians(angle))
    profiles = []
    for i, dy in enumerate((-120, -40, 40, 120)):
        y = cy+40+dy
        x = cx-t*(y-cy)
        profiles.append(ProfileGeometry(str(i), y, x-width/2, x+width/2, x, width, True))
    classification = classify_profiles(profiles, cy)
    result = fit_rotation(classification, tuple(profiles))
    assert result.valid, result.reasons
    return result


def vertical(angle=2, center=(1000., -2000.), dx=50, height=None):
    cx, cy = center
    xv = cx+dx
    yv = cy+tan(radians(angle))*dx
    height = 500/cos(radians(angle)) if height is None else height
    lo, hi = yv-height/2, yv+height/2
    settings = ScanSettings('y', cy-350, cy+350, 1, xv,
                            StageBounds(xv-1, xv+1, cy-351, cy+351, 'synthetic'))
    def signal(y):
        return max(0, min(1, (y-lo)/4+.5, (hi-y)/4+.5))
    points = [ScanPoint(i, p, p, signal(p[1]), 0, 0)
              for i, p in enumerate(settings.positions())]
    return ScanResult(settings, ScanStatus.COMPLETED, points)


class CenterTests(unittest.TestCase):
    def solve(self, angle=2, center=(1000., -2000.), dx=50, **kwargs):
        return refine_marker_center(rotation(angle, center), vertical(angle, center, dx), **kwargs)

    def assert_center(self, result, center=(1000., -2000.)):
        self.assertTrue(result.valid, result.reasons)
        self.assertAlmostEqual(result.x_center_stage_um, center[0], places=8)
        self.assertAlmostEqual(result.y_center_stage_um, center[1], places=8)

    def assert_failure(self, result, reason):
        self.assertFalse(result.valid)
        self.assertIn(reason, result.reasons)
        self.assertIsNone(result.x_center_stage_um)
        self.assertIsNone(result.y_center_stage_um)

    def test_zero_rotation(self):
        self.assert_center(self.solve(0))

    def test_positive_rotation(self):
        self.assert_center(self.solve(3))

    def test_negative_rotation(self):
        self.assert_center(self.solve(-3))

    def test_known_center_noiseless(self):
        self.assert_center(self.solve(1.7, (2345.25, -4567.75), -30), (2345.25, -4567.75))

    def test_translation_invariance(self):
        self.assert_center(self.solve(2, (1001000., -2002000.)), (1001000., -2002000.))

    def test_failed_rotation_no_analysis(self):
        with patch('experiment.marker_center_refinement.analyze_scan') as analyze:
            result = refine_marker_center(replace(rotation(), valid=False), vertical())
        analyze.assert_not_called()
        self.assert_failure(result, 'rotation_not_accepted')

    def test_missing_angle(self):
        self.assert_failure(refine_marker_center(replace(rotation(), theta_mid_deg=None), vertical()),
                            'missing_or_invalid_accepted_angle')

    def test_missing_fit(self):
        self.assert_failure(refine_marker_center(replace(rotation(), midpoint_fit=None), vertical()),
                            'missing_or_invalid_midpoint_fit')

    def test_invalid_edges(self):
        scan = vertical()
        scan.points = [replace(p, signal=0) for p in scan.points]
        self.assert_failure(refine_marker_center(rotation(), scan), 'invalid_vertical_edges')

    def test_x_spread(self):
        scan = vertical()
        scan.points[0] = replace(scan.points[0], measured_um=(1052., -2350.))
        self.assert_failure(refine_marker_center(rotation(), scan), 'vertical_x_spread_exceeded')

    def test_chord_height(self):
        self.assert_failure(refine_marker_center(rotation(), vertical(height=540)),
                            'vertical_chord_height_mismatch')

    def test_positive_corner(self):
        self.assert_failure(self.solve(dx=245), 'vertical_scan_not_safely_central')

    def test_negative_corner(self):
        self.assert_failure(self.solve(dx=-245), 'vertical_scan_not_safely_central')

    def test_exact_guard_boundaries(self):
        for dx in (-240, 240):
            with self.subTest(dx=dx):
                self.assert_failure(self.solve(0, dx=dx), 'vertical_scan_not_safely_central')
                self.assert_center(self.solve(0, dx=dx*.999))

    def test_shuffled_points_rejected(self):
        scan = vertical()
        Random(17).shuffle(scan.points)
        self.assert_failure(refine_marker_center(rotation(), scan), 'nonmonotonic_positions')

    def test_reverse_measured_order(self):
        scan = vertical()
        scan.points.reverse()
        self.assert_center(refine_marker_center(rotation(), scan))

    def test_constraint_residuals(self):
        result = self.solve()
        self.assertLess(abs(result.horizontal_constraint_residual_um), 1e-10)
        self.assertLess(abs(result.vertical_constraint_residual_um), 1e-10)

    def test_angle_sensitivity(self):
        # At theta=0, dxc/dtheta_rad=y_ref-yv=40, dyc/dtheta_rad=a-xv=-50.
        r = replace(rotation(0), theta_mid_standard_error_deg=.001)
        result = refine_marker_center(r, vertical(0))
        self.assertTrue(result.valid)
        eps = radians(.001)
        self.assertAlmostEqual(result.angle_plus_se.delta_x_um/eps, 40, delta=.002)
        self.assertAlmostEqual(result.angle_plus_se.delta_y_um/eps, -50, delta=.002)
        self.assertAlmostEqual(result.angle_minus_se.delta_x_um/eps, -40, delta=.002)
        self.assertAlmostEqual(result.angle_minus_se.delta_y_um/eps, 50, delta=.002)

    def test_side_angles_not_used(self):
        r = rotation()
        self.assertEqual(refine_marker_center(r, vertical()), refine_marker_center(
            replace(r, theta_left_deg=-9, theta_right_deg=9), vertical()))

    def test_inconsistent_angle_rejected(self):
        self.assert_failure(refine_marker_center(replace(rotation(), theta_mid_deg=4), vertical()),
                            'midpoint_angle_slope_mismatch')

    def test_rotation_failure_reasons_rejected(self):
        self.assert_failure(refine_marker_center(replace(rotation(), reasons=('bad',)), vertical()),
                            'rotation_not_accepted')

    def test_nonfinite_geometry(self):
        scan = vertical()
        scan.points[1] = replace(scan.points[1], measured_um=(float('nan'), -2349.))
        self.assert_failure(refine_marker_center(rotation(), scan), 'invalid_vertical_readback')

    def test_missing_readback(self):
        scan = vertical()
        scan.points[1] = replace(scan.points[1], measured_um=None)
        self.assert_failure(refine_marker_center(rotation(), scan), 'invalid_vertical_readback')

    def test_incomplete_scan(self):
        scan = vertical()
        scan.status = ScanStatus.FAILED
        self.assert_failure(refine_marker_center(rotation(), scan), 'incomplete_vertical_scan')

    def test_wrong_axis(self):
        scan = vertical()
        scan.settings = replace(scan.settings, axis='x')
        self.assert_failure(refine_marker_center(rotation(), scan), 'not_vertical_scan')

    def test_incomplete_points(self):
        scan = vertical()
        scan.points.pop()
        self.assert_failure(refine_marker_center(rotation(), scan), 'incomplete_scan')

    def test_commanded_x_not_used(self):
        scan = vertical()
        scan.points = [replace(p, commanded_um=(9999., p.commanded_um[1])) for p in scan.points]
        result = refine_marker_center(rotation(), scan)
        self.assert_center(result)
        self.assertEqual(result.vertical_scan_x_um, 1050)

    def test_initial_center_comparison_only(self):
        result = self.solve(initial_center_um=(900., -2010.))
        self.assert_center(result)
        self.assertAlmostEqual(result.center_correction_from_initial_x_um, 100)
        self.assertAlmostEqual(result.center_correction_from_initial_y_um, 10)
        self.assertAlmostEqual(result.total_correction_um, (100**2+10**2)**.5)

    def test_warnings_preserved(self):
        r = replace(rotation(), warnings=('left_right_angle_disagreement_warning',))
        result = refine_marker_center(r, vertical())
        self.assertTrue(result.valid)
        self.assertEqual(result.warnings, r.warnings)
        self.assertEqual(refine_marker_center(r, vertical(height=540)).warnings, r.warnings)

    def test_invalid_settings(self):
        for value in (0, -1, float('nan'), True):
            with self.assertRaises(ValueError):
                CenterRefinementSettings(max_chord_height_error_um=value)

    def test_invalid_angle_se(self):
        self.assert_failure(refine_marker_center(replace(rotation(), theta_mid_standard_error_deg=None),
                                                 vertical()), 'invalid_angle_standard_error')

    def test_inconsistent_edge_result(self):
        bad = EdgeResult(True, left_edge_um=0, right_edge_um=500, midpoint_um=1,
                         width_um=500, position_source='measured')
        with patch('experiment.marker_center_refinement.analyze_scan', return_value=bad):
            self.assert_failure(refine_marker_center(rotation(), vertical()), 'invalid_vertical_edge_geometry')


if __name__ == '__main__':
    unittest.main()
