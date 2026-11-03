# Phase residual versus Doppler residual transfer

Use the existing six acquisition-family donor pairs:2 16/17,3 18/20,4 7/11,
5 4/19,6 0/10,7 5/14. All data, inferred identities and fixed geometry remain
bound to the availability-correct earlier DS10 calibration. No DS11 data enter.

The predictor is training-only phase quadratic curvature minus the frozen
family-specific intercept and orbital-curvature relation. The response is a
robust linear slope of Doppler residuals about the original causal prediction.
Fit slope and intercept with soft-L1 scale100 canonical Hz, separately on
training and held visits, retaining every qualification failure. Median-pool
track fragments and RX/RF copies by inferred physical NORAD; do not treat copies
as independent sources. Fit a two-parameter relation from the calibration
recording's training predictor and training Doppler slopes, soft-L1 scale10Hz/s.
The predictor is scaled by0.01us/s² for numerical conditioning only.

Evaluate against held Doppler slopes from the separate validation recording,
using that recording's training-only phase predictor. Compare zero correction,
the calibration median-Doppler-slope constant, and all nonzero cyclic shifts of
source predictors. Require>=5% lower median absolute error than all three
controls and a strict majority of per-source wins over zero to pass a family.
At least five valid sources per recording are required. Report every family.
This conditional residual audit does not identify orbit/clock causes or authorize
subtracting a position-dependent error; any position model must retain both
observations' position dependence and source/identity uncertainty.

Existing metadata/banks only, no collection or IQ reprocessing. Children<=90s,
at most three single-thread workers. Preserve all source hashes and failures.
