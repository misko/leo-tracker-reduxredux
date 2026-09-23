# First-16 TRAIN causal-state cache export

This report freezes and exports compact causal state caches for exactly the
first 16 session IDs, in order, from the frozen TRAIN partition in
`../2026_09_23_long_inventory_complete/manifest.json`. The selection manifest
was written before export and asserts that no validation or test ID is present.
No position fit or search ran.

All 16 selected caches are available under
`/tmp/leo-long-training-cache-first16/{session_id}/`. Fifteen were exported by
the verified public helper with four bounded concurrent workers. The first cache
was copied only after verifying its receipt's exporter and cache hashes against
the same helper version. The report intentionally does not commit the
approximately 204 MB of reproducible NPZ inputs.

| Item | Value |
|---|---:|
| Frozen TRAIN IDs | 16 |
| Completed / failed | 16 / 0 |
| Verified reuse / fresh exports | 1 / 15 |
| Total cache bytes | 203,811,723 |
| Per-cache bytes | 11,184,710--13,581,596 |
| Sum of exporter runtimes | 150.134 s |
| Per-export runtime | 7.144--12.087 s |

`manifest.json` records the source cohort and verified exporter hashes before
any export. `progress.json` retains the incremental completed-ID accounting.
`results.json` records each receipt hash, source input/analysis/evidence/
trajectory/snapshot digest, exporter and cache digest, byte count, runtime, and
any error. The result fails closed at publication: all 16 manifest IDs must have
exactly one completed receipt and no errors.

The caches use the committed
`reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py`
helper (SHA-256 `472835e7837e9ad0e6b43be5e93bcb35deeeb5c9ce5860f423841cee470ca5e8`)
through the `leo` service identity. Its public preparation port supplies causal
TLE inputs; the exporter retains only candidate state grids that satisfy its
conservative regional visibility bound. No RF was collected or modified.
