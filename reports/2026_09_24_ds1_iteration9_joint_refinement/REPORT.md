# DS1 iteration 9: symmetric shared-coordinate joint refinement

## Result

The completed iteration-9 inference selects a shared coordinate of
`(37.8591055916, -122.4795180271)` with equal group weighting.  Its balanced
exact full-observation capped loss is `0.0581348587`; the sealed external
post-seal evaluation is **1.2428905 km**.

The winner is `+0.1953125 km` east and `-0.1953125 km` north of the sealed
iteration-8 shared coordinate.  Both group-specific taus are interior to the
predeclared grid: `-0.75 s` for `20260921_00` and `-0.50 s` for
`20260921_16`.

## Method

Iteration 9 starts only from the sealed, reference-free iteration-8 shared
winner.  It performs three symmetric 3-by-3 local lattices at 0.78125,
0.390625, and 0.1953125 km spacing.  At each coordinate, each group evaluates
the common tau grid `{-1.25, -1.00, -0.75, -0.50, -0.25}` with all qualified
observations, independent hard associations, per-NORAD causal rates, and
per-track CFOs.  The proposal objective gives each group equal weight and
retains three basins at each level.

At the final level, the eight lowest balanced proposal coordinates each retain
the top two converged taus per group.  The 32 resulting group/coordinate/tau
rows receive exact-SGP4 audits.  The final coordinate is selected by the
equal-weight mean of each group's best exact capped-loss row, with no
reference information in the selection path.

## Exact qualification and inference boundary

All 32 exact audits passed their 0.2 Hz exact-replay gate.  The selected rows
are:

| Group | Tau | Exact capped loss | Replay maximum |
|---|---:|---:|---:|
| `20260921_00` | -0.75 s | 0.0390251485 | 0.0000532 Hz |
| `20260921_16` | -0.50 s | 0.0772445689 | 0.0000475 Hz |

`inference.json` declares `reference_used_for_fit: false` and contains no
reference/truth fields.  The reference coordinate exists only in
`evaluate_postseal.py`, which writes the separately labelled `evaluation/`
artifacts after inference.  No inference was rerun during this finalization.

## What worked

The reference-free proposal/exact procedure produced a qualified shared
coordinate in 1,089.7 seconds with four workers.  The exact audit improved the
balanced objective over nearby finalists and gave an external 1.2428905 km
result.  The inference CSV and scatter PNG expose all eight exact finalists;
the evaluation CSV and PNG expose the post-seal result separately.

## What did not resolve

The selected coordinate lies on the positive-east, negative-north corner of
the finest lattice relative to iteration 8.  The first and second exact rows
are also nearly tied (0.0581348587 versus 0.0581349875), so the current mesh
does not demonstrate that its local minimum has been enclosed.  This result
does not justify a one-sided extrapolation or a wider geographic search.

## Next bounded iteration

Run one predeclared, symmetric 3-by-3 confirmation lattice **centered on the
iteration-9 winner** with 0.09765625 km spacing.  Keep the same observations,
equal group weighting, associations/rate/CFO policy, and tau grid.  Exact-audit
all nine coordinates using the same two proposal taus per group (36 exact
audits).  The winner's edge position motivates centering the next symmetric
lattice there; the interior selected taus do not motivate expanding timing.
Report the exact margin to the runner-up and stop if the exact winner is
interior at that finer scale.

## Validation and artifacts

- `inference.json.gz`: deterministic gzip copy of the completed reference-free
  inference and all exact audits. Decompress it to `inference.json` before
  running the export or evaluation commands.
- `inference/iteration9-inference-finalists.csv` and PNG: reference-free
  finalist summary.
- `evaluation/iteration9-postseal.json`, CSV, and PNG: post-seal evaluation.

Validation completed without rerunning inference:

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration9_joint_refinement/test_run.py
.venv/bin/ruff format --check reports/2026_09_24_ds1_iteration9_joint_refinement
.venv/bin/ruff check reports/2026_09_24_ds1_iteration9_joint_refinement
```
