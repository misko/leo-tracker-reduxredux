# Scale prediction depends on scoring target; variable weights still lack an advantage

At the unchanged DS10 location and timing, variable scales improve the sum of individual held predictive log scores but worsen joint held-track likelihood. The constant-scale control performs slightly better on individual prediction and clearly better on joint prediction. Thus the earlier scalar calibration success does not justify the track-variable geographic weights.

| Frozen model versus baseline | Joint held-track log-score gain | Scans with joint gain | Sum of individual held log-score gains | Scans with individual-score gain |
|---|---:|---:|---:|---:|
| Matched constant scale | +2.705519 | 14/24 | +6.818231 | 16/24 |
| Track-variable scale | −1.554663 | 10/24 | +6.736574 | 11/24 |
| Variable minus constant | −4.260182 | — | −0.081657 | — |

The individual-score difference between the two scale arms is tiny relative to their totals; it does not demonstrate an advantage for the variable feature. No refit, new score optimization or selection of a favorable scoring target occurred.

## What the two scores measure

The joint score is `log p(training, all held) − log p(training)` for each track. The individual score sums `log p(training, one held point) − log p(training)` over held points. Every individual prediction conditions only on training data; it does not update on earlier held outcomes.

These are different predictive targets. The sum of individual log densities is not a joint density for dependent held observations. The shared candidate mixture and multivariate Student-t contrast model couple predictions within a track, so the rankings can differ even when geography, timings, measurements and scale values are identical. A sign reversal alone does not identify the physical source or exact covariance structure of the errors.

Both comparisons use all 1443 tracks, including 707 supported variable-scale tracks and unchanged fallback for the rest. Candidate visibility is determined from the original training mask in every scoring arm. The scales and q020 likelihood are exactly those frozen in the [geographic weighting pilot](../2026_09_30_ds10_scale_weighting/README.md).

## Consequence

The original scalar calibration and geographic likelihood target different residual populations, centering conventions and dependence structures. This diagnostic isolates one part of that mismatch by comparing two predictive scores within the same geographic model and complete observation population. It does not attribute the entire discrepancy to temporal correlation.

Keep the geographic model unchanged. Do not switch the validation score to individual predictions merely because the variable arm becomes positive: the matched constant control still performs at least as well. If further scale calibration is attempted, fit and validate the actual conditional contrast likelihood on donor recordings first, preserving a constant-scale control and whole-dataset transfer, before any additional geographic fit. The existing results do not justify adding a new temporal covariance parameter either.

## Verification and evidence

The [protocol](PROTOCOL.md) preceded execution. All track/arm direct joint and training scores agree with the original full-model implementation to within **1.70e−11**. Two component-owned tests pass: a single held point has identical joint and individual scores, and batch individual predictions agree with separate single-point evaluations. Held-value mutation leaves training score unchanged in the second test.

The complete diagnostic takes **9.42 seconds**, within the 180-second cap. Input/source hashes verify. [results.json](results.json) preserves individual scores, track totals and arm comparisons; [summary.json](summary.json) includes every scan. The SHA-256 inventory binds all artifacts.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_scale_score_diagnostic -p 'test_*.py'
cd reports/2026_09_30_scale_score_diagnostic
sha256sum -c evidence.sha256
```

This is a fixed-location diagnosis on exposed DS10 data. It provides no new geographic accuracy result. No RF collection, export, propagation, fitting, production change or remote publication occurred.
