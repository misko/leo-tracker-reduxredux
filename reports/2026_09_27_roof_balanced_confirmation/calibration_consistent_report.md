# Calibration-only consistent-direction refit

The original topology-filtered 6,378 reception rows join one-to-one with the robust direction extraction across all 344 retained tracks. Only `east` and `up` were replaced. Outcomes, receiver/channel-edge/sample-rate nuisance fields, anchor margins, ridge (`1.0`), and unit-total-per-track weighting are unchanged. No evaluation outcome, location, or search enters this fit.

The direction-free M0 detection model, M0 ratio model, and M0 ratio variance are bit-for-bit invariant. This is a direct negative-control check on the exact join and refit implementation.

## Calibration fit changes

The consistent M1 detection calibration log loss is 0.52897 versus 0.50966 under the old directions. Its standardized coefficient-vector L2 change is 0.20527; the standardized signed-east coefficient changes from 1.35217 to 1.23944.

The consistent M1 conditional-ratio MSE/variance is 0.20505 versus 0.19443 under the old directions. Its coefficient-vector L2 change is 0.07543; the standardized east coefficient changes from 0.25393 to 0.24448.

In conditional leave-one-calibration-scan-out reception fits, consistent directions improve detection loss on two scans and worsen it on four; they improve ratio MSE on one scan and worsen it on five. These are not fully nested frequency validation: the robust frequency parameters, identities, and weights were estimated from all six calibration scans.

The consistency refit therefore removes a measured modular mismatch, but it does not improve calibration reception fit and is not evidence of geographic improvement. It retains the further limitation that reception training uses marginalized direction features while geographic scoring marginalizes candidate likelihoods.

The full serialized M0/M1 models, each model's ratio variance, losses, coefficient changes, exact hashes, join accounting, and per-session conditional LOSO results are in `calibration_consistent_calibration.json`.
