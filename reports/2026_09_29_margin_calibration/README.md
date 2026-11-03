# Detector margin as a CFO reliability predictor

The prototype does **not** support promoting detector margin to a Doppler precision weight. Cross-dataset transfer is mixed, and every fitted exponent predicts larger smooth-history residuals at higher margin. This evaluates one confidence-calibration step, not a new frame estimator or a geographic accuracy improvement.

## Frozen experiment

Use the 24 previously exported balanced-N8 scans (eight each from DS7, DS8 and DS9), with verified observation and quality-sidecar hashes. Keep tracks with at least two training observations and one held observation, matching baseline eligibility. For each held observation, linearly interpolate canonical dealiased CFO from the nearest strictly earlier and later training observations. Require an endpoint gap no greater than two seconds; no extrapolation.

Normalize the held residual by `sqrt(1 + (1-w)^2 + w^2)`, an equal-independent-noise approximation for the contribution from the held sample and two endpoints. This is a **smooth-history residual proxy**, not measured absolute CFO error. Fit a zero-centered Student-t distribution with four degrees of freedom: constant scale versus `log(scale) = a + b log(margin)`. Calibration excludes the entire target dataset and weights donor scans equally. Each donor's original held samples become calibration residuals; target residuals never enter parameter fitting. No orbit, candidate state, geographic fit, or reference coordinate is used.

All choices above were fixed before running this experiment. These datasets have been used in prior research; this is exploratory transfer validation, not a research-blind test.

## Results

Positive score change favors margin calibration. Scores are mean log-density differences in nats per eligible observation, averaged equally across eight target scans.

| Target | Eligible held observations | Constant scale (Hz) | Margin exponent b | Scans improved | Mean score change |
|---|---:|---:|---:|---:|---:|
| DS7 | 5,295 | 45.68 | +0.317 | 5/8 | +0.01130 |
| DS8 | 4,661 | 45.82 | +0.695 | 4/8 | −0.02194 |
| DS9 | 5,320 | 50.22 | +0.335 | 7/8 | +0.00968 |

The equal-dataset mean change is approximately −0.00032 nats. There is no consistent transferable benefit. Positive b means higher margin predicts larger residual scale, contrary to simply treating higher margin as higher CFO precision. This association is not evidence that stronger detections cause worse frequency estimates.

| Dataset | Excluded: endpoint gap >2 s | Excluded: no strict bracket | Ineligible tracks |
|---|---:|---:|---:|
| DS7 | 3,214 | 620 | 0 |
| DS8 | 2,702 | 577 | 1 |
| DS9 | 2,978 | 712 | 0 |

Of 26,079 held observations in eligible tracks, 15,276 support this interpolation test. It does not establish reliability for sparse or unbracketed observations. Residuals share training endpoints and may reuse alternative source observations, so observations are not independent and no iid significance claim is made.

## Interpretation and next experiment

Margin measures detector separation from a control, which is not necessarily carrier-frequency precision. Physical curvature, alias choices, shared endpoint error, source alternatives, and conditioning on successfully selected tracks all affect this residual. The equal-noise normalization is deliberately simple and does not isolate the held sample's variance.

Keep the existing geographic model unchanged. For the sequence-aware Doppler/frame direction, the next useful test is a bounded paired waveform estimator: use only demonstrated repeatable pilot/header regions, estimate phase slope from training regions, and score disjoint held complex samples against the existing estimator. Evaluate phase ambiguity, frame alignment and frequency uncertainty explicitly before adding its outputs to geolocation. This calibration experiment does not replace that waveform comparison or establish a subkm result.

## Reproduction and evidence

From repository root:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_margin_calibration -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_margin_calibration/run.py
```

Three tests passed: training-only interpolation and held-value independence; bracket/gap exclusions; analytic likelihood gradient against finite differences. All six optimizations succeeded with gradients below 1e-5 and interior fitted parameters. Source hashes and per-scan scores are in `results.json`; all eligible residuals and predictions are in `residuals.json`. No new RF collection, archive export, or location-model modification. Files are local; this report has not been pushed to remote main.
