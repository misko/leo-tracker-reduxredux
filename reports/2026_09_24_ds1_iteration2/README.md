# DS1 iteration 2: sealed local geographic refinement

This is a TRAIN-only, full-observation local refinement of the one-hour DS1
comparison. It consumes the sealed stage-1 one-hour manifest and the eight
sealed `global_time` results for the same four fixed views and two original
priors. Each stage-1 result contributes its RF-objective winner coordinate as
the seed for exactly two iteration-2 fits:

| Timing method | Task count |
|---|---:|
| `global_time` | 8 |
| `per_scan_time` (regularized) | 8 |
| Total | 16 |

The seed is not a reference position. It is the selected coordinate in the
matching sealed stage-1 `global_time` inference artifact. The builder verifies
the stage-1 manifest and every source artifact SHA-256 seal before it reads a
coordinate. It rejects incomplete, non-TRAIN, non-full-observation, or
reference-contaminated sources.

Every iteration-2 task keeps the stage-1 session sequence and uses all
qualified observations, with no within-track holdout. No validation or TEST
session can enter the manifest.

## Fixed search contract

Each task searches a 25 km local radius around its own sealed stage-1 seed.
The geographic refinement levels are fixed before execution:

`6.25, 3.125, 1.5625, 0.78125, 0.390625 km`.

Each arm uses a fixed four-point timing stencil: tau zero plus the matching
sealed stage-1 global-time winner and its +/-0.25-second neighbours. This keeps
the tau-zero control while profiling timing locally without repeating the wide
screen at every fine geographic cell. `per_scan_time` retains its
regularization; it is not an independent per-track timing fit. A runner scores
and selects only with its RF objective and writes a new sealed result for the
iteration-2 task ID. The original wide prior name remains an arm label; the
seed is the local-search origin.

Build the sealed manifest after the stage-1 global-time outputs are present:

```bash
.venv/bin/python reports/2026_09_24_ds1_iteration2/build_manifest.py
```

The command validates and binds existing sealed inputs; it does not run
inference. The resulting `iteration2-inference-manifest.json` and sibling
SHA-256 file are the execution contract. Do not regenerate it after an
iteration-2 result exists: task IDs, seeds, source digests, and search grid are
frozen in that file.

The manifest deliberately retains the existing stage-1 task schema so the
bounded scheduler and timing runner can execute it directly. It adds iteration
metadata and source provenance, while `task.prior` is the 25 km seeded local
prior required by the runner. Run it from the stage-1 report root:

```bash
cd reports/2026_09_24_ds1_train_full
../../.venv/bin/python run_scheduler.py \
  --manifest ../2026_09_24_ds1_iteration2/iteration2-inference-manifest.json \
  --registry runner_registry.json --tiers extended --workers 16
```

The runner must preserve all iteration-2 options verbatim and place output only
at each declared `output_path`.

After all results are sealed, complete [REPORT.md](REPORT.md). Any reference
coordinate may appear only in a separate post-seal evaluator; it cannot choose
a seed, task, timing method, or reported winner here.
