# Independent scientific and artifact audit

The saved experiment passes the scientific-construction and artifact checks for its declared **conditional Gaussian moment diagnostic**. The score is exact for the saved diagonal-plus-low-rank Gaussian vectors. It is not exact predictive evidence for the original Student/Gamma, nonlinear-phase model, nor independent end-to-end validation of the inherited graph, labels, aliases, mode support, noise estimates, or accuracy at unseen sites.

## Scoring and leakage review

The three seeded folds hold every original curved and predictive owner of a family together across receivers and channels. Training masks remove every held curved likelihood factor, and held predictive entries are absent from the train position objective. Original training-family predictive factors can influence position but never enter curved calibration normal equations. Predictive factors therefore affect calibration indirectly through the fitted position; the conditional calibration calculation at a fixed position uses curved training observations only.

Each model and c arm uses the same fold membership, original factors, regional bounds, cold start and five-by-48 search budget. The fitted train position is a point estimate; its uncertainty is not included in the held covariance. Target timing is linearized at its causal prior mean, not a target-fitted or incumbent phase.

The score retains the complete joint training nuisance covariance, conditional on variational Gamma precisions and the original generalized-likelihood powers. All held-local training feature columns are exactly zero. Held phase variance is reset to its original standardized Student marginal variance of one, instead of using the unused mean-field precision; its cross-covariance with trained coordinates is exactly zero. Held orbit coordinates retain unit Gaussian variance. Original curved and predictive fragment constants each retain independent 300 Hz Gaussian priors.

All 48 saved target vectors use the original per-ID native sigma exactly. The primary multiplier is sqrt(2), matching E[1/tau] = 2 for an unseen Gamma(2,2) precision, with factors one and two retained as frozen sensitivities. This matches moments, not the original heavy tails. Every saved held phase reference equals the causal prior mean in all target slots. No target coefficient, Gamma precision, or phase refresh is learned from target CFO values.

The five owned heldout tests cover a dense Gaussian oracle, shared covariance, retention of position-sensitive shapes, whole-family factor removal, and held-CFO redaction. The redaction check verifies training coefficients, precisions, objective and residuals, plus one identical eight-step optimization trajectory, for DS24-0017/fold0/sharedRF50/fitted-c. It does not independently replay all 24 fits. Five owned geometry tests cover Schur algebra, coefficient-block partitioning, normalized loss closure, legacy phase-reference reconstruction, and reconstructed group Gamma costs.

## Independent artifact checks

`check_baseline_membership.py` reconstructs original likelihood membership without fitting. DS24-0017 has 2,881 curved and 888 predictive points across 31 likelihood families. DS24-0095 has 2,262 curved points and no predictive points across 15 families. All IDs have a single family, and curved/predictive likelihood IDs are disjoint.

`audit_artifacts.py` independently verifies:

- All 24 expected position fits, 48 crossover vectors and 144 sensitivity scores, with no omitted case/fold/model/c-arm combination.
- Every held and training ID set against independently reconstructed baseline membership. Each original likelihood ID is held exactly once, and no held family owner survives in training.
- The held protocol, input manifest, 359 source dependencies, original baseline hashes, native sigmas, causal held phase references, result/NPZ hashes and measurement bindings.
- Both finalized geometry source/input seals, frozen RF50 endpoint files, matching factor contracts across both models and both c arms, all 88 path points, and exact normalized-loss decomposition.

Independent observation-space SVD calculations reproduce every Gaussian score component to a maximum absolute difference of **7.46e-11**. The largest geometry loss-decomposition discrepancy is **1.46e-11**. Held-local/trained covariance is zero. All saved Gamma updates meet the declared 1e-5 log-precision tolerance.

One train fit does **not** meet the original 0.01 s phase-refresh criterion: DS24-0095/fold2/fitted-c/baseline ends at **0.0150179 s** after the frozen budget. It remains in the diagnostic. The symmetric fixed-position crossover refreshes all converge below 0.01 s, and every full-data geometry path point passes both phase and Gamma convergence. Completion of 24 bounded fits must not be described as convergence of all 24 train position fits.

`audit_heldout_tables.py` additionally reconstructs all five report CSVs: **156 rows and 1,104 numeric cells** agree with raw results. The five-test receipt's source, protocol and log hashes are valid. The documented convergence sensitivity removes 0095/fold2 consistently across both c arms, both predictors and all noise scales; all 12 retained two-fold movement sums remain negative. This sensitivity is descriptive and does not replace the full-denominator primary result.

`audit_geometry_tables.py` verifies all 11 final geometry CSV hashes, 416 family-owned derivative rows, 104 model-change rows and all 16 family/global derivative groups. Direct directional derivative decomposition agrees within **5.68e-11**. Separately differenced x/y gradients dotted into the displacement differ by up to **5.89e-6**, consistent with the distinct finite-difference formulas; these are not treated as exact algebraic identities.

## Independently reconstructed primary results

Positive movement gain means that the same predictor favors its RF50-trained endpoint over its baseline-trained endpoint. The following are sums of three conditional fold scores, with overlapping training sets, not independent experimental replications.

| Scan | c arm | Movement gain under baseline predictor | Movement gain under RF50 predictor | Own-model gain |
|---|---|---:|---:|---:|
| 0017 | c0 | +5.035 | +15.629 | +254.350 |
| 0017 | fitted-c | +5.636 | +16.724 | +267.279 |
| 0095 | c0 | -12.541 | -6.625 | +139.953 |
| 0095 | fitted-c | -11.031 | -5.807 | +135.298 |

The two cases differ in conditional support for moving the position, despite positive own-model predictive gains in both. Own-model gain combines predictive mean, covariance, location and nuisance changes. A predictor change at a fixed position also changes **both mean and covariance**; it cannot be called a covariance-only effect. The same-predictor crossover is the relevant movement contrast, while its position-dependent nuisance mean and covariance are refreshed consistently.

The full-data geometry is descriptive mechanism evidence. In fitted-c, the frozen shifts are 0.882 km and 1.602 km. Under RF50, normalized loss decreases by only 5.009 and 2.709 along those shifts, respectively. At the baseline endpoint, the local Gamma-fixed mean-information calculation attributes 3.26% versus 18.05% of displacement-direction information removal to appended receiver modes, with maximum phase/displacement correlations about 0.918 versus 0.967. These values support a stronger local receiver/phase/position tradeoff on 0095; they do not establish a hardware cause, a wrong identity, calibrated confidence, or geographic accuracy.

The cases were chosen after opposite geographic effects in the preceding study. Their sign contrast cannot become a per-case enable/disable rule or a new release qualification. No GPS value was used for scientific construction, scoring, methodological review, or any selection in this audit. No new position fit, RF collection, QNAP write, scientific-golden change, or production-source change was performed.

After the scientific artifacts were sealed, the parent requested a separate geographic reporting audit. `audit_positions.py` checks all **32** reported rows against original saved endpoints or sealed train-only endpoints and independently reconstructs spherical distances. Its maximum distance discrepancy is **4.44e-16 km**. This final reporting-only use of the evaluation coordinate changes no inference, method, gate, fold, or result selection.

## Corrections made before final evidence

The primary noise reference was changed from a proposed fixed 75 Hz to the original per-ID sigma before production fits. The runner's pre-fit seal checks were extended to enforce its saved input manifest, original baseline, measurement binding and fold membership before any production fit. Geometry outputs were replayed under the finalized source after an empty-predictive-entry guard and source-at-start/source-at-end guard were added. Final artifacts pass current source seals; intermediate outputs are not mixed into the final comparison.

Machine-readable evidence is in `baseline_membership.json`, `artifact_audit.json`, `heldout_table_audit.json`, `geometry_table_audit.json` and `position_reporting_audit.json`. The audit scripts run with one process and one BLAS/OMP/MKL thread; none performs position fitting.
