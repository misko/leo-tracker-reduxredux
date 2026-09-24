# DS1 iteration 11 symmetric fine confirmation

## Result

Iteration 11 sealed a reference-free shared coordinate at
`(37.85844765, -122.47868468)` degrees, `+0.0244142 km` east and
`+0.0244141 km` north of the sealed iteration-10 winner.  Its equal-weight
exact cap-800 loss is `0.0581393921`: `0.0390417205` for `20260921_00` and
`0.0772370637` for `20260921_16`.  The independently fitted taus remain
`-0.75 s` and `-0.50 s` respectively; associations, per-NORAD rates, and
per-track CFOs remain group-specific.

All 32 exact SGP4 gates passed.  The winner's maximum cache/exact Doppler
differences are `5.12e-05 Hz` (00) and `4.75e-05 Hz` (16), both below the
`0.2 Hz` gate.

The inference record was sealed before reference access.  Its separate
post-seal evaluator reports `1.2126138 km`; this value did not select a
coordinate, tau, finalist, or winner.

## Method and bound

The driver consumes only the sealed reference-free iteration-10 inference and
validates the inherited common tau grid `[-1.25, -1.00, -0.75, -0.50,
-0.25] s`.  It starts from that winner alone, retains three RF-ranked proposal
basins at every level, and evaluates symmetric nine-point lattices at
`0.048828125`, `0.0244140625`, and `0.01220703125 km`.  Coordinate overlap
left 9, 26, and 27 unique points at those levels.

Each coordinate receives one independent screen for each group, with equal
weights of 0.5.  The groups do not pool observations or nuisance parameters.
The predeclared exact stage audits eight final proposal coordinates and the two
best proposal taus for each group, for exactly 32 audits.  Four workers
completed the run in `1120.34 s` (18.67 minutes), under one hour.  The shared
runner was not changed.

## Objective assessment and grid floor

The fine proposal screen appeared to improve: its selected proposal objective
was `0.2161985074`, `1.22e-06` below iteration 10's `0.2161997274`.  Exact
audit reversed that apparent gain.  Iteration 11's best exact loss is
`0.0581393921`, which is `1.17329e-05` *higher* than iteration 10's sealed
`0.0581276592`.

The top two iteration-11 exact finalists differ by only `7.88e-08`, while the
best fine-grid exact result remains worse than the frozen iteration-10
baseline.  Together, those facts indicate that the grid-only joint refinement
has reached a local objective floor at this resolution: more spatial halving
would mostly resolve a nearly flat local ranking rather than demonstrate a
reproducible exact-loss gain.  This is an inference conclusion based on exact
losses only, independent of the post-seal geographic comparison.

The next productive step is not another finer grid.  Freeze iteration 10 as
the retained in-sample solution and evaluate a predeclared randomized
whole-session validation split, keeping correlated observations together.
That test can establish whether the small local variation has predictive value
before expanding timing or spatial search.

## Artifacts and reproduction

- `inference.json.gz` is the deterministic gzip copy of the sealed RF-only
  inference record stored in the repository. Decompress it to `inference.json`
  for the replay and export commands below.
- `inference/iteration11-inference-finalists.csv` and `.png` contain no
  reference-derived quantities.
- `evaluation/iteration11-postseal.json`, `.csv`, and `.png` are post-seal
  only.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration11_fine_confirmation/test_run.py
.venv/bin/python reports/2026_09_24_ds1_iteration11_fine_confirmation/run.py \
  --output reports/2026_09_24_ds1_iteration11_fine_confirmation/inference.json --workers 4
.venv/bin/python reports/2026_09_24_ds1_iteration11_fine_confirmation/export_inference.py \
  --inference reports/2026_09_24_ds1_iteration11_fine_confirmation/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration11_fine_confirmation/inference
.venv/bin/python reports/2026_09_24_ds1_iteration11_fine_confirmation/evaluate_postseal.py \
  --inference reports/2026_09_24_ds1_iteration11_fine_confirmation/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration11_fine_confirmation/evaluation
```
