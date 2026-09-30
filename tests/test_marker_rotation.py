"""Synthetic offline tests; no measured journals or hardware dependencies."""
import unittest
from dataclasses import replace
from math import atan, degrees, radians, tan, sqrt
from random import Random
from unittest.mock import patch

import experiment.marker_rotation as rotation
from experiment.marker_profile_classification import (
    ProfileGeometry, ProfileClass, classify_profiles,
)
from experiment.marker_rotation import RotationSettings, fit_rotation


def profiles(angle=0, ys=(-160, -80, 0, 80, 160), noise=0):
    rng = Random(37)
    result = []
    for i, y in enumerate(ys):
        mid = 4200 - tan(radians(angle))*y
        left = mid - 250 + rng.uniform(-noise, noise)
        right = mid + 250 + rng.uniform(-noise, noise)
        result.append(ProfileGeometry(str(i), y, left, right,
                                      (left+right)/2, right-left, True))
    return tuple(result)


def shift(p, left=0, right=0):
    a, b = p.left_edge_um+left, p.right_edge_um+right
    return replace(p, left_edge_um=a, right_edge_um=b,
                   midpoint_um=(a+b)/2, width_um=b-a)


class RotationTests(unittest.TestCase):
    def fit(self, p, settings=RotationSettings()):
        c = classify_profiles(p, 0)
        self.assertTrue(c.sufficient_for_rotation_fit, c.reasons)
        return fit_rotation(c, tuple(r.profile for r in c.profiles
                                    if r.classification is ProfileClass.CENTRAL), settings)

    def test_zero_rotation(self):
        r = self.fit(profiles())
        self.assertTrue(r.valid)
        self.assertEqual(r.accepted_theta_deg, 0)
        self.assertEqual(r.theta_mid_standard_error_deg, 0)
        self.assertEqual(r.midpoint_fit.y_ref_um, 0)
        self.assertEqual(r.width_std_um, 0)

    def test_positive_rotation(self):
        r = self.fit(profiles(3))
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.accepted_theta_deg, 3)

    def test_negative_rotation(self):
        r = self.fit(profiles(-3))
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.accepted_theta_deg, -3)

    def test_independent_edge_noise(self):
        r = self.fit(profiles(2, noise=.2))
        self.assertTrue(r.valid)
        self.assertGreater(r.theta_mid_standard_error_deg, 0)
        self.assertLess(abs(r.theta_mid_deg-2), .1)

    def test_midpoint_primary_not_mean_side_angles(self):
        p = tuple(shift(q, .003*q.measured_y_um, -.003*q.measured_y_um)
                  for q in profiles(4))
        r = self.fit(p)
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.theta_mid_deg, 4)
        self.assertIn('left_right_angle_disagreement_warning', r.warnings)
        self.assertEqual(r.accepted_theta_deg, -degrees(atan(r.midpoint_fit.slope)))
        self.assertGreater(abs(r.theta_mid_deg-(r.theta_left_deg+r.theta_right_deg)/2), 1e-7)

    def test_shuffled(self):
        p = profiles(2, noise=.2)
        c = classify_profiles(p, 0)
        expected = fit_rotation(c, p)
        shuffled = list(p)
        Random(4).shuffle(shuffled)
        self.assertEqual(fit_rotation(replace(c, profiles=tuple(reversed(c.profiles))), shuffled), expected)

    def forged_geometry(self, p):
        # Deliberately inconsistent approval tests the production boundary;
        # these records could not pass the real classifier's leverage gates.
        c = classify_profiles(profiles(), 0)
        rows = tuple(replace(c.profiles[i], profile=q) for i, q in enumerate(p))
        return fit_rotation(replace(c, profiles=rows), p)

    def test_insufficient_count(self):
        r = self.forged_geometry(profiles()[:2])
        self.assertFalse(r.valid)
        self.assertIn('insufficient_central_profiles', r.reasons)
        self.assertIsNone(r.left_fit)

    def test_insufficient_distinct_y(self):
        r = self.forged_geometry(profiles(ys=(0, 0, 0)))
        self.assertIn('insufficient_distinct_y', r.reasons)
        self.assertIsNone(r.accepted_theta_deg)

    def test_insufficient_span(self):
        r = self.fit(profiles(ys=(-20, 0, 20)))
        self.assertFalse(r.valid)
        self.assertIn('insufficient_y_span', r.reasons)

    def test_side_disagreement(self):
        p = tuple(shift(q, .003*q.measured_y_um, -.003*q.measured_y_um)
                  for q in profiles())
        r = self.fit(p)
        self.assertTrue(r.valid)
        self.assertGreater(r.left_right_angle_disagreement_deg, .25)
        self.assertLess(r.left_right_angle_disagreement_deg, 1)
        self.assertEqual(r.warnings, ('left_right_angle_disagreement_warning',))
        self.assertEqual(r.reasons, ())
        self.assertEqual(r.accepted_theta_deg, r.theta_mid_deg)
        self.assertFalse(r.diagnostic_only)

    def test_below_warning_threshold(self):
        p = tuple(shift(q, .001*q.measured_y_um, -.001*q.measured_y_um)
                  for q in profiles())
        r = self.fit(p)
        self.assertTrue(r.valid)
        self.assertLess(r.left_right_angle_disagreement_deg, .25)
        self.assertEqual(r.warnings, ())
        self.assertEqual(r.accepted_theta_deg, r.theta_mid_deg)

    def controlled_side_angles(self, disagreement):
        # Isolate exact production-QC boundaries from coordinate roundoff and
        # the classifier's independent screening policy. OLS is tested elsewhere.
        p = profiles()
        c = classify_profiles(p, 0)
        base = rotation._fit_line(tuple(q.midpoint_um for q in p),
                                  tuple(q.measured_y_um for q in p))
        b = tan(radians(disagreement/2))
        fits = (replace(base, slope=-b), replace(base, slope=b), base)
        with patch.object(rotation, '_fit_line', side_effect=fits):
            return fit_rotation(c, p)

    def test_exact_warning_boundary(self):
        r = self.controlled_side_angles(.25)
        self.assertEqual(r.left_right_angle_disagreement_deg, .25)
        self.assertTrue(r.valid)
        self.assertEqual(r.warnings, ())
        self.assertEqual(r.accepted_theta_deg, r.theta_mid_deg)

    def test_exact_hard_boundary(self):
        r = self.controlled_side_angles(1)
        self.assertEqual(r.left_right_angle_disagreement_deg, 1)
        self.assertTrue(r.valid)
        self.assertEqual(r.reasons, ())
        self.assertEqual(r.warnings, ('left_right_angle_disagreement_warning',))
        self.assertEqual(r.accepted_theta_deg, r.theta_mid_deg)

    def test_above_hard_boundary(self):
        r = self.controlled_side_angles(1.1)
        self.assertGreater(r.left_right_angle_disagreement_deg, 1)
        self.assertFalse(r.valid)
        self.assertIsNone(r.accepted_theta_deg)
        self.assertEqual(r.reasons, ('excessive_left_right_angle_disagreement',))
        self.assertEqual(r.warnings, ('left_right_angle_disagreement_warning',))

    def test_warning_plus_hard_residual_failure(self):
        p = tuple(shift(q, .003*q.measured_y_um, -.003*q.measured_y_um)
                  for q in profiles())
        p = p[:2]+(shift(p[2], 2.6, 2.6),)+p[3:]
        r = self.fit(p)
        self.assertGreater(r.midpoint_rms_residual_um, 1)
        self.assertIn('midpoint_rms_residual_exceeded', r.reasons)
        self.assertIn('left_right_angle_disagreement_warning', r.warnings)
        self.assertFalse(r.valid)
        self.assertIsNone(r.accepted_theta_deg)

    def test_rms_residual(self):
        p = profiles()
        p = p[:2]+(shift(p[2], 2, 2),)+p[3:]
        r = self.fit(p, RotationSettings(max_rms_residual_um=.5))
        self.assertIn('midpoint_rms_residual_exceeded', r.reasons)

    def test_max_residual(self):
        p = profiles()
        p = p[:2]+(shift(p[2], 2, 2),)+p[3:]
        r = self.fit(p, RotationSettings(max_abs_residual_um=1))
        self.assertIn('midpoint_max_residual_exceeded', r.reasons)
        self.assertNotIn('midpoint_rms_residual_exceeded', r.reasons)

    def test_width_variation(self):
        p = tuple(shift(q, 0, .002*q.measured_y_um) for q in profiles())
        r = self.fit(p, RotationSettings(max_width_peak_to_peak_um=.5))
        self.assertIn('width_variation_exceeded', r.reasons)
        self.assertTrue(self.fit(p, RotationSettings(max_width_peak_to_peak_um=None)).valid)

    def test_uncertainty_decreases_with_span(self):
        short = self.fit(profiles(ys=(-80, -40, 0, 40, 80), noise=.2))
        long = self.fit(profiles(noise=.2))
        self.assertAlmostEqual(short.theta_mid_standard_error_deg /
                               long.theta_mid_standard_error_deg, 2, places=5)

    def test_uncertainty_formula(self):
        r = self.fit(profiles(3, noise=.2))
        f = r.midpoint_fit
        expected = degrees(f.slope_standard_error/(1+f.slope**2))
        self.assertAlmostEqual(r.theta_mid_standard_error_deg, expected, places=14)
        sse = sum(v*v for v in f.residuals_um)
        syy = sum((p.measured_y_um-f.y_ref_um)**2 for p in r.per_profile)
        self.assertAlmostEqual(f.slope_standard_error, sqrt(sse/3/syy))

    def test_noncentral_input_rejected(self):
        p = profiles()
        c = classify_profiles(p, 0)
        for state in (ProfileClass.CORNER_AFFECTED, ProfileClass.INCONSISTENT, ProfileClass.INVALID):
            with self.subTest(state=state):
                changed = replace(c, profiles=c.profiles[:-1]+(replace(c.profiles[-1], classification=state),))
                r = fit_rotation(changed, p)
                self.assertIn('central_set_mismatch', r.reasons)
                self.assertIsNone(r.left_fit)

    def test_classifier_insufficient(self):
        p = profiles()
        r = fit_rotation(replace(classify_profiles(p, 0), sufficient_for_rotation_fit=False), p)
        self.assertIn('classifier_not_sufficient', r.reasons)

    def test_classifier_fits_missing(self):
        p = profiles()
        r = fit_rotation(replace(classify_profiles(p, 0), usable_final_fits=None), p)
        self.assertIn('classifier_fits_unavailable', r.reasons)

    def test_no_deletion_on_qc_failure(self):
        p = tuple(shift(q, .003*q.measured_y_um, -.003*q.measured_y_um)
                  for q in profiles())
        with patch.object(rotation, '_fit_line', wraps=rotation._fit_line) as fit:
            # Preserve the no-deletion-on-failure test with an explicit stricter
            # synthetic policy; production defaults are unchanged.
            r = self.fit(p, RotationSettings(
                warning_left_right_angle_disagreement_deg=.1,
                hard_max_left_right_angle_disagreement_deg=.25))
        self.assertFalse(r.valid)
        self.assertEqual(fit.call_count, 3)
        self.assertEqual(r.used_profile_ids, tuple(q.identifier for q in p))
        self.assertEqual(len(r.per_profile), len(p))

    def test_subset_and_altered_geometry_rejected(self):
        p = profiles()
        c = classify_profiles(p, 0)
        for changed in (p[:-1], (shift(p[0], 1, 1),)+p[1:]):
            self.assertIn('central_set_mismatch', fit_rotation(c, changed).reasons)

    def test_mean_y_reference_and_translation_invariance(self):
        p = profiles(2, noise=.2)
        c = classify_profiles(p, 0)
        original = fit_rotation(c, p)
        translated = tuple(replace(q, measured_y_um=q.measured_y_um-26111) for q in p)
        ct = classify_profiles(translated, -26100)  # Center used only for classification.
        r = fit_rotation(ct, translated)
        self.assertTrue(r.valid)
        self.assertEqual(r.midpoint_fit.y_ref_um, -26111)
        self.assertEqual(r.theta_mid_deg, original.theta_mid_deg)

    def test_invalid_settings(self):
        for kw in ({'minimum_profiles': 2}, {'minimum_y_span_um': 0},
                   {'max_rms_residual_um': float('nan')}, {'max_abs_residual_um': True},
                   {'warning_left_right_angle_disagreement_deg': 2},
                   {'hard_max_left_right_angle_disagreement_deg': float('inf')}):
            with self.assertRaises(ValueError):
                RotationSettings(**kw)

    def test_nonfinite_geometry_boundary(self):
        p = profiles()
        bad = (replace(p[0], measured_y_um=float('inf')),)+p[1:]
        r = self.forged_geometry(bad)
        self.assertIn('invalid_profile_geometry', r.reasons)


if __name__ == '__main__':
    unittest.main()
