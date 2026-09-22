"""Offscreen GUI workflow tests for manual GDS role assignment.

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
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gdstk
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from test_gds_preview import test_application
from ui.gds_assignment import GDSAssignmentWidget
from ui.gds_preview_scene import gds_to_scene


class AssignmentWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = test_application()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        library = gdstk.Library()
        cell = library.new_cell("root")
        cell.add(gdstk.rectangle((0, 0), (20, 20)),
                 gdstk.rectangle((100, 100), (110, 110)),
                 gdstk.rectangle((-100, 100), (-90, 110)))
        library.new_cell("other").add(gdstk.rectangle((0, 0), (2, 2)))
        self.path = Path(self.temp.name) / "test.gds"
        library.write_gds(self.path)
        self.widget = GDSAssignmentWidget()
        self.addCleanup(self.widget.close)
        self.widget.resize(1350, 1000)
        self.widget.show()
        self.widget.load_file(self.path)
        self.app.processEvents()
        self.widget.fit_view()
        polygons = [f for f in self.widget.scene.features.values() if f.feature_type == "polygon"]
        self.marker = next(f for f in polygons if f.width_um == 20)
        self.ms = sorted((f for f in polygons if f.width_um == 10), key=lambda f: f.center_x_um)

    def click(self, feature, button):
        point = self.widget.view.mapFromScene(gds_to_scene(feature.center_x_um, feature.center_y_um))
        QTest.mouseClick(self.widget.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.widget.selected_feature.feature_id, feature.feature_id)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.app.processEvents()

    def test_click_assign_remove_clear_and_persistent_highlights(self):
        self.click(self.marker, self.widget.marker_button)
        self.click(self.ms[0], self.widget.ms_button)
        self.click(self.ms[1], self.widget.ms_button)
        self.assertEqual(len(self.widget.chip_layout.ms_pixels), 2)
        self.assertEqual(len(self.widget._assignment_items), 6)
        self.widget.view.zoom(2)
        self.widget.select_feature(None)
        self.assertEqual(len(self.widget._assignment_items), 6)
        self.widget.show_root("root")
        self.assertEqual(len(self.widget._assignment_items), 6)
        self.widget.select_feature(self.marker)
        self.widget.remove_assignment()
        self.assertIsNone(self.widget.chip_layout)
        self.assertEqual(self.widget.assignment_table.item(0, 5).text(), "Unavailable")
        self.assertEqual(len(self.widget.assignments.ms_assignments), 2)
        self.widget.clear_assignments()
        self.assertEqual(self.widget._assignment_items, [])
        self.assertEqual(self.widget.assignment_table.rowCount(), 0)
        self.assertIsNotNone(self.widget.layout_model)

    def test_marker_replacement_confirmation(self):
        self.click(self.marker, self.widget.marker_button)
        self.widget.select_feature(self.ms[0])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.widget.assign_marker()
        self.assertEqual(self.widget.assignments.marker.feature_id, self.marker.feature_id)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.widget.assign_marker()
        self.assertEqual(self.widget.assignments.marker.feature_id, self.ms[0].feature_id)

    def test_invalid_assignment_and_rename_messages(self):
        self.click(self.marker, self.widget.marker_button)
        with patch.object(QMessageBox, "warning") as warning:
            self.widget.assign_ms()
            warning.assert_called_once()
        self.click(self.ms[0], self.widget.ms_button)
        self.click(self.ms[1], self.widget.ms_button)
        with patch.object(QMessageBox, "warning") as warning:
            self.widget.assignment_table.item(2, 0).setText("MS_1")
            warning.assert_called_once()
        self.assertEqual(self.widget.assignment_table.item(2, 0).text(), "MS_2")
        self.widget.assignment_table.item(2, 0).setText("Custom")
        self.assertEqual(self.widget.chip_layout.ms_pixels[1].name, "Custom")

    def test_root_switch_and_file_reload_lifecycle(self):
        self.click(self.marker, self.widget.marker_button)
        self.widget.root_combo.setCurrentText("other")
        self.assertEqual(len(self.widget._assignment_items), 0)
        self.assertIsNotNone(self.widget.assignments.marker)
        self.widget.root_combo.setCurrentText("root")
        self.assertEqual(len(self.widget._assignment_items), 2)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.widget.load_file(self.path)
        self.assertIsNotNone(self.widget.assignments.marker)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.widget.load_file(self.path)
        self.assertFalse(self.widget.assignments.has_assignments)
        self.assertEqual(self.widget._assignment_items, [])

    def test_assignment_path_blocks_hardware_imports(self):
        code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'instruments', 'qcl_scanning_imaging_ui', 'qcl_spectral_scan_ui', 'PyDAQmx', 'PIPython', 'serial'}:
            raise AssertionError('Hardware import attempted: ' + fullname)
sys.meta_path.insert(0, Guard())
from PyQt6.QtWidgets import QApplication
from ui.gds_assignment import GDSAssignmentWidget
app = QApplication([])
widget = GDSAssignmentWidget()
widget.load_file(sys.argv[1])
polygons = [f for f in widget.scene.features.values() if f.feature_type == 'polygon']
widget.select_feature(next(f for f in polygons if f.width_um == 20))
widget.assign_marker()
widget.select_feature(next(f for f in polygons if f.width_um == 10))
widget.assign_ms()
assert widget.chip_layout is not None
widget.close()
'''
        result = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


FIXTURE = Path(r"C:\Data\Yuxin\MS localization algorithm test\S37a.GDS")


@unittest.skipUnless(FIXTURE.is_file(), "Optional local fixture unavailable")
class AssignmentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = test_application()

    def test_s37a_click_button_workflow(self):
        digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        widget = GDSAssignmentWidget()
        self.addCleanup(widget.close)
        widget.resize(1400, 1050)
        widget.show()
        widget.load_file(FIXTURE)
        chip = next(f for f in widget.scene.features.values() if f.feature_type == "reference"
                    and f.source_cell_name == "Altug2009" and f.center_y_um < 0)
        widget.select_feature(chip)
        widget.inspect_selected()
        self.app.processEvents()
        widget.fit_view()
        features = list(widget.scene.features.values())
        marker = next(f for f in features if f.feature_type == "polygon" and f.layer_datatypes == ((3, 0),))
        pixels = sorted((f for f in features if f.feature_type == "reference" and 290 < f.width_um < 310),
                        key=lambda f: (f.center_y_um, f.center_x_um))
        self.assertEqual(len(pixels), 4)
        for feature, button in [(marker, widget.marker_button)] + [(f, widget.ms_button) for f in pixels]:
            point = widget.view.mapFromScene(gds_to_scene(feature.center_x_um, feature.center_y_um))
            QTest.mouseClick(widget.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
            self.assertEqual(widget.selected_feature.feature_id, feature.feature_id)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
        result = widget.chip_layout
        self.assertEqual(len(result.ms_pixels), 4)
        expected = [(-498.192, -500.475), (502.158, -500.125), (-498.192, 499.525), (501.808, 499.525)]
        for pixel, local in zip(result.ms_pixels, expected):
            self.assertAlmostEqual(pixel.center_local_x, local[0])
            self.assertAlmostEqual(pixel.center_local_y, local[1])
        self.assertEqual(len(widget._assignment_items), 10)
        snapshot = os.environ.get("GDS_ASSIGNMENT_SNAPSHOT")
        if snapshot:
            self.assertTrue(widget.grab().save(snapshot))
        widget.remove_assignment()
        self.assertEqual(len(widget.chip_layout.ms_pixels), 3)
        widget.clear_assignments()
        self.assertIsNone(widget.chip_layout)
        self.assertEqual(widget._assignment_items, [])
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
