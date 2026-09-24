# DS1 TRAIN full-observation timing worker

`run.py` runs one independent TRAIN-only task.  It never reads a reference
coordinate and ignores the legacy `training_mask` stored in the cache receipt.
Every qualified track observation is used to profile the track's constant CFO,
score satellite candidates, fit timing parameters, and select the geographic
point.

The task JSON is deliberately narrow:

```json
{
  "task_id": "train-20260921-00-1-sacramento-shared",
  "group_id": "20260921_00",
  "session_ids": ["scan-hop-85afa91453f8847b"],
  "prior": {"name": "sacramento", "lat": 38.5816, "lon": -121.4944, "radius_km": 250},
  "method": "shared_global_tau",
  "output_path": "/absolute/path/inference.json",
  "options": {"geographic_levels_km": [100, 50], "beam_width": 2}
}
```

Supported normalized methods are `baseline`, `shared_global_tau`,
`regularized_per_scan_tau`, and `independent_per_track_tau`.  The scheduler
aliases `global_time`, `per_scan_time`, and `independent_per_track_time` are
accepted and recorded as `method_requested`; `method` records the normalized
name. The last is a diagnostic because every track receives an unrelated time
shift. Each output records process peak RSS, and is atomically written and
sealed with a sibling `.json.sha256` file.

The worker defaults `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, and
`MKL_NUM_THREADS` to one before importing NumPy. A scheduler can therefore run
many independent task processes without nested BLAS pools. Geographic search
starts afresh from the task prior; it has no dependency on earlier DS1 points,
identities, or search traces.

For a combined-TRAIN task, set `session_groups` to an exact mapping of every
`session_id` to either `20260921_00` or `20260921_16`. The worker resolves each
session from that group's causal cache. Normal one-group tasks do not need this
field.

Run with:

```bash
python reports/2026_09_24_ds1_train_full_timing/run.py --task task.json
```
