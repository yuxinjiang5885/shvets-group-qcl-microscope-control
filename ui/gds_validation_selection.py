"""Standalone manual validation selection using the existing Module 3 preview.

Module 4's LayoutAssignments stores named non-reference selections internally;
its 'MS' container is reused solely for membership/overlap/geometry validation.
No MS/bar/cross semantics are assigned to validation targets.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QInputDialog, QMessageBox

from experiment.layout_assignment import LayoutAssignments
from ui.gds_preview import GDSLayoutPreviewWidget


class GDSValidationSelector(GDSLayoutPreviewWidget):
    confirmed = pyqtSignal(object)

    def __init__(self):
        self.assignments = None
        super().__init__()
        self.setWindowTitle('Offline QCL validation: manual GDS selection')
        self.resize(1400, 950)
        controls = QHBoxLayout()
        for name, callback in (
            ('Set reference marker', self.set_marker),
            ('Add validation feature / name', self.add_target),
            ('Remove selected assignment', self.remove_target),
            ('Use these selections', self.finish),
        ):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.selection_summary = QLabel('No reference or validation targets assigned.')
        self.selection_summary.setWordWrap(True)
        self.layout().addLayout(controls)
        self.layout().addWidget(self.selection_summary)

    def set_layout(self, model):
        if self.assignments and self.assignments.has_assignments:
            QMessageBox.warning(self, 'Selection retained', 'Start a new selector to load another GDS.')
            return
        self.assignments = LayoutAssignments(model)
        super().set_layout(model)

    def action(self, operation):
        try:
            if self.selected_feature is None:
                raise ValueError('Select a GDS feature first.')
            operation()
            marker = self.assignments.marker
            lines = [f'Reference: {marker.feature_id if marker else "not selected"}']
            lines += [f'{e.name}: {e.feature_id}' for e in self.assignments.ms_assignments.values()]
            self.selection_summary.setText('\n'.join(lines))
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, 'Selection unchanged', str(error))

    def set_marker(self):
        # Replacing a marker requires explicit removal, preserving Module 4 checks.
        self.action(lambda: self.assignments.set_marker(self.selected_feature))

    def add_target(self):
        name, ok = QInputDialog.getText(self, 'Validation label', 'Your display name (no inferred feature type):')
        if ok:
            self.action(lambda: self.assignments.add_ms(self.selected_feature, name))

    def remove_target(self):
        self.action(lambda: self.assignments.remove(self.selected_feature.feature_id))

    def finish(self):
        if self.assignments is None or self.assignments.marker is None:
            QMessageBox.warning(self, 'Reference required', 'Manually select and assign one reference marker.')
            return
        self.confirmed.emit(self.assignments)
