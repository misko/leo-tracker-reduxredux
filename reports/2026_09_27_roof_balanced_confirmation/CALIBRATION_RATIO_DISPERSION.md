# Conditional held-out ratio residual-sum audit

All six frozen reception LOSO fits were evaluated without refitting, using 285 tracks with matched reception and 3,982 matched rows. Candidate weights were conditioned on the full detection pattern, but never on the ratio outcomes being checked. This matches the old model's joint factorization into detection followed by conditional ratios.

For each track, compute its sum of ratio residuals relative to the detection-conditioned candidate-averaged prediction. The model-implied variance is the sum of Gaussian observation variances plus the variance of the sum of candidate means under that same candidate distribution. The diagnostic is the sum of squared residual sums divided by the sum of these variances.

| Frozen arm | Residual-sum dispersion |
|---|---:|
| Directionless M0 | 6.7997 |
| Mean direction | 6.9200 |
| Candidate mixture | 5.7768 |

The mixture's ratio observations also have considerably more track-level residual variation than predicted. This can result from persistent mean bias, observation dependence, underestimated variance, or incorrect candidate identities. It does not uniquely identify a random-intercept model or specify a valid likelihood weight. Candidate-conditioning itself uses the existing detection model, already shown to be misspecified.

This is a post-hoc calibration-only descriptive diagnostic, not a significance test or geographic validation. Frequency priors use all six calibration sessions; only reception coefficients are LOSO. No true satellite IDs are available. Two analytic-fixture tests verify the shared-identity variance and that ratio outcomes cannot change the candidate weights/variance.

The detection random-intercept experiment deliberately leaves the ratio model fixed. This finding therefore limits how much that first experiment can be expected to address: a successful detection ablation would not validate the whole reception likelihood.

Artifacts: `calibration_ratio_dispersion.py`, `calibration_ratio_dispersion.json`, and `test_calibration_ratio_dispersion.py`.
