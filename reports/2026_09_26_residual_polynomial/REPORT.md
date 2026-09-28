# Polynomial residual diagnostic: DS5 08:50

## Finding

Unrestricted quadratic/cubic corrections can make conflicting satellite hypotheses nearly indistinguishable, including on the original evaluation observations. Residual RMS after polynomial subtraction is therefore not a sufficient association test. The magnitude and complexity of the required correction contain potentially useful information, but need physical calibration and independent validation before defining rejection thresholds.

This is the previously diagnosed session `scan-fw-dc1153010e57ac76`. Original ID 64068 and alternative ID 50844 are competing hypotheses, not independently authenticated wrong/correct labels. The known receiver coordinates do not establish satellite identity.

## Paired-receiver example

Channel 3, overlapping tracks `0b8ea715` and `98dbb677`, at the known receiver coordinates. Each row fixes its own previously training-selected independent timing; polynomial coefficients use training observations only. Values are evaluation RMS in Hz.

| Receiver / candidate | Fixed timing (s) | Constant | Linear | Quadratic | Cubic |
|---|---:|---:|---:|---:|---:|
| 0 / original 64068 | -18.1 | 3768.7 | 1341.2 | 131.0 | 88.8 |
| 0 / alternative 50844 | +42.0 | 342.6 | 221.3 | 77.5 | 77.1 |
| 1 / original 64068 | -9.0 | 2786.7 | 273.0 | 74.8 | 28.7 |
| 1 / alternative 50844 | +41.6 | 428.2 | 182.4 | 28.1 | 27.9 |

For receiver 0, the fitted cubic correction varies by 11,945.8 Hz over the training timestamps for 64068, versus 1,191.4 Hz for 50844. The simpler linear-only slope is -343.6 versus -28.3 Hz/s. These are conditional model corrections, not measured oscillator drift. Timing and polynomial terms are confounded; magnitude comparisons should eventually be made in a jointly regularized model.

The problem is not limited to these two IDs. Candidate 67700 reaches cubic RMS 73.9 Hz on receiver 0 and 27.4 Hz on receiver 1, slightly below 50844. This does not establish 67700 as correct: the unconstrained polynomial has absorbed much of the differentiating Doppler shape.

## Protocol and artifacts

- Reuse the immutable earlier diagnostic's saved residuals, timestamps and masks; verify all 147 saved candidate/track/site baseline RMS values within 1e-7 Hz.
- Evaluate all eight previously diagnosed tracks and every saved candidate at each of the three independently generated fixed sites: 147 candidate/track/site combinations, each with degrees 0, 1, 2 and 3.
- Freeze each candidate's independent training-MAP timing from the earlier experiment. This is **not** the shared-timing model or a joint timing/polynomial optimizer. Consequently these baselines must not be compared directly to the earlier shared-timing table.
- Fit ordinary least squares in centered, scaled time using only original training observations. The constant arm refits the intercept by OLS rather than retaining the earlier robust CFO; this explains differences from previously quoted RMS values.
- Report all degrees; do not select candidates or degrees using evaluation scores. No classifier, regularization strength, threshold or posterior association probability is learned here.
- This is a conditional unregularized flexibility stress test, not the proposed final regularized inference model. No cross-receiver correction transfer has been tested.
- The case and tracks were selected retrospectively, evaluation masks have been reused, and observations are correlated. These are not fresh validation scores or confirmed-ID classification accuracy. No geographic search, cross-site candidate sharing, production changes or RF collection.

`results.json` contains every fit, coefficients, evaluation residuals and source/evidence/snapshot hashes. `polynomial_core.py` is pure numerical code; `run_example.py` performs local artifact I/O. Six tests pass, including exact polynomial recovery, partition guards and invariance of fitted coefficients to arbitrary changes in evaluation values.

Reproduce with the installed API environment:

```sh
/opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_26_residual_polynomial/run_example.py
/opt/leo-tracker/current-api/.venv/bin/python -m pytest -q reports/2026_09_26_residual_polynomial/test_polynomial_core.py
```

## Next model experiment

Use a shrinkage prior on correction amplitude/curvature calibrated outside these cases, and score predictive evidence with complexity accounted for. Test whether one satellite-shared correction predicts other receiver/channel tracks, while accounting separately for receiver frequency effects. Any inner model selection must re-fit timing and polynomial terms within each training fold; reusing a timing fit from the full training partition would leak into an inner holdout. Preserve an ambiguous-association outcome when several hypotheses remain plausible. This experiment does not authorize promoting any candidate to a verified identity.
