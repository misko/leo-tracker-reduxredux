# Regional-box correction within the local Gaussian predictive model

Box conditioning changes none of the aggregate RF ranks: SD4 remains first and SD2 second for both scans, both c arms, and all/target/other held subsets. On DS26-0070 the SD4 all-held gains versus legacy are 105.83 and 107.69 in −2 log-density units (c0 and fitted-c); other-family gains are 84.16 and 85.70. On DS26-0309 the correction is negligible. This fixes the declared local Gaussian box normalization without resolving its approximation or inherited qualification limits.

All 48 cap15 endpoints were re-evaluated without optimization, using identical native training/held IDs and the actual ±12.5 km box. The corrected density integrates the local Gaussian position approximation conditional on that box. No RF parameter, noise model or nuisance coefficient was fitted using held observations. Original scores and convergence flags are preserved.

The identity is `p(y|train, x∈B) = p(y|train) × P(x∈B|train,y) / P(x∈B|train)`. With conditional prediction covariance `C`, total posterior-mean position Jacobian `J`, and frozen position covariance `S`, the integration-only posterior is `S₂=(S⁻¹+JᵀC⁻¹J)⁻¹` and `m₂=m+S₂JᵀC⁻¹r`. `C` includes noise and nuisance covariance conditional on position. Using the derivative of the total predictive mean preserves the nuisance/position cross-covariance audited in the cap15 control; it is not an independent extra position term.

Box conditioning is not an automatic score penalty. When the held observations concentrate the integration-only position distribution inside the box, the numerator box probability exceeds the denominator and the normalized held density increases. The observed corrections are small relative to the SD4-versus-legacy margins, and do not explain away those margins. Their scientific interpretation remains limited by the inherited model and convergence issues.

Box probabilities use deterministic scaled one-dimensional conditional-normal quadrature. Seeded SciPy bivariate rectangle CDF provides an independent numerical check. Tests also match direct two-dimensional integration and show that a broad box restores the original score. Gaussian conditioning on held observations appears only inside the probability-ratio integral; its coordinates are not new fitted RF solutions.

| Scan | Arm | Held subset | Solver | SD | Unbounded rank | Box rank | Box score sum | Box gain vs legacy | Inherited numerical passes |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
|DS26-0309|c0|all|legacy|1|4|4|17301.540|0.000|3/3|
|DS26-0309|c0|all|damped_half|1|3|3|17301.515|0.025|3/3|
|DS26-0309|c0|all|damped_half|2|2|2|17276.354|25.185|3/3|
|DS26-0309|c0|all|damped_half|4|1|1|17226.881|74.658|2/3|
|DS26-0309|c0|target|legacy|1|3|3|3415.408|0.000|3/3|
|DS26-0309|c0|target|damped_half|1|4|4|3415.419|-0.012|3/3|
|DS26-0309|c0|target|damped_half|2|2|2|3408.486|6.921|3/3|
|DS26-0309|c0|target|damped_half|4|1|1|3394.092|21.316|2/3|
|DS26-0309|c0|other|legacy|1|4|4|13884.590|0.000|3/3|
|DS26-0309|c0|other|damped_half|1|3|3|13884.586|0.003|3/3|
|DS26-0309|c0|other|damped_half|2|2|2|13871.995|12.595|3/3|
|DS26-0309|c0|other|damped_half|4|1|1|13845.769|38.821|2/3|
|DS26-0309|fitted_c|all|legacy|1|4|4|17307.727|0.000|3/3|
|DS26-0309|fitted_c|all|damped_half|1|3|3|17307.719|0.008|2/3|
|DS26-0309|fitted_c|all|damped_half|2|2|2|17282.905|24.822|2/3|
|DS26-0309|fitted_c|all|damped_half|4|1|1|17233.669|74.058|2/3|
|DS26-0309|fitted_c|target|legacy|1|3|3|3406.988|0.000|3/3|
|DS26-0309|fitted_c|target|damped_half|1|4|4|3407.002|-0.014|2/3|
|DS26-0309|fitted_c|target|damped_half|2|2|2|3400.989|5.999|2/3|
|DS26-0309|fitted_c|target|damped_half|4|1|1|3388.531|18.457|2/3|
|DS26-0309|fitted_c|other|legacy|1|4|4|13892.194|0.000|3/3|
|DS26-0309|fitted_c|other|damped_half|1|3|3|13892.192|0.002|2/3|
|DS26-0309|fitted_c|other|damped_half|2|2|2|13879.876|12.318|2/3|
|DS26-0309|fitted_c|other|damped_half|4|1|1|13854.482|37.712|2/3|
|DS26-0070|c0|all|legacy|1|4|4|13763.382|0.000|1/3|
|DS26-0070|c0|all|damped_half|1|3|3|13751.275|12.108|2/3|
|DS26-0070|c0|all|damped_half|2|2|2|13669.369|94.013|2/3|
|DS26-0070|c0|all|damped_half|4|1|1|13657.556|105.826|2/3|
|DS26-0070|c0|target|legacy|1|4|4|2751.222|0.000|1/3|
|DS26-0070|c0|target|damped_half|1|3|3|2749.470|1.752|2/3|
|DS26-0070|c0|target|damped_half|2|2|2|2721.036|30.186|2/3|
|DS26-0070|c0|target|damped_half|4|1|1|2717.381|33.841|2/3|
|DS26-0070|c0|other|legacy|1|4|4|11023.269|0.000|1/3|
|DS26-0070|c0|other|damped_half|1|3|3|11013.803|9.466|2/3|
|DS26-0070|c0|other|damped_half|2|2|2|10949.635|73.634|2/3|
|DS26-0070|c0|other|damped_half|4|1|1|10939.112|84.157|2/3|
|DS26-0070|fitted_c|all|legacy|1|4|4|13773.444|0.000|1/3|
|DS26-0070|fitted_c|all|damped_half|1|3|3|13760.621|12.823|3/3|
|DS26-0070|fitted_c|all|damped_half|2|2|2|13677.824|95.620|2/3|
|DS26-0070|fitted_c|all|damped_half|4|1|1|13665.753|107.691|2/3|
|DS26-0070|fitted_c|target|legacy|1|4|4|2753.635|0.000|1/3|
|DS26-0070|fitted_c|target|damped_half|1|3|3|2751.426|2.210|3/3|
|DS26-0070|fitted_c|target|damped_half|2|2|2|2723.473|30.162|2/3|
|DS26-0070|fitted_c|target|damped_half|4|1|1|2719.805|33.830|2/3|
|DS26-0070|fitted_c|other|legacy|1|4|4|11032.387|0.000|1/3|
|DS26-0070|fitted_c|other|damped_half|1|3|3|11022.396|9.990|3/3|
|DS26-0070|fitted_c|other|damped_half|2|2|2|10957.364|75.023|2/3|
|DS26-0070|fitted_c|other|damped_half|4|1|1|10946.683|85.704|2/3|

These are RF-only diagnostic ranks under the declared local Gaussian. Exact box integration fixes its unbounded-position mass but does not establish that the Laplace approximation is accurate, especially at a boundary. Inherited optimizer failures, phase nonconvergence and curvature flags remain active. Full-data nomination, empirical point-noise preprocessing, aliases, likelihood powers and RF starts remain inherited; Gamma uncertainty and residual correlation are not fully integrated; ancillary likelihoods remain omitted. Reused folds and this post-hoc model debugging are not fresh generalization evidence or production qualification. No localization accuracy or GPS was accessed.

`all`, `target`, and `other` are separate marginal densities and do not add. Overlapping fold sums rank these declared diagnostics; they are not independent-sample evidence or identity probabilities. A favorable corrected score alone does not qualify a failed or model-sensitive fit.

Audit: {"errors": 0, "frozen_sources_unchanged": true, "jobs": 48, "max_absolute_posterior_box_quadrature_scipy_difference": 4.440892098500626e-16, "max_absolute_prior_box_quadrature_scipy_difference": 4.440892098500626e-16, "max_absolute_reconstructed_unbounded_score_difference": 0.0, "max_quadrature_relative_error": 9.951835673093333e-12, "original_frozen_inputs_unchanged": true, "rank_changes": 0, "seconds": 19.620690727606416, "tests": "4 pass: box quadrature versus direct 2-D integration and seeded SciPy CDF; broad-box recovery; position conditioning versus dense joint Gaussian; complete bounded predictive density versus direct position integration."}.

Files: `protocol.json`/`.sha256`, `results.json`, per-cell box probabilities and integration-only position moments, `scores.csv`, `rank_changes.csv`, `audit_summary.json`, and the numerical implementation/tests. Reproduce with the parent environment and `predictive/bounded/run.py`.
