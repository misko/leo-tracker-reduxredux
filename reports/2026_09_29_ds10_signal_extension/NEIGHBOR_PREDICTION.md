# Can recorded neighbors explain symbols 4 and 6?

Following `EARLY_IQ.md`, this test predicts the real-component changes in OFDM
symbols 4 and 6 from recorded neighbors. It uses existing paired DS10 caches,
the same discovery/evaluation frame split, and no new RF collection.

Three preselected linear models use (a) adjacent carriers in the same symbol,
(b) the preceding and following symbols on the same carrier, or (c) both.
Every complex neighbor supplies real and imaginary features. Each target and
receiver has a separate ridge regression with fixed alpha=1 after feature
standardization on discovery frames. There is no parameter or lag search.
Only targets whose immediately adjacent native FFT bins are both present enter
any model, preserving the same carrier population for all comparisons.

Evaluation uses later frames; target values never enter the regression fit.
The baseline predicts the discovery mean separately for each target. All nonzero
cyclic shifts of the discovery target relative to its features provide additional
descriptive controls. The small discovery samples (22/9/10 frames) constrain
what this experiment can exclude. Evaluation frames have been used in earlier
analyses and are not an untouched confirmation dataset.

## Result

Every model has negative held-out MSE reduction relative to the constant baseline
for both receivers, both symbols and all three visits. This means prediction
error increased. The combined-neighbor model gives:

| Visit | Symbol | RX0 error increase | RX1 error increase | Residual cross-RX correlation |
|---|---:|---:|---:|---:|
| v1085 | 4 | 11.1% | 10.7% | 0.516 |
| v1085 | 6 | 5.2% | 5.0% | 0.509 |
| v1150 | 4 | 14.8% | 18.9% | 0.401 |
| v1150 | 6 | 24.1% | 13.5% | 0.361 |
| v1162 | 4 | 20.7% | 16.8% | 0.374 |
| v1162 | 6 | 19.6% | 26.6% | 0.362 |

The residual statistic centers every carrier across evaluation frames before
correlation. It measures shared changes, not decoded bits. Its persistence
alone does not prove an independent message source: correlated predictor errors
can contribute. The negative held-out MSE results are the decisive evidence
against using these fitted models as predictive explanations on this sample.

The shared structure is not successfully explained by these regularized linear
models of the immediately recorded neighbors. This does **not** exclude nonlinear
leakage, leakage from unrecorded carriers, time-varying coefficients, common
interference, or other channel effects. Even a successful prediction would not
by itself distinguish physical leakage from coded redundancy.

No additional message bits or fields were decoded. A defensible next analysis
would examine the amplitude distribution of the reproducible components with
held-out receiver/frame likelihood checks, rather than assign binary levels
from the present correlations alone.

## Reproduction

`neighbor_prediction.py` writes ignored
`local/within-visit/neighbor-prediction.json`, containing frame selections,
source-cache and script hashes, exact target bins, every model's before/after
statistics, and all shifted-discovery prediction controls. Two synthetic tests
check generalization of a true linear relationship and the constant-feature
case. Tests and Ruff pass. Existing manifests and sealed analysis files remain
unchanged.
