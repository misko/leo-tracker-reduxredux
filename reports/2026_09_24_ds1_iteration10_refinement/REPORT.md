# DS1 iteration 10 shared-position refinement

## Result

The sealed, reference-free iteration selected the shared receiver coordinate
`(37.85822833, -122.47896246)` degrees.  Relative to the sealed iteration-9
winner that was its only spatial origin, it is `+0.0488287 km` east and
`-0.0976563 km` north.  Its equal-group exact cap-800 loss is `0.0581276592`:
`0.0390230396` for `20260921_00` and `0.0772322787` for `20260921_16`.

Each group selected its own nuisance solution.  The selected global taus are
`-0.75 s` (00) and `-0.50 s` (16); hard associations, per-NORAD rates, and
per-track CFOs are likewise group-specific.  Both exact SGP4 gates passed.
Their largest cache/exact Doppler differences were `5.17e-05 Hz` (00) and
`4.75e-05 Hz` (16), well below the `0.2 Hz` gate.

`inference.json` was sealed before the reference was consulted.  The separate
post-seal evaluator measured `1.1792858 km` error, versus `1.2428905 km` for
iteration 9.  That `0.0636047 km` reduction is evaluation only; it did not
choose an origin, proposal, finalist, tau, or winner.

## Method and bound

The driver accepts only the completed, reference-free iteration-9 inference
and validates its fixed common tau grid.  It centres a symmetric nine-point
local lattice on the iteration-9 winner, retains the best three proposal
basins at each level, and uses spacings of `0.1953125`, `0.09765625`, and
`0.048828125 km`.  Deduplication left 9, 23, and 26 coordinates at the three
levels respectively.

At every coordinate, each group independently evaluates the unchanged fixed
tau grid `[-1.25, -1.00, -0.75, -0.50, -0.25] s`.  Its score is the equal
mean of the groups' best cap-300 proposal losses, so no group obtains extra
weight from its observation count.  The predeclared exact stage audited the
eight best final proposal coordinates and two tau proposals per group: exactly
32 SGP4 audits.

The run used four workers and completed in `1093.73 s` (18.23 minutes), under
the one-hour bound.  It does not alter the shared runner and does not read the
post-seal evaluator from the inference path.

## What worked, what did not, and next

The RF-only screen and exact audit both favored a compact east/south local
move while retaining the same independently selected group taus as iteration
9.  The joint exact loss improved by `7.20e-06`, and all exact gates passed.
The post-seal comparison also improved, but this corroborates the sealed
result rather than validating its selection procedure.

The exact margin remains narrow: the runner-up loss is `0.0581392185`, only
`1.16e-05` above the winner.  That does not establish sub-50-metre spatial
identifiability, and a two-tau exact shortlist still leaves untested timing
proposals by design.

The next iteration should freeze this winner and predeclare a randomized
whole-session validation split, keeping correlated observations together.  It
can then evaluate whether the small local loss improvement persists out of
sample before spending more compute on a finer spatial or tau grid.

## Artifacts and reproduction

- `inference.json.gz` is the deterministic gzip copy of the sealed inference
  record stored in the repository. Decompress it to `inference.json` for the
  replay and export commands below.
- `inference/iteration10-inference-finalists.csv` and `.png` export finalists
  without a geographic reference.
- `evaluation/iteration10-postseal.json`, `.csv`, and `.png` are the separate
  post-seal reference comparison.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration10_refinement/test_run.py
.venv/bin/python reports/2026_09_24_ds1_iteration10_refinement/run.py \
  --output reports/2026_09_24_ds1_iteration10_refinement/inference.json --workers 4
.venv/bin/python reports/2026_09_24_ds1_iteration10_refinement/export_inference.py \
  --inference reports/2026_09_24_ds1_iteration10_refinement/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration10_refinement/inference
.venv/bin/python reports/2026_09_24_ds1_iteration10_refinement/evaluate_postseal.py \
  --inference reports/2026_09_24_ds1_iteration10_refinement/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration10_refinement/evaluation
```
