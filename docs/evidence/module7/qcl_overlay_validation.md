# Module 7 QCL overlay validation evidence

Module 7 is **COMPLETE within documented validation limits**.
**QUALITATIVE PHYSICAL VALIDATION: PASSED**, based on the operator's overlay
review. **Quantitative physical localization accuracy: NOT CALIBRATED.**

## Sources and replay

- QCL CSV: `C:\Data\_experiment_data\2026-09-29_012\stacks\pattern0\lineScan_1500_0invcm.csv`
- CSV SHA256: `bf7182c385aef3c6b32de10540f5e50faf89b502a50cdc6a8e4e4d0e0cf5576f`
- GDS: `C:\Data\Yuxin\MS localization algorithm test\S37a.GDS`
- GDS SHA256: `5361e2aa478c6309e1152be745543bb5aac2093a1161cef1bd92d95b72016569`
- Acquisition settings source: `C:\Data\_experiment_data\2026-09-29_012\experiment.log`;
  snake scan, origin (3300, -25400) um, step (2, 2) um, counts (850, 850), 1500 cm^-1.

The [overlay PNG](qcl_registration_overlay.png) and
[selection/prediction report](selection_and_predictions.json) were copied unchanged
from `C:\Users\Discovery\AppData\Local\Temp\module7_qcl_overlay_review\`.
On closeout, evaluator replay reproduced both artifacts byte-for-byte (SHA256
PNG `a194e649af3405635774cc016d16d57db9c8026ec60f4e1f2536813040e41924`,
JSON `4b4346c4ba30a1a2bef115c5e8178ce6c3bc5007ef6dd6818cc84578ec16aa3f`).
The permanent copies do not depend on Temp. Raw CSV and GDS remain external inputs
and are required to regenerate the image; they are not embedded in this archive.
Source journals, CSV and GDS were not changed.

From the repository root, using a new output directory:

```powershell
python -B .\square_marker_qcl_overlay_check.py --selection docs/evidence/module7/selection_and_predictions.json --output-dir "$env:TEMP\module7_overlay_replay_new"
```

The replay uses saved operator selections instead of opening the selector again.
It runs the existing horizontal-journal analysis -> classifier -> production
rotation -> vertical-journal analysis -> center refinement -> Module 5 transform
chain, retaining upstream QC. There is no image-based registration optimization,
manual image shift, fitting to validation features, or hardware access.

## Scan-coordinate convention

The operator explicitly chose reproduction of the **normal QCL snake-scan UI
display**, not correction to acquisition/trigger coordinates. The CSV is headerless,
850 rows by 850 columns, indexed [Y row, X column]; all 722500 samples are finite.
Saved snake rows already reverse alternate acquisition directions; this overlay
does not reverse or transpose them again. It does not use the separate above-view mode.

The normal display uses `SNAKE_TRIG_INDENT = 1` and endpoint arrays from origin plus
indent to origin plus indent +/- count times step. With `imshow(origin="upper")`,
these endpoints define image boundaries: X [3301, 5001], Y [-27099, -25399] um.
Rendered pixel centers are X 3302 through 5000 and Y -25400 through -27098 um,
at 2 um spacing. Display source: `plot_snakescans` in `qcl_scanning_imaging_ui.py`,
coordinate arrays in `experiment/routines.py`, save/reversal in `experiment/auxiliary.py`.

**This display mapping differs from acquisition/trigger coordinates.** No correction
was applied; these displayed coordinates are not calibrated encoder/trigger readbacks.
This discrepancy is relevant to any future quantitative observed-versus-predicted error.

## Manual identities

The reference marker and all validation features were **operator selected** through
the standalone GDS selector. Labels are operator-provided, not intrinsic GDS semantics.
The program did not classify marker/bar/cross roles from geometry.
The reference is the lower marker at absolute GDS (0, -4600) um; local coordinates
subtract this reference. Full hierarchy paths and polygon vertices are in the JSON.

| Operator label | Selected feature ID |
| --- | --- |
| Reference marker | `7ea7ba28d6ac774ff40e747491998e489c4ad1c558ff527f9e325e33cd503ae2` |
| L=1.05 | `0174514771832f84fef733fca879077a90c6ffa583e95275ba58776056d7485c` |
| empty | `3f2f59a1019d920eaac320f994b41b10464cb5156d4abfc9ec9a41f6a95f0b25` |
| P=1.5 | `895e0c8b017a5dcf737ddfeba79575ea888ef6ac7ff74bf6b60a1bb4b1889857` |
| P=1.6 | `89af4767948ef9493ba22d0054354f41bbc94eac6513f786a30717a5b68ae0bb` |
| Cross_left | `889dd1a69c45def85f5c5ddadf5d9af26a88870a26cf44db4107013211fe1981` |
| Cross_right | `7294c4fe2982f7cdda845d743e29556ddf5d7b706da7dc0e4be16252992f0240` |

The two cross selections correspond to individual vertical polygons, not automatically
grouped full crosses. The full selected polygons are transformed into stage coordinates;
missing arms were not inferred or added. The reference is excluded from the six
independent validation-feature count. The intended MS pixels were not fabricated on
this sample; this review does not validate their predicted physical positions or
establish the fabrication status of unselected GDS features.

## Accepted registration and automated validation

| Quantity | Verified value |
| --- | --- |
| Marker stage X | 4214.965309833208 um |
| Marker stage Y | -26111.10204224153 um |
| Effective midpoint rotation | +0.13199759820576185 deg |
| Orientation / scale / shear | FLIP_X / 1 / none |
| Retained warning | `left_right_angle_disagreement_warning` |
| Hard-failure reasons | `()` |
| Classifier | P1-P4 CENTRAL; P5 INCONSISTENT |
| Classifier sufficient / rotation valid / center valid | True / True / True |

Registration parameters are obtained from the existing result chain, not fitted to
this image. Midpoint rotation is the registration estimate; side disagreement does
not establish a physical cause. Fitting and QC thresholds were unchanged and remain
provisional engineering limits. Regression statistical SE and angle-fit sensitivity
are not calibrated physical uncertainty.

Closeout rerun: **258 tests passed, zero failures**: overlay 20, integration 20,
center refinement 32, rotation 28, classification 31, reflection scan 47, adapters 25,
StageRegistration 11, ChipLayout 11, layout assignment 12, GDS layout 21.
These are offline tests; adapter tests use fake bindings/devices. The real-data
overlay replay also passed. This closeout performed no hardware initialization/motion.

## Qualitative conclusion and limits

The operator's review concludes that the reference marker aligns with the measured
QCL structure, and independently selected gold bars/crosses appear at the correct
general predicted locations. Quadrant/orientation behavior is correct; FLIP_X, scale
and gross translation are physically consistent. No large sign/orientation failure
is visible. This supports **QUALITATIVE PHYSICAL VALIDATION: PASSED**.

A small systematic angular/positional mismatch remains visible in the overlay.
Possible contributors include rotation estimation, marker geometry, optical edge bias,
scan-coordinate convention and drift. The cause has not been quantitatively isolated.
No manual observed-center measurement or quantitative observed-minus-predicted error
was performed. No micron-level physical localization accuracy is claimed.

The archived evaluator JSON retains `physically_validated: false`: the automated
prediction tool does not certify physical accuracy. The subsequent operator qualitative
review is recorded separately in this note; it does not turn the report into a
quantitative physical validation or silently change its generated provenance.

Future precision work may include improved rotation estimation, additional horizontal
profiles, clicked/observed feature centers, scan-coordinate calibration and
drift/systematic-error characterization. These are not blockers for Module 8 UI
integration using the existing validated algorithms and visible warnings/limitations.
