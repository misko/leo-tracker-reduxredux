# RX-difference scale also predicts individual and shared residuals

The training-only paired-RX scale feature improves DS10 held likelihood for **both individual receivers and their shared residual mean**, using calibration fitted only on DS7–DS9. Gains are smaller than for RX differences. This supports testing relative observation weights, but does not establish absolute receiver uncertainty or improved location accuracy.

| Predicted residual channel | DS10 held pairs | Scans improved | Equal-scan mean log-score gain | Donor constant t4 scale | Learned feature exponent |
|---|---:|---:|---:|---:|---:|
| RX0 | 7,195 | 20/24 | +0.020033 nats | 149.301 Hz | 0.328199 |
| RX1 | 7,195 | 17/24 | +0.017777 nats | 144.725 Hz | 0.394164 |
| Mean of RX0 and RX1 | 7,195 | 17/24 | +0.014486 nats | 133.971 Hz | 0.301552 |

![Individual and shared residual prediction](transfer.png)

The preceding [RX-difference test](../2026_09_30_rx_difference_calibration/README.md) improved 24/24 scans by +0.063693 nats. All four channels use the same target pair membership. The individual/common gains demonstrate predictive information beyond disagreement alone, but the targets differ and these gains are not additive or geographic accuracy percentages.

## Exact matched experiment

The [protocol](PROTOCOL.md) freezes all 1308 prior track pairs: 953 donor pairs across 72 DS7–DS9 scans, and 355 target pairs across 24 DS10 scans. There are 17,888 donor and 7,195 target held paired observations. No new pair is selected, and no channel is dropped after seeing outcomes.

For every pair, reconstruct the same mutual-nearest RX observations within one microsecond and require both-training or both-held masks. The prior difference feature, difference residuals and support counts must replay exactly. Form three raw channels: RX0 residual, RX1 residual and their arithmetic mean. Subtract each channel's median over both-training observations, then score both-held values. Slopes are not removed; all candidate/position residual evolution remains in the prediction target.

For each channel, fit a constant t4 scale and `log(scale)=a+b log(feature)` on donors, using the frozen bounds, optimizer and gates. The feature remains the original training-only RX-difference MAD. Equal donor-dataset and donor-scan weights prevent high-count scans from dominating calibration; the target summary averages scan means equally. DS10 values never fit parameters. Individual scales are calibrated separately, not inferred by dividing difference scale by sqrt(2).

All six fits qualify. Maximum parameter-gradient magnitude is 8.71e−8 and maximum finite-difference discrepancy is 1.07e−9; all parameters are interior and optimizers report success. Full coefficients and per-scan scores are in [summary.json](summary.json).

## What this supports—and what remains unresolved

The feature contains some transferable information about candidate-conditioned model residual scale, including the shared component. That makes a small, controlled geographic weighting test worthwhile. A suitable next experiment would freeze donor-learned **relative** scale ratios, preserve unsupported-track fallback, compare against a receiver-constant scale control, and evaluate all fixed panels without selecting by reference distance.

The scalar t4 residual scales here are not automatically the correct scales for the multivariate contrast likelihood used in geographic fitting. They include timing, association, orbit, transmitter and fitted-location mismatch, plus measurement noise. The residuals also depend on baseline geography fitted using both receivers' training data. Their predictive improvement does not identify a causal noise source and does not justify changing candidate probabilities or adding free slopes without a separate experiment.

There is no measured absolute CFO truth or calibrated position uncertainty. Track alternatives may share observations, and pairs are dependent. These datasets have prior research exposure. No geographic fit or uncertainty weight has been applied in this experiment.

## Verification and evidence

Two component-owned tests pass: a shared additive trend changes the common channel while preserving the difference feature, and held-value mutations cannot change any training center or the feature. The inherited calibration code's analytic gradient was tested in the previous experiment; all six actual fits also undergo finite-difference audits. Source hashes verify and every paired difference/support value exactly replays the preceding experiment. [results.json](results.json) preserves channel residuals, centers, features and provenance; `evidence.sha256` binds all artifacts.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_rx_scale_common_transfer -p 'test_*.py'
cd reports/2026_09_30_rx_scale_common_transfer
sha256sum -c evidence.sha256
```

No new RF collection, export, propagation, production change or remote publication occurred.
