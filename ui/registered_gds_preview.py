"""GDS-frame annotations of approved stage predictions; no motion callbacks."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem
from ui.gds_assignment import GDSAssignmentWidget
from ui.gds_preview_scene import gds_to_scene, cosmetic_pen, feature_rect


class RegisteredGDSPreview(GDSAssignmentWidget):
    def __init__(self, parent=None):
        self.registered_predictions = {}
        self._prediction_items = []
        super().__init__(parent)

    def _display(self, feature):
        self._prediction_items = []  # Parent clears/deletes all scene objects.
        super()._display(feature)
        self._draw_predictions()

    def set_predictions(self, predictions):
        if predictions == self.registered_predictions and self._prediction_items:
            return
        self.registered_predictions = dict(predictions)
        self._draw_predictions()

    def _draw_predictions(self):
        for item in self._prediction_items:
            self.scene.removeItem(item)
        self._prediction_items = []
        for feature_id, prediction in self.registered_predictions.items():
            focus = getattr(self.scene, 'focus', None)
            assignments = self.assignments
            if focus is None or assignments is None or assignments.marker is None:
                continue
            if feature_id != assignments.marker.feature_id and feature_id not in assignments.ms_assignments:
                continue  # A layout/root change may precede the invalidation signal.
            feature = assignments.marker if feature_id == assignments.marker.feature_id else assignments.ms_assignments[feature_id].feature
            point = gds_to_scene(*prediction.absolute_gds_um)
            if feature.top_cell_name != focus.top_cell_name or not feature_rect(focus).contains(point):
                continue
            dot = self.scene.addEllipse(-4,-4,8,8,cosmetic_pen('#ffdd66',2))
            dot.setPos(point)
            label = self.scene.addSimpleText(
                f'{prediction.label}: stage ({prediction.stage_um[0]:.3f}, {prediction.stage_um[1]:.3f}) um')
            label.setBrush(QColor('#ffdd66'))
            label.setPos(point)
            for item in (dot,label):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                item.setZValue(120)
                self._prediction_items.append(item)
