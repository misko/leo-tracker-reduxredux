# Offset uncertainty is material, but a constant offset cannot explain all dependence

At the sealed training-only winners on12development scans,526assigned tracks
have a median conditional frequency-offset standard deviation of40.89Hz and
p90of100.79Hz under the existing raw noise covariance assumption. For192/526,
that standard deviation exceeds the corresponding43–50Hz calibrated Cauchy
residual scale. These are different distribution parameters, not comparable
variances: Cauchy variance does not exist.

This exposes a potentially material approximation in plugging a GLS offset
estimate into every checking prediction. It is not proof that the raw covariance
assumption measures physical offset uncertainty or that adding a nuisance will
improve geographic accuracy.

## Conditional model

For raw training residuals r, covariance scale C, n observations, Student degrees
of freedom nu=4 and a flat prior on a track's constant frequency offset b:

    a = 1' C^-1 1
    b_hat = (1' C^-1 r) / a
    q = (r - b_hat 1)' C^-1 (r - b_hat 1)
    b | training, state, identity ~ Student_t(df=nu+n-1, location=b_hat,
                                            scale²=(nu+q)/[(nu+n-1)a])

The variance is (nu+q)/[(nu+n-3)a] when the degrees of freedom exceed2.
The audit reproduces q from the existing contrast likelihood for every track.
A density-ratio test verifies this conditional distribution against the raw
multivariate Student likelihood. A second test demonstrates the identifiability
limit: adding arbitrary common-mode covariance c11' leaves all contrasts
unchanged while changing offset uncertainty. The contrast fit alone therefore
cannot identify the uncertainty being audited; this is an explicit raw-model
extension, conditional on fitted geometry and satellite identity.

The already calibrated candidate scale describes total residuals around b_hat.
It does not isolate measurement noise. Convolving that same calibrated density
with this offset distribution would risk counting offset uncertainty twice.
Any integrated-offset model must recalibrate its intrinsic candidate noise on
donor data, and update both b_hat and q as geometry changes.

## Temporal structure

The7933checking groups with exactly one active prediction produce7407successive
within-track pairs.4821pairs share a nearest-peak residual sign (65.09%), versus
4026.81expected (54.37%) under shuffling conditional on each track's sign count.
Allthree datasets exhibit this excess. Median pair separation is1.46seconds,
p90is2.67seconds; only106pairs are at most0.5seconds apart. No maximum-gap cut
is imposed in this diagnostic.

Because the shuffle retains each track's total sign count, a constant track
bias alone cannot explain the ordering effect. Smooth model mismatch, incorrect
associations, correlated observation error or persistent peak selection can
all contribute. Nearest-peak residuals are selected from admitted candidates,
not verified emitter errors. No iid significance test or physical-clock claim
is made. The median absolute track-level median residual is18.20Hz.

![Offset uncertainty and residual sign persistence](conditional-offset-audit-v1.png)

## Next discriminating experiment

At fixed training-only states, compare a shared-offset integral over each
track's checking groups with a control that integrates offsets independently
per group. The control has the same one-group marginal distributions, so their
difference isolates the assumed shared dependence. Recalibrate intrinsic noise
and signal probability on donor datasets, exclude the target dataset, and check
numerical quadrature convergence before scoring. Do not refit geography until
this predictive test supports the added dependence model. Treat remaining
temporal structure separately; do not assume a constant offset solves it.

The22.54second audit made no localization fits, used noGPS and collected noRF.
The64scan baseline is unchanged. This adds no accepted geographic error,
end-to-end runtime or position-uncertainty calibration result. Sources, parent
inputs and outputs are sealed in `conditional-offset-audit-v1.json` and its
SHA256 sidecar; two mathematical/model tests pass.
