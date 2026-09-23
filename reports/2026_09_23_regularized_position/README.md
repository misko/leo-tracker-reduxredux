# Regularized per-track timing diagnostic

This bounded mechanism diagnostic compares integer per-track timing offsets with
per-scan clock shrinkage on the first 48 frozen training sessions.  At each
candidate identity and timing offset, one constant CFO is profiled from the
saved randomized training rows only.  For each scan clock on the integer
`[-5, 5]` second grid, each track then chooses the candidate/timing profile
minimizing `training_MSE + lambda * (tau_track - clock)^2`.  The fixed penalties
are 0, 100, 1,000, 10,000, and 100,000 Hz²/s².  A separate hard-shared control
sets every track offset equal to the scan clock.

The three original 16-scan finalist coordinates are fixed inputs.  The
duration-weighted, 800-Hz-capped randomized reserved-row RMS selects both the
penalty and one of those three points within the exposed training cohort.  It
is inner model selection, not untouched validation.  `inference.json` records
that choice and bindings before the worker opens any validation state cache.

The frozen selected penalty is then replayed against lambda zero on the 49
retrospective development-validation sessions.  For every 1-, 6-, 18-, and
48-scan manifest window, each model can select only among the same three fixed
points using its window's training rows; its reserved rows are reported after
that selection.  Reference-coordinate distance is appended only after the
train seal and is never used for a choice.

The free `[-5, 5]` shared center is a latent regularization parameter, not a
measured receiver UTC clock.  It may absorb TLE and propagation error.  The
per-scan center uses equal-track raw MSE plus the shrinkage penalty; location
ranking uses the separate duration-weighted, uncoupled capped-RMS heuristic.
This is not a joint MAP or global likelihood.

The candidate pool is a conditional union of production-selected identities,
not a full-catalogue discovery procedure.  The fixed locations were derived
from prior exposed development data.  This experiment therefore measures a
timing-nuisance mechanism under strong conditioning; it cannot establish
independent position recovery or prospective accuracy.

Reproduce from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python \
  tools/research/position_regularized_timing.py \
  --manifest reports/2026_09_23_position_train_val_test/dataset/manifest.json \
  --locations reports/2026_09_23_sixteen_scan_comparison/common_finalists.json \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --output reports/2026_09_23_regularized_position
.venv/bin/python -m pytest -q tests/tools/test_position_regularized_timing.py
```

`results.json` binds the dataset and cache manifests, locations, joint cache
consumer, sealed inference payload, and replay worker by SHA-256.  A
validation-only replay rejects changed dataset, locations, cache manifests,
joint consumer, or fixed model list; its worker digest may differ from the
sealed training worker after an audited replay-only bug fix.  `training_selection.png`
visualizes the inner selection scores.
