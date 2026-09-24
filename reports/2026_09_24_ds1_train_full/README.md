# DS1 TRAIN full-observation development harness

This is a resumable, parallel benchmark using only the two DS1 TRAIN recording
groups. Every inference task uses every qualified observation in each selected
scan. Generated task files contain no validation/test session, cache root,
reference coordinate, or reference error.

Build its sealed task manifest:

```bash
python reports/2026_09_24_ds1_train_full/build_manifest.py
```

`core` runs baseline and global-time fits for every one of the 151 TRAIN scans
and every multi-scan case. `extended` runs the expensive methods on eight
chronology-stratified single scans per group plus every multi-scan case.
`expansion` holds the remaining expensive single scans until runtime review.
Stratification depends only on recorded scan order, never position error or any
other reference information.

The default manifest contains core and extended tasks only. After reviewing
their runtime, regenerate it with `--include-expansion` to add the deferred
single-scan work.

The multi-scan cases are nested prefixes and non-overlapping chronological
blocks of 2, 4, 8, 16, and 32 scans, each full TRAIN group, and combined TRAIN.
Duplicate scan sequences run once and retain every applicable selection label.

## Method-runner contract

Method owners make a registry from `runner_registry.example.json`; no harness
edit is needed. `{task}` is replaced with an absolute path. The scheduler gives
the runner a private copy of the task whose `output_path` points to a temporary
result file; the runner writes the result there:

```json
{
  "schema": "ds1-train-full-inference-result/v1",
  "task_id": "copied from the task",
  "partition": "train",
  "reference_used_for_fit": false,
  "observation_use": {
    "policy": "all_qualified_observations",
    "heldout_observation_count": 0
  },
  "estimated_position": {"latitude_deg": 0.0, "longitude_deg": 0.0},
  "fitted_parameters": {},
  "rf_objective": {}
}
```

The scheduler rejects output with held-out observations, a non-TRAIN partition,
or post-seal reference fields. Reference error belongs in a later evaluator and
must not modify inference artifacts.

For every `input_scans` entry, a runner must load the existing strict-causal
cache from its own `causal_state_cache_root`, verify `cache_receipt.json` has
the matching session ID, and verify the receipt's state-cache digest. The
combined TRAIN task deliberately contains entries from both TRAIN cache roots.

Run a configured tier:

```bash
python reports/2026_09_24_ds1_train_full/run_scheduler.py \
  --registry /path/to/runner_registry.json --tiers core,extended --workers 24
```

The scheduler dynamically fills free workers from the next runnable task and
honours optional per-method `max_concurrency` caps. Set the exact orbit models
to eight concurrent workers and allow the timing/soft queues to fill the other
cores. It pins all numerical libraries to one thread per worker. A runner that
owns geographic subdivision can declare `geographic_shards`; the scheduler
passes that count as `DS1_GEOGRAPHIC_SHARD_COUNT` while the runner retains
responsibility for selecting its one RF-objective winner.

Artifacts are written to a task-private temporary directory, schema-validated,
then atomically renamed to `artifacts/<method>/<task-id>.json` with a sibling
SHA-256 seal. Valid sealed artifacts are skipped on rerun.

## One-hour post-seal evaluation

After the one-hour manifest has been run, render its fixed 64-task matrix with:

```bash
.venv/bin/python reports/2026_09_24_ds1_train_full/evaluate_one_hour_postseal.py
```

The evaluator reads only matching SHA-256-sealed, complete JSON outputs. It
introduces the Sausalito reference only after that validation, writes a sealed
JSON and CSV plus a PNG under `post-seal-evaluation/`, and accounts explicitly
for every missing or failed task. See `REPORT.md` for the final report template.
