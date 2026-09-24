# Cached consistent-cap800 runner for DS2

## Status

The runner is implemented and locally tested, but DS2 inference has not been
launched. The frozen DS2 inventory currently has zero analysis-ready sessions,
so no scientifically valid group manifest can yet be constructed.

This runner addresses the measured DS1 iteration-12 bottleneck without
changing its statistical objective. Proposal selection and exact selection
both use the cap-800, track-duration-weighted, all-qualified-observation loss.
Regularization still identifies per-NORAD nuisance rates, but its prior is not
added to the geographic selection score.

## Execution design

Each geographic point, group, and tau has a deterministic identity bound to
the entire frozen run manifest. Its hard support is stored as an atomic NPZ
plus a digest-bound JSON receipt containing associations and track weights.
A process interruption after support construction therefore does not require
rebuilding predictions.

Each completed nuisance fit and exact audit is also cached atomically. Level
results are immutable JSON artifacts; only a small digest-bound checkpoint
pointer is replaced. Resume verifies the frozen configuration and every
completed level, then starts at the first incomplete level. It never treats a
partially completed level as complete.

Warm starts follow two deterministic paths:

1. the same tau at the nearest retained parent location; then
2. the preceding tau at the current location.

They only initialize the convex regularized nuisance optimization. The
published score remains the identical cap-800 loss. Cache identities include
the warm-start digest so a changed initialization policy cannot silently reuse
an old fit.

## Frozen run manifest

The execution manifest uses schema `consistent-cap800-frozen-run/v1` and must
bind:

- one frozen dataset manifest and its SHA-256;
- two or more disjoint whole-session groups with positive weights summing to
  one;
- embedded full-observation tasks for each group;
- a reference-free origin and seed set;
- the tau grid, spatial levels, basin/tau/finalist budgets; and
- exact paths to the joint-support, full-observation, and orbit modules.

If the dataset has a `scans` inventory, every grouped session must explicitly
be `analysis_ready: true`. Geographic reference data is forbidden from the
inference manifest.

## Current DS2 gate

The read-only preflight against
`reports/2026_09_24_ds2_inventory/manifest.json` returns zero analysis-ready
sessions and `launchable: false`. No support, prediction, fit, checkpoint, or
exact audit was created.

## Verification

The focused tests cover atomic cache round trips and corruption detection,
immutable/resumable level checkpoints, warm-start objective invariance,
nearest-parent warm starts, frozen manifest validation, disjoint session
groups, and the current DS2 readiness gate.

```bash
.venv/bin/python -m pytest -q \
  reports/2026_09_24_ds2_consistent_cap800_runner/test_runner.py

.venv/bin/python reports/2026_09_24_ds2_consistent_cap800_runner/runner.py \
  --inventory-preflight reports/2026_09_24_ds2_inventory/manifest.json \
  --output reports/2026_09_24_ds2_consistent_cap800_runner/ds2-preflight.json
```

Once an analysis-ready frozen run manifest exists, first invoke
`--manifest ... --preflight-only`. Execution additionally requires a local
`--work-root` and final `--output`; rerunning the same command resumes from
verified caches and completed levels.
