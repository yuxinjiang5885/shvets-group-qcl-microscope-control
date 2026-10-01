# Production marker quality fixtures

These three byte-preserved journals are the minimum runtime evidence required by
production marker-selection/local-quality regression tests:

- wide_25um_H.jsonl: run 402745357b0c4b769431c2ccc138617c, initial H; generic
  wide-region quality rejects the marker, while anchor/size identity and local
  100 um quality accept it without lowering thresholds.
- reference_10um_H.jsonl and reference_10um_V.jsonl: run
  8493cabf1df6424fa2bee5e25e5d8396, known-good H/V comparisons.

Original bytes and journal metadata are retained. Tests require these fixtures;
they no longer silently skip when a runtime directory is missing. The existing
committed vertical_marker_scan journal remains a separate 20 um reference.
No fixture implies quantitative physical relocation accuracy.
