"""Bounded Qt rendering of Module 2 geometry and selectable features.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Scene coordinates are (GDS X, -GDS Y), in um. This adapter never parses GDS.
Dense arrays are shown as envelopes rather than thousands of antenna items.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene


def gds_to_scene(gds_x_um, gds_y_um):
    return QPointF(gds_x_um, -gds_y_um)


def feature_rect(feature):
    if feature.bbox_um is None:
        return QRectF()
    return QRectF(feature.bbox_min_x_um, -feature.bbox_max_y_um,
                  feature.width_um, feature.height_um)


def cosmetic_pen(color, width=1):
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCosmetic(True)
    return pen


class PreviewScene(QGraphicsScene):
    """Actual polygons grouped by layer plus lightweight feature-ID overlays.

    Public features/items_by_id map exactly to Module 2 IDs. Rendering budgets
    affect detail only, never mutate the loaded geometry or its hierarchy.
    """

    ARRAY_LIMIT = 256
    FEATURE_LIMIT = 2000
    POLYGON_LIMIT = 4000
    VERTEX_LIMIT = 100000
    DEPTH_LIMIT = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.features = {}
        self.items_by_id = {}
        self.approximations = 0
        self.polygon_count = 0
        self.vertex_count = 0
        self.setBackgroundBrush(QColor("#20252b"))

    def display(self, layout, focus):
        self.clear()
        self.features.clear()
        self.items_by_id.clear()
        self.layout_model = layout
        self.focus = focus
        self.approximations = 0
        self.polygon_count = 0
        self.vertex_count = 0
        self._visit(focus, 0)
        bounds = feature_rect(focus)
        if bounds.isEmpty():
            bounds = QRectF(-1, -1, 2, 2)
        margin = max(bounds.width(), bounds.height()) * 0.1
        self.setSceneRect(bounds.adjusted(-margin, -margin, margin, margin))

    def add_feature(self, feature):
        if feature.bbox_um is None or feature.feature_id in self.features:
            return
        item = QGraphicsRectItem(feature_rect(feature))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setData(0, feature.feature_id)
        self.addItem(item)
        self.features[feature.feature_id] = feature
        self.items_by_id[feature.feature_id] = item

    def _envelope(self, feature):
        if feature.bbox_um is None:
            return
        item = self.addRect(feature_rect(feature), cosmetic_pen("#81a7bb"),
                            QBrush(QColor("#476373"), Qt.BrushStyle.Dense4Pattern))
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.approximations += 1

    def _draw_cell_geometry(self, feature):
        cell = self.layout_model.cells[feature.source_cell_name]
        if self.polygon_count + len(cell.polygons) + len(cell.paths) > self.POLYGON_LIMIT:
            self._envelope(feature)
            return
        groups = {}
        polygons = list(cell.polygons)
        for path in cell.paths:
            polygons.extend(path.to_polygons())
        for polygon in polygons:
            if (self.vertex_count + len(polygon.points) > self.VERTEX_LIMIT
                    or self.polygon_count >= self.POLYGON_LIMIT):
                self._envelope(feature)
                break
            self.polygon_count += 1
            self.vertex_count += len(polygon.points)
            points = [gds_to_scene(*feature.transform_to_top.apply(point))
                      for point in polygon.points]
            if not points:
                continue
            key = (polygon.layer, polygon.datatype)
            path = groups.setdefault(key, QPainterPath())
            path.setFillRule(Qt.FillRule.WindingFill)
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path.closeSubpath()
        for (layer, datatype), path in groups.items():
            color = QColor.fromHsv((layer * 67 + datatype * 31) % 360, 100, 205)
            item = QGraphicsPathItem(path)
            item.setPen(cosmetic_pen(color))
            item.setBrush(color)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.addItem(item)

    def _visit(self, feature, depth):
        self.add_feature(feature)
        if feature.bbox_um is None:
            return
        count = self.layout_model.child_count(feature)
        if (depth >= self.DEPTH_LIMIT or len(self.features) + count > self.FEATURE_LIMIT
                or (feature.feature_type == "array" and count > self.ARRAY_LIMIT)):
            self._envelope(feature)
            return
        if feature.feature_type in ("cell", "reference"):
            self._draw_cell_geometry(feature)
        children = self.layout_model.children(feature, limit=max(1, count))
        # A placed polygon-only cell is a useful group (including polygon text).
        # Opening it explicitly exposes its individual polygons.
        group_polygons = (depth > 0 and feature.feature_type == "reference"
                          and not self.layout_model.cells[feature.source_cell_name].references)
        for child in children:
            if child.feature_type in ("polygon", "path"):
                if not group_polygons:
                    self.add_feature(child)
            else:
                self._visit(child, depth + 1)

    def candidates(self, scene_point):
        candidates = [feature for feature in self.features.values()
                      if feature_rect(feature).contains(scene_point)]
        # Prefer smaller structures; equal envelopes prefer a cell instance over
        # its dense array. Repeated clicks can still reach overlapping ancestors.
        priority = {"reference": 0, "polygon": 1, "path": 1, "array": 2, "cell": 3}
        return sorted(candidates, key=lambda feature: (
            round(feature.width_um * feature.height_um, 6),
            priority[feature.feature_type], -len(feature.hierarchy_path), feature.feature_id))
