import unittest
from PyQt6.QtWidgets import QApplication
from experiment.stage_registration import Orientation
from ui.auto_relocation_widget import AutoRelocationWidget
from qcl_scanning_imaging_autorelocation_ui import OfflineAutoRelocationWindow


class OrientationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_normal_default_and_hidden_stale_selector_ignored(self):
        w=AutoRelocationWidget()
        try:
            self.assertIs(w.state.context.orientation,Orientation.FLIP_X)
            self.assertIn('FLIP_X (default)',w.orientation_default_label.text())
            self.assertTrue(w.orientation.isHidden())
            w.orientation.setCurrentText('FLIP_Y');w.sync_context()
            self.assertIs(w.state.context.orientation,Orientation.FLIP_X)
        finally:w.deleteLater()

    def test_developer_selector_changes_context_and_fresh_normal_resets(self):
        w=OfflineAutoRelocationWindow(developer_mode=True)
        try:
            panel=w.auto_relocation;before=panel.state.context_generation
            self.assertFalse(panel.orientation.isHidden())
            panel.orientation.setCurrentText('FLIP_Y')
            self.assertIs(panel.state.context.orientation,Orientation.FLIP_Y)
            self.assertGreater(panel.state.context_generation,before)
            fresh=OfflineAutoRelocationWindow()
            self.assertIs(fresh.auto_relocation.state.context.orientation,Orientation.FLIP_X)
            fresh.deleteLater()
        finally:w.deleteLater()
