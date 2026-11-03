# Direct contrast calibration still favors constant scales over the RX feature

Calibrating the actual geographic conditional likelihood does not rescue the track-variable RX-difference weights. On fixed DS10 N24 data, the learned variable model improves held score over fixed100 but remains worse than a receiver-constant control. **The declared geographic-refit trigger fails; no location fit is launched.**

| DS7–DS9 calibrated model | DS10 joint held log-score gain vs fixed100 | Equal-scan gain per supported held observation | Scans improved |
|---|---:|---:|---:|
| Receiver-constant scale | +6.117427 | +0.00035914 nats | 12/24 |
| Receiver-specific variable scale | +2.481090 | +0.00022656 nats | 14/24 |
| Variable minus constant | −3.636337 | −0.00013258 nats | — |

These are fixed-position/timing model comparisons, not improvements in geographic accuracy. The variable model has more positive scan signs but a lower total and equal-scan mean than the constant control. No choice is made using reference distance, and the existing DS10 location estimate is unchanged.

## Calibrated model and population

The [protocol](PROTOCOL.md) replaces the earlier scalar residual target with the actual normalized q020 contrast mixture: joint full-data log density minus training log density. The signal still marginalizes retained visible candidates; the background retains its physical 2000 Hz/s slope prior. Both arms fit only observation-noise scales, with location, timings, candidates, feature and support frozen.

The same paired-RX training feature supplies 1891 supported donor tracks across nine DS7–DS9 eight-scan panels, and 707 target tracks in DS10 N24. Target supported tracks contain 16,624 held observations. Unsupported DS10 tracks retain scale 100 Hz and contribute exactly zero to model-score deltas, so the tabulated total gains also apply to the complete 1443-track panel. Per-observation averages use supported held counts; they should not be mistaken for averages over every original observation.

Donor calibration weights datasets equally, then scans equally within dataset, and normalizes each scan by its supported held count. Target evaluation uses equal scan averages with the same normalization. Each track's feature is the median log feature across its accepted pairs. Target held values never fit scales.

Constant fitted scales are **106.535 Hz for RX0** and **85.028 Hz for RX1**. For the variable model,

```text
log(sigma / 100) = a_rx + b_rx * log(feature / 100)
RX0: a = −0.0913421, b = −0.3346089
RX1: a = −0.0495789, b = +0.2662313
```

The RX0 exponent is negative, whereas the earlier scalar residual calibration gave a positive exponent. This highlights dependence on the predictive target; it does not identify a causal receiver noise law. Neither fit touches its declared parameter bounds.

## Decision

The track-variable feature fails the matched-control test under both scalar-derived geographic weights and directly calibrated conditional-contrast weights. Stop this specific weighting recipe before another geographic fit. The feature can remain a descriptive RX-disagreement diagnostic, but it is not established as a useful geographic precision weight.

The small positive constant-scale score gain is not evidence of a sub-km method. It does not justify searching receiver widths using reference error. Remaining work should prioritize independently constrained timing, signal identity, orbit or installation geometry rather than repeating scale variants on the same exposed target.

## Numerical implementation and verification

[core.py](core.py) evaluates candidate residual sums of squares and background parallel/perpendicular moments, including density normalization and analytic derivatives with respect to log scale. It retains the original physical background slope prior. This permits donor scale calibration without repeatedly loading or propagating candidate states.

Two component-owned tests pass: sufficient-statistic signal/background densities agree with direct implementations across scales, and both ordinary and constant-time conditional derivatives agree with finite differences. Frozen baseline training and held scores replay per track to **2.85e−13**. Both calibrations pass optimizer success, interior bounds, gradient and derivative-audit gates; maximum fitted gradient is 6.37e−8 and maximum audit discrepancy 7.28e−11.

An independent [full-model replay](audit.json) evaluates the learned DS10 scales through the previous normalized scale wrapper and matches score gains to **6.19e−11**. Thus the negative matched-control result is not explained by a sufficient-statistic implementation discrepancy. Statistics preparation takes 25.60 seconds and calibration/evaluation 4.01 seconds, each within its 180-second cap. Source and input hashes verify.

[statistics.json](statistics.json) preserves all donor/target likelihood moments and coverage. [results.json](results.json) and [summary.json](summary.json) preserve coefficients, qualifications and scan scores. The SHA-256 inventory binds all report artifacts.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_contrast_scale_calibration -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_30_contrast_scale_calibration/audit.py
cd reports/2026_09_30_contrast_scale_calibration
sha256sum -c evidence.sha256
```

This is exploratory transfer on previously exposed observations and baseline-conditioned features, not blind navigation validation. No new RF, archive mutation, propagation, geographic refit, production change or remote publication occurred.
