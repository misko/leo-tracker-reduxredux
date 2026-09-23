# Second frozen TRAIN 8-hour causal cache

This cache export is exactly the complete-inventory UTC group
`2026-09-21T16:00:00+00:00`: 79 IDs, equal to frozen `TRAIN[72:]`, and
disjoint from frozen validation and test IDs. Selection was recorded in
`manifest.json` before any public read-only export.

All 79 caches verified: each receipt session ID, exporter hash, receipt hash,
and NPZ hash matches its receipt binding. The export used four bounded
`sudo -u leo` public-store workers, produced 1,020,409,558 bytes of state
caches, and has zero final failures or dropped IDs. `results.json` records
each receipt/cache/evidence/input/snapshot hash, bytes, and exporter runtime.

One initial setup attempt failed closed before any cache was created because
the new `/tmp` cache parent was not writable by `leo`. The parent permissions
were corrected; the final 79-record `progress.jsonl` run has only `exported`
statuses. No QNAP path was modified and no RF was collected.

Reproduce from the frozen manifest:

```bash
.venv/bin/python reports/2026_09_23_long_training_cache_second8h/export_second8h.py \
  --manifest reports/2026_09_23_long_training_cache_second8h/manifest.json \
  --cache-root /tmp/leo-long-training-cache-second8h \
  --exporter reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py
```

The driver fail-closes if the group label/count, partition checks, exporter
hash, an existing cache, or any final receipt/cache binding is invalid. This
report stops at verified cache export; it performs no position fit or search.
