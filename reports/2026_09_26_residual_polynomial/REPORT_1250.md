# All-track constant versus quadratic residuals: 12:50 UTC

Session `scan-fw-d86e8f23c0624bac`; all 46 tracks at each of the independently estimated locations. Sacramento's location error is 13.444 km, Reno's is 706.761 km. These names denote search branches, not receiver locations in the named cities.

| Evaluation metric | Sacramento constant | Sacramento quadratic | Reno constant | Reno quadratic |
|---|---:|---:|---:|---:|
| Median RMS (Hz) | 83.27 | 69.82 | 140.22 | 69.64 |
| 90th percentile RMS (Hz) | 289.71 | 163.81 | 365.11 | 169.71 |
| Maximum RMS (Hz) | 907.92 | 937.31 | 781.55 | 947.72 |

Quadratic fitting improves 28/46 Sacramento tracks and 36/46 Reno tracks. The median paired reduction is 12.1% and 40.2%, respectively (not the percentage change in population medians). The median training-span peak-to-peak quadratic correction is 105.5 Hz at Sacramento and 260.8 Hz at Reno.

The much-worse Reno location benefits more from polynomial flexibility: the median and 90th-percentile distributions nearly coincide after correction. This is evidence that unregularized per-track quadratic correction removes useful location discrimination in this selected case. It is not proof of particular satellite identities or an evaluation of a regularized joint solver. Maximum evaluation RMS increases at both locations; training improvements do not guarantee evaluation improvements.

## Exact comparison

- Freeze each branch's own training-only zero-timing satellite IDs from the earlier DS5 probabilistic experiment; these are not necessarily the production document's selected IDs.
- For each track independently, select baseline timing using the original age-conditioned t4 prior plus robust frequency likelihood (100 Hz scale), over -60 to +60 seconds in 0.1-second steps, with only training observations. No fits hit this timing boundary.
- Hold that timing and satellite ID fixed for both polynomial arms. Fit degree 0 or degree 2 by ordinary least squares on training data. Degree 2 includes intercept, linear and quadratic terms. Degree 0 refits the robust baseline offset by least squares for consistency.
- Evaluate RMS on the original evaluation observations. Use no RMS cap; each track has equal weight in the plotted distributions. No degree selection or evaluation-guided fitting.
- Same 46 track IDs at both sites: 92 unique track/site rows, all present. No candidate, location or fitted correction sharing across sites. Reusing universal propagation calculations is not sharing candidate proposals.
- This uses independent per-track timing, not satellite-shared timing or the newly learned empirical prior. No quadratic retiming or reassignment, no new geographic search, no reference-location fit, no new RF collection or production changes.
- The original masks and previously selected geographic estimates have been reused. The case was selected retrospectively; tracks/observations are correlated. Do not treat these as fresh independent validation or confirmed-association classification.

`run_1250.py` reconstructs predictions from the original prepared inputs and asserts matching evidence and TLE snapshot digests. `results_1250.json` records all fits, coefficients, evaluation residuals, source hashes, counts and timing. `distribution_1250.png` shows empirical CDFs and paired before/after scatter. Six polynomial-core tests pass, including isolation from evaluation values.

Reproduce:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python reports/2026_09_26_residual_polynomial/run_1250.py
```
