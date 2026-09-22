"""Hardware-free tests of manual semantic assignment and Module 1 construction.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

from pathlib import Path
import tempfile
import unittest

import gdstk

from experiment.chip_layout import ChipLayout, MSPixel, SquareMarker
from experiment.gds_layout import load_gds
from experiment.layout_assignment import LayoutAssignments, MarkerReplacementRequired


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        library = gdstk.Library()
        root = library.new_cell("root")
        root.add(gdstk.rectangle((750, 1750), (1250, 2250)),
                 gdstk.rectangle((1450, 2450), (1550, 2550)),
                 gdstk.rectangle((450, 2440), (550, 2560)),
                 gdstk.rectangle((1560, 1655), (1640, 1745)))
        leaf = library.new_cell("element").add(gdstk.rectangle((0, 0), (10, 20)))
        root.add(gdstk.Reference(leaf, columns=17, rows=1, spacing=(30, 0), origin=(-1000, 0)))
        library.new_cell("other").add(gdstk.rectangle((0, 0), (3, 3)))
        path = Path(self.temp.name) / "fixture.gds"
        library.write_gds(path)
        self.layout = load_gds(path)
        self.root = self.layout.features("root")[0]
        features = self.layout.children(self.root)
        self.marker = next(f for f in features if f.center_x_um == 1000)
        self.replacement = next(f for f in features if f.center_x_um == 1500)
        self.ms_1 = next(f for f in features if f.center_x_um == 500)
        self.ms_2 = next(f for f in features if f.center_x_um == 1600)
        self.array = next(f for f in features if f.feature_type == "array")
        self.state = LayoutAssignments(self.layout)

    def test_marker_and_one_ms_construct_module1(self):
        self.state.set_marker(self.marker)
        self.assertIs(self.state.marker, self.marker)
        self.assertFalse(self.state.is_valid)
        entry = self.state.add_ms(self.ms_1)
        self.assertEqual(entry.name, "MS_1")
        self.assertEqual(entry.feature_id, self.ms_1.feature_id)
        chip = self.state.build_chip_layout()
        self.assertIsInstance(chip, ChipLayout)
        self.assertIsInstance(chip.marker, SquareMarker)
        self.assertIsInstance(chip.ms_pixels[0], MSPixel)
        self.assertEqual((chip.marker.center_local_x, chip.marker.center_local_y), (0, 0))
        self.assertEqual((chip.ms_pixels[0].center_local_x, chip.ms_pixels[0].center_local_y), (-500, 500))
        self.assertEqual((chip.ms_pixels[0].width, chip.ms_pixels[0].height), (100, 120))

    def test_multiple_pixels_coordinates(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.ms_1)
        self.state.add_ms(self.ms_2)
        chip = self.state.build_chip_layout()
        self.assertEqual((chip.get_ms_pixel("MS_2").center_local_x,
                          chip.get_ms_pixel("MS_2").center_local_y), (600, -300))

    def test_marker_replacement_requires_deliberate_action(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.ms_1)
        with self.assertRaises(MarkerReplacementRequired):
            self.state.set_marker(self.replacement)
        self.assertIs(self.state.marker, self.marker)
        self.state.set_marker(self.replacement, replace=True)
        chip = self.state.build_chip_layout()
        self.assertEqual((chip.ms_pixels[0].center_local_x, chip.ms_pixels[0].center_local_y), (-1000, 0))

    def test_marker_removal_invalidates_and_keeps_ms(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.ms_1)
        self.state.remove(self.marker.feature_id)
        self.assertEqual(len(self.state.ms_assignments), 1)
        self.assertFalse(self.state.is_valid)
        with self.assertRaises(ValueError):
            self.state.build_chip_layout()

    def test_arbitrary_count_and_independent_array_instances(self):
        self.state.set_marker(self.marker)
        for feature in self.layout.children(self.array):
            self.state.add_ms(feature)
        self.assertEqual(len(self.state.build_chip_layout().ms_pixels), 17)
        self.assertEqual(len(self.state.ms_assignments), 17)
        self.assertEqual(len({entry.feature_id for entry in self.state.ms_assignments.values()}), 17)

    def test_duplicate_feature_and_role_conflicts(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.replacement)
        for operation in (lambda: self.state.add_ms(self.replacement),
                          lambda: self.state.add_ms(self.marker),
                          lambda: self.state.set_marker(self.replacement, replace=True)):
            with self.assertRaises(ValueError):
                operation()
        self.assertIs(self.state.marker, self.marker)
        self.assertEqual(len(self.state.ms_assignments), 1)

    def test_names_and_rename_validation(self):
        self.state.add_ms(self.ms_1, " A ")
        self.state.add_ms(self.ms_2, "B")
        for name in ("", " ", "A"):
            with self.assertRaises(ValueError):
                self.state.rename_ms(self.ms_2.feature_id, name)
        with self.assertRaises(ValueError):
            self.state.add_ms(self.replacement, "B")
        self.state.rename_ms(self.ms_2.feature_id, "renamed")
        self.assertEqual(self.state.ms_assignments[self.ms_2.feature_id].name, "renamed")
        self.assertEqual(self.state.ms_assignments[self.ms_1.feature_id].name, "A")

    def test_remove_clear_and_default_names(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.ms_1)
        self.state.add_ms(self.ms_2)
        self.state.remove(self.ms_1.feature_id)
        self.assertEqual(self.state.add_ms(self.ms_1).name, "MS_1")
        self.state.clear()
        self.assertFalse(self.state.has_assignments)
        self.assertIsNone(self.state.marker)
        self.assertEqual(len(self.state.ms_assignments), 0)

    def test_grouped_array_and_hierarchy_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "physical array instance"):
            self.state.add_ms(self.array)
        instance = self.layout.children(self.array)[0]
        self.state.add_ms(instance)
        polygon = self.layout.children(instance)[0]
        with self.assertRaisesRegex(ValueError, "ancestor or descendant"):
            self.state.add_ms(polygon)

    def test_mixed_root_rejected(self):
        self.state.set_marker(self.marker)
        other = self.layout.children(self.layout.features("other")[0])[0]
        with self.assertRaisesRegex(ValueError, "same root"):
            self.state.add_ms(other)

    def test_nonsquare_marker_rejected_without_corrupting_state(self):
        self.state.set_marker(self.marker)
        with self.assertRaisesRegex(ValueError, "square"):
            self.state.set_marker(self.ms_1, replace=True)
        self.assertIs(self.state.marker, self.marker)

    def test_chip_snapshots_do_not_mutate_assignments(self):
        self.state.set_marker(self.marker)
        self.state.add_ms(self.ms_1)
        chip = self.state.build_chip_layout()
        chip.ms_pixels[0].center_gds_x = 0
        self.assertEqual(self.state.build_chip_layout().ms_pixels[0].center_gds_x, 500)


if __name__ == "__main__":
    unittest.main()
