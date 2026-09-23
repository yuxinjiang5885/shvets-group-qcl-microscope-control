"""Analytical tests and noisy experimental regression for coordinate transforms.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Experimental measurements are validation fixtures, never fitted parameters.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from math import sqrt
import unittest

from experiment.chip_layout import ChipLayout, MSPixel, SquareMarker
from experiment.stage_registration import (
    Orientation, StageRegistration, local_to_stage, stage_to_local,
    transform_chip_layout_to_stage,
)


class CoordinateTests(unittest.TestCase):
    def assertPoint(self, actual, expected, tolerance=1e-9):
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, delta=tolerance)

    def test_marker_origin_and_flip_x_examples(self):
        registration = StageRegistration(10000, 20000)
        self.assertEqual(registration.orientation, Orientation.FLIP_X)
        for local, expected in (((0, 0), (10000, 20000)),
                                ((500, 500), (9500, 20500)),
                                ((-500, 500), (10500, 20500))):
            with self.subTest(local=local):
                self.assertEqual(local_to_stage(*local, registration), expected)

    def test_all_orientation_mappings_analytically(self):
        expected = {
            Orientation.IDENTITY: (2, 3), Orientation.FLIP_X: (-2, 3),
            Orientation.FLIP_Y: (2, -3), Orientation.FLIP_XY: (-2, -3),
            Orientation.SWAP_XY: (3, 2), Orientation.SWAP_XY_FLIP_X: (-3, 2),
            Orientation.SWAP_XY_FLIP_Y: (3, -2), Orientation.SWAP_XY_FLIP_XY: (-3, -2),
        }
        for orientation, wanted in expected.items():
            with self.subTest(orientation=orientation):
                self.assertEqual(local_to_stage(2, 3, StageRegistration(0, 0, orientation=orientation)), wanted)

    def test_orientation_matrices_are_signed_orthogonal(self):
        self.assertEqual(len({orientation.matrix for orientation in Orientation}), 8)
        for orientation in Orientation:
            matrix = orientation.matrix
            for row in matrix:
                self.assertTrue(all(value in (-1, 0, 1) for value in row))
            for row in range(2):
                for column in range(2):
                    self.assertEqual(sum(matrix[index][row] * matrix[index][column] for index in range(2)),
                                     int(row == column))

    def test_rotation_order_analytically(self):
        # Flip (2,3) to (-2,3), rotate +90 to (-3,-2), then translate.
        registration = StageRegistration(10, 20, 90, Orientation.FLIP_X)
        self.assertPoint(local_to_stage(2, 3, registration), (7, 18))
        self.assertPoint(stage_to_local(7, 18, registration), (2, 3))
        self.assertPoint(local_to_stage(2, 3, StageRegistration(0, 0, -90, Orientation.IDENTITY)), (3, -2))

    def test_round_trips_all_orientations_and_angles(self):
        points = [(0, 0), (0.001, -0.002), (123.456, -789.012), (-500, 500), (123456, -98765)]
        for orientation in Orientation:
            for angle in (0, 1.3, -17.8, 90, -180, 721):
                registration = StageRegistration(8500, -17250, angle, orientation)
                for point in points:
                    with self.subTest(orientation=orientation, angle=angle, point=point):
                        self.assertPoint(stage_to_local(*local_to_stage(*point, registration), registration), point)
                        self.assertPoint(local_to_stage(*stage_to_local(*point, registration), registration), point)

    def test_marker_origin_all_orientations(self):
        for orientation in Orientation:
            registration = StageRegistration(8500, -17250, -13.7, orientation)
            self.assertEqual(local_to_stage(0, 0, registration), (8500, -17250))
            self.assertEqual(stage_to_local(8500, -17250, registration), (0, 0))

    def test_validation_and_immutable_registration(self):
        self.assertEqual(StageRegistration(0, 0, orientation="swap_xy").orientation, Orientation.SWAP_XY)
        for orientation in ("unknown", ((2, 0), (0, 1)), None):
            with self.assertRaises(ValueError):
                StageRegistration(0, 0, orientation=orientation)
        for invalid in (float("nan"), float("inf"), None, "10", True):
            for field in ("marker_stage_x_um", "marker_stage_y_um", "rotation_deg"):
                arguments = {"marker_stage_x_um": 0, "marker_stage_y_um": 0, "rotation_deg": 0}
                arguments[field] = invalid
                with self.assertRaises(ValueError):
                    StageRegistration(**arguments)
            for function in (local_to_stage, stage_to_local):
                with self.assertRaises(ValueError):
                    function(invalid, 0, StageRegistration(0, 0))
                with self.assertRaises(ValueError):
                    function(0, invalid, StageRegistration(0, 0))
        registration = StageRegistration(0, 0)
        with self.assertRaises(FrozenInstanceError):
            registration.rotation_deg = 20

    def test_layout_snapshot_and_input_preservation(self):
        layout = ChipLayout(SquareMarker(1000, 2000, 500, 500), [
            MSPixel("left", 500, 2500, 100, 120), MSPixel("right", 1600, 1700, 90, 80)])
        original = deepcopy(layout)
        registration = StageRegistration(10000, 20000)
        result = transform_chip_layout_to_stage(layout, registration)
        self.assertEqual(result.marker_stage_center, (10000, 20000))
        self.assertEqual(dict(result.ms_stage_centers), {"left": (10500, 20500), "right": (9400, 19700)})
        self.assertEqual(layout, original)
        with self.assertRaises(TypeError):
            result.ms_stage_centers["left"] = (0, 0)
        with self.assertRaises(FrozenInstanceError):
            result.marker_stage_center = (0, 0)

    def test_empty_layout_and_invalid_local_state(self):
        layout = ChipLayout(SquareMarker(0, 0, 10, 10))
        registration = StageRegistration(1, 2)
        self.assertEqual(dict(transform_chip_layout_to_stage(layout, registration).ms_stage_centers), {})
        layout.ms_pixels.append(MSPixel("unset", 10, 10, 1, 1))
        with self.assertRaisesRegex(ValueError, "local_x_um"):
            transform_chip_layout_to_stage(layout, registration)
        layout.update_local_coordinates()
        layout.ms_pixels.append(deepcopy(layout.ms_pixels[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            transform_chip_layout_to_stage(layout, registration)


# Experimental calibration inputs and measured points only belong in tests.
CALIBRATION = StageRegistration(8500, -17250, -1.3046882845, Orientation.FLIP_X)
GOLD_LOCAL = [(-322.442, 500.275), (677.558, 500.275),
              (677.558, -499.725), (-322.442, -499.725)]
GOLD_MEASURED = [(8836, -16764), (7836, -16742), (7808, -17740), (8808, -17762)]
GOLD_PREDICTED = [(8833.749, -16757.196), (7834.008, -16734.427),
                  (7811.239, -17734.168), (8810.980, -17756.937)]
MS_LOCAL = [(-498.192, 499.525), (501.808, 499.525),
            (-498.192, -500.475), (502.158, -500.125)]
MS_PREDICTED = [(9009.437, -16761.948), (8009.696, -16739.179),
                (8986.667, -17761.689), (7986.585, -17738.562)]


class ExperimentalRegressionTests(unittest.TestCase):
    def test_gold_bar_predictions_and_noisy_position_rms(self):
        predicted = [local_to_stage(*point, CALIBRATION) for point in GOLD_LOCAL]
        for actual, expected in zip(predicted, GOLD_PREDICTED):
            for value, wanted in zip(actual, expected):
                self.assertAlmostEqual(value, wanted, delta=0.001)
        # RMS of 2D position errors, not per-coordinate RMS; measured centers
        # have manual localization noise and are not expected to match exactly.
        rms = sqrt(sum((pred.stage_x_um - measured[0]) ** 2 + (pred.stage_y_um - measured[1]) ** 2
                       for pred, measured in zip(predicted, GOLD_MEASURED)) / len(predicted))
        self.assertAlmostEqual(rms, 6.92, delta=0.02)

    def test_current_ms_predictions_through_chiplayout(self):
        layout = ChipLayout(SquareMarker(1000, 2000, 500, 500), [
            MSPixel(f"MS_{index}", 1000 + local[0], 2000 + local[1], 300, 300)
            for index, local in enumerate(MS_LOCAL, 1)])
        original = deepcopy(layout)
        result = transform_chip_layout_to_stage(layout, CALIBRATION)
        for index, expected in enumerate(MS_PREDICTED, 1):
            for value, wanted in zip(result.ms_stage_centers[f"MS_{index}"], expected):
                self.assertAlmostEqual(value, wanted, delta=0.001)
        self.assertEqual(layout, original)


if __name__ == "__main__":
    unittest.main()
