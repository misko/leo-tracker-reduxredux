# Shared ratio uncertainty passes conditional reception validation

The analytic shared ratio-offset experiment passed its predeclared calibration gate. No geographic result for this dual-effect model is implied by these scores.

One zero-mean Gaussian offset v is shared across matched log-ratio rows in a track, with population standard deviation tau learned on training sessions only. Its exact covariance is the frozen independent variance times I plus tau squared times 11'. The existing shared detection effect, all response coefficients, candidates/weights, ratio independent variance, and normalization stay fixed. Both effects share the same candidate identity and are independent conditional on that identity.

## Conditional-LOSO performance

Lower joint reception NLL per track is better. All 344 tracks appear exactly once in held-out scoring.

| Arm | Shared detection only | Shared detection and ratio |
|---|---:|---:|
| Directionless M0 | 0.773205 | 0.679958 |
| Mean direction | 0.652007 | 0.556422 |
| Candidate mixture | 0.542909 | 0.476114 |

Mixture results by held recording:

| Held session suffix | Tracks | Learned ratio tau | Detection-only NLL/track | Dual-effect NLL/track |
|---|---:|---:|---:|---:|
| 39ac2b14d1bb5f0f | 62 | 0.264449 | 0.386102 | 0.365897 |
| 4c56320fb5ca6994 | 60 | 0.260469 | 0.585757 | 0.506993 |
| 9d7b6a0db558703a | 57 | 0.238466 | 0.638644 | 0.509373 |
| aa9770c66396e928 | 55 | 0.250132 | 0.632985 | 0.566974 |
| c559f436d578c9bd | 52 | 0.256045 | 0.482336 | 0.443770 |
| da2858f6cd2521b7 | 58 | 0.237232 | 0.541012 | 0.472140 |

All six folds improve. Pooled gain is 0.066795 NLL/track; removing the largest-gain fold leaves 0.054387. Detection NLL is exactly unchanged at 0.318508; the mixture conditional ratio increment improves from 0.224402 to 0.157606.

The full mixture tau is 0.25181019547182615 natural-log-ratio units. Detection sigma remains 2.561859822112572 logit units. No scale reaches a bound. At this tau and the frozen independent variance 0.1055653759495091, the model implies conditional within-track ratio correlation 0.375256. For a known candidate and a constant-level measurement, 20 correlated rows have the mean-estimation information of about 2.46 independent rows with the same marginal variance. This is a consequence of the assumed covariance, not an empirically verified count of independent satellite observations.

## Interpretation limits

This is a nested covariance augmentation, not a clean variance-component decomposition. The frozen ratio variance was fitted under an iid model and already absorbs persistent offsets, bias, candidate error, and tails. Adding tau raises diagonal variance as well as covariance. Its value must not be called a measured physical receiver gain error.

A separate full-calibration descriptive check (not held-out evidence) found identity-adjusted centered ratio energy 288.190 versus an iid expectation of 390.275 on 266 tracks with at least two matches. Thus retaining the old independent variance can overstate within-track noise; future joint within/between variance estimation would require its own training-only comparison. This does not invalidate the present exact tau-zero nested ablation, but limits its interpretation.

Only reception fitting is leave-one-session-out; the frozen frequency priors use all six sessions. Candidate IDs are model associations, not decoded identities. Calibration success permits the declared geographic development test; it does not prove positioning accuracy or justify consuming the unused confirmation cohort yet.

## Checks

Analytic likelihood matches dense multivariate-Gaussian reference calculations. Tau-zero full/fold scores reproduce the accepted detection-only model to at most 2.28e-13. Main independently verified all seven output hashes and their code receipts, and verified detection scores are exactly unchanged. All 212 experiment-directory tests pass. No new RF, geographic tuning, or production change occurred.

Artifacts: `ratio_random_intercept.json`, `ratio-random-intercept-full.json`, six `ratio-random-intercept-fold-*.json` files, `ratio_random_intercept.py`, `run_ratio_random_intercept.py`, and `RATIO_RANDOM_INTERCEPT_PROTOCOL.md`.
