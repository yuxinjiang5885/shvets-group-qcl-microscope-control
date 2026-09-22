"""Offscreen tests for the generic, hardware-free GDS preview.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gdstk
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QFont, QFontDatabase, QWheelEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from ui.gds_preview import GDSLayoutPreviewWidget
from ui.gds_preview_scene import feature_rect, gds_to_scene


def test_application():
    app = QApplication.instance() or QApplication([])
    # The Windows offscreen plugin does not enumerate installed system fonts.
    if not QFontDatabase.families():
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font_path.is_file():
            identifier = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(identifier)
            if families:
                app.setFont(QFont(families[0], 9))
    return app


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = test_application()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        library = gdstk.Library()
        leaf = library.new_cell("structure").add(gdstk.rectangle((0, 0), (30, 40), layer=5))
        root = library.new_cell("root")
        root.add(gdstk.Reference(leaf, columns=2, rows=1, spacing=(100, 0)),
                 gdstk.rectangle((-80, -30), (-50, 0), layer=9))
        library.new_cell("other").add(gdstk.rectangle((0, 0), (2, 2)))
        self.path = Path(self.temporary.name) / "synthetic.gds"
        library.write_gds(self.path)
        self.widget = GDSLayoutPreviewWidget()
        self.widget.resize(1200, 800)
        self.widget.show()
        self.widget.load_file(self.path)
        self.app.processEvents()
        self.widget.fit_view()
        self.addCleanup(self.widget.close)

    def instances(self):
        return sorted((feature for feature in self.widget.scene.features.values()
                       if feature.source_cell_name == "structure" and feature.feature_type == "reference"),
                      key=lambda feature: feature.center_x_um)

    def click_feature(self, feature):
        point = self.widget.view.mapFromScene(gds_to_scene(feature.center_x_um, feature.center_y_um))
        QTest.mouseClick(self.widget.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()

    def test_coordinates_and_bbox_mapping(self):
        self.assertEqual(gds_to_scene(12, 34), QPointF(12, -34))
        feature = self.instances()[0]
        rect = feature_rect(feature)
        self.assertEqual((rect.left(), rect.top(), rect.right(), rect.bottom()), (0, -40, 30, 0))
        origin = self.widget.view.mapFromScene(gds_to_scene(0, 0))
        above = self.widget.view.mapFromScene(gds_to_scene(0, 20))
        self.assertLess(above.y(), origin.y())

    def test_fit_and_wheel_preserve_aspect(self):
        view = self.widget.view
        before = view.transform().m11()
        event = QWheelEvent(QPointF(200, 200), QPointF(200, 200), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(view.viewport(), event)
        self.assertGreater(view.transform().m11(), before)
        self.assertAlmostEqual(view.transform().m11(), view.transform().m22())
        QTest.mouseClick(self.widget.fit_button, Qt.MouseButton.LeftButton)
        self.assertAlmostEqual(view.transform().m11(), before)

    def test_selection_highlight_and_information(self):
        self.assertEqual(self.widget.info.toPlainText(), "No feature selected")
        spy = QSignalSpy(self.widget.selection_changed)
        first, second = self.instances()
        self.click_feature(first)
        self.assertEqual(self.widget.selected_feature.feature_id, first.feature_id)
        self.assertEqual(len(self.widget._highlight), 2)
        self.assertTrue(self.widget._highlight[0].pen().isCosmetic())
        self.assertIn("Center X: 15.000000 um", self.widget.info.toPlainText())
        self.click_feature(second)
        self.assertEqual(self.widget.selected_feature.feature_id, second.feature_id)
        self.assertEqual(len(self.widget._highlight), 2)
        self.assertEqual(len(spy), 2)
        self.widget.select_at(QPointF(10000, 10000))
        self.assertIsNone(self.widget.selected_feature)
        self.assertEqual(self.widget._highlight, [])

    def test_array_instances_have_backend_ids(self):
        array = next(feature for feature in self.widget.scene.features.values() if feature.feature_type == "array")
        expected = {feature.feature_id for feature in self.widget.layout_model.children(array)}
        self.assertEqual({feature.feature_id for feature in self.instances()}, expected)
        for feature in self.instances():
            self.assertEqual(self.widget.scene.items_by_id[feature.feature_id].data(0), feature.feature_id)
        original = set(self.widget.scene.items_by_id)
        self.widget.show_root("root")
        self.assertEqual(original, set(self.widget.scene.items_by_id))

    def test_overlap_cycle_and_parent(self):
        feature = self.instances()[0]
        point = gds_to_scene(feature.center_x_um, feature.center_y_um)
        self.widget.select_at(point)
        self.assertEqual(self.widget.selected_feature.feature_id, feature.feature_id)
        self.widget.select_at(point)
        self.assertNotEqual(self.widget.selected_feature.feature_id, feature.feature_id)
        self.widget.select_feature(feature)
        self.widget.select_parent()
        self.assertEqual(self.widget.selected_feature.feature_type, "array")
        self.assertEqual(self.widget.overlap_combo.currentData(), self.widget.selected_feature.feature_id)

    def test_root_switch_and_inspect(self):
        self.widget.select_feature(self.instances()[0])
        self.widget.inspect_selected()
        self.assertTrue(any(feature.feature_type == "polygon" for feature in self.widget.scene.features.values()))
        self.widget.root_combo.setCurrentText("other")
        self.assertIsNone(self.widget.selected_feature)
        self.assertEqual(self.widget.scene.focus.top_cell_name, "other")
        self.assertIn("synthetic.gds", self.widget.file_label.text())

    def test_drag_pans_without_changing_selection(self):
        feature = self.instances()[0]
        self.widget.select_feature(feature)
        view = self.widget.view
        view.zoom(3)
        before = view.mapToScene(QPoint(200, 200))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
        QTest.mouseMove(view.viewport(), QPoint(250, 230), delay=20)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(250, 230))
        self.assertNotEqual(view.mapToScene(QPoint(200, 200)), before)
        self.assertEqual(self.widget.selected_feature.feature_id, feature.feature_id)

    def test_dense_array_budget_and_explicit_instance(self):
        library = gdstk.Library()
        leaf = library.new_cell("tiny").add(gdstk.rectangle((0, 0), (0.2, 0.5)))
        library.new_cell("dense").add(gdstk.Reference(leaf, columns=200, rows=200, spacing=(1, 1)))
        path = Path(self.temporary.name) / "dense.gds"
        library.write_gds(path)
        self.widget.load_file(path)
        self.assertLess(len(self.widget.scene.items()), 10)
        array = next(feature for feature in self.widget.scene.features.values() if feature.feature_type == "array")
        self.widget.select_feature(array)
        self.widget.instance_index.setValue(39999)
        self.widget.select_instance()
        selected = self.widget.selected_feature
        self.assertEqual(selected.hierarchy_path[-1], "instance:39999")
        self.assertAlmostEqual(selected.center_x_um, 199.1)
        self.widget.inspect_selected()
        self.assertEqual(self.widget.scene.polygon_count, 1)

    def test_invalid_file_keeps_existing_layout(self):
        old = self.widget.layout_model
        with self.assertRaises(FileNotFoundError):
            self.widget.load_file(Path(self.temporary.name) / "absent.gds")
        self.assertIs(self.widget.layout_model, old)

    def test_empty_root(self):
        library = gdstk.Library()
        library.new_cell("empty")
        path = Path(self.temporary.name) / "empty.gds"
        library.write_gds(path)
        self.widget.load_file(path)
        self.assertIn("no polygon/path geometry", self.widget.status_label.text())
        self.assertEqual(len(self.widget.scene.features), 0)

    def test_standalone_import_and_load_block_hardware_imports(self):
        code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'instruments', 'qcl_scanning_imaging_ui', 'qcl_spectral_scan_ui', 'PyDAQmx', 'PIPython', 'serial'}:
            raise AssertionError('Hardware import attempted: ' + fullname)
sys.meta_path.insert(0, Guard())
from PyQt6.QtWidgets import QApplication
from ui.gds_preview import GDSLayoutPreviewWidget
app = QApplication([])
widget = GDSLayoutPreviewWidget()
widget.load_file(sys.argv[1])
widget.show()
app.processEvents()
widget.close()
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


FIXTURE = Path(r"C:\Data\Yuxin\MS localization algorithm test\S37a.GDS")


@unittest.skipUnless(FIXTURE.is_file(), "Optional local fixture unavailable")
class PreviewIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = test_application()

    def test_fixture_geometry_selection_and_snapshot(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        widget = GDSLayoutPreviewWidget()
        self.addCleanup(widget.close)
        widget.resize(1250, 850)
        widget.show()
        widget.load_file(FIXTURE)
        self.app.processEvents()
        widget.fit_view()
        self.assertEqual(widget.root_combo.currentText(), "Arra")
        features = list(widget.scene.features.values())
        squares = [feature for feature in features if feature.feature_type == "polygon"
                   and feature.layer_datatypes == ((3, 0),)]
        self.assertEqual(len(squares), 2)
        for square in squares:
            self.assertAlmostEqual(square.width_um, 500)
            widget.select_at(gds_to_scene(square.center_x_um, square.center_y_um))
            self.assertEqual(widget.selected_feature.feature_id, square.feature_id)
        instances = [feature for feature in features if feature.feature_type == "reference"
                     and feature.source_cell_name == "p=1.5um,$L=1.05um"]
        self.assertEqual(len(instances), 4)
        for feature in instances:
            widget.select_at(gds_to_scene(feature.center_x_um, feature.center_y_um))
            self.assertEqual(widget.selected_feature.feature_id, feature.feature_id)
            self.assertAlmostEqual(feature.width_um, 298.73)
        self.assertLess(len(widget.scene.items()), 200)
        widget.select_feature(squares[0])
        self.app.processEvents()
        snapshot = os.environ.get("GDS_PREVIEW_SNAPSHOT")
        if snapshot:
            self.assertTrue(widget.grab().save(snapshot))
            chip = next(feature for feature in features if feature.source_cell_name == "Altug2009"
                        and feature.feature_type == "reference")
            widget.select_feature(chip)
            widget.inspect_selected()
            detailed = next(feature for feature in widget.scene.features.values()
                            if feature.source_cell_name == "p=1.5um,$L=1.05um"
                            and feature.feature_type == "reference")
            widget.select_at(gds_to_scene(detailed.center_x_um, detailed.center_y_um))
            self.app.processEvents()
            self.assertTrue(widget.grab().save(str(Path(snapshot).with_name("gds-preview-detail.png"))))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
