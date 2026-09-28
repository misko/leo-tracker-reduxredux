# Bounded calibration-only mixture test

This implements the separate design in `CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md`. The previous location replay is complete and immutable; no geographic outcomes enter this calibration fit, feature selection, optimizer, or advancement decision.

Use all 344 topology-retained tracks and 6,378 reception rows from the six original calibration recordings. Each has three frozen candidate IDs and finite normalized log probabilities. Do not drop ambiguous or confident tracks. A descriptive check found 59 tracks with maximum prior weight below 0.99, 27 below 0.9, and 13 below 0.75; these are descriptions, not selection rules.

Fit feature levels and scalers on each training fold only. Detection uses all training rows; ratio retains the legacy matched-row feature specification. Ratio tensors may be transformed for all rows but unmatched ratio contributions are zero. Derive directional scaling from fixed-prior robust mean directions on those training rows and share it between the mean and mixture arms. Preserve the existing joint channel:edge nuisance encoding, sample-rate encoding, receiver effect, and detection log-anchor-margin feature. No new nuisance terms are selected.

Run three arms: candidate-free directionless M0, mean-direction M1, and shared-candidate-mixture M1. All use the same full-row-normalized joint detection/conditional-ratio objective, ridge lambda=1 with lambda/2 squared penalty, and jointly learned log_sigma. Intercepts and log_sigma are unpenalized. This changes the objective relative to legacy separate calibration, so the primary isolation contrast is mixture versus the same-objective mean arm.

Exactly three deterministic starts are used for every arm/fold: all zero; coefficients +0.2 and log_sigma +0.25; coefficients -0.2 and log_sigma -0.25. Pre-fit numerical requirements: gradient maximum <=1e-6, multistart objective range <=1e-7, prediction maximum difference <=1e-4, and minimum local Hessian eigenvalue >1e-7. Report failures and all diagnostics; do not relax tolerances after seeing outcomes. An optimizer success flag alone does not establish convergence or identifiability.

First run only the descriptive full-six fit to measure runtime and check numerical behavior. Six leave-one-session-out fits follow only after review; no multi-hour campaign or RF collection is authorized by this protocol. Report these folds as conditional on the frequency model already trained on all six sessions, not fully nested validation.

The advancement decision is implemented in `mixture_advancement.py`: every fold must converge; pooled equally weighted-track NLL must beat both controls; at least four of six scans must improve versus mean; and the pooled gain must stay positive after removing the single largest favorable scan contribution. Differences must exceed 1e-8 NLL per track to count, solely to exclude floating-point noise. Each fold supplies summed track-normalized heldout NLL and track count; do not average scan means equally.

Score decomposition must respect shared identity: report detection-marginal NLL and the conditional-ratio increment (joint minus detection), which sum to joint NLL. Independently marginalizing detection and ratio then summing is not this joint score.

Global direction reversal with unrestricted slope signs is a parameter symmetry, not evidence that the receiver's physical orientation is correct. It is an implementation control. Direction-trajectory permutation is a different calibration control and cannot change source membership or outcomes.

Passing calibration gates is necessary to advance this model, not proof of improved position resolution. Any subsequent geographic claim requires an explicitly frozen estimator and disjoint confirmation data. Failure stops this iteration instead of prompting tuning against known location errors.
