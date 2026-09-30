"""Experimental UI entry point. Default is hardware-independent registration only.

--hardware explicitly opts into ALL existing mainWindow startup side effects:
MIRcat/Prior/PI connections and stage speed/acceleration/joystick configuration.
The old module is never imported by the default/offline path. Registration remains
archived/offline even in the hardware window; no scan or move action is added.
"""
import argparse
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from ui.auto_relocation_widget import AutoRelocationWidget


class OfflineAutoRelocationWindow(QMainWindow):
    """Safe standalone panel host; does not simulate operational instrument controls."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Auto Relocation — OFFLINE ONLY')
        self.resize(1400, 1000)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.auto_relocation = AutoRelocationWidget()
        self.tabs.addTab(self.auto_relocation, 'Auto Relocation')


def operational_window_class(base_class=None):
    """Lazy subclass, with an injectable inert base for offline contract tests.

    Do not call without a fake base during offline validation: importing the
    legacy module loads vendor libraries, and its constructor starts hardware.
    No overrides of existing callbacks, lifecycle, controls or cleanup.
    """
    if base_class is None:
        from qcl_scanning_imaging_ui import mainWindow
        base_class = mainWindow

    class AutoRelocationMainWindow(base_class):
        def __init__(self):
            super().__init__()
            self.auto_relocation = AutoRelocationWidget()
            self.tabs.addTab(self.auto_relocation, 'Auto Relocation')

    return AutoRelocationMainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--offline', action='store_true', help='Default: registration-only, no vendor imports')
    modes.add_argument('--hardware', action='store_true', help='Start the original hardware UI plus the offline registration tab')
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    window = operational_window_class()() if args.hardware else OfflineAutoRelocationWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
