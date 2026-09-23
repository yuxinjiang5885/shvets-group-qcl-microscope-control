# Chip-local and stage coordinate transformation

Author: Yuxin Jiang

Email: yj546@cornell.edu

Module 5 is pure mathematical transformation. It has no UI or hardware imports,
does not fit calibration parameters, and does not move any instrument.

```python
from experiment.stage_registration import (
    Orientation, StageRegistration, local_to_stage, stage_to_local,
    transform_chip_layout_to_stage,
)

registration = StageRegistration(
    marker_stage_x_um=10000, marker_stage_y_um=20000,
    rotation_deg=0, orientation=Orientation.FLIP_X,
)
stage = local_to_stage(500, 500, registration)  # StagePoint(9500, 20500)
local = stage_to_local(*stage, registration)   # LocalPoint(500, 500)
# stage_layout = transform_chip_layout_to_stage(chip_layout, registration)
```

All lengths are micrometers. Input to `local_to_stage` is chip-local geometry
relative to the assigned marker, never absolute GDS coordinates. The marker's
local origin maps exactly to the supplied stage marker position.

`StageRegistration` is immutable and validates finite numeric positions/angles.
Its orientation accepts an `Orientation` member or its string value. The default
is `flip_x` for the current QCL configuration; all eight mappings remain explicit
options. Unsupported mappings are rejected. Rotation is supplied in degrees,
reduced modulo 360, and explicitly converted to radians internally.

| Orientation | Oriented coordinates from `(local_x, local_y)` |
|---|---|
| `identity` | `(local_x, local_y)` |
| `flip_x` | `(-local_x, local_y)` |
| `flip_y` | `(local_x, -local_y)` |
| `flip_xy` | `(-local_x, -local_y)` |
| `swap_xy` | `(local_y, local_x)` |
| `swap_xy_flip_x` | `(-local_y, local_x)` |
| `swap_xy_flip_y` | `(local_y, -local_x)` |
| `swap_xy_flip_xy` | `(-local_y, -local_x)` |

Forward order is `stage = translation + rotation * orientation * local`.
Positive rotation is counterclockwise after the discrete mapping. Inverse order
is `local = orientation_transpose * rotation_transpose * (stage - translation)`.
There is no numerical matrix inversion, arbitrary scaling, or shear.

The result types `StagePoint` and `LocalPoint` are immutable named tuples, with
explicit coordinate-system field names and ordinary tuple unpacking support.

`transform_chip_layout_to_stage()` returns an immutable `StageLayout` containing
the registration, marker stage center, and a read-only MS-name-to-StagePoint
mapping. It uses the existing stored local centers and leaves the input layout
unchanged. As in Module 1, callers must update local coordinates after editing
GDS geometry. Missing/nonfinite local centers or duplicate MS names are rejected.
Marker-only layouts return an empty MS mapping. Module 4's separate feature-ID
associations remain unchanged; no feature IDs are inferred from geometry here.

Tests include analytic translations/reflections/90-degree rotations, all eight
signed orthogonal matrices, two-way round trips across positive and negative
angles, input preservation, and experimental gold-bar/MS regression data.
Rounded predicted positions are checked within 0.001 um. Gold-bar RMS is the
square root of the mean squared 2D position-error norm; its approximately 6.92 um
residual reflects manually estimated measurements, not transform error. Real
calibration positions and angle occur only in tests.

```powershell
python -m unittest discover -s tests -p test_stage_registration.py -v
python -m unittest discover -s tests -p 'test_*.py' -v
```
