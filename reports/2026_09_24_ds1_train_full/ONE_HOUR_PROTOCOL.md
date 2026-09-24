# DS1 TRAIN one-hour full-observation comparison

This is a bounded TRAIN-development benchmark.  It uses the frozen DS1 TRAIN
membership and the existing receipt-bound causal caches, and writes no cache
or source-corpus data.  Validation and TEST inputs are not in the manifest.

The sealed manifest has four views, selected solely by dataset order:

| TRAIN group | Single scan | Multi-scan view |
|---|---|---|
| 20260921_00 | first recorded scan | first six recorded scans |
| 20260921_16 | first recorded scan | first six recorded scans |

The singleton is intentionally retained inside the matching prefix-6 only to
make the requested single-versus-multi comparison.  The benchmark removes all
other sliding windows, disjoint blocks, nested 2/4/8/16/32 prefixes, full
groups, and the combined group.  The four views are not independent samples.

Every view runs from both frozen priors: Sacramento, 250 km; Reno, 500 km.
Every fit uses all qualified observations from every input scan.  A track's
constant CFO, identity/association, timing nuisance, RF objective, and
location are fitted/scored on that same full observation set.  There is no
within-track mask or held-out observation.  The receiver reference coordinate
is absent from all tasks and may be introduced only by a separate post-seal
TRAIN evaluator to report great-circle error.  That evaluator must never
alter an inference result or select which task to run.

## Frozen task matrix

The 4 views × 2 priors form 8 case-prior arms.

| Stage | Methods | Tasks |
|---|---|---:|
| Core | baseline, global time, regularized per-scan time, independent per-track time, soft association, soft association + global time | 48 |
| Exact orbit | causal per-NORAD orbit rate, global time + per-NORAD orbit rate | 16 |
| Total | eight supported methods on every case-prior arm | 64 |

The unsupported joint soft-association + global-time + orbit-rate method is
excluded rather than approximated by a different model.  Finish and seal all
48 core tasks before launching the predeclared 16 orbit tasks.  This staging
does not promote cases based on position error, truth, or any other observed
outcome; all eight case-prior arms always proceed to the orbit stage.

All methods use the same 100, 50, 25, and 12.5 km geographic levels and beam
width two.  Timing methods use the fixed symmetric -2 to +2 s grid at 0.5 s
spacing.  Orbit tasks use that nine-point grid when global time is fitted,
one exact RF-selected finalist, and one internal exact-rate worker.  The
result is a 12.5-km-grid method comparison, not a sub-kilometre positioning
claim.

## Runtime budget on 24 cores

The current post-fix pilot measured a Reno baseline's initial 121-cell pass
at 6.25 seconds.  The declared four-level beam-two search has at most 175
Reno and 70 Sacramento spatial evaluations: the initial grid plus at most 18
new points at each of three refinements.  The nine-point timing grid gives a
conservative one-scan timing-arm estimate of 82 seconds for Reno and 33
seconds for Sacramento before cache-load overhead.  Budgeting prefix-6 at an
eightfold single-scan cost gives 11 and 4.5 minutes respectively per
timing-heavy arm.

The core's conservative aggregate is about 9,000 single-core seconds.  At 24
one-thread workers that is under 7 minutes of ideal wall time; reserve 15
minutes for loading, scheduling imbalance, and the soft likelihood.  The
exact-orbit stage is the riskier part: run at its registry cap of eight task
processes, each with one exact finalist and one internal worker.  Reserve two
15-minute waves (30 minutes) for its 16 arms.  Leave 15 minutes for sealed
artifact validation, post-seal TRAIN truth scoring, and a rerun of any failed
non-orbit core task.  The projected wall time is therefore 45 minutes, with a
15-minute margin inside one hour.

If an orbit task cannot finish in its 15-minute allocation, record it as a
bounded non-completion and do not substitute a cheaper method or select a
truth-favoured subset.  A scheduler-enforced per-task timeout is required to
turn that allocation into a hard one-hour ceiling.

## Build and run

```bash
.venv/bin/python reports/2026_09_24_ds1_train_full/build_one_hour_manifest.py

.venv/bin/python reports/2026_09_24_ds1_train_full/run_scheduler.py \
  --manifest reports/2026_09_24_ds1_train_full/one-hour-inference-manifest.json \
  --registry reports/2026_09_24_ds1_train_full/runner_registry.json \
  --tiers core --workers 24

.venv/bin/python reports/2026_09_24_ds1_train_full/run_scheduler.py \
  --manifest reports/2026_09_24_ds1_train_full/one-hour-inference-manifest.json \
  --registry reports/2026_09_24_ds1_train_full/runner_registry.json \
  --tiers extended --workers 24
```

Set the orbit registry's two method caps to eight.  A sealed artifact is
resumed only when its task ID, result schema, full-observation attestation,
and SHA-256 seal validate; a legacy artifact with different options or task
ID is not reused.
