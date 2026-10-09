# Remaining ordinary-error opportunity

The simplest remaining candidate is **measurement-dependent frequency precision**, preceded by a small reference-free observability audit. This is a research recommendation, not an implemented model, numerical protocol or demonstrated improvement. It extends the untested third hypothesis in [iteration86](../2026_10_09_position_error_iter86/NEXT_MODELS.md); it should not be advertised as a newly discovered mechanism. No fits, reserve access or RF collection were performed for this memo.

The ordinary error remains material. The published [B7 ablation](../2026_10_09_position_error_iter85/RESULTS.md) gives fitted-c DS16 mean/median 0.979/0.835 km, DS17 0.819/0.696 km and DS18 2.692/1.122 km; the full148 mean is 1.317354 km. Even descriptively removing the single 53.400741 km failure leaves approximately 0.963 km over147 members. This is arithmetic explaining the scale of the remaining problem, not a permitted exclusion. Search-region recovery cannot by itself establish the 0.4 km objective.

## Evidence against repeating simple prior/noise changes

| Already examined change | Published evidence | Implication |
|---|---|---|
| Geometry-protected satellite-slope prior | [Iteration86](../2026_10_09_position_error_iter86/RESULTS.md): fitted-c mean 1.317354→1.327178 km, median 0.863677→0.883465 km; one raw failure | Do not repeat the protected0.25 variant or claim geometry-based shrinkage already works. |
| Uniform frequency width125→100 Hz | [Iteration106](../2026_10_09_position_error_iter106/DECISION.md): fitted-c mean 1.317354→1.290684 km, median 0.863677→0.804999 km, worst53.400741→54.835462 km; acceptance gates fail in both arms | A globally narrower mixture is insufficient; lower frequency RMS can accompany worse position. |
| Additional paired receiver/satellite offsets | [Iteration90](../2026_10_09_position_error_iter90/DECISION.md): median eligible contrast23.944 Hz raw,5.583 Hz after linear/channel projection,1.874 Hz after existing smooth-clock projection (fitted c) | Most apparent differential bias overlaps existing nuisance modes. This diagnostic did not test position improvement; do not call it a failed localization fit or enlarge the prior to manufacture an effect. |
| Identity persistence opportunity | [Iteration108](../2026_10_09_position_error_iter108/DECISION.md):43.63% of rows linked;92.70% of linked fitted-c rows already have conditional probability≥0.9 | Persistence is a separate bounded trial with limited obvious ambiguity support, not evidence of physical label correctness. |

## Proposed lean precision model

Replace the scalar Gaussian frequency width with a frozen vector `sigma_i² = sigma_floor² + v_i`, while retaining Gaussian normalization and the existing clutter mixture. Estimate `v_i` from orbit-blind frequency-repeatability evidence from the existing recordings, using one globally learned rule. Keep an exact scalar125 Hz control. This changes how reliable frequency measurements influence a fit; it does not add another clock or satellite correction that can absorb spatial motion.

A raw GLRT margin must not be mapped to variance by assumption. The [full148 residual audit](../2026_10_09_position_error_iter87/RESULTS.md) reports fitted-c median recording RMS61.719 Hz, median absolute residual31.999 Hz and median adjacent temporal correlation0.261 across8,072 eligible temporal groups. These are conditional fitted residuals with dependent observations, not calibrated measurement noise. Repeated adjacent residuals can contain real clock/orbit/model error. A useful precision estimate therefore needs held-block prediction or repeatability after a local orbit-blind trend, with receiver/channel/track boundaries preserved. This memo chooses no mapping, floor, clipping range or per-scan hyperparameter.

Learn any rule on whole recording groups and check it on held-out development groups; keep both receivers and shared/duplicate inputs together. Do not split windows at random or learn weights from reference position errors. Existing DS16/17/18 folds are consumed-data stability checks, not unseen validation. If repeatability does not predict out-of-block dispersion, stop rather than invent a weight function.

## Observability guard before any position prototype

At ordinary reference-free B7 hypotheses, whiten the spatial frequency Jacobian and existing nuisance Jacobian by the same proposed measurement precision. Project the spatial Jacobian off the nuisance span with QR/SVD, and report its two singular values and directions. Use candidate geometry, never known receiver coordinates. Preserve timing/visibility information and report any conditional/Gaussian approximation; this frequency-only diagnostic is not the full mixture posterior or a calibrated position covariance.

This distinguishes a weak spatial direction confounded with clocks/RF stretch from inconsistent measurements that still constrain both spatial directions. It is descriptive initially: no scan exclusion, reference-directed retention, prior selection or extra-fit allocation follows from it. A tiny projected singular value is a warning that adding nuisance flexibility may worsen identifiability; it is not evidence that a precision model will recover the missing information.

Only after repeatability calibration and derivative/likelihood checks should a single fixed precision model receive a controlled full-membership comparison: same observations, candidate banks, ordinary starts, other priors and budgets; matched fitted-c/c=0 arms and same-start B7 control; all failures/fallbacks preserved. Report per-dataset mean/median/p95/worst, paired regressions, convergence and runtime, with frequency effects separate. RF calibration and source changes belong in a separate ablation. No available report quantifies this model's position gain or warrants an expectation of0.4 km, and production B7 should remain unchanged until such evidence exists.
