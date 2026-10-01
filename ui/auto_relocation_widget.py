"""Registration panel shared by the offline shell and experimental legacy subclass."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QLabel, QLineEdit,
                            QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
                            QScrollArea, QSizePolicy, QGroupBox)

from experiment.stage_registration import Orientation
from ui.registered_gds_preview import RegisteredGDSPreview
from ui.translation_registration import TranslationEvidence
from ui.registration_state import RegistrationState, RegistrationStatus, replay_archived_evidence
from ui.localization_orchestration import LocalizationController, Command


def auto_location_scroll(content):
    """Tab wrapper only; the stable operational tabs/palette are untouched."""
    scroll=QScrollArea()
    scroll.setObjectName('AutoLocationScroll')
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet('QScrollArea#AutoLocationScroll { background: #f3f4f6; border: none; }')
    scroll.setWidget(content)
    return scroll


class AutoRelocationWidget(QWidget):
    def __init__(self, parent=None, *, evidence_loader=None, developer_mode=False):
        super().__init__(parent)
        self.developer_mode=developer_mode
        self.setObjectName('AutoLocationPanel')
        # A local stylesheet overrides inherited legacy dark QWidget rules.
        # Scene drawing keeps its own deliberate dark canvas/feature colors.
        self.setStyleSheet('''
            #AutoLocationPanel, #AutoLocationPanel QWidget {
                background-color: #f3f4f6; color: #20252b; font-size: 10pt;
            }
            #AutoLocationPanel QLineEdit, #AutoLocationPanel QComboBox,
            #AutoLocationPanel QAbstractItemView, #AutoLocationPanel QPlainTextEdit {
                background-color: #ffffff; color: #20252b;
                border: 1px solid #828b95; selection-background-color: #245f96;
                selection-color: #ffffff;
            }
            #AutoLocationPanel QPushButton {
                background-color: #e5e9ed; border: 1px solid #828b95;
                border-radius: 3px; padding: 5px;
            }
            #AutoLocationPanel QPushButton:hover { background-color: #d4e3ef; }
            #AutoLocationPanel QWidget:disabled { color: #606975; background-color: #e7eaee; }
            #AutoLocationPanel QHeaderView::section { background-color: #e5e9ed; color: #20252b; }
            #AutoLocationPanel QAbstractItemView::item:selected { background-color: #245f96; color: white; }
        ''')
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        self.state = RegistrationState()
        self.orchestration = LocalizationController(self.state)
        self.run_display = {}
        self._model = None
        self._gds_hash = ''
        self._source_path = ''
        self._evidence_loader = evidence_loader or (lambda: replay_archived_evidence(Path(__file__).resolve().parents[1]))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(8)
        layout.addWidget(QLabel('Select a square gold marker and targets manually. Locate Marker uses H then V.\n'
            'Translation-only MVP: rotation assumed 0 degrees, not calibrated. No target motion.'))
        self.selection = RegisteredGDSPreview()
        self.selection.ms_button.setText('Add as Target / MS Feature')
        # The reusable assignment widget has five buttons in a single row.
        # Reflow this instance only; other GDS and stable UI consumers are unchanged.
        outer=self.selection.layout()
        for index in range(outer.count()):
            row=outer.itemAt(index).layout()
            if row and any(row.itemAt(i).widget() is self.selection.marker_button for i in range(row.count())):
                buttons=[]
                while row.count():buttons.append(row.takeAt(0).widget())
                outer.takeAt(index)
                grid=QGridLayout()
                for i,button in enumerate(buttons):grid.addWidget(button,i//3,i%3)
                outer.insertLayout(index,grid)
                row.deleteLater()
                break
        self.selection.root_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selection.root_combo.setMinimumContentsLength(10)
        self.selection.view.setMinimumHeight(300)
        self.selection.info.setMinimumWidth(200)
        self.selection.assignment_table.setMinimumHeight(115)
        self.selection.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        for label in self.selection.findChildren(QLabel):label.setWordWrap(True)
        layout.addWidget(self.selection)
        form = QFormLayout()
        self.orientation = QComboBox(self)
        for item in Orientation:
            self.orientation.addItem(item.name, item.value)
        self.orientation.setCurrentText('FLIP_X')
        self.orientation_default_label = QLabel('Orientation: FLIP_X (default)')
        form.addRow(self.orientation_default_label)
        self.orientation.setVisible(developer_mode)
        self.orientation_default_label.setVisible(not developer_mode)
        if developer_mode:
            form.addRow('Orientation (developer)', self.orientation)
        self.context_fields = {}
        for field, label in (('frame_id', 'Coordinate frame / zero identity'),
                             ('sample_id', 'Sample identity'), ('inputs_id', 'Registration inputs identity')):
            edit = QLineEdit(getattr(self.state.context, field))
            self.context_fields[field] = edit
            form.addRow(label, edit)
            edit.textChanged.connect(self.sync_context)
        self.orientation.currentIndexChanged.connect(self.sync_context)
        layout.addLayout(form)
        actions = QGridLayout()
        self.locate_button = QPushButton('Locate Marker — H+V / translation only')
        self.locate_button.setEnabled(False)
        self.load_button = QPushButton('Replay archived Module 7 registration')
        self.review_button = QPushButton('Review Registration')
        self.predict_button = QPushButton('Predict Selected Target')
        self.targets = QComboBox()
        self.targets.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.targets.setMinimumContentsLength(12)
        for i,widget in enumerate((self.locate_button, self.review_button, self.targets, self.predict_button)):
            actions.addWidget(widget,i//2,i%2)
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
        self.review_text.setMinimumHeight(80)
        layout.addWidget(self.review_text)
        self.development = QGroupBox('Development / Diagnostics (optional)')
        dev_layout = QVBoxLayout(self.development)
        self.development_toggle = QPushButton('Show / hide optional development tools')
        self.development_toggle.setCheckable(True)
        dev_layout.addWidget(self.development_toggle)
        self.development_body = QWidget()
        self.development_body.setLayout(QVBoxLayout())
        self.development_body.layout().addWidget(self.load_button)
        self.hardware_diagnostics_provider = None
        self.hardware_diagnostics_group = QGroupBox('Hardware / DAQ Ownership Diagnostics')
        ownership_layout = QVBoxLayout(self.hardware_diagnostics_group)
        self.hardware_diagnostics_button = QPushButton('Refresh Hardware / DAQ Diagnostics')
        self.hardware_diagnostics_text = QPlainTextEdit()
        self.hardware_diagnostics_text.setReadOnly(True)
        self.hardware_diagnostics_text.setMinimumHeight(200)
        self.hardware_diagnostics_text.setMaximumHeight(320)
        ownership_layout.addWidget(self.hardware_diagnostics_button)
        ownership_layout.addWidget(self.hardware_diagnostics_text)
        self.development_body.layout().addWidget(self.hardware_diagnostics_group)
        self.hardware_diagnostics_button.clicked.connect(self.refresh_hardware_diagnostics)
        self.refresh_hardware_diagnostics()
        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setMaximumHeight(160)
        self.development_body.layout().addWidget(self.diagnostics_text)
        dev_layout.addWidget(self.development_body)
        self.development_body.setVisible(False)
        self.development_toggle.toggled.connect(self.development_body.setVisible)
        layout.addWidget(self.development)
        self.selection.selection_changed.connect(self.selected_preview_feature)
        self.selection.chip_layout_changed.connect(self.assignments_changed)
        self.load_button.clicked.connect(self.load_registration)
        self.review_button.clicked.connect(self.review_registration)
        self.predict_button.clicked.connect(self.predict_target)
        self.targets.currentIndexChanged.connect(self.clear_prediction)
        for label in self.findChildren(QLabel):label.setWordWrap(True)
        self.refresh()

    def refresh_hardware_diagnostics(self):
        """Explicit cached-state refresh; never starts handoff or acquisition."""
        try:
            report = (self.hardware_diagnostics_provider() if self.hardware_diagnostics_provider else
                      dict(read_only=True, available=False, reason='operational_bridge_not_attached'))
        except Exception as error:
            report = dict(read_only=True, available=False, reason='diagnostics_unavailable', error=str(error))
        self.hardware_diagnostics_text.setPlainText(json.dumps(report, indent=2, default=str))

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
            orientation=Orientation(self.orientation.currentData()) if self.developer_mode else Orientation.FLIP_X,
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
        if isinstance(evidence, TranslationEvidence):
            self.review_text.setPlainText(repr(evidence))
            return
        self.review_text.setPlainText(
            'Archived evidence only; invalidated evidence is diagnostic, not usable.\n'
            + '\n'.join(f'{name}: {getattr(evidence, name)!r}' for name in
                        ('context', 'classification', 'rotation', 'center', 'source_hashes')))

    def selected_preview_feature(self, feature):
        if feature is None:
            return
        predictions = self.state.registered_predictions()
        if feature.feature_id in predictions:
            self.state.prediction = predictions[feature.feature_id]
            index = self.targets.findData(feature.feature_id)
            if index >= 0:
                self.targets.blockSignals(True)
                self.targets.setCurrentIndex(index)
                self.targets.blockSignals(False)
            self.refresh()

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

    def consume_localization_event(self, event):
        """GUI-thread slot for injected/fake runs; never starts acquisition."""
        if not self.orchestration.event_is_current(event):
            return
        if event.name == 'started':
            self.run_display = {'phase': 'starting'}
        elif event.name == 'progress' and isinstance(event.detail, dict):
            self.run_display.update(event.detail)
        elif event.name == 'phase_changed':
            self.run_display['phase'] = event.detail
        self.refresh()

    def refresh(self):
        snapshot = self.orchestration.snapshot()
        self.acquisition_label.setText(
            f"Acquisition: {snapshot['acquisition']}; run: {snapshot['run_id'] or 'none'}; "
            f"ownership: {snapshot['ownership']}; context generation: {snapshot['generation']}\n"
            f"Candidate pending: {snapshot['candidate_pending']}; approved retained: {snapshot['approved_retained']}; "
            f"run warnings: {snapshot['warnings'] or 'none'}; "
            f"run/ownership failures: {snapshot['reasons'] or 'none'}")
        diagnostic_text = repr(self.run_display)
        if self.diagnostics_text.toPlainText() != diagnostic_text:
            self.diagnostics_text.setPlainText(diagnostic_text)
        editable = self.orchestration.ownership.guard(Command.GDS_CHANGE).allowed
        self.selection.setEnabled(editable)
        self.orientation.setEnabled(editable)
        for edit in self.context_fields.values():
            edit.setEnabled(editable)
        self.load_button.setEnabled(self.orchestration.ownership.guard(Command.REPLAY).allowed)
        mode = self.state.registration_mode
        suffix = ' — TRANSLATION ONLY' if mode == 'translation_only' else ' (offline calibrated evidence)'
        self.status_label.setText('Registration: ' + self.state.status.value + (suffix if mode else ''))
        reg = self.state.registration.registration if self.state.registration else None
        self.values_label.setText('No usable registration' if reg is None else
            f'Marker center: ({reg.marker_stage_x_um:.12f}, {reg.marker_stage_y_um:.12f}) um; ' +
            ('rotation: assumed 0° — not calibrated; ' if mode == 'translation_only' else
             f'rotation: {reg.rotation_deg:+.12f} deg; ') +
            f'orientation: {reg.orientation.name}; scale=1; shear=none')
        self.warnings_label.setText('Warnings: ' + ('; '.join(self.state.warnings) or 'none'))
        self.failures_label.setText('Hard failures / invalidation: ' + ('; '.join(self.state.reasons) or 'none'))
        self.predict_button.setEnabled(self.state.status is RegistrationStatus.VALID and self.targets.count() > 0)
        self.selection.set_predictions(self.state.registered_predictions())
        prediction = self.state.prediction
        self.prediction_label.setText('No target prediction' if prediction is None else
            f'OFFLINE PREDICTION ONLY — {prediction.label} [{prediction.feature_id}]\n'
            f'Absolute GDS: {prediction.absolute_gds_um} um; marker-local: {prediction.marker_local_um} um; '
            f'predicted stage: {prediction.stage_um} um')
        if self.state.evidence is None:
            self.review_text.clear()
