# Candidate-mixture reception calibration design

## The remaining mismatch

The consistent-direction refit trains reception models on one weighted-mean direction per row,

\[
\bar e_{ti}=\sum_k w_{tk}e_{tki},
\]

then evaluates a logistic detection likelihood and a conditional Gaussian ratio likelihood at \(\bar e_{ti}\). Geographic scoring instead evaluates each candidate direction separately, accumulates all frequency and reception evidence under one track-wide satellite identity, and marginalizes identity only after summing log likelihoods:

\[
-\frac{1}{n_t}\log\sum_k w_{tk}\exp\{F_{tk}+D_{tk}+R_{tk}\}.
\]

Here `robust_core.joint_heldout_score` uses `F` for reserved Student-t frequency evidence, `D` for every matched/unmatched reception row, and `R` for matched rows only; its denominator is the full reserved-observation count. Because logistic and Gaussian log likelihoods are nonlinear, generally

\[
\ell(y;\sum_k w_ke_k) \ne \log\sum_k w_k\exp\{\ell(y;e_k)\},
\]

and the discrepancy is larger still when one identity is shared across a track rather than redrawn per row. Replacing the old direction by a robust weighted mean fixes the association convention but not this likelihood mismatch.

## Smallest matching calibration objective

Keep the robust frequency candidate IDs and normalized `log_weights` fixed. Do not use reception outcomes to change the shortlist, CFO, weights, timing, or candidate directions. For each retained calibration track \(t\), candidate \(k\), and reception row \(i\), define the existing nuisance predictors and direction terms without changing their feature encoding:

- detection: \(a_{ti}(\alpha)+\beta s_{ti}e_{tki}\), where \(s=+1\) for an RX0 anchor and \(-1\) for RX1;
- conditional ratio: \(m_{ti}(\gamma)+\delta e_{tki}\), with the ratio always RX1/RX0;
- ratio contribution zero when unmatched, exactly as in scoring.

The candidate reception log likelihood is

\[
Q_{tk}=\sum_i \log \operatorname{Bernoulli}(y_{ti};\operatorname{logit}^{-1}(a_{ti}+\beta s_{ti}e_{tki}))
+\sum_{i:y_{ti}=1}\log N(r_{ti};m_{ti}+\delta e_{tki},\sigma^2).
\]

Fit the existing detection nuisance coefficients, ratio nuisance coefficients, direction slopes, and `log_sigma` jointly by minimizing

\[
\sum_t \frac{-\log\sum_k\exp(\log w_{tk}+Q_{tk})}{n_t}
+\frac{\lambda}{2} (\|\theta_D^{\neg intercept}\|_2^2+\|\theta_R^{\neg intercept}\|_2^2),
\]

with the already declared `lambda=1`. The factor `1/2` is required to match `model_eval`'s gradient convention (`lambda * beta`) and Hessian convention (`lambda * I`). The division occurs *outside* `logsumexp`: candidate identity still gains evidence across the whole track, while each track retains unit total influence as closely as possible to the present design. `n_t` is the full number of reception rows, so conditional-ratio terms retain zero contribution for nondetections. Fit positive variance through `log_sigma`; include the complete Gaussian normalization term. Do not reuse the present weighted residual-MSE formula, which is not the MLE variance under a latent shared identity.

This objective deliberately changes more than candidate marginalization relative to the legacy fits. In particular, legacy `fit_continuous_models` gives each track unit weight over its **matched** rows, whereas the joint objective divides detection plus conditional-ratio evidence by **all** reception rows. Jointly estimating Gaussian variance also changes the effective balance between ratio fit and the fixed ridge penalty. Consequently, its M0 coefficients, predictions, and variance are not expected to reproduce the legacy separately fitted M0. They must not be used as a bit-parity gate.

To isolate candidate nonlinearity, fit a nested mean-direction M1 with the *same* joint objective, nuisance design, all-row denominator, joint variance parameterization, ridge convention, optimizer, and starts, replacing every candidate trajectory by the robust weighted-mean trajectory. Compare candidate-mixture M1 primarily with this nested mean-direction M1. Retain the existing consistent-mean M1 only as a labeled legacy reference; differences from it combine mixture nonlinearity with the changed joint objective and weighting.

This is the smallest objective matching reception scoring. It does not add timing shifts, candidate caps, new nuisance terms, receiver dependence, or a new cohort. Frequency `F` should **not** enter reception calibration: doing so would train the reception coefficients partly to the reserved frequency residuals. The fixed training-derived \(w\) is the identity prior for this calibration; `F` remains new evidence at geographic scoring time.

## Required frozen inputs

The fit can be built without new propagation or RF data by exact joins:

- `calibration_directions_data.json.rows`: `session_id`, `track_id`, `observation_id`, `track_observation_index`, and each `robust_candidates[]` member's `candidate_id`, `east`, and `up`;
- `topology_frequency_fixedpoint.json.final_tracks`: per track `candidate_ids`, normalized `log_weights`, `weights`, and frozen parameter/source bindings;
- `model_rows.json`, after the existing topology exclusion: receiver outcome, `receiver_id`, joint `channel:edge`, `sample_rate_hz`, `anchor_margin`, matched ratio, and exact row keys;
- `audit_source_topology.json`: the ten excluded calibration tracks and six-session membership.

The direction artifact's `weight` field alone is insufficient because valid tiny probabilities may underflow to zero. The fitter must join candidate IDs to the fixed-point artifact and use its finite normalized `log_weights` directly. Candidate order must be validated, not assumed.

A resulting artifact should preserve: all source/code hashes; exact join and exclusion accounting; candidate IDs and fixed log-weight digests per track; serialized feature levels/scalers; detection and ratio coefficients; `log_sigma`, variance, ridge, optimizer status/gradient norm; all-six calibration joint NLL; and six conditional-LOSO reception results. No evaluation artifact belongs in this contract.

## Leakage, dependence, and identifiability

The robust identity weights use Doppler-training observations, while reception rows are reserved observations, so reception outcomes do not directly select candidates. However, the weights and Student-t hyperparameters were fitted using all six calibration scans. A leave-one-scan-out reception fit that keeps these weights is therefore conditional LOSO, not fully nested frequency validation. It must retain that label. Fully nested validation would require refitting the frequency model and shortlist without the held scan, which is a different, larger experiment.

At geographic scoring, reserved frequency and reception evidence can originate from the same RF observation. Their product assumes conditional independence given identity/location even though CFO quality, detection, and margin may share signal-strength or interference causes. Shared identity is not itself double counting, but unmodeled dependence can make the joint likelihood overconfident. Report D, detection, and conditional-ratio contributions separately and do not interpret their sum as calibrated geographic uncertainty without a dependence study.

Direction is correlated with scan, channel lane, sample rate, and satellite identity. Keep the existing joint `channel:edge`, sample-rate, receiver, and anchor-margin nuisance terms and training-derived standardization. With only six scans and often nearly one-hot identity weights, the latent-mixture objective may provide little information beyond a MAP fit; direction slopes and variance can trade off, while unconstrained variance could approach a pathological small value. Use no outcome-tuned cap, but require a finite interior optimum, positive-definite local curvature in identifiable directions (or an explicit rank warning), and stability from deterministic dispersed starts. A failure is evidence that this model is not identifiable from these scans.

## Falsifiable calibration-only gates

Implementation gates:

1. Exact 6,378-row/344-track join; the excluded ten tracks are absent. Candidate IDs match the fixed-point top three in order, and `logsumexp(log_weights)=0` for every track.
2. Perturbing any reception outcome or ratio leaves candidate IDs, directions, CFOs, and log weights byte-identical.
3. Candidate permutation leaves the objective and predictions unchanged. Splitting one component into two identical directions whose weights sum to the original also leaves them unchanged.
4. A one-hot identity reduces exactly to the ordinary candidate-specific GLM likelihood. Identical candidate direction trajectories reduce exactly to the corresponding single-direction likelihood.
5. Direction-free candidate-mixture M0 cancels normalized latent weights exactly and reproduces an independently implemented candidate-free **same-joint-objective** M0 within numerical tolerance. It is not required to reproduce legacy `model_eval` M0, whose matched-row ratio weighting and separately learned variance define a different objective.
6. The nested mean-direction M1 uses exactly the mixture objective's nuisance features, all-row denominator, ridge penalty, variance parameterization, optimizer, and starts. When all candidate directions are replaced by their weighted mean, mixture and nested implementations agree numerically. The existing consistent-mean fit is reported separately as a legacy reference, not this algebraic oracle.
7. Shared-identity likelihood matches a brute-force small fixture and differs from a deliberately row-redrawn identity fixture. Matched plus unmatched rows verify that ratio contribution is normalized by all reception rows.
8. Analytic gradients match central finite differences; objective, gradients, coefficients, and variance are finite. Multiple deterministic starts converge to the same objective and materially equivalent predictions; otherwise report non-identifiability and stop.
9. Reversing direction or permuting track direction trajectories is retained as a calibration-only negative control and must not alter nuisance/source membership.

Evidence gates, declared before any geographic replay:

- Report all-six fit only as descriptive. Report conditional six-way reception LOSO with fixed all-six frequency weights and its caveat.
- Compare mixture M1 against mixture M0 and the nested same-objective mean-direction M1 on the same held scan using full normalized detection-plus-conditional-ratio NLL, plus the two components separately. Report the legacy consistent-mean M1 as context, not as the isolation contrast.
- The advancement gate is fixed in advance: all folds must converge finitely; pooled equal-track conditional-LOSO joint NLL must be lower than both mixture M0 and nested mean-direction M1; at least four of six held scans must improve versus the nested mean model; and the pooled improvement must remain positive after removing the single scan with the largest favorable contribution. This last leave-largest-gain-out rule is the numerical meaning of “not driven by one scan.” Failure stops the iteration; it is not repaired using evaluation locations, errors, or search outcomes.

Passing these gates would establish a coherent calibration likelihood, not geographic improvement. Any later replay on already unblinded grids remains development evidence; a resolution claim still requires a separately frozen estimator and disjoint confirmation recordings.
