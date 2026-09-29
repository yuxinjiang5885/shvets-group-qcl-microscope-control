"""Synthetic, hardware-independent tests for square-profile classification."""
import unittest
from dataclasses import replace
from math import radians, cos, sin, tan
from random import Random
from unittest.mock import patch
import experiment.marker_profile_classification as classifier
from experiment.marker_profile_classification import (
    ProfileGeometry, ProfileClass as C, ClassificationSettings, classify_profiles,
)


def square(y, angle=0, identifier=None):
    # Intersect a horizontal line with both rotated-square inequalities.
    t = radians(angle)
    c, s = cos(t), sin(t)
    bounds = [((-250-y*s)/c, (250-y*s)/c)]
    if abs(s) > 1e-12:
        xs = [(y*c-250)/s, (y*c+250)/s]
        bounds.append((min(xs), max(xs)))
    left, right = max(b[0] for b in bounds), min(b[1] for b in bounds)
    return ProfileGeometry(str(y) if identifier is None else identifier, y, left, right,
                           (left+right)/2, right-left, True)


def altered(p, left=0, right=0):
    a, b = p.left_edge_um+left, p.right_edge_um+right
    return replace(p, left_edge_um=a, right_edge_um=b, midpoint_um=(a+b)/2, width_um=b-a)


class ClassificationTests(unittest.TestCase):
    def base(self, angle=0):
        return [square(y, angle) for y in (-160, -80, 0, 80, 160)]

    def test_unrotated(self):
        r = classify_profiles(self.base(), 0)
        self.assertTrue(r.sufficient_for_rotation_fit)
        self.assertEqual(len(r.central_identifiers), 5)
        self.assertEqual(r.provisional_rotation_deg, 0)
        self.assertEqual(len(r.usable_final_fits), 3)

    def test_positive_rotation(self):
        r = classify_profiles(self.base(4), 0)
        self.assertTrue(r.sufficient_for_rotation_fit)
        self.assertAlmostEqual(r.provisional_rotation_deg, 4)

    def test_negative_rotation(self):
        r = classify_profiles(self.base(-4), 0)
        self.assertTrue(r.sufficient_for_rotation_fit)
        self.assertAlmostEqual(r.provisional_rotation_deg, -4)

    def test_top_corner(self):
        r = classify_profiles(self.base(5)+[square(250, 5)], 0)
        self.assertIn('250', r.corner_affected_identifiers)
        self.assertTrue(r.sufficient_for_rotation_fit)

    def test_bottom_corner(self):
        r = classify_profiles(self.base(-5)+[square(-250, -5)], 0)
        self.assertIn('-250', r.corner_affected_identifiers)

    def test_corrupted_left_is_not_corner(self):
        p = self.base(); p[-1] = altered(p[-1], left=12)
        r = classify_profiles(p, 0)
        self.assertIn('160', r.inconsistent_identifiers)
        self.assertNotIn('160', r.corner_affected_identifiers)
        self.assertTrue(r.sufficient_for_rotation_fit)

    def test_translated_edges(self):
        p = self.base(); p[-1] = altered(p[-1], 12, 12)
        r = classify_profiles(p, 0)
        row = next(r for r in r.profiles if r.profile.identifier == '160')
        self.assertEqual(row.classification, C.INCONSISTENT)
        self.assertEqual(row.width_deviation_um, 0)
        self.assertIn('midpoint_um_seed_residual_outlier', row.reasons)

    def test_invalid_edge(self):
        p = self.base()+[replace(square(200), edge_valid=False)]
        self.assertIn('200', classify_profiles(p, 0).invalid_identifiers)

    def test_shuffled(self):
        p = self.base(3)+[square(250, 3)]
        a = classify_profiles(p, 0)
        Random(42).shuffle(p)
        self.assertEqual(a, classify_profiles(p, 0))

    def test_insufficient(self):
        r = classify_profiles(self.base()[:2], 0)
        self.assertFalse(r.sufficient_for_rotation_fit)
        self.assertIsNone(r.provisional_rotation_deg)
        self.assertIsNone(r.usable_final_fits)

    def test_realistic_noise(self):
        rng = Random(21)
        p = [altered(p, rng.uniform(-.3,.3), rng.uniform(-.3,.3)) for p in self.base(2)]
        self.assertTrue(classify_profiles(p, 0).sufficient_for_rotation_fit)

    def test_zero_mad_floor(self):
        r = classify_profiles(self.base(), 0)
        self.assertEqual(r.width_limit_um, 5)
        self.assertEqual(r.residual_limits_um, (3,3,3))

    def test_guard_band(self):
        r = classify_profiles(self.base()+[square(245)], 0)
        row = next(p for p in r.profiles if p.profile.identifier == '245')
        self.assertEqual(row.classification, C.CORNER_AFFECTED)
        self.assertEqual(row.reasons, ('corner_boundary_guard',))

    def test_bad_seed_fails_closed(self):
        p = self.base(); p[2] = altered(p[2], 20, 20)
        r = classify_profiles(p, 0)
        self.assertFalse(r.sufficient_for_rotation_fit)
        self.assertFalse(r.central_identifiers)
        self.assertIsNone(r.provisional_rotation_deg)

    def test_short_seed_slope_allowance(self):
        p = self.base()
        p[1] = altered(p[1], -.8, .8)
        p[3] = altered(p[3], .8, -.8)
        r = classify_profiles(p, 0)
        self.assertTrue(r.sufficient_for_rotation_fit)
        self.assertLessEqual(r.slope_disagreement, .01)

    def test_missing_and_nonfinite(self):
        p = self.base()+[replace(square(200), left_edge_um=None),
                         replace(square(210), measured_y_um=float('nan'))]
        self.assertEqual(len(classify_profiles(p, 0).invalid_identifiers), 2)

    def test_geometry_mismatch(self):
        p = self.base()+[replace(square(200), width_um=400)]
        self.assertIn('200', classify_profiles(p, 0).invalid_identifiers)

    def test_duplicate_ids(self):
        with self.assertRaises(ValueError): classify_profiles([square(0)]*3, 0)

    def test_no_y_leverage(self):
        p = [square(0, identifier=str(i)) for i in range(3)]
        self.assertFalse(classify_profiles(p, 0).sufficient_for_rotation_fit)

    def test_outside_footprint(self):
        p = replace(square(160), identifier='outside', measured_y_um=300)
        r = classify_profiles(self.base()+[p], 0)
        self.assertIn('outside', r.inconsistent_identifiers)
        self.assertNotIn('outside', r.corner_affected_identifiers)

    def test_config_validation(self):
        for kw in ({'minimum_profiles':2}, {'width_floor_um':0}, {'boundary_guard_um':250}):
            with self.assertRaises(ValueError): ClassificationSettings(**kw)

    def test_seed_geometric_boundary_rejected(self):
        r = classify_profiles([square(y, 5) for y in (230,240,250)], 0,
                              ClassificationSettings(minimum_y_span_um=10))
        self.assertFalse(r.sufficient_for_rotation_fit)

    def test_final_parallel_check_fails_closed(self):
        p = [square(y) for y in (-400,-300,-80,0,80,300,400)]
        # Larger square and distant central profiles amplify slope disagreement,
        # while individual seed residuals stay below the 3 um floor.
        p = [replace(q, left_edge_um=-500, right_edge_um=500, midpoint_um=0, width_um=1000) for q in p]
        p[0] = altered(p[0], 2.9, -2.9)
        p[-1] = altered(p[-1], -2.9, 2.9)
        r = classify_profiles(p, 0, ClassificationSettings(side_um=1000, width_floor_um=10,
                              max_slope_disagreement=.005))
        self.assertFalse(r.sufficient_for_rotation_fit)
        self.assertFalse(r.central_identifiers)
        self.assertIsNone(r.usable_final_fits)
        self.assertIn('final_central_model_inconsistent', r.reasons)
        self.assertIsNotNone(r.slope_disagreement)
        self.assertTrue(all(row.left_residual_um is not None for row in r.profiles))

    def shifted_plateau(self, ys):
        # The narrow seed is valid. A majority at width 506 moves the plateau
        # by 6 um; their +/-3 um edge residuals still pass the absolute floor.
        seed = [square(y, identifier=f's{i}') for i, y in enumerate((-20, 0, 20))]
        group = [altered(square(y, identifier=f'g{i}'), -3, 3)
                 for i, y in enumerate(ys)]
        return seed + group

    def gated_result(self, profiles):
        # A rejected set may fit the three seed lines, never final lines.
        with patch.object(classifier, '_fit', wraps=classifier._fit) as fit:
            result = classify_profiles(profiles, 0)
        self.assertEqual(fit.call_count, 3)
        self.assertFalse(result.sufficient_for_rotation_fit)
        self.assertIsNone(result.usable_final_fits)
        return result

    def test_post_selection_narrow_y_span(self):
        r = self.gated_result(self.shifted_plateau((100, 101, 102, 103)))
        self.assertEqual(len(r.central_identifiers), 4)
        self.assertIn('insufficient_final_y_span', r.reasons)
        self.assertIn('seed_support_lost', r.reasons)

    def test_post_selection_identical_y(self):
        r = self.gated_result(self.shifted_plateau((100, 100, 100, 100)))
        self.assertIn('insufficient_distinct_y', r.reasons)
        self.assertIn('insufficient_final_y_span', r.reasons)

    def test_seed_support_lost_by_width_plateau(self):
        # Surviving group has ample span: seed loss alone must reject it.
        r = self.gated_result(self.shifted_plateau((100, 120, 140, 160)))
        self.assertEqual(r.reasons, ('seed_support_lost',))
        self.assertEqual(r.seed_identifiers, ('s1', 's0', 's2'))
        self.assertEqual(r.width_plateau_um, 506)

    def test_post_selection_count_below_minimum(self):
        p = self.shifted_plateau((100, 120, 140, 160))
        # Width majority persists, but common translation rejects two members.
        p[-2:] = [altered(q, 20, 20) for q in p[-2:]]
        r = self.gated_result(p)
        self.assertEqual(len(r.central_identifiers), 2)
        self.assertIn('insufficient_central_profiles', r.reasons)
        self.assertIn('seed_support_lost', r.reasons)

    def test_competing_coherent_groups_no_model_switch(self):
        p = self.shifted_plateau((100, 120, 140, 160))
        expected = self.gated_result(p)
        for seed in range(5):
            Random(seed).shuffle(p)
            self.assertEqual(self.gated_result(p), expected)
        self.assertEqual(expected.reasons, ('seed_support_lost',))
        self.assertEqual(expected.seed_identifiers, ('s1', 's0', 's2'))

    def test_near_zero_mad_floors(self):
        p = [altered(q, i * 1e-8, (i % 2) * 1e-8)
             for i, q in enumerate(self.base())]
        widths = [q.width_um for q in p]
        self.assertGreater(classifier.median(abs(w-classifier.median(widths))
                                            for w in widths), 0)
        r = classify_profiles(p, 0)
        self.assertTrue(r.sufficient_for_rotation_fit)
        self.assertEqual(len(r.central_identifiers), 5)
        self.assertEqual(r.width_limit_um, 5)
        self.assertEqual(r.residual_limits_um, (3, 3, 3))

    def test_boundary_equalities_both_sides(self):
        base = self.base(5)
        reference = classify_profiles(base, 0)
        half = reference.central_y_interval_um[1]
        guard = reference.guarded_central_y_interval_um[1]
        outer = reference.outer_half_height_um
        for sign in (-1, 1):
            for boundary, kind, reason in (
                    (guard, C.CORNER_AFFECTED, 'corner_boundary_guard'),
                    (half, C.CORNER_AFFECTED, 'corner_region'),
                    (outer, C.INCONSISTENT, 'outside_square_footprint')):
                with self.subTest(sign=sign, boundary=boundary):
                    # A finite-width edge claim at the exact outer boundary is
                    # geometrically impossible; keep it input-valid to exercise
                    # the footprint gate rather than the invalid-edge gate.
                    q = replace(square(160, 5), identifier='boundary',
                                measured_y_um=sign * boundary)
                    r = classify_profiles(base + [q], 0)
                    row = next(row for row in r.profiles
                               if row.profile.identifier == 'boundary')
                    self.assertEqual(row.classification, kind)
                    self.assertEqual(row.reasons, (reason,))
                    self.assertTrue(r.sufficient_for_rotation_fit)

    def test_initial_center_perturbation_near_guard(self):
        p = self.base() + [square(-239), square(239)]
        nominal = classify_profiles(p, 0)
        self.assertIn('-239', nominal.central_identifiers)
        self.assertIn('239', nominal.central_identifiers)
        for center, excluded, retained in ((2, '-239', '239'), (-2, '239', '-239')):
            with self.subTest(center=center):
                r = classify_profiles(p, center)
                self.assertIn(excluded, r.corner_affected_identifiers)
                self.assertIn(retained, r.central_identifiers)
                self.assertTrue(r.sufficient_for_rotation_fit)
        # This characterizes the fixed guard, not uncertainty propagation:
        # moving the supplied center excludes the farther near-boundary profile.


if __name__ == '__main__':
    unittest.main()
