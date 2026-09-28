# Calibration-only association-consistency refit

Motivation comes from calibration data, not evaluation-location tuning:20 of344 retained calibration tracks switch MAP satellite between the Gaussian associations used by reception training and the robust frequency model. The reconstructed6378 reception observations show concentrated direction-feature changes. MAP-changing tracks account for358 observations with mean absolute east-component change0.414987, versus0.002377 among6020 other observations (row-weighted descriptive statistics).

Create a separate reception calibration artifact; preserve the current frozen model and all completed experiments. Join reconstructed robust direction features onto the original calibration rows by exact(session_id,track_id,observation_id). Reject missing, duplicate or unexpected retained rows. Apply the unchanged source-topology exclusion. Retain all other observations, receiver outcomes, nuisance fields, weighting and regularization.

First isolate feature consistency: substitute robust weighted-mean east/up for the old Gaussian weighted means and refit the identical M0/M1 detection and conditional-ratio models with ridge1. Recompute each model's own conditional-ratio variance. Do not change timing, frequency parameters, track weights, search policy, reference coordinates or reception matching. M0 should remain invariant because its feature design contains no direction terms; verify this numerically.

Report coefficient changes and calibration reception losses under both old and new feature conventions. If evaluating leave-one-calibration-scan-out reception fits, label them conditional on the frequency parameters/associations already fitted to the full calibration cohort; do not call them fully nested out-of-sample frequency validation.

This first refit still uses marginalized direction features for reception training while geographic scoring marginalizes candidate likelihoods. Retain this limitation explicitly. The newly saved candidate-specific directions permit a later matched mixture-calibration experiment, but do not silently combine that methodological change with the first consistency comparison.

No evaluation cohort may choose the regularization, model form, sign, sample-rate encoding or replacement tracks. Any geographic replay of the already-unblinded recordings is development evidence. Freeze the eventual estimator and evaluate disjoint recordings before claiming a general resolution improvement.
