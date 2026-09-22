"""Manual semantic assignment controls layered on the generic GDS preview.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Module 3 continues to own geometry and temporary selection. This subclass owns
only assignment controls, persistent indicators, and Module 1 layout snapshots.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QGraphicsItem, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
)

from experiment.layout_assignment import LayoutAssignments, MarkerReplacementRequired
from ui.gds_preview import GDSLayoutPreviewWidget
from ui.gds_preview_scene import cosmetic_pen, feature_rect


class GDSAssignmentWidget(GDSLayoutPreviewWidget):
    """Assignment-enabled preview; chip_layout is None while invalid.

    chip_layout_changed emits a new ChipLayout snapshot or None after edits.
    Assignment state is in memory; loading another file clears it only after
    confirmation. Root switching retains state but never mixes root frames.
    """

    chip_layout_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        self.assignments = None
        self.chip_layout = None
        self._assignment_items = []
        super().__init__(parent)
        self.marker_button = QPushButton("Set as Marker")
        self.ms_button = QPushButton("Add as MS Pixel")
        self.remove_button = QPushButton("Remove Assignment")
        self.clear_button = QPushButton("Clear All Assignments")
        self.summary_button = QPushButton("Inspect ChipLayout")
        self.marker_button.clicked.connect(self.assign_marker)
        self.ms_button.clicked.connect(self.assign_ms)
        self.remove_button.clicked.connect(self.remove_assignment)
        self.clear_button.clicked.connect(self.clear_assignments)
        self.summary_button.clicked.connect(self.inspect_chip_layout)
        controls = QHBoxLayout()
        for button in (self.marker_button, self.ms_button, self.remove_button,
                       self.clear_button, self.summary_button):
            controls.addWidget(button)
        self.assignment_status = QLabel("Assigned Layout: select a marker and at least one MS pixel.")
        self.assignment_status.setTextFormat(Qt.TextFormat.PlainText)
        self.assignment_status.setWordWrap(True)
        self.assignment_table = QTableWidget(0, 7)
        self.assignment_table.setHorizontalHeaderLabels(
            ["Role / Name", "Feature ID", "GDS X (um)", "GDS Y (um)", "Size W x H (um)",
             "Local X (um)", "Local Y (um)"])
        self.assignment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.assignment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.assignment_table.setMaximumHeight(190)
        self.assignment_table.setMinimumHeight(115)
        self.assignment_table.itemChanged.connect(self._rename)
        self.assignment_table.cellClicked.connect(self._select_assignment)
        self.layout().addLayout(controls)
        self.layout().addWidget(self.assignment_status)
        self.layout().addWidget(self.assignment_table)
        self.layout().addWidget(QLabel("Assignments: magenta = marker; cyan = MS | "
                                       "Yellow = current selection | Double-click an MS name to rename"))
        self.selection_changed.connect(self._selection_changed)
        self._refresh_assignments()

    def set_layout(self, model):
        if self.assignments and self.assignments.has_assignments:
            response = QMessageBox.question(
                self, "Load another GDS", "Loading a GDS clears all current assignments. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes:
                return
        self.assignments = LayoutAssignments(model)
        self.chip_layout = None
        self._assignment_items = []
        super().set_layout(model)
        self._refresh_assignments()

    def _display(self, feature):
        # Module 3 clears the scene; discard references to the deleted overlays.
        self._assignment_items = []
        super()._display(feature)
        self._draw_assignments()

    def _selection_changed(self, feature):
        enabled = feature is not None and self.assignments is not None
        self.marker_button.setEnabled(enabled)
        self.ms_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _message(self, error):
        QMessageBox.warning(self, "Assignment not changed", str(error))

    def assign_marker(self):
        if not self.selected_feature or self.assignments is None:
            return
        try:
            try:
                self.assignments.set_marker(self.selected_feature)
            except MarkerReplacementRequired:
                answer = QMessageBox.question(
                    self, "Replace marker", "Replace the current marker with the selected feature?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                self.assignments.set_marker(self.selected_feature, replace=True)
        except ValueError as error:
            self._message(error)
            return
        self._refresh_assignments()

    def assign_ms(self):
        if not self.selected_feature or self.assignments is None:
            return
        try:
            self.assignments.add_ms(self.selected_feature)
        except ValueError as error:
            self._message(error)
            return
        self._refresh_assignments()

    def remove_assignment(self):
        if not self.selected_feature or self.assignments is None:
            return
        try:
            self.assignments.remove(self.selected_feature.feature_id)
        except ValueError as error:
            self._message(error)
            return
        self._refresh_assignments()

    def clear_assignments(self):
        if self.assignments:
            self.assignments.clear()
            self._refresh_assignments()

    def _rows(self):
        if self.assignments is None:
            return []
        rows = [("Marker", self.assignments.marker)] if self.assignments.marker else []
        return rows + [(entry.name, entry.feature) for entry in self.assignments.ms_assignments.values()]

    def _refresh_assignments(self):
        self.chip_layout = (self.assignments.build_chip_layout()
                            if self.assignments and self.assignments.is_valid else None)
        rows = self._rows()
        self.assignment_table.blockSignals(True)
        self.assignment_table.setRowCount(len(rows))
        for row, (name, feature) in enumerate(rows):
            is_marker = feature is self.assignments.marker
            local = (0.0, 0.0) if is_marker else None
            if not is_marker and self.chip_layout:
                pixel = self.chip_layout.get_ms_pixel(name)
                local = (pixel.center_local_x, pixel.center_local_y)
            values = [name, feature.feature_id[:12], f"{feature.center_x_um:.3f}",
                      f"{feature.center_y_um:.3f}", f"{feature.width_um:.3f} x {feature.height_um:.3f}",
                      f"{local[0]:.3f}" if local else "Unavailable", f"{local[1]:.3f}" if local else "Unavailable"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, feature.feature_id)
                item.setToolTip(f"{feature.source_cell_name}\n{feature.feature_id}\n" + " / ".join(feature.hierarchy_path))
                if column != 0 or is_marker:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.assignment_table.setItem(row, column, item)
        self.assignment_table.blockSignals(False)
        if self.chip_layout:
            self.assignment_status.setText(f"Assigned Layout: valid; 1 marker, {len(self.chip_layout.ms_pixels)} MS pixels. "
                                           "ChipLayout updates automatically (um).")
        elif self.assignments and self.assignments.marker:
            self.assignment_status.setText("Assigned Layout: invalid until at least one MS pixel is added. Marker local center = (0, 0).")
        else:
            self.assignment_status.setText("Assigned Layout: marker missing. MS local coordinates are unavailable.")
        self.summary_button.setEnabled(self.chip_layout is not None)
        self.clear_button.setEnabled(bool(rows))
        self._selection_changed(self.selected_feature)
        self._draw_assignments()
        self.chip_layout_changed.emit(self.chip_layout)

    def _draw_assignments(self):
        for item in self._assignment_items:
            self.scene.removeItem(item)
        self._assignment_items = []
        if self.assignments is None or not hasattr(self.scene, "focus"):
            return
        focus = self.scene.focus
        for name, feature in self._rows():
            if feature.top_cell_name != focus.top_cell_name:
                continue
            rect = feature_rect(feature)
            if not rect.intersects(feature_rect(focus)):
                continue
            is_marker = feature is self.assignments.marker
            color = "#ff78d1" if is_marker else "#55e6e6"
            pen = cosmetic_pen(color, 4)
            if is_marker:
                pen.setStyle(Qt.PenStyle.DashLine)
            outline = self.scene.addRect(rect, pen)
            outline.setZValue(90)
            label = self.scene.addSimpleText(name)
            label.setBrush(QColor(color))
            label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setPos(rect.topLeft())
            label.setZValue(110)
            for item in (outline, label):
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._assignment_items.append(item)

    def _rename(self, item):
        if item.column() != 0:
            return
        try:
            self.assignments.rename_ms(item.data(Qt.ItemDataRole.UserRole), item.text())
        except (ValueError, KeyError) as error:
            self._message(error)
        self._refresh_assignments()

    def _select_assignment(self, row, column):
        name, feature = self._rows()[row]
        if self.root_combo.currentText() != feature.top_cell_name:
            self.root_combo.setCurrentText(feature.top_cell_name)
        self.select_feature(feature)
        self.view.ensureVisible(feature_rect(feature), 20, 20)

    def inspect_chip_layout(self):
        if self.chip_layout:
            message = QMessageBox(self)
            message.setWindowTitle("ChipLayout snapshot")
            message.setText("Valid ChipLayout in micrometers. Expand details to inspect geometry.")
            message.setDetailedText(self.chip_layout.summary())
            message.exec()
