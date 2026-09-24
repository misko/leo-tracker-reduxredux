# DS2 readiness-gated experiment scheduler

`run.py` converts a sealed DS2 manifest and the frozen 17-model registry into
one machine-readable schedule. It does not run an RF/positioning model while
tracking evidence is absent. Instead, it emits a `blocked` task with the exact
missing receipt, cache, policy, geometry, dependency, or adapter condition.
This makes the missing data visible without treating an empty result as an
inference failure.

## Inference boundary

The manifest must declare all of the following:

```json
{
  "schema": "ds2-position-manifest/v1",
  "manifest_sealed": true,
  "reference_coordinate_in_manifest": false,
  "position_evaluation": "post_seal_external_only"
}
```

It rejects coordinates or truth fields under the known reference names, a
session duplicated across groups, a partial tracking-product map, and a prior
that does not explicitly state `reference_used_for_selection: false`.
Inference tasks are made only from `train` groups. Validation and test groups
remain listed in the manifest for the later external evaluator but are never
included in task session IDs. A task records
`reference_used_for_inference: false` and has no evaluation coordinate or
error field.

Each whole-session group needs a product record for every session with a
complete tracking status (`complete`, `completed`, or the compatibility value
`ready`), a `tracking_product_digest`, a receipt file, a causal/cache file, and
a candidate-policy digest. These records are the sealed product artifacts
reported by `/api/v1/scanner/tracking/{session_id}`; legacy analysis endpoint
`track_count` is not a readiness input. The scheduler rejects inconsistent
ready policy digests across TRAIN groups. It preserves source cache paths in
the manifest/task boundary instead of rebuilding or copying large caches.

## Staged plan

The planner emits these classes independently:

| Class | Arms | When eligible |
| --- | ---: | --- |
| Primary | 4 | receipt-bound products and explicit runner adapter |
| Conditional | 5 | primary/joint predecessor and any support condition |
| Diagnostic | 8 | primary baseline plus geometry/adapter gate where required |

Every task fixes a bounded search policy: 100 km screening cells, 25 and 6.25
km refinements, beam width 3, and at most 8 exact finalists. The joint arms
require at least two whole TRAIN groups. The shared-NORAD-rate task remains
blocked on an explicit post-baseline NORAD-overlap receipt. The scheduler does
not turn that conditional prerequisite into a guessed association.

Cone tasks use the same staged geographic screen and cache receipt. The
full-FOV diagnostic sweep covers 10, 20, 25, 30, 40, 50, 60, 70, 80, and 90°;
the local fitted sweep covers 10–50°. Fixed-cone tasks carry 10, 15, 20, and
30° half-angle cases. All cone variants require a readable geometry artifact,
a verified RX/LNB mapping or symmetric two-mapping marginalization, and an
upward-direction constraint before they can become runnable.

## Running it

Once a DS2 manifest is frozen, build a plan with:

```bash
.venv/bin/python reports/2026_09_24_ds2_experiment_scheduler/run.py \
  --manifest /path/to/ds2-manifest.json \
  --output reports/2026_09_24_ds2_experiment_scheduler/artifacts
```

This writes `schedule.json`, its SHA-256 seal, one JSON file per task, and
`status.json`. `schedule.json` contains status counts, per-group readiness,
each task's configuration/dependencies, and required source paths. The plan is
safe to inspect before any evidence is available.

To launch after DS2-specific adapters have been registered, pass a separate
runner registry with schema `ds2-runner-registry/v1`; each runner command must
contain `{task}`. Execution is deliberately opt-in and bounded:

```bash
.venv/bin/python reports/2026_09_24_ds2_experiment_scheduler/run.py \
  --manifest /path/to/ds2-manifest.json \
  --runner-registry /path/to/ds2-runners.json \
  --output /path/to/schedule-output \
  --execute-ready --max-tasks 8
```

After an arm seals, write only its opaque task IDs to
`{"sealed_task_ids": [...]}` and pass that file with
`--completed-dependencies` to create the next stage. Dependencies include the
prior ID, so a completed Sacramento task cannot accidentally unlock a Reno
conditional task. The receipt reader rejects reference fields too.

`status.json` records command result, elapsed runtime, and stdout/stderr tails
for each attempted task. Models without an explicit DS2 adapter remain
`adapter_required`; the scheduler never substitutes the DS1 hard-coded cache
roots. It will also not execute unbounded or dependency-blocked work.

## Frozen inventory binding

`build_tracking_manifest.py` reads the frozen DS2 inventory and the
authoritative per-session tracking endpoint, then saves a reduced receipt for
each raw-eligible session. It deliberately strips `observer_site` and all
other product body fields except state, product/configuration/candidate-policy
digests, and artifact hashes. It also creates a deterministic whole-session
TRAIN/validation/test partition and keeps radio/sample-rate cohorts separate.

The checked-in binding at `artifacts_cohort_v1/ds2-tracking-manifest.json` was made from
the frozen 20-session inventory. At binding time it found 17 `complete` and 3
`pending` tracking products, with 10/7/3 sessions in TRAIN/validation/test and
eight radio/sample-rate batch groups. Its scheduled 63 tasks are all correctly
blocked: completed products still lack bound causal cache paths, three TRAIN
products were pending, the blind geographic prior has not been bound, and the
capture-time geometry binding has not been supplied. The builder creates
four-session batches inside each radio/sample-rate cohort; only the 2.5 MS/s
`radio_pluto_5d4d` cohort currently has two TRAIN batches eligible for a
same-cohort joint arm. No inference command was launched. The status and task
records are in `artifacts_cohort_v1/schedule/`.

## Verification

`test_run.py` covers blocked tracking evidence, the fully ready primary path,
geometry gating, whole-session uniqueness, reference-data rejection, schedule
sealing, and a one-task bounded adapter execution. Verified with:

```bash
.venv/bin/ruff check reports/2026_09_24_ds2_experiment_scheduler
.venv/bin/pytest -q reports/2026_09_24_ds2_experiment_scheduler/test_run.py
```
