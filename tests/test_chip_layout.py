"""Hardware-free unit tests for chip layout geometry in micrometers.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

from dataclasses import FrozenInstanceError
import unittest

from experiment.chip_layout import ChipLayout, MSPixel, SquareMarker


class ChipLayoutTests(unittest.TestCase):
    def setUp(self):
        self.marker = SquareMarker(1000.0, 2000.0, 500.0, 500.0)
        self.ms_1 = MSPixel("MS_1", 500.0, 2500.0, 100.0, 120.0)
        self.ms_2 = MSPixel("MS_2", 1600.0, 1700.0, 80.0, 90.0)
        self.layout = ChipLayout(self.marker, [self.ms_1, self.ms_2])

    def test_marker_origin_is_fixed(self):
        self.assertEqual(self.marker.center_local_x, 0.0)
        self.assertEqual(self.marker.center_local_y, 0.0)
        with self.assertRaises(FrozenInstanceError):
            self.marker.center_local_x = 1.0

    def test_synthetic_local_coordinates(self):
        self.assertEqual(
            (self.ms_1.center_local_x, self.ms_1.center_local_y), (-500.0, 500.0)
        )
        self.assertEqual(
            (self.ms_2.center_local_x, self.ms_2.center_local_y), (600.0, -300.0)
        )

    def test_lookup_and_missing_name(self):
        self.assertIs(self.layout.get_ms_pixel("MS_1"), self.ms_1)
        self.assertIs(self.layout.get_ms_pixel("MS_2"), self.ms_2)
        with self.assertRaises(KeyError):
            self.layout.get_ms_pixel("missing")

    def test_dimensions_and_gds_centers_are_preserved(self):
        for geometry, expected in (
            (self.marker, (1000.0, 2000.0, 500.0, 500.0)),
            (self.ms_1, (500.0, 2500.0, 100.0, 120.0)),
            (self.ms_2, (1600.0, 1700.0, 80.0, 90.0)),
        ):
            self.assertEqual(
                (geometry.center_gds_x, geometry.center_gds_y,
                 geometry.width, geometry.height), expected
            )

    def test_duplicate_names_rejected(self):
        duplicate = MSPixel("MS_1", 0.0, 0.0, 10.0, 10.0)
        with self.assertRaisesRegex(ValueError, "Duplicate MS pixel name"):
            ChipLayout(self.marker, [self.ms_1, duplicate])

    def test_duplicates_after_edit_rejected_before_update(self):
        self.ms_2.name = "MS_1"
        self.ms_1.center_gds_x = 0.0
        with self.assertRaises(ValueError):
            self.layout.update_local_coordinates()
        self.assertEqual(self.ms_1.center_local_x, -500.0)
        with self.assertRaises(ValueError):
            self.layout.get_ms_pixel("MS_1")

    def test_recalculate_after_geometry_changes(self):
        self.layout.marker = SquareMarker(100.0, 200.0, 500.0, 500.0)
        self.ms_1.center_gds_x = 400.0
        self.layout.update_local_coordinates()
        self.assertEqual(
            (self.ms_1.center_local_x, self.ms_1.center_local_y), (300.0, 2300.0)
        )
        self.assertEqual(
            (self.ms_2.center_local_x, self.ms_2.center_local_y), (1500.0, 1500.0)
        )

    def test_empty_layout_and_independent_collections(self):
        empty = ChipLayout(self.marker)
        another = ChipLayout(self.marker)
        empty.ms_pixels.append(self.ms_1)
        self.assertEqual(another.ms_pixels, [])
        another.update_local_coordinates()
        self.assertIn("0 MS pixels", another.summary())

    def test_unassigned_pixel_local_centers_are_unset(self):
        pixel = MSPixel("new", 1.0, 2.0, 10.0, 10.0)
        self.assertIsNone(pixel.center_local_x)
        self.assertIsNone(pixel.center_local_y)

    def test_invalid_geometry_and_names(self):
        for values in (
            (float("nan"), 0.0, 10.0, 10.0),
            (0.0, float("inf"), 10.0, 10.0),
            (0.0, 0.0, 0.0, 10.0),
            (0.0, 0.0, 10.0, -1.0),
            (0.0, 0.0, float("inf"), 10.0),
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    MSPixel("invalid", *values)
                with self.assertRaises(ValueError):
                    SquareMarker(*values)
        with self.assertRaises(ValueError):
            MSPixel(" ", 0.0, 0.0, 10.0, 10.0)
        with self.assertRaises(ValueError):
            SquareMarker(0.0, 0.0, 10.0, 20.0)

    def test_summary_labels_units_and_coordinate_systems(self):
        summary = self.layout.summary()
        for expected in (
            "ChipLayout (um): 2 MS pixels", "Marker:", "local=(0.0, 0.0)",
            "MS_1: GDS=(500.0, 2500.0)", "local=(-500.0, 500.0)",
            "MS_2:", "size=100.0 x 120.0",
        ):
            self.assertIn(expected, summary)


if __name__ == "__main__":
    unittest.main()
