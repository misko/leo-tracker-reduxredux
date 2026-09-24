# DS1 iteration 4: seed-union exact selection

## Result

Iteration 4 removed seed-specific choice after candidate generation.  For each
prefix-6 TRAIN group, the Reno and Sacramento iteration-3 traces supplied a
reference-free candidate union.  The predeclared surrogate shortlist was
deduplicated, fully recomputed, and exact-SGP4 audited before one group winner
was selected strictly by exact capped full-observation loss.

The run completed 17 candidates in 394.7 seconds using four workers: eight
for `20260921_00` and nine for `20260921_16`.  Every exact replay gate passed,
with maximum Doppler discrepancies below 0.0000583 Hz.

## Inference design

For each group, the fixed candidate procedure was:

1. union the reference-free Reno and Sacramento iteration-3 geographic/tau
   traces;
2. retain the eight unique lowest surrogate-score coordinates, then add both
   iteration-3 finalists if absent;
3. recompute full hard associations, bounded causal per-NORAD rates, and
   per-track CFOs at every retained coordinate from the causal caches;
4. fit and exact-SGP4 audit every recomputed candidate; and
5. select the group winner only by exact full-observation capped loss.

The engine source is a deterministic group-owned cache binding.  It does not
select by, compare, or preserve either original seed.  No reference data,
error value, truth coordinate, or observation mask is read by the inference
driver.

## Surrogate versus exact ranking

| Group | Candidates | Surrogate-leading exact loss | Exact-selected loss | Exact-selected surrogate score | Result |
|---|---:|---:|---:|---:|---|
| `20260921_00` | 8 | 0.039699 | 0.039190 | 0.060021 | exact selection moved from the surrogate leader |
| `20260921_16` | 9 | 0.077410 | 0.077349 | 0.101072 | exact selection moved from the surrogate leader |

The precise-order changes validate the concern behind this iteration: cache
surrogate ranking and exact rate loss can disagree in a tight geographic
basin.  Both differences are small, but they are enough to make a
surrogate-only seed-specific winner unreliable.

| Group | Exact-selected latitude / longitude | Tau | Exact capped loss | Surrogate/exact loss difference | Exact replay maximum |
|---|---|---:|---:|---:|---:|
| `20260921_00` | 37.867725, -122.527274 | -1.25 s | 0.039190 | 0.004639 | 0.0000549 Hz |
| `20260921_16` | 37.846808, -122.481747 | -0.75 s | 0.077349 | 0.002004 | 0.0000582 Hz |

## Post-seal comparison

The external reference was introduced only in
`evaluate_iteration4_postseal.py`, after the complete inference artifact had
been checked for reference fields and exact-gate success.  It did not affect
the candidate union, recomputation, exact audit, or selection.

| Group | Iteration-3 seed error range | Iteration-4 exact-selected error | Difference from best iteration-3 seed |
|---|---:|---:|---:|
| `20260921_00` | 4.204–4.260 km | 4.204 km | 0.000 km |
| `20260921_16` | 0.635–2.949 km | 0.423 km | -0.212 km |

## What worked, what did not, and next

The seed-union procedure worked as intended: both groups produce one
seed-free exact choice, all candidates are qualified, and exact selection
changed the surrogate leader in each group.  The `20260921_16` choice also
improved the post-seal result relative to either iteration-3 seed.

The procedure did not improve `20260921_00` beyond the better iteration-3
seed: exact selection recovered that existing candidate.  It also remains a
small, overlapping TRAIN development matrix, so its post-seal distances are
not independent validation.

The next justified step is to retain this union/exact finalizer and widen
candidate generation only when a bounded cache screen exposes separated
basins.  A full exact rate fit at every geographic point is not warranted by
these two tight basins; their rank mismatch is resolved by the modest exact
shortlist.

## Artifacts and reproduction

- `iteration4-results.json` is the reference-free machine-readable inference
  result, including every recomputation, exact audit, and winning objective.
- `iteration4-postseal/iteration4-postseal.json`, CSV, and PNG are external
  evaluation artifacts.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_joint_rate_search/test_*.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_24_ds1_joint_rate_search/iteration4_group_union.py \
  --workers 4 \
  --output reports/2026_09_24_ds1_joint_rate_search/iteration4-results.json

.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/evaluate_iteration4_postseal.py \
  --inference reports/2026_09_24_ds1_joint_rate_search/iteration4-results.json \
  --output-dir reports/2026_09_24_ds1_joint_rate_search/iteration4-postseal
```
