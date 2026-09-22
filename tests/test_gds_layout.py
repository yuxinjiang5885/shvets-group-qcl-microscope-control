"""Synthetic and optional real-file tests for hardware-independent GDS loading.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

import hashlib
from math import pi
from pathlib import Path
import tempfile
import unittest

import gdstk

from experiment.gds_layout import load_gds


class GDSLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def load(self, library, name="test.gds"):
        path = self.directory / name
        library.write_gds(path)
        return load_gds(path)

    def assertBox(self, actual, expected):
        self.assertIsNotNone(actual)
        for value, wanted in zip(actual, expected):
            self.assertAlmostEqual(value, wanted, places=6)

    def reference_layout(self, **kwargs):
        library = gdstk.Library()
        leaf = library.new_cell("leaf")
        leaf.add(gdstk.rectangle((1, 2), (3, 5), layer=7, datatype=9))
        root = library.new_cell("root")
        reference = gdstk.Reference(leaf, **kwargs)
        root.add(reference)
        return self.load(library), reference

    def test_units_normalized_and_metadata_preserved(self):
        library = gdstk.Library(unit=1e-3, precision=1e-8)
        library.new_cell("millimeters").add(gdstk.rectangle((1, 2), (3, 4)))
        layout = self.load(library)
        self.assertAlmostEqual(layout.user_unit_m, 1e-3)
        self.assertAlmostEqual(layout.database_unit_m, 1e-8)
        self.assertBox(layout.features()[0].bbox_um, (1000, 2000, 3000, 4000))
        self.assertAlmostEqual(layout.cells["millimeters"].polygons[0].points[0][0], 1000)

    def test_polygon_geometry(self):
        library = gdstk.Library()
        library.new_cell("shape").add(gdstk.rectangle((-3, 2), (5, 8), layer=12, datatype=4))
        layout = self.load(library)
        root, = layout.features()
        polygon, = layout.children(root)
        self.assertEqual(polygon.feature_type, "polygon")
        self.assertBox(polygon.bbox_um, (-3, 2, 5, 8))
        self.assertEqual((polygon.center_x_um, polygon.center_y_um), (1, 5))
        self.assertEqual((polygon.width_um, polygon.height_um), (8, 6))
        self.assertEqual(polygon.layer_datatypes, ((12, 4),))
        self.assertEqual(polygon.parent_feature_id, root.feature_id)
        self.assertEqual(layout.children(polygon), ())

    def test_translation(self):
        layout, _ = self.reference_layout(origin=(10, -20))
        reference, = layout.children(layout.features()[0])
        self.assertBox(reference.bbox_um, (11, -18, 13, -15))
        polygon, = layout.children(reference)
        self.assertBox(polygon.bbox_um, reference.bbox_um)
        self.assertEqual(polygon.hierarchy_path[:-1], reference.hierarchy_path)
        self.assertEqual(reference.transform_to_top.apply((1, 2)), (11, -18))

    def test_rotation(self):
        layout, _ = self.reference_layout(rotation=pi / 2)
        reference, = layout.children(layout.features()[0])
        self.assertBox(reference.bbox_um, (-5, 1, -2, 3))
        self.assertBox(layout.children(reference)[0].bbox_um, reference.bbox_um)

    def test_reflection(self):
        layout, _ = self.reference_layout(x_reflection=True)
        reference, = layout.children(layout.features()[0])
        self.assertBox(reference.bbox_um, (1, -5, 3, -2))
        self.assertTrue(layout.cells["root"].references[0].x_reflection)

    def test_magnification(self):
        layout, _ = self.reference_layout(magnification=2.5)
        reference, = layout.children(layout.features()[0])
        self.assertBox(reference.bbox_um, (2.5, 5, 7.5, 12.5))

    def test_array_stays_grouped_and_expands_by_page(self):
        layout, _ = self.reference_layout(columns=200, rows=200, spacing=(10, 20))
        root, = layout.features()
        array, = layout.children(root)
        self.assertEqual(array.feature_type, "array")
        self.assertEqual(array.repetition.count, 40000)
        self.assertEqual(layout.child_count(array), 40000)
        self.assertBox(array.bbox_um, (1, 2, 1993, 3985))
        instances = layout.children(array, start=39998, limit=2)
        self.assertEqual(len(instances), 2)
        self.assertBox(instances[-1].bbox_um, (1991, 3982, 1993, 3985))
        self.assertEqual(instances[-1].parent_feature_id, array.feature_id)
        polygon, = layout.children(instances[-1])
        self.assertBox(polygon.bbox_um, instances[-1].bbox_um)
        self.assertEqual(layout.children(array, start=40000), ())

    def test_rotated_reflected_magnified_array(self):
        layout, original = self.reference_layout(
            columns=3, rows=2, spacing=(10, 20), origin=(30, -8),
            rotation=pi / 3, x_reflection=True, magnification=1.5,
        )
        array, = layout.children(layout.features()[0])
        expected = original.bounding_box()
        # GDS array endpoints are rounded to the database grid on writing.
        for actual, wanted in zip(array.bbox_um, (*expected[0], *expected[1])):
            self.assertAlmostEqual(actual, wanted, delta=0.002)
        instances = layout.children(array)
        self.assertEqual(len(instances), 6)
        for instance in instances:
            self.assertBox(layout.children(instance)[0].bbox_um, instance.bbox_um)

    def test_nested_transforms_use_geometry_not_rotated_bbox(self):
        library = gdstk.Library()
        leaf = library.new_cell("triangle")
        leaf.add(gdstk.Polygon([(0, 0), (8, 0), (0, 2)]))
        middle = library.new_cell("middle")
        middle.add(gdstk.Reference(leaf, origin=(3, 5), rotation=pi / 3, x_reflection=True))
        root = library.new_cell("root")
        outer = gdstk.Reference(middle, origin=(-20, 7), rotation=pi / 4, magnification=2)
        root.add(outer)
        layout = self.load(library)
        expected = outer.bounding_box()
        feature = layout.features()[0]
        for _ in range(4):
            self.assertBox(feature.bbox_um, (*expected[0], *expected[1]))
            children = layout.children(feature)
            if children:
                feature = children[0]

    def test_nested_array_instances(self):
        library = gdstk.Library()
        leaf = library.new_cell("leaf").add(gdstk.rectangle((0, 0), (1, 2)))
        middle = library.new_cell("middle").add(
            gdstk.Reference(leaf, columns=2, rows=2, spacing=(3, 4), x_reflection=True))
        library.new_cell("root").add(gdstk.Reference(middle, rotation=pi/2, origin=(10, 20)))
        layout = self.load(library)
        outer, = layout.children(layout.features()[0])
        array, = layout.children(outer)
        self.assertBox(array.bbox_um, (10, 20, 16, 24))
        last = layout.children(array)[-1]
        self.assertBox(last.bbox_um, (14, 23, 16, 24))

    def test_multiple_roots_and_empty_labels(self):
        library = gdstk.Library()
        library.new_cell("empty")
        library.new_cell("labels").add(gdstk.Label("native label", (100, 200), layer=8))
        library.new_cell("geometry").add(gdstk.rectangle((0, 0), (1, 1)))
        layout = self.load(library)
        self.assertEqual(layout.top_level_cells, ("empty", "geometry", "labels"))
        self.assertIsNone(layout.features("empty")[0].bbox_um)
        self.assertIsNone(layout.features("labels")[0].center_x_um)
        self.assertEqual(layout.cells["labels"].labels[0].text, "native label")
        self.assertEqual(layout.child_count(layout.features("labels")[0]), 0)

    def test_path_preserved_and_selectable(self):
        library = gdstk.Library()
        library.new_cell("route").add(gdstk.FlexPath([(0, 0), (10, 0)], 2, simple_path=True,
                                                   layer=6, datatype=2))
        layout = self.load(library)
        self.assertEqual(len(layout.cells["route"].paths), 1)
        path, = layout.children(layout.features()[0])
        self.assertEqual(path.feature_type, "path")
        self.assertBox(path.bbox_um, (0, -1, 10, 1))
        self.assertEqual(path.layer_datatypes, ((6, 2),))

    def test_ids_stable_across_loads_and_element_order(self):
        def create(reverse):
            library = gdstk.Library()
            leaf = library.new_cell("leaf").add(gdstk.rectangle((0, 0), (1, 1)))
            elements = [gdstk.Reference(leaf, origin=(3, 4)),
                        gdstk.Reference(leaf, origin=(5, 6)),
                        gdstk.rectangle((-1, -2), (0, 0)),
                        gdstk.rectangle((-1, -2), (0, 0))]
            library.new_cell("root").add(*(reversed(elements) if reverse else elements))
            return self.load(library, f"order{reverse}.gds")
        first, second = create(False), create(True)
        first_features = first.children(first.features()[0])
        second_features = second.children(second.features()[0])
        first_ids = [feature.feature_id for feature in first_features]
        self.assertEqual(first_ids, [feature.feature_id for feature in second_features])
        self.assertEqual(len(set(first_ids)), 4)
        reloaded = load_gds(first.source_path)
        self.assertEqual(first_ids, [feature.feature_id for feature in reloaded.children(reloaded.features()[0])])

    def test_polygon_vertex_order_does_not_change_id(self):
        ids = []
        for index, points in enumerate(([(0, 0), (1, 0), (1, 2), (0, 2)],
                                        [(1, 2), (1, 0), (0, 0), (0, 2)])):
            library = gdstk.Library()
            library.new_cell("root").add(gdstk.Polygon(points))
            layout = self.load(library, f"vertices{index}.gds")
            ids.append(layout.children(layout.features()[0])[0].feature_id)
        self.assertEqual(ids[0], ids[1])

    def test_array_instance_ids_unique(self):
        layout, _ = self.reference_layout(columns=3, rows=2, spacing=(5, 7))
        root = layout.features()[0]
        array = layout.children(root)[0]
        features = [root, array]
        for instance in layout.children(array):
            features.append(instance)
            features.extend(layout.children(instance))
        self.assertEqual(len(features), len({feature.feature_id for feature in features}))

    def test_hierarchy_and_native_reference_metadata(self):
        layout, _ = self.reference_layout(origin=(8, 9), rotation=pi/2, magnification=2,
                                         x_reflection=True)
        self.assertEqual(layout.hierarchy, {"leaf": (), "root": ("leaf",)})
        reference = layout.cells["root"].references[0]
        self.assertEqual(reference.origin, (8, 9))
        self.assertAlmostEqual(reference.rotation, pi/2)
        self.assertEqual(reference.magnification, 2)
        self.assertTrue(reference.x_reflection)

    def test_invalid_pagination_and_missing_file(self):
        layout, _ = self.reference_layout()
        root = layout.features()[0]
        with self.assertRaises(ValueError):
            layout.children(root, limit=0)
        with self.assertRaises(ValueError):
            layout.children(root, start=-1)
        with self.assertRaises(FileNotFoundError):
            load_gds(self.directory / "missing.gds")

    def test_cycle_rejected(self):
        library = gdstk.Library()
        first = library.new_cell("first")
        second = library.new_cell("second")
        first.add(gdstk.Reference(second))
        second.add(gdstk.Reference(first))
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            self.load(library)

    def test_unresolved_reference_rejected(self):
        library = gdstk.Library()
        library.new_cell("root").add(gdstk.Reference("missing"))
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            self.load(library)

    def test_summary_is_bounded(self):
        layout, _ = self.reference_layout(columns=200, rows=200, spacing=(10, 20))
        summary = layout.summary(depth=2, limit=3)
        self.assertIn("39997 more children", summary)
        self.assertIn("Displayed selectable features: 5", summary)
        self.assertIn("precision:", summary)


FIXTURE = Path(r"C:\Data\Yuxin\MS localization algorithm test\S37a.GDS")


@unittest.skipUnless(FIXTURE.is_file(), "Optional local S37a fixture is unavailable")
class S37aIntegrationTests(unittest.TestCase):
    def test_read_only_hierarchy_and_large_structures(self):
        before_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        before_stat = FIXTURE.stat()
        layout = load_gds(FIXTURE)
        self.assertAlmostEqual(layout.user_unit_m, 1e-6)
        self.assertAlmostEqual(layout.precision_m, 1e-9)
        self.assertEqual(len(layout.cells), 14)
        roots = layout.features()
        self.assertEqual(len(roots), 2)
        root = layout.features("Arra")[0]
        arrays = layout.children(root)
        self.assertTrue(all(feature.feature_type == "array" for feature in arrays))
        chips = next(feature for feature in arrays if feature.source_cell_name == "Altug2009")
        self.assertEqual(chips.repetition.count, 2)
        self.assertGreater(chips.height_um, 10000)
        for chip in layout.children(chips):
            children = layout.children(chip)
            squares = [feature for feature in children if feature.layer_datatypes == ((3, 0),)]
            self.assertEqual(len(squares), 1)
            self.assertAlmostEqual(squares[0].width_um, 500)
            self.assertAlmostEqual(squares[0].height_um, 500)
            self.assertTrue(any(feature.feature_type == "array" for feature in children))
            self.assertLess(len(children), 30)
        self.assertTrue(layout.hierarchy["Arra"])
        self.assertEqual(sum(len(cell.labels) for cell in layout.cells.values()), 0)
        self.assertTrue(layout.cells["TEXT"].polygons)
        self.assertIn("Displayed selectable features:", layout.summary(depth=3))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(FIXTURE.stat().st_mtime_ns, before_stat.st_mtime_ns)
        self.assertEqual(FIXTURE.stat().st_size, before_stat.st_size)


if __name__ == "__main__":
    unittest.main()
