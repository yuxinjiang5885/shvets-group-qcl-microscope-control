# Generic GDS backend

Author: Yuxin Jiang

Email: yj546@cornell.edu

This module loads geometry for future visualization and manual selection. It
does not classify markers or MS pixels, construct Module 1 semantic objects,
import hardware drivers, or change the microscope UI.

## Setup and inspection

The repository previously had no dependency manifest. The optional backend uses
the existing pip environment, with a small dedicated requirements file:

```powershell
python -m pip install -r requirements-gds.txt
python inspect_gds_features.py "C:\path\layout.gds" --depth 3 --limit 30
python -m unittest discover -s tests -p "test_*.py" -v
```

The inspection command reads the input without writing or copying it. Depth 0
shows root cells, depth 1 their direct contents. Each parent is limited separately;
the displayed count is for that traversal, not a count of flattened polygons.
The external integration fixture is optional and is never copied into the repo.
Do not run the separate hardware-oriented `prior_api_test.py` for this backend.

## Public API and coordinate frames

```python
from experiment.gds_layout import load_gds

layout = load_gds("layout.gds")
roots = layout.features()
features = layout.children(roots[0], start=0, limit=100)
print(layout.summary(depth=2))
```

- `GDSLayout.source_path`: resolved source path.
- `user_unit_m`: original file user unit in meters.
- `precision_m` / `database_unit_m`: original database grid in meters.
- `cells`: name-to-gdstk-cell mapping, preserving polygons, paths, labels,
  references, repetitions, and properties. All geometric lengths are normalized
  to **micrometers**, in the owning cell's coordinate frame. Reference `origin`
  and repetition vectors are in the containing cell's frame; rotation is in
  radians, reflection is across the referenced cell's horizontal axis, and
  magnification is dimensionless. Treat native objects as read-only: modifying
  them invalidates cached geometry and identities. The mapping itself is read-only.
- `top_level_cells`: sorted unreferenced roots; no metadata cells are filtered
  automatically. `hierarchy` gives dependency names; native references preserve
  individual placements and transformation parameters.
- `features(top_cell_name=None)`: one feature per root; a named cell may also be
  inspected as an independent root in its own coordinate frame.
- `children(feature, start=0, limit=100)` and `child_count(feature)`: lazy traversal.
  A cell exposes direct references, arrays, polygons, and paths. An array exposes
  placed cell instances only when explicitly opened; each instance can then be
  opened to its cell contents. Array offsets are paginated without allocating
  every occurrence. Grid instance indices use column-major order.
- `SelectableFeature`: ID, type (`cell`, `reference`, `array`, `polygon`, `path`),
  source cell, top cell, hierarchy path, parent ID, layer/datatype pairs, bbox,
  center, dimensions, transform, and optional repetition metadata. For direct
  polygons/paths the source cell is their owning cell.
- `Transform`: affine cell-to-root map. On grouped arrays it maps the base
  instance; repetition offsets remain in the containing cell's frame and must
  also receive ancestor transforms.
- `RepetitionInfo`: count, grid dimensions/vectors or explicit offsets, in um.

Every feature bbox and center is in its `top_cell_name` GDS coordinate frame.
Different roots need not share a physical origin. These are neither chip-local
nor stage coordinates. Centers are axis-aligned bounding-box midpoints, not area
centroids. Dimensions describe actual geometry, not nominal array pitch extents.
Reference bounds use transformed convex hulls, not transformed bounding boxes.
Array hulls use extreme repetition offsets without flattening repeated geometry.

Native text labels are preserved but do not have physical polygon extents and
are not selectable geometric features in this module. Polygonized text remains
ordinary selectable geometry. Empty/label-only cells remain visible in hierarchy
with `None` bbox/center/dimensions. Paths remain native and are polygonized for
their geometric bounds. Cyclic and unresolved references raise `ValueError`.

## Feature identity and selection policy

IDs are SHA-256 hashes of hierarchy paths. Element path tokens use cell names,
geometry/reference content, transforms, and repetition metadata. Polygon winding
and starting vertex are normalized. Sorting content tokens makes IDs independent
of element insertion order; identical duplicate elements receive occurrence
suffixes. Indistinguishable duplicates have a stable *set* of IDs, with no implied
identity between individual identical copies. Editing geometry or placement can
change its ID. IDs are layout-scoped, not globally unique across unrelated files.

No cell names, layers, marker dimensions, chip counts, or geometry patterns have
semantic meaning in this loader. The default is grouped root selection, followed
by explicit hierarchy traversal. A future UI decides what level is meaningful
and assigns marker/MS roles manually. Module 1 remains independent.
