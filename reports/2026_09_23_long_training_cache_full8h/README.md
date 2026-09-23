# Full Sep 21 00Z TRAIN cache inventory

This cache inventory freezes all 72 session IDs in the metadata inventory's
`2026-09-21T00:00:00+00:00` group. The manifest verifies that this exact ordered
group equals the first 72 frozen TRAIN IDs; no validation or test ID is opened.

All 72 caches verified successfully under
`/tmp/leo-long-training-cache-full8h/{session_id}/`: 16 are hash-verified
symlink reuses of the earlier first-16 caches and 56 are fresh bounded
read-only exports. Total cache storage is 1,006,772,221 bytes; no NPZ cache is
committed to the repository.

`manifest.json` binds the inventory, cohort, selected IDs, and exporter.
`progress.json` retains completed-ID accounting. `results.json` retains every
receipt, source/export/cache digest, byte count, runtime, and error; all 72
selected IDs are accounted for with zero failures.

Reproduce or repair verified missing caches with the four-worker driver:

```bash
.venv/bin/python reports/2026_09_23_long_training_cache_full8h/export_full8h.py \
  --manifest reports/2026_09_23_long_training_cache_full8h/manifest.json \
  --cache-root /tmp/leo-long-training-cache-full8h \
  --exporter reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py
```

The driver fails closed if an existing cache is invalid or the exporter differs
from the frozen source hash. It uses the `leo` service identity and public
read-only adapters. No RF collection, position search, or fit ran.
