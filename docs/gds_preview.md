# Generic GDS preview

Author: Yuxin Jiang

Email: yj546@cornell.edu

Module 3 displays Module 2 geometry without semantic classification or microscope
initialization. It uses the existing PyQt6 installation and the Module 2 gdstk
dependency. The main QCL window is neither imported nor launched.

```powershell
python preview_gds_layout.py "C:\path\layout.gds"
# Or launch without a filename and use Load GDS...
python preview_gds_layout.py
```

## Interaction

- Choose any top-level cell using the root dropdown. Initially the largest root
  by geometric bounding-box area is displayed; no cell name is special.
- Wheel zooms with equal axis scale. Left drag pans. Fit to View restores the
  current inspection view; Back to root restores the chosen root's full layout.
- Click selects the smallest feature envelope under the cursor. Click again to
  cycle overlapping features, or use the overlap dropdown. Selection uses
  bounding boxes, so a concave polygon's empty interior can also be selected.
- A yellow cosmetic outline and center dot remain visible at any zoom. The panel
  shows the Module 2 feature ID, GDS frame, center, dimensions, bounds, layers,
  repetition metadata, parent ID, and hierarchy path (including instance index).
- Select parent moves to a displayed ancestor. Inspect selected opens a cell's
  contents and fits them, enabling access to polygon-only child cells. Back to
  root recovers the full view.
- Arrays of up to 256 instances are traversed automatically. Larger arrays stay
  grouped. Select their envelope, enter a zero-based instance index, and press
  Select instance to independently select any physical occurrence. Inspect
  selected then displays that instance. The backend hierarchy is unchanged.

## Architecture and rendering limits

`GDSLayoutPreviewWidget` in `ui/gds_preview.py` accepts `load_file(path)` or an
existing Module 2 model with `set_layout(model)`. Its `selection_changed` signal
emits a Module 2 `SelectableFeature` or `None`. It can eventually be embedded as
a tab in the existing main window, but no integration is performed here.

`PreviewScene` consumes normalized native cells and the public Module 2 hierarchy
API. It groups actual polygon geometry into painter paths by layer and draws
reference arrays recursively where affordable. Paths are polygonized only for
display. Native text labels have no physical extent and are not drawn; polygon
text is displayed normally. Scene coordinates are explicitly `(GDS X, -GDS Y)`
in micrometers: +X points right, +Y points up. No stage or chip-local coordinates
are involved.

Rendering uses limits of 256 automatic array instances, 2,000 feature overlays,
4,000 polygons, 100,000 vertices, and 16 hierarchy levels. When a branch exceeds
the budget it is displayed as a hatched geometric bounding envelope. The status
line reports simplification. Dense antenna arrays therefore do not allocate
tens of thousands of selectable graphics objects. Ordinary placed polygon-only
cells stay grouped until explicitly inspected. Layer colors are deterministic
and have no semantic meaning. Geometry loading and scene construction are
synchronous; this is a bounded preview, not a full layout editor.

Feature overlay items store the exact backend ID in Qt item data slot 0. The
widget owns selection state and one temporary highlight; geometry is never
edited. Smallest-area selection prefers reference instances when an instance
and its array share the same envelope. No marker/MS assignment is performed.

## Tests

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s tests -p 'test_*.py' -v
python preview_gds_layout.py "C:\path\layout.gds" --smoke-test
```

Tests cover coordinates, aspect ratio, mouse input, fit/pan/zoom, selection,
highlighting, instance identity, hierarchy inspection, root switching, rendering
limits, read-only fixture loading, and a subprocess that blocks hardware imports.
The optional S37a integration test is skipped when the external file is absent.
Do not launch `prior_api_test.py` or the main QCL application for these tests.
To use the visible preview after offscreen tests, remove `QT_QPA_PLATFORM` from
the shell environment before launching it normally.
