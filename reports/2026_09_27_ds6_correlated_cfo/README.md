# Cross-subset slope uncertainty does not improve DS6 positioning

All four matched experiments completed. Adding learned slope uncertainty improves held-out predictive density on every scan but worsens geographic error against the zero-slope control on every scan. The slope arm is not adopted. Four tests pass.

| MS/s | Original stationary error (km) | Track-t zero-slope error (km) | Track-t learned-slope error (km) | Slope minus zero held log score | Slope winner at bound |
|---|---:|---:|---:|---:|---|
| 10 | 4.925 | 3.314 | 5.223 | +237.088 | No |
| 2.5 | 3.643 | 4.837 | 11.883 | +356.937 | Yes |
| 5 | 8.502 | 9.313 | 16.510 | +590.234 | Yes |
| 7.5 | 0.465 | 0.902 | 1.426 | +585.727 | No |

The likelihood is a multivariate Student-t4 per track with scale covariance `100^2 I + 10^12 11' + slope_scale^2 tt'`. Time is centered using training observations only. Low-rank SVD evaluates the normalized density stably with large offset variance. Training likelihood uses training observations; held predictive log density is the full joint log density minus training log density. Candidate identities are marginalized using the inherited shortlist and training visibility rule.

This differs from the preceding independent pointwise-t4 likelihood and profiled offset. A matched zero-slope arm therefore isolates the slope addition within the new likelihood; it does not attribute all differences from the original baseline to slope uncertainty. The multivariate-t construction integrates random offset and slope components with a shared track-level scale. It is not identical to independent pointwise-t noise plus independent Gaussian random effects.

The slope scale is fixed from the opposite randomized scan subset's previously exported training OLS residual slopes: median absolute slope divided by 0.6744897501960817, with zero prior mean. No target-subset observations or geographic reference set that scale. Eligibility and donor trace provenance remain inherited from the satellite-slope diagnostic. This is plug-in calibration; uncertainty in its estimate is not integrated. Tracks within a scan remain correlated, and repeated development data are not an untouched validation set.

Both arms use the same four pre-existing development scans, three starts, inherited local position and timing bounds, causal elements, training-only winner selection, and exact propagation audits. Geographic assessment runs only afterward. Two slope winners reach local search bounds, so they are constrained estimates, not established unconstrained optima. Inherited satellite shortlists have not been revalidated under this new likelihood. These limitations preclude a global performance claim; no favourable configuration is selected using geographic error.

Tests compare the low-rank density with a dense multivariate-t calculation, check large-offset stability and held-data isolation, bind frozen inputs and target-excluding calibration, and verify complete fits, training winner selection, exact propagation, and evaluation reference hashes.

This experiment shows a recurring problem: greater freedom to explain smooth residual trajectories can improve prediction while degrading geographic discrimination. It does not establish the physical origin of those trajectories or rule out a properly constrained physical correction. The verified independent baseline remains 6/43 below 1 km; the separately validated pooled estimate remains 754.938 m.
