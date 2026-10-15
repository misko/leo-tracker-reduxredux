# Acquisition-conditioned density: component qualification, not localization evidence

Source `649f83fe7` adds a conditional native density with one externally supplied clutter-log-odds shift per observation. The planned objective will generate those shifts from one shared coefficient and a measured detector covariate. That objective and its actual-data qualification are separate work; this report does not claim that a model fit or position evaluation has occurred.

The coefficient-zero case preserves the existing conditional native likelihood, including its visibility normalization, satellite propensities, branch evidence and clutter floor. Positive shifts increase clutter odds. The new routine returns derivatives with respect to every predicted frequency, satellite logit and per-window odds shift. A wrapper can obtain the shared coefficient derivative by multiplying the last derivative by its fixed covariate and summing.

Eight component tests passed in 0.82 seconds; Ruff passed:

- All original returned values and gradients agree at zero shift.
- Constant shifts agree with the original density evaluated directly at the changed clutter probability.
- Every native prediction, satellite-logit and window-odds derivative agrees with central finite differences at nonzero parameters.
- Satellite and clutter responsibilities sum to one; an observation without visible satellite support remains uniform after conditioning.
- Log-space calculation remains finite at odds shifts of minus and plus 1000, including empty support.
- Numerical integration on the frequency circle gives unit density for fixed acquisition covariates and partial visibility.

The implementation invokes the immutable baseline density for validation, then performs a second density calculation in log space. This avoids trying to recover signal evidence from a rounded or underflowed baseline posterior. Both passes are algebraic likelihood calculations: neither predicts an orbit nor runs an optimizer. This extra density work must be included in later measured objective runtimes.

## Source review and limits of the proposed covariate

The public `TrackingCandidate` contract carries fractional exact score, control score, margin and the passing-gate flag. `application/scanner_trajectory.py` copies those fields into projected native candidates. `analysis/starlink/fast_scan_scores.py` defines its score margin as exact minus control; actual qualification must also bind the fractional generator and every selected candidate used by the pilot.

The proposed covariate is the log of the selected observation's positive margin, centered and scaled using only its assigned training fold. It must not be replaced by a maximum over other alternatives, a fitted responsibility, a position-derived statistic, or an assumed detection probability. Conditioning on this acquisition statistic may retain selection effects and overlap with existing waveform evidence. Predictive comparisons therefore remain conditional development tests.

There is a separate obstacle to treating missing observations as non-detections: `application/research_fast_scan_tracking.py` excludes `skipped_fast_score` windows and incomplete fractional candidates before constructing its public tracking input. Public probe counts alone do not establish the complete assessed exposure. Any later count model must distinguish omitted computation, incomplete evidence and assessed negative detections.

Required before numerical fits: source-bound selected-candidate margin equality, finite positive margins for every assigned observation, nonzero training-fold scale, exact beta-zero full-objective and gradient nesting, and nonzero-beta actual-data derivative checks. The same seeds, candidate banks, folds, priors and budgets must be used by the baseline and extension. Opposite-fold likelihood, direct density substitution and position accuracy must remain separate outcomes. No full-cohort accuracy claim follows from these component tests.
