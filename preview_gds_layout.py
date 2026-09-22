"""Launch only the software-only GDS preview, without microscope initialization.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Modification: launch the Module 4 manual assignment preview.
"""

import argparse
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.gds_assignment import GDSAssignmentWidget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="Optional GDS file; otherwise use Load GDS")
    parser.add_argument("--smoke-test", action="store_true", help="Show preview and exit after event-loop validation")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    widget = GDSAssignmentWidget()
    widget.setWindowTitle("GDS Layout Preview and Manual Assignment")
    widget.resize(1350, 1000)
    if args.source:
        try:
            widget.load_file(args.source)
        except (OSError, ValueError, RuntimeError) as error:
            parser.exit(1, f"Cannot load GDS: {error}\n")
    widget.show()
    QTimer.singleShot(0, widget.fit_view)
    if args.smoke_test:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
