"""Reusable hardware-independent GDS preview widget with selection/navigation.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QPainter
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QGraphicsItem, QGraphicsView, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from experiment.gds_layout import load_gds
from ui.gds_preview_scene import PreviewScene, cosmetic_pen, feature_rect, gds_to_scene


class LayoutView(QGraphicsView):
    """Equal-scale navigation; scene already has its GDS Y coordinate inverted."""

    clicked = pyqtSignal(QPointF)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumSize(360, 300)
        self._press = None
        self._dragged = False

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if 1e-9 <= scale <= 1e9:
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 ** (event.angleDelta().y() / 120))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and (event.position().toPoint() - self._press).manhattanLength() > 4:
            self._dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            if not self._dragged:
                self.clicked.emit(self.mapToScene(event.position().toPoint()))
            self._press = None


class GDSLayoutPreviewWidget(QWidget):
    """Consumes Module 2 only; selection_changed emits a feature or None.

    load_file(path) reads via Module 2. set_layout(model) accepts an existing
    model. No hardware objects or semantic marker/MS roles are used here.
    """

    selection_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_model = None
        self.selected_feature = None
        self._highlight = []
        self._last_click = None
        self._overlap_ids = []
        self.scene = PreviewScene(self)
        self.view = LayoutView(self.scene)
        self.view.clicked.connect(self.select_at)
        self.root_combo = QComboBox()
        self.root_combo.currentTextChanged.connect(self.show_root)
        self.file_label = QLabel("No GDS loaded")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setWordWrap(True)
        self.status_label = QLabel("GDS coordinates (um): +X right, +Y up")
        self.status_label.setWordWrap(True)
        self.info = QPlainTextEdit("No feature selected")
        self.info.setReadOnly(True)
        self.info.setMinimumWidth(300)
        self.overlap_combo = QComboBox()
        self.overlap_combo.setToolTip("Features under the last click, smallest first")
        self.overlap_combo.currentIndexChanged.connect(self._choose_overlap)
        self.instance_index = QSpinBox()
        self.instance_index.setPrefix("Instance ")
        self.instance_index.setEnabled(False)
        self.instance_button = QPushButton("Select instance")
        self.instance_button.setEnabled(False)
        self.instance_button.clicked.connect(self.select_instance)
        self.inspect_button = QPushButton("Inspect selected")
        self.inspect_button.clicked.connect(self.inspect_selected)
        self.parent_button = QPushButton("Select parent")
        self.parent_button.clicked.connect(self.select_parent)
        self.fit_button = QPushButton("Fit to View")
        self.fit_button.clicked.connect(self.fit_view)
        load_button = QPushButton("Load GDS...")
        load_button.clicked.connect(self.choose_file)
        root_button = QPushButton("Back to root")
        root_button.clicked.connect(lambda: self.show_root(self.root_combo.currentText()))
        toolbar = QHBoxLayout()
        for widget in (load_button, self.root_combo, self.fit_button, root_button):
            toolbar.addWidget(widget)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("Selection / overlapping features"))
        side_layout.addWidget(self.overlap_combo)
        side_layout.addWidget(self.info, 1)
        side_layout.addWidget(self.parent_button)
        side_layout.addWidget(self.inspect_button)
        row = QHBoxLayout()
        row.addWidget(self.instance_index)
        row.addWidget(self.instance_button)
        side_layout.addLayout(row)
        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([850, 350])
        outer = QVBoxLayout(self)
        outer.addLayout(toolbar)
        outer.addWidget(self.file_label)
        outer.addWidget(splitter, 1)
        outer.addWidget(self.status_label)
        outer.addWidget(QLabel("Wheel: zoom | Left drag: pan | Click again: cycle overlaps | "
                               "Hatched areas: simplified geometry"))
        self.select_feature(None)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load GDS", "", "GDS files (*.gds *.GDS);;All files (*)")
        if path:
            try:
                self.load_file(path)
            except (OSError, ValueError, RuntimeError) as error:
                QMessageBox.warning(self, "Cannot load GDS", str(error))

    def load_file(self, path):
        model = load_gds(path)
        self.set_layout(model)

    def set_layout(self, model):
        self.layout_model = model
        self.file_label.setText(f"{model.source_path.name} | Geometry: um | "
                                f"File user unit: {model.user_unit_m:g} m | "
                                f"Precision: {model.precision_m:g} m")
        self.file_label.setToolTip(str(model.source_path))
        self.root_combo.blockSignals(True)
        self.root_combo.clear()
        self.root_combo.addItems(model.top_level_cells)
        # Prefer the largest geometric root without interpreting any cell name.
        roots = model.features()
        if roots:
            largest = max(roots, key=lambda feature: (feature.width_um or 0) * (feature.height_um or 0))
            self.root_combo.setCurrentText(largest.source_cell_name)
        self.root_combo.blockSignals(False)
        self.show_root(self.root_combo.currentText())

    def show_root(self, name):
        if self.layout_model is None:
            return
        self.select_feature(None)
        if not name:
            self.scene.clear()
            self.scene.features.clear()
            self.scene.items_by_id.clear()
            self.status_label.setText("No root cells in this file")
            return
        self._display(self.layout_model.features(name)[0])

    def _display(self, feature):
        self.select_feature(None)
        self._last_click = None
        self.overlap_combo.clear()
        self._overlap_ids = []
        self.scene.display(self.layout_model, feature)
        self.status_label.setText(
            f"GDS frame: {feature.top_cell_name} | +X right, +Y up | "
            f"{len(self.scene.features)} selectable features | "
            f"{self.scene.approximations} simplified envelopes"
        )
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        if feature.bbox_um is None:
            self.status_label.setText("This cell has no polygon/path geometry (empty or labels only)")
        self.fit_view()

    def fit_view(self):
        self.view.resetTransform()
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def select_at(self, point):
        candidates = self.scene.candidates(point)
        ids = [feature.feature_id for feature in candidates]
        repeated = (self._last_click is not None
                    and (self.view.mapFromScene(point) - self.view.mapFromScene(self._last_click)).manhattanLength() <= 4
                    and ids == self._overlap_ids)
        index = 0
        if repeated and self.selected_feature and self.selected_feature.feature_id in ids:
            index = (ids.index(self.selected_feature.feature_id) + 1) % len(ids)
        self._last_click = point
        self._overlap_ids = ids
        self.overlap_combo.blockSignals(True)
        self.overlap_combo.clear()
        for feature in candidates:
            self.overlap_combo.addItem(f"{feature.feature_type}: {feature.source_cell_name} "
                                       f"[{feature.feature_id[:10]}]", feature.feature_id)
        if candidates:
            self.overlap_combo.setCurrentIndex(index)
        self.overlap_combo.blockSignals(False)
        self.select_feature(candidates[index] if candidates else None)

    def _choose_overlap(self, index):
        identifier = self.overlap_combo.itemData(index)
        if identifier in self.scene.features:
            self.select_feature(self.scene.features[identifier])

    def select_feature(self, feature):
        for item in self._highlight:
            self.scene.removeItem(item)
        self._highlight = []
        self.selected_feature = feature
        self.overlap_combo.blockSignals(True)
        if feature is None:
            self.overlap_combo.clear()
        else:
            index = self.overlap_combo.findData(feature.feature_id)
            if index < 0:
                self.overlap_combo.clear()
                self.overlap_combo.addItem(
                    f"{feature.feature_type}: {feature.source_cell_name} [{feature.feature_id[:10]}]",
                    feature.feature_id,
                )
                index = 0
            self.overlap_combo.setCurrentIndex(index)
        self.overlap_combo.blockSignals(False)
        self.instance_index.setEnabled(bool(feature and feature.feature_type == "array"))
        self.instance_button.setEnabled(self.instance_index.isEnabled())
        self.inspect_button.setEnabled(bool(feature))
        self.parent_button.setEnabled(bool(feature and feature.parent_feature_id in self.scene.features))
        if feature is None:
            self.info.setPlainText("No feature selected")
            self.selection_changed.emit(None)
            return
        self.scene.add_feature(feature)
        if feature.repetition:
            self.instance_index.setRange(0, feature.repetition.count - 1)
        if feature.bbox_um is not None:
            outline = self.scene.addRect(feature_rect(feature), cosmetic_pen("#ffdc68", 2.5))
            outline.setZValue(100)
            outline.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            center = self.scene.addEllipse(-4, -4, 8, 8, cosmetic_pen("#ffdc68", 2), QBrush(Qt.BrushStyle.NoBrush))
            center.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            center.setPos(gds_to_scene(feature.center_x_um, feature.center_y_um))
            center.setZValue(101)
            center.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._highlight = [outline, center]
        number = lambda value: "None" if value is None else f"{value:.6f}"
        repetition = feature.repetition
        lines = [f"Type: {feature.feature_type}", f"Cell: {feature.source_cell_name}",
                 f"Feature ID: {feature.feature_id[:16]}", f"GDS frame: {feature.top_cell_name}", "",
                 f"Center X: {number(feature.center_x_um)} um", f"Center Y: {number(feature.center_y_um)} um",
                 f"Width: {number(feature.width_um)} um", f"Height: {number(feature.height_um)} um", "",
                 "Bounding box (um): " + (", ".join(number(value) for value in feature.bbox_um)
                                          if feature.bbox_um else "None"),
                 f"Layers/datatypes: {feature.layer_datatypes}",
                 f"Repetition count: {repetition.count if repetition else 1}",
                 f"Parent ID: {feature.parent_feature_id or 'None'}", "", "Hierarchy:",
                 *feature.hierarchy_path]
        if repetition:
            lines.extend([f"Grid: {repetition.columns} columns x {repetition.rows} rows",
                          f"Column vector (um): {repetition.column_vector_um}",
                          f"Row vector (um): {repetition.row_vector_um}"])
        self.info.setPlainText("\n".join(lines))
        self.selection_changed.emit(feature)

    def select_instance(self):
        feature = self.selected_feature
        if feature and feature.feature_type == "array":
            instance = self.layout_model.children(feature, start=self.instance_index.value(), limit=1)[0]
            self.select_feature(instance)
            self.view.ensureVisible(feature_rect(instance), 20, 20)

    def select_parent(self):
        if self.selected_feature:
            parent = self.scene.features.get(self.selected_feature.parent_feature_id)
            if parent:
                self.select_feature(parent)

    def inspect_selected(self):
        if self.selected_feature:
            feature = self.selected_feature
            # Leaf geometry has already been drawn in the containing cell frame.
            if feature.feature_type in ("polygon", "path"):
                self.view.fitInView(feature_rect(feature), Qt.AspectRatioMode.KeepAspectRatio)
            else:
                self._display(feature)
