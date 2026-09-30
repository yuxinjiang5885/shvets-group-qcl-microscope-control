"""Registration panel shared by the offline shell and experimental legacy subclass."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                            QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from experiment.stage_registration import Orientation
from ui.gds_assignment import GDSAssignmentWidget
from ui.registration_state import RegistrationState, RegistrationStatus, replay_archived_evidence
from ui.localization_orchestration import LocalizationController, Command


class AutoRelocationWidget(QWidget):
    def __init__(self, parent=None, *, evidence_loader=None):
        super().__init__(parent)
        self.state = RegistrationState()
        self.orchestration = LocalizationController(self.state)
        self._model = None
        self._gds_hash = ''
        self._source_path = ''
        self._evidence_loader = evidence_loader or (lambda: replay_archived_evidence(Path(__file__).resolve().parents[1]))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('OFFLINE PREDICTION ONLY — archived frame, not current hardware registration.\n'
            'Qualitative validation only; quantitative physical accuracy is not calibrated.'))
        self.selection = GDSAssignmentWidget()
        self.selection.ms_button.setText('Add as Target / MS Feature')
        layout.addWidget(self.selection, 1)
        form = QFormLayout()
        self.orientation = QComboBox()
        for item in Orientation:
            self.orientation.addItem(item.name, item.value)
        self.orientation.setCurrentText('FLIP_X')
        form.addRow('Orientation', self.orientation)
        self.context_fields = {}
        for field, label in (('frame_id', 'Coordinate frame / zero identity'),
                             ('sample_id', 'Sample identity'), ('inputs_id', 'Registration inputs identity')):
            edit = QLineEdit(getattr(self.state.context, field))
            self.context_fields[field] = edit
            form.addRow(label, edit)
            edit.textChanged.connect(self.sync_context)
        self.orientation.currentIndexChanged.connect(self.sync_context)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.locate_button = QPushButton('Locate Marker (acquisition not wired)')
        self.locate_button.setEnabled(False)
        self.load_button = QPushButton('Replay archived Module 7 registration')
        self.review_button = QPushButton('Review Registration')
        self.predict_button = QPushButton('Predict Selected Target')
        self.targets = QComboBox()
        for widget in (self.locate_button, self.load_button, self.review_button, self.targets, self.predict_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        self.status_label = QLabel()
        self.values_label = QLabel()
        self.warnings_label = QLabel()
        self.failures_label = QLabel()
        self.prediction_label = QLabel()
        self.acquisition_label = QLabel()
        for label in (self.status_label, self.values_label, self.warnings_label,
                      self.failures_label, self.prediction_label, self.acquisition_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.review_text = QPlainTextEdit()
        self.review_text.setReadOnly(True)
        self.review_text.setMaximumHeight(120)
        layout.addWidget(self.review_text)
        self.selection.chip_layout_changed.connect(self.assignments_changed)
        self.load_button.clicked.connect(self.load_registration)
        self.review_button.clicked.connect(self.review_registration)
        self.predict_button.clicked.connect(self.predict_target)
        self.targets.currentIndexChanged.connect(self.clear_prediction)
        self.refresh()

    def assignments_changed(self, _=None):
        model = self.selection.layout_model
        if model is not self._model:
            self._model = model
            self.state.invalidate('gds_reloaded')
            self._source_path, self._gds_hash = '', ''
            if model:
                try:
                    path = Path(model.source_path).resolve()
                    self._source_path = str(path)
                    self._gds_hash = sha256(path.read_bytes()).hexdigest()
                except OSError as error:
                    self.state.invalidate('gds_source_unreadable: ' + str(error))
        self.state.targets_changed(self.selection.assignments)
        self.sync_context()
        selected = self.targets.currentData()
        self.targets.blockSignals(True)
        self.targets.clear()
        if self.selection.assignments:
            for entry in self.selection.assignments.ms_assignments.values():
                self.targets.addItem(entry.name, entry.feature_id)
        index = self.targets.findData(selected)
        if index >= 0:
            self.targets.setCurrentIndex(index)
        self.targets.blockSignals(False)
        self.refresh()

    def sync_context(self, *_):
        assignments = self.selection.assignments
        marker = assignments.marker if assignments else None
        self.state.set_context(replace(self.state.context,
            gds_path=self._source_path, gds_sha256=self._gds_hash,
            marker_id=marker.feature_id if marker else '',
            orientation=Orientation(self.orientation.currentData()),
            **{key: edit.text() for key, edit in self.context_fields.items()}))
        self.orchestration.context_updated()
        self.refresh()

    def load_registration(self):
        if not self.orchestration.ownership.guard(Command.REPLAY).allowed:
            self.refresh()
            return
        self.sync_context()
        self.state.begin()
        self.refresh()
        try:
            self.state.accept(self._evidence_loader())
        except Exception as error:
            if self.state.status is not RegistrationStatus.INVALID:
                self.state.invalidate(str(error))
        self.refresh()
        self.review_registration()

    def review_registration(self):
        evidence = self.state.evidence
        if evidence is None:
            self.review_text.setPlainText('No registration evidence loaded.')
            return
        self.review_text.setPlainText(
            'Archived evidence only; invalidated evidence is diagnostic, not usable.\n'
            + '\n'.join(f'{name}: {getattr(evidence, name)!r}' for name in
                        ('context', 'classification', 'rotation', 'center', 'source_hashes')))

    def clear_prediction(self, *_):
        self.state.prediction = None
        self.refresh()

    def predict_target(self):
        self.sync_context()
        try:
            self.state.predict(self.targets.currentData())
        except (ValueError, KeyError) as error:
            self.state.prediction = None
            self.refresh()
            self.prediction_label.setText('Prediction unavailable: ' + str(error))
            return
        self.refresh()

    def refresh(self):
        snapshot = self.orchestration.snapshot()
        self.acquisition_label.setText(
            f"Acquisition: {snapshot['acquisition']}; run: {snapshot['run_id'] or 'none'}; "
            f"ownership: {snapshot['ownership']}; context generation: {snapshot['generation']}\n"
            f"Candidate pending: {snapshot['candidate_pending']}; approved retained: {snapshot['approved_retained']}; "
            f"run warnings: {snapshot['warnings'] or 'none'}; "
            f"run/ownership failures: {snapshot['reasons'] or 'none'}")
        editable = self.orchestration.ownership.guard(Command.GDS_CHANGE).allowed
        self.selection.setEnabled(editable)
        self.orientation.setEnabled(editable)
        for edit in self.context_fields.values():
            edit.setEnabled(editable)
        self.load_button.setEnabled(self.orchestration.ownership.guard(Command.REPLAY).allowed)
        self.status_label.setText('Registration: ' + self.state.status.value + ' (offline evidence)')
        reg = self.state.registration.registration if self.state.registration else None
        self.values_label.setText('No usable registration' if reg is None else
            f'Marker center: ({reg.marker_stage_x_um:.12f}, {reg.marker_stage_y_um:.12f}) um; '
            f'rotation: {reg.rotation_deg:+.12f} deg; orientation: {reg.orientation.name}; scale=1; shear=none')
        self.warnings_label.setText('Warnings: ' + ('; '.join(self.state.warnings) or 'none'))
        self.failures_label.setText('Hard failures / invalidation: ' + ('; '.join(self.state.reasons) or 'none'))
        self.predict_button.setEnabled(self.state.status is RegistrationStatus.VALID and self.targets.count() > 0)
        prediction = self.state.prediction
        self.prediction_label.setText('No target prediction' if prediction is None else
            f'OFFLINE PREDICTION ONLY — {prediction.label} [{prediction.feature_id}]\n'
            f'Absolute GDS: {prediction.absolute_gds_um} um; marker-local: {prediction.marker_local_um} um; '
            f'predicted stage: {prediction.stage_um} um')
        if self.state.evidence is None:
            self.review_text.clear()
