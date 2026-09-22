# Manual marker and MS assignment

Author: Yuxin Jiang

Email: yj546@cornell.edu

Module 4 adds manual semantic roles to the hardware-free standalone preview:

```powershell
python preview_gds_layout.py "C:\path\layout.gds"
```

Select a physical feature, then click **Set as Marker** or **Add as MS Pixel**.
The software does not infer roles from cell names, layers, sizes, or positions.
The marker must have a positive square bounding box, as required by Module 1.
Grouped arrays must first be opened or an individual instance selected.

The assignment table shows names, backend feature IDs, GDS centers, dimensions,
and chip-local centers in micrometers. Double-click an MS name to rename it.
Names are trimmed, case-sensitive, nonempty, and unique. Click a table row to
select its underlying feature again. The marker has a magenta dashed outline;
MS features have cyan outlines and names. Yellow still denotes current selection.
These indicators survive selection changes, zoom, pan, and hierarchy navigation.

**Remove Assignment** removes the currently selected feature's role. **Clear All
Assignments** removes all roles without unloading geometry. Replacing the marker
requires a confirmation. Removing it preserves MS assignments but invalidates
local coordinates immediately. Loading another GDS requires confirmation before
discarding existing assignments; root changes retain them. Features from different
root coordinate frames cannot be combined. No distance threshold or automatic
chip grouping is applied within a root: the user decides which instances belong.

## Architecture

`experiment.layout_assignment.LayoutAssignments` owns the state for one Module 2
model. The marker retains its `SelectableFeature`; MS entries are immutable
`MSAssignment` records keyed by the full deterministic feature ID, with a separate
human-readable name. Duplicate IDs, role conflicts, and simultaneous ancestor /
descendant assignments are rejected. Coordinates are not used as identity.

`set_marker(feature, replace=False)`, `add_ms(feature, name=None)`,
`rename_ms(feature_id, name)`, `remove(feature_id)`, and `clear()` validate changes
before altering state. Replacement requires an explicit `replace=True` after UI
confirmation. `build_chip_layout()` constructs fresh `SquareMarker`, `MSPixel`,
and `ChipLayout` objects. Module 1 performs the coordinate subtraction; Module 4
does not duplicate it. A valid result requires a marker and at least one MS.

`ui.gds_assignment.GDSAssignmentWidget` subclasses the generic Module 3 preview.
It adds controls and scene overlays, without changing parsing or generic selection.
After every successful change, `chip_layout` becomes a new valid snapshot or
`None`. `chip_layout_changed` emits that value. **Inspect ChipLayout** displays the
current snapshot; it is disabled until valid. State is session-only: saving or
restoring assignments is not part of this module.

Module 1's strict equal-width/height marker validation is preserved. Dimensions
come from the selected top-level bounding box, not a fitted or inferred square.
No geometry is edited and no stage coordinates, registration, or scan controls
are introduced. Modules 1–3 remain unchanged; the standalone launcher now uses
the assignment-enabled subclass.

## Verification

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s tests -p 'test_*.py' -v
python preview_gds_layout.py "C:\path\layout.gds" --smoke-test
```

The optional S37a integration test uses Qt mouse clicks and button presses to
assign one square and four independently selected surrounding features. It
checks local coordinates, role outlines, removal, clearing, and input-file hash.
Other tests use synthetic files with arbitrary counts and repeated instances.
A subprocess blocks hardware-driver imports while loading and assigning.
Remove `QT_QPA_PLATFORM` from the shell before launching the visible application.
