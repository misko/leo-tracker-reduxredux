# DS1 iteration 6: matched cap-300 proposal / exact-rank ablation

## Result

Iteration 6 completed in 1,139.7 seconds (19.0 minutes) using four workers.
It reused the already converged 153 iteration-5 coordinate/tau proposals and
performed no new geographic or timing scan.  For each prefix-6 TRAIN group and
each of the nine fixed tau values, it retained the three lowest converged
cap-300 proposal rows.  The resulting 27 rows per group were augmented by the
iteration-4 exact winner coordinate at its original tau when absent, producing
28 exact-SGP4 audits per group.

Expanded exact coverage changed the selected coordinate for both groups while
retaining the iteration-5 selected tau in each case.  The exact objective
improved for both groups.  This directly confirms that the prior top-12
shortlist was excluding better rows under the final exact objective.

## Method and inference boundary

Candidate coordinates and the common tau grid are fixed by the completed,
reference-free iteration-5 artifact.  A proposal must already have reached
the cap-300 rate-fit convergence criterion.  The predeclared rule takes the
top three distinct spatial rows at each tau by the stored cap-300 objective,
then deduplicates `(latitude, longitude, tau)`.  It explicitly retains the
iteration-4 exact winner at its original tau if the top-three rule omitted it.

For every retained row, the audit creates a fresh full-observation hard
association and runs the existing exact-SGP4 cap-800 rate fit.  Exact cap-800
full-observation capped loss alone selects the group winner; all other fields
are diagnostic or deterministic tie breaks.  No reference coordinate or
post-seal error is read by the inference script.  Reference enters only in
`evaluate_iteration6_postseal.py` after the inference artifact is complete.

## TRAIN results

| Group | Reused converged rows | Exact rows | Tau | Iteration-5 exact loss | Iteration-6 exact loss | Exact replay max |
|---|---:|---:|---:|---:|---:|---:|
| `20260921_00` | 72 | 28 | -1.00 s | 0.039314 | 0.038965 | 0.0000622 Hz |
| `20260921_16` | 81 | 28 | -0.50 s | 0.077364 | 0.077087 | 0.0000476 Hz |

Both exact replay gates passed the 0.2 Hz threshold.  Group `00` moved from
`(37.87484256, -122.51261467)` to `(37.86781662, -122.51261552)` at -1.00 s.
Group `16` moved from `(37.86085709, -122.47284114)` to
`(37.84680823, -122.48174711)` at -0.50 s.  The latter is the iteration-4
spatial coordinate, now selected at a different tau; its required retained
iteration-4 audit at -0.75 s ranked below this -0.50 s row.

Each group needed the explicit iteration-4 retained row, so the final audit
sets contain 27 cap-300 top-three rows and one retained iteration-4 row.  The
retained rows were not selected: their exact losses were 0.039190 (`00`) and
0.077349 (`16`), respectively.

## Post-seal comparison

| Group | Iteration-5 error | Iteration-6 error | Delta |
|---|---:|---:|---:|
| `20260921_00` | 3.720 km | 3.157 km | -0.563 km |
| `20260921_16` | 1.730 km | 0.423 km | -1.307 km |

The wider exact audit improves the sealed comparison for both groups and
recovers the iteration-4 spatial error for `16`.  These are shared TRAIN
observations and remain development evidence, not a held-out model claim.

## What worked, what did not, and next

The ablation worked as intended: all exact-eligible candidates were previously
converged, the fixed candidate policy was deterministic, fresh association was
used for every exact audit, and expanded exact coverage changed both results
without widening the geographic or tau search.  The run remained well below
the one-hour bound.

The cap-300 proposal ranking still does not exactly reproduce the cap-800
ranking.  A bounded next step is to compare proposal and exact rank
correlation within these completed 56 audits, then decide whether a modest
per-tau exact quota above three is justified.  It should continue using the
frozen spatial/tau set until that measurement supports a wider search.

## Artifacts and reproduction

- `iteration6-results.json`: reference-free inference, reused proposals,
  fresh associations, exact audits, and exact-only winners.
- `iteration6-postseal/iteration6-postseal.json`, CSV, and PNG: external
  evaluation only.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_joint_rate_search/test_*.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_24_ds1_joint_rate_search/iteration6_matched_exact_ablation.py \
  --workers 4 --output reports/2026_09_24_ds1_joint_rate_search/iteration6-results.json
.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/evaluate_iteration6_postseal.py \
  --inference reports/2026_09_24_ds1_joint_rate_search/iteration6-results.json \
  --output-dir reports/2026_09_24_ds1_joint_rate_search/iteration6-postseal
```
