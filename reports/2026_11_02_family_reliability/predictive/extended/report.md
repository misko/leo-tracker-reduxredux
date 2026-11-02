# Uniform phase-cap15 conditional control

The larger phase cap closes all DS26-0070 damped SD2/SD4 fits, while its legacy control still closes only one fold per c arm. It does not resolve the position-posterior limitation: SD2 and SD4 fold 2 lie on the regional boundary in both arms. Every DS26-0070 SD4 fold places at least 9–50% of its untruncated position Gaussian outside the declared box. Its attractive held score therefore remains a diagnostic sensitivity, not reliable bounded-position posterior validation. DS26-0309 outcomes are unchanged, including its optimizer failures.

All 48 original model/arm/fold cells were rerun with phase cap 15. Native train/held IDs, guard groups, priors, empirical preprocessing, aliases, model cells, common RF start, and optimizer settings are unchanged. No original result was overwritten and no early-stopped result was reused. The frozen solver source exactly matches the SHA256 recorded by the original run. The separate protocol and source hashes were written before the cap15 outcomes, after the cap8 outcomes had been inspected. This is a controlled replication on reused folds, not new independent validation.

Held scores below are diagnostic even where numerical checks pass. Full-data nomination, point-noise preprocessing, likelihood powers, aliases and RF initialization persist; ancillary accepted-family/linear likelihoods remain omitted. Three overlapping random folds provide conditional development evidence, not independent generalization or production acceptance. Position accuracy and GPS were not accessed.

| Scan | Arm | Solver | SD | All-score gain vs legacy | Other-family gain | Phase closed | Optimizer success | Boundary | Numerically qualified |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
|DS26-0309|c0|legacy|1|0.000|0.000|3/3|3/3|0/3|3/3|
|DS26-0309|c0|damped_half|1|0.025|0.003|3/3|3/3|0/3|3/3|
|DS26-0309|c0|damped_half|2|25.185|12.595|3/3|3/3|0/3|3/3|
|DS26-0309|c0|damped_half|4|74.658|38.821|3/3|2/3|0/3|2/3|
|DS26-0309|fitted_c|legacy|1|0.000|0.000|3/3|3/3|0/3|3/3|
|DS26-0309|fitted_c|damped_half|1|0.008|0.002|3/3|2/3|0/3|2/3|
|DS26-0309|fitted_c|damped_half|2|24.822|12.318|3/3|2/3|0/3|2/3|
|DS26-0309|fitted_c|damped_half|4|74.058|37.712|3/3|2/3|0/3|2/3|
|DS26-0070|c0|legacy|1|0.000|0.000|1/3|2/3|0/3|1/3|
|DS26-0070|c0|damped_half|1|12.881|10.239|3/3|2/3|0/3|2/3|
|DS26-0070|c0|damped_half|2|93.453|73.078|3/3|3/3|1/3|2/3|
|DS26-0070|c0|damped_half|4|104.807|83.185|3/3|3/3|1/3|2/3|
|DS26-0070|fitted_c|legacy|1|0.000|0.000|1/3|3/3|0/3|1/3|
|DS26-0070|fitted_c|damped_half|1|13.640|10.807|3/3|3/3|0/3|3/3|
|DS26-0070|fitted_c|damped_half|2|95.145|74.552|3/3|3/3|1/3|2/3|
|DS26-0070|fitted_c|damped_half|4|106.777|84.840|3/3|3/3|1/3|2/3|

A numerically qualified row requires phase closure, successful position optimization, an interior regional solution, positive unfloored position curvature, and a positive normalized predictive covariance. Scores from unqualified rows are retained visibly; their improvement cannot be presented as validated prediction. Changing phase cap cannot cure a position optimizer termination or turn an untruncated boundary Laplace approximation into a valid bounded posterior. No additional starts or optimizer changes were introduced in this controlled comparison.

The covariance construction does not double count position and nuisance uncertainty in its local Gaussian interpretation. It uses `D + U Cov(beta|x,train) Uᵀ + J_mean Cov(x|train) J_meanᵀ`, where `J_mean` differentiates the total posterior predictive mean, including the training nuisance-mean response to position. The law of total covariance supplies these two terms; a component test matches their sum to the full joint Gaussian posterior covariance, including cross-correlations. Using only the orbital derivative while holding the nuisance posterior mean fixed would fail this test.

For a score expressed as −2 log density, the position precision is half its Hessian. The implementation restores both `log det(D + UUᵀ)` and `n log(2π)` in Hz units. Every cap15 all-held score was independently reconstructed with the full dense covariance. The diagonal noise plus shared nuisance and position covariance is positive definite when all noise SDs are positive; negative predictive quadratic forms and normalization disagreements are separately flagged. This algebraic audit does not calibrate the empirical noise model, missing Gamma uncertainty, nonlinear phase approximation or within-group residual correlation.

The original curvature floor is a heuristic based on the regional uniform-prior variance; it cannot justify a nonpositive Hessian. Any floor activation is therefore unqualified. A boundary cell is also unqualified because an untruncated Gaussian extends outside the allowed regional box. A better diagnostic held score at such a cell does not establish a generalizable model.

A separately labeled post-hoc box-tail audit also checks interior modes: marginal Gaussian tails give a lower bound (largest coordinate tail) and upper bound (sum of coordinate tails, capped at one) on posterior mass outside the 25 × 25 km regional box. A lower bound above 5% exposes a material truncated-prior mismatch even where the optimizer mode is interior. This diagnostic does not change the frozen scores or preregistered numerical flags; a passed numerical flag alone must not be read as calibrated Laplace coverage. See `position_box_audit.csv`.

Audit: {"boundary_cells": 4, "curvature_floor_cells": 0, "dense_normalization_passes": 48, "errors": 0, "jobs": 48, "maximum_absolute_dense_vs_lowrank_score_delta": 2.000888343900442e-11, "negative_predictive_quadratics": 0, "nonpositive_position_precision_cells": 0, "numerical_fit_qualified_cells": 35, "original_frozen_artifacts_unchanged": true, "original_phase_closed_cells": 40, "originally_closed_maximum_absolute_score_change": 0.0, "posthoc_cells_with_at_least_5pct_Gaussian_mass_outside_regional_box": 12, "preregistered_sources_unchanged": true, "seconds": 167.68898800667375, "tests": "Two original density/split tests plus two extended Gaussian covariance/Hessian tests pass."}.

Artifacts: `protocol.json`/`.sha256`, unchanged-source `frozen_solver.py`, full per-job solver histories and covariance audits, `scores.csv`, `summary.csv`, `audit_summary.json`, and `results.json`. Reproduce with the same Python/environment as the parent predictive manifest and `.../extended/control.py`; tests are `.../extended/test_covariance.py`.
