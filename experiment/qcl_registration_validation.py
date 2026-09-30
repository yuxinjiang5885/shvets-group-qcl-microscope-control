"""Offline selected-GDS geometry prediction; no image fitting or hardware.

Selection semantics belong to the operator. Module 4 supplies assignment checks;
Module 5 supplies every stage transform. Native GDS polygon contours (including
weakly simple contours representing holes) are retained without union/filling.
"""
from dataclasses import dataclass
from math import hypot

import numpy as np

from experiment.stage_registration import local_to_stage


@dataclass(frozen=True)
class QCLImageData:
    """Normal snake UI display coordinates, NOT calibrated trigger positions.

    auxiliary.writeSnakeScan writes signal[row_y, column_x], no metadata.
    routines.snakeScan creates linspace endpoints origin+indent to
    origin+indent +/- N*step. plot_snakescans uses their min/max as imshow
    *boundaries*, origin upper, no transpose in the normal view. Pixel centers
    below reproduce that rendering. The linspace entries themselves are NOT
    imshow centers. The 1 um indent follows defaults.SNAKE_TRIG_INDENT.
    Current source conventions are evidence, not acquisition-time telemetry.
    """
    signal: np.ndarray
    x_um: np.ndarray
    y_um: np.ndarray
    extent_um: tuple[float, float, float, float]
    coordinate_convention: str = 'normal_snake_UI_display_not_trigger_readback'


def load_qcl_image(path, *, x_origin_um, y_origin_um, x_pixels, y_pixels,
                   spacing_um, trigger_indent_um=1.0):
    """Headerless CSV only; reject shape mismatch and any nonfinite sample."""
    if any(type(n) is not int or n <= 0 for n in (x_pixels, y_pixels)):
        raise ValueError('Pixel counts must be positive integers')
    if not all(np.isfinite(v) for v in (x_origin_um, y_origin_um, spacing_um, trigger_indent_um)) or spacing_um <= 0:
        raise ValueError('Finite origin/indent and positive spacing required')
    signal = np.loadtxt(path, delimiter=',', ndmin=2)
    if signal.shape != (y_pixels, x_pixels):
        raise ValueError(f'CSV shape {signal.shape} != expected {(y_pixels, x_pixels)}; no reshaping')
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite CSV samples rejected; no interpolation or masking')
    left, top = x_origin_um+trigger_indent_um, y_origin_um+trigger_indent_um
    extent = (left, left+x_pixels*spacing_um, top-y_pixels*spacing_um, top)
    x = left + (np.arange(x_pixels)+.5)*spacing_um
    y = top - (np.arange(y_pixels)+.5)*spacing_um
    for a in (signal, x, y):
        a.setflags(write=False)
    return QCLImageData(signal, x, y, extent)


@dataclass(frozen=True)
class FeaturePrediction:
    label: str
    feature_id: str
    hierarchy_path: tuple[str, ...]
    is_reference: bool
    gds_center_um: tuple[float, float]
    local_center_um: tuple[float, float]
    stage_center_um: tuple[float, float]
    gds_polygons_um: tuple
    stage_polygons_um: tuple
    stage_bbox_um: tuple[float, float, float, float]
    distance_from_marker_um: float


def feature_polygons(layout, feature, *, max_vertices=100000, max_features=10000):
    """Extract full selected geometry, not preview envelopes; fail on budget limits.

    Module 2 has no public leaf-polygon accessor. Its existing stable _elements
    tokens resolve the selected native leaf; parent placement uses its public
    transform_to_top. No token hashing, GDS affine math or parsing is duplicated.
    This deliberately narrow dependency is isolated here.
    """
    layout.child_count(feature)  # Membership validation.
    polygons, count, vertices = [], 0, 0
    pending = [feature]
    while pending:
        current = pending.pop()
        count += 1
        if count > max_features:
            raise ValueError('Selected geometry exceeds feature budget; select a smaller feature')
        children = layout.child_count(current)
        if children:
            if count + len(pending) + children > max_features:
                raise ValueError('Selected geometry exceeds feature budget')
            pending.extend(reversed(layout.children(current, limit=children)))
            continue
        if current.feature_type not in ('polygon', 'path'):
            continue
        token = current.hierarchy_path[-1]
        native = next(element for key, element in layout._elements(current.source_cell_name) if key == token)
        native_polys = [native.copy()] if current.feature_type == 'polygon' else native.to_polygons()
        for polygon in native_polys:
            # Native repetition is expanded on copies only; original GDS untouched.
            if polygon.repetition.size * len(polygon.points) > max_vertices:
                raise ValueError('Selected geometry exceeds vertex budget')
            for poly in [polygon, *polygon.apply_repetition()]:
                points = tuple(current.transform_to_top.apply(p) for p in poly.points)
                vertices += len(points)
                if vertices > max_vertices:
                    raise ValueError('Selected geometry exceeds vertex budget')
                polygons.append(points)
    if not polygons:
        raise ValueError('Selected feature has no polygon geometry')
    return tuple(polygons)


def predict_selection(assignments, registration):
    """One manually selected marker and zero or more manually named targets.

    registration is an OfflineMarkerRegistration produced by the accepted
    Module 7 chain. Assignment names do not imply physical feature types.
    """
    from experiment.marker_stage_registration import OfflineMarkerRegistration
    if not isinstance(registration, OfflineMarkerRegistration):
        raise ValueError('Require accepted offline registration result')
    if assignments.marker is None:
        raise ValueError('Manually select exactly one reference marker')
    marker = assignments.marker
    rows = [('Reference marker', marker, True)] + [
        (entry.name, entry.feature, False) for entry in assignments.ms_assignments.values()]
    predictions = []
    for label, feature, reference in rows:
        gds = (feature.center_x_um, feature.center_y_um)
        local = (gds[0]-marker.center_x_um, gds[1]-marker.center_y_um)
        polygons = feature_polygons(assignments.gds_layout, feature)
        transformed = tuple(tuple(tuple(local_to_stage(
            x-marker.center_x_um, y-marker.center_y_um, registration.registration))
            for x, y in polygon) for polygon in polygons)
        vertices = np.concatenate(transformed)
        bbox = (*vertices.min(axis=0), *vertices.max(axis=0))
        predictions.append(FeaturePrediction(label, feature.feature_id, feature.hierarchy_path,
            reference, gds, local, tuple(local_to_stage(*local, registration.registration)),
            polygons, transformed, tuple(float(v) for v in bbox), hypot(*local)))
    return tuple(predictions)


def plot_overlay(image, predictions, warnings=()):
    """Fixed registration overlay; equal scales, outlines only, no alignment fit."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(11, 10), constrained_layout=True)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    raster = ax.imshow(image.signal, extent=image.extent_um, origin='upper',
                       cmap='inferno', interpolation='none', aspect='equal')
    fig.colorbar(raster, ax=ax, label='Reflection magnitude (V)')
    for prediction in predictions:
        color = 'cyan' if prediction.is_reference else 'lime'
        for i, polygon in enumerate(prediction.stage_polygons_um):
            xy = np.asarray((*polygon, polygon[0]))
            ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=1.2,
                    label=prediction.label if i == 0 else None)
        x, y = prediction.stage_center_um
        ax.plot(x, y, '+', color=color)
        ax.annotate(prediction.label, (x, y), xytext=(5, 5), textcoords='offset points', color='white',
                    bbox={'facecolor': 'black', 'alpha': .55, 'edgecolor': 'none'})
    ax.set(xlabel='Stage X (um)', ylabel='Stage Y (um)',
           xlim=image.extent_um[:2], ylim=image.extent_um[2:])
    ax.set_aspect('equal')
    if predictions:
        ax.legend(loc='upper right')
    ax.set_title('OFFLINE PREDICTION / IMAGE VALIDATION\nNormal QCL snake UI display coordinates; no registration adjustment')
    fig.text(.02, .005, 'Outline colors distinguish roles, not correctness. Warnings: '+', '.join(warnings), fontsize=8)
    return fig
