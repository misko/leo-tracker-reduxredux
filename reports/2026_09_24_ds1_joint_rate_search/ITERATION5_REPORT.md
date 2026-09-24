# DS1 iteration 5: fixed-spatial timing and convergence refinement

## Result

Iteration 5 completed in 531.9 seconds with four workers.  It froze the eight
and nine iteration-4 spatial coordinates for the two prefix-6 TRAIN groups,
then evaluated all 153 coordinate/tau combinations on the common grid
`{-2.25, -2.00, ..., -0.25}` seconds.  All 72 rows in `20260921_00` and all
81 rows in `20260921_16` reached the cap-300 rate-profile convergence
criterion, so no unconverged row was eligible for exact selection.

The selected taus, -1.00 and -0.50 seconds, are both interior to the fixed
grid.  This removes the earlier local-stencil timing-edge diagnostic for this
bounded spatial candidate set.

## Method

Spatial coordinates come only from the completed, reference-free iteration-4
candidate union.  At each frozen coordinate, tau is processed in ascending
grid order.  A rate fit begins from the preceding tau’s per-NORAD rate map
when the NORAD is retained, otherwise at zero.  Hard candidate association is
still recomputed at every tau.

The screening profile has a 300 Hz capped loss, the historical bounded
Normal-rate prior, an analytic gradient, and a 300-iteration limit.  Its
`converged` flag is required for exact-shortlist eligibility.  The shortlist
contains one deterministic converged surrogate leader per tau plus spatially
separated candidates up to the predeclared top-12 limit.  It contained nine
and ten candidates respectively.  Exact SGP4 then reranks each shortlist by
the existing reviewed exact full-observation objective.

## TRAIN results

| Group | Frozen spatial points | Converged tau fits | Exact shortlist | Selected tau | Cap-300 surrogate loss | Exact capped loss | Exact replay max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `20260921_00` | 8 | 72 / 72 | 9 | -1.00 s | 0.183175 | 0.039314 | 0.0000628 Hz |
| `20260921_16` | 9 | 81 / 81 | 10 | -0.50 s | 0.207619 | 0.077364 | 0.0000475 Hz |

Both exact replay gates passed the 0.2 Hz threshold.  The cap-300 surrogate
loss is intentionally not numerically comparable to the existing exact
cap-800 objective; its role is timing proposal and convergence control.  The
exact cap-800 full-observation objective alone selects the group result.

## Post-seal comparison

Reference data enters only after inference completion in
`evaluate_iteration5_postseal.py`.

| Group | Iteration-4 error | Iteration-5 error | Delta |
|---|---:|---:|---:|
| `20260921_00` | 4.204 km | 3.720 km | -0.484 km |
| `20260921_16` | 0.423 km | 1.730 km | +1.307 km |

The timing refinement improved one group and substantially worsened the other
in post-seal evaluation.  Since the shared TRAIN observations selected tau,
the pair is development evidence only and does not establish a timing model
improvement.

## What worked, what did not, and next

The continuation implementation worked: all fixed-grid profiles converged,
the total run stayed under ten minutes, and no eligible exact candidate was
truncated.  The bounded grid also produced interior tau selections, directly
addressing the measured edge issue.

The cap-300 timing surrogate did not transfer consistently to post-seal
position.  Its selected `20260921_16` tau moved away from the iteration-4
position despite a qualified exact RF fit.  The remaining limitation is a
surrogate/exact objective mismatch: cap-300 proposes timing, while cap-800
exact loss makes the final choice.

The next justified step is not a wider geographic or timing grid.  It is a
small matched ablation that evaluates cap-300 and cap-800 exact score ranks on
the same fixed tau shortlist, retaining the exact-only group selection rule.

## Artifacts and reproduction

- `iteration5-results.json`: reference-free inference, all convergence rows,
  exact shortlists, and exact winner gates.
- `iteration5-postseal/iteration5-postseal.json`, CSV, and PNG: external
  evaluation only.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_joint_rate_search/test_*.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_24_ds1_joint_rate_search/iteration5_timing_refinement.py \
  --workers 4 --output reports/2026_09_24_ds1_joint_rate_search/iteration5-results.json
.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/evaluate_iteration5_postseal.py \
  --inference reports/2026_09_24_ds1_joint_rate_search/iteration5-results.json \
  --output-dir reports/2026_09_24_ds1_joint_rate_search/iteration5-postseal
```
