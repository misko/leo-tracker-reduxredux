# DS1 iteration 12: consistent-objective arm

## Outcome

This arm did not produce a position estimate. The authoritative run was
stopped when measured throughput projected an 82--100 minute completion time,
beyond the predeclared one-hour bound. No partial level, coordinate, or
post-seal reference comparison was used to choose or publish a winner.

The scientific change is implemented and tested: proposal selection now uses
the same cap-800, all-qualified-observation capped loss as the exact SGP4
stage. The nuisance fit remains regularized, but its prior is no longer added
to the geographic selection score. Both groups retain independent hard
associations, timing, per-NORAD rates, and per-track CFOs. The input is the
complete DS1 TRAIN prefix-6 bundle; VAL and TEST are untouched.

## Why it exceeded the bound

The previous search was fast because it used cap-300 continuation fits for
proposal screening and reserved cap-800 exact SGP4 work for a shortlist. A
strict matched cap-800 screen must rebuild and optimize all five tau supports
for both groups at every coordinate. Under concurrent host load of roughly
85--131, the authoritative run needed about 14.5 minutes for 12 level-1
coordinates. Level 2 remained incomplete after another 25.5 minutes. A third
level and 24 exact audits still remained, giving an 82--100 minute projection.

| Attempt | Observed time | Result | Decision |
|---|---:|---|---|
| Three full seed lattices | ~22 min | First level still running | Rejected the redundant 27-coordinate expansion |
| Shared lattice, 120 iterations | ~10 min | Tau convergence gate failed | Restored the established 300-iteration proposal limit |
| Authoritative bounded run | ~41 min | Level 1 passed; level 2 incomplete | Stopped once completion projected beyond one hour |

The 120-iteration attempt was not accepted by relaxing convergence. The test
suite explicitly verifies that nonconverged tau rows are rejected and that the
authoritative configuration uses the established 300-iteration limit.

## What worked

- Proposal and exact geographic ranking now share the cap-800 loss definition.
- The inference path contains no reference coordinate and rejects unsealed
  seed artifacts.
- The search uses one shared iteration-10-centered lattice plus the sealed
  iteration 8, 9, and 10 winners, preserving a bounded initialization check.
- The exact shortlist is fixed at six coordinates and two taus per group, or
  24 audits.
- Seven focused tests cover the matched loss, multi-seed lattice, equal group
  weighting, convergence rejection, artifact separation, and whole-scan
  omission support.

## What did not work

The matched objective cannot yet be evaluated over the existing three-level
adaptive search inside one hour. Because a level is held in memory until every
coordinate finishes, the interrupted run also cannot safely expose a partial
ranking. That is the immediate engineering bottleneck; the arm says nothing
about whether the matched objective improves position error.

## Next iteration

The next version should preserve exactly this objective while changing the
execution plan:

1. Persist each completed tau-location support and checkpoint every level.
2. Warm-start adjacent tau nuisance fits, as the established screen did,
   without changing the published cap-800 selection loss.
3. Deduplicate support construction across nearby proposal and exact rows.
4. Seal the complete proposal ranking before starting exact SGP4 audits.

Those changes target repeated computation rather than the statistical model.
They should be benchmarked on level 1 first; the full arm should launch only
if projected runtime remains below one hour.

## Reproduction and artifacts

- `run-status.json` is the machine-readable negative result and runtime record.
- `iteration12-runtime-status.png` visualizes attempts and the authoritative
  runtime projection.
- `run.py` is the reference-free matched-objective implementation.
- `export_inference.py`, `evaluate_postseal.py`, and
  `leave_one_scan_out.py` are prepared for a future completed inference. They
  were not run and no post-seal artifact was generated in this arm.

```bash
.venv/bin/python -m pytest -q \
  reports/2026_09_24_ds1_iteration12_consistent_objective/test_run.py \
  reports/2026_09_24_ds1_iteration12_consistent_objective/test_artifacts.py \
  reports/2026_09_24_ds1_iteration12_consistent_objective/test_leave_one_scan_out.py

.venv/bin/python reports/2026_09_24_ds1_iteration12_consistent_objective/make_status_plot.py \
  --status reports/2026_09_24_ds1_iteration12_consistent_objective/run-status.json \
  --output reports/2026_09_24_ds1_iteration12_consistent_objective/iteration12-runtime-status.png
```
