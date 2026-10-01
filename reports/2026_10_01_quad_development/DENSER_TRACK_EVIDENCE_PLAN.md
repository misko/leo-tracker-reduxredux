# Next evidence hypothesis: nested denser track sampling

## Measured opportunity

The [sealed sampling inventory](track-sampling-inventory-v1.json) verifies the actual selected observation IDs against every original single-scan receipt. Across 64 scans and 2,906 retained tracks, the estimator uses 23,208 of 134,822 available retained evidence points. The cap is eight points per track; 2,867 tracks have more than eight points, and the median retained track has 44. The median of the selected within-track median time gaps is 3.37 seconds.

A cap of sixteen could retain 45,758 points; thirty-two could retain 84,601. Counts are not independent sample counts or effective information. No excluded track is restored by this inventory, and no new RF or orbit propagation is involved.

The current time-spread selector is not nested: changing its cap from eight to sixteen would drop at least one previously used point in 2,531 tracks. That would mix added evidence with changed evidence selection. Preserve all eight original selected IDs, then fill additional slots deterministically by the greatest distance in time from the selected set, breaking ties chronologically. A sixteen-point arm must contain the complete eight-point arm; a thirty-two-point arm must contain the sixteen-point arm.

## Model and hypothesis

Keep the same fixed height, position support, timing/drift/epoch priors and full-catalogue hard association model. For a track with raw observations y and predicted Doppler f(theta), project out the constant frequency offset with the existing contrast matrix B. The residual is r = B(y-f(theta)) and the scale matrix is S = B C B-transpose. Retain the existing multivariate Student-t4 density, including its dimension-dependent normalization and log determinant. Recompute both signal and background likelihoods for the new observation dimension; do not compare raw objective values across eight- and sixteen-point models.

The initial hypothesis is that additional trajectory samples constrain curvature and distinguish candidate satellites or location modes missed by the eight-point representation. Added observations can also magnify model mismatch. The existing covariance already includes temporal correlation; do not replace it with an independent-observation assumption. Earlier [correlation experiments](../2026_09_28_covariance_position/README.md) improved predictive likelihood without consistent geographic gains, and used different datasets and models. They do not establish that denser sampling improves the current estimator.

## Bounded prerequisite and pilot

First implement and test nested selection: exact retention of the baseline eight IDs, deterministic handling of ties, unique IDs, chronological output, and limits for short tracks. Rebuild ports with the selected observations and corresponding covariance. The eight-point control must reproduce the frozen baseline observation IDs, scores and predictions. Check sixteen-point gradients against finite differences on metadata-first DS9/DS10/DS11 single scans before any fit. Validate background dimension and prior normalization as well as signal residual derivatives.

Then freeze a three-single warm diagnostic, starting both controls and denser arms from the same original state and charging original inference work. Compare numerical acceptance and geography only after independent audits. This would test local model sensitivity, not cold acquisition or runtime. If supported, test cold acquisition separately before pairs and quads. Do not simultaneously change seed count, timing priors, visibility, covariance hyperparameters or optimizer.

Keep the thirty-two-point arm as a later option rather than expanding automatically. The full first-start ablation must finish independently; saved-start runtime gains do not grant unlimited computation or prove that this extra evidence is useful. No denser fits have run yet. This plan is motivated by measured unused evidence, not by choosing points that favor the reference location.

The inventory is read-only, uses no reference coordinates, and seals parent receipts, evidence inputs and implementation sources. Its central verification is exact reproduction of the baseline's selected IDs across all 64 scans, rather than an assumption based solely on a default configuration value.
