# Conditional family scoring: read-only helper review

At a fixed held-curved-family cavity position/phase, form predictive residuals y, shared design U and curved posterior precision G. With native measurement covariance D and path-constant design B, the joint predictive covariance is K = D + U G⁻¹ Uᵀ + BBᵀ. The same shared latent creates cross-family covariance; individual marginal family scores cannot be added as independent evidence.

Partition held-family H from remaining predictive paths R. Conditional mean residual is y_H − K_HR K_RR⁻¹ y_R and covariance is S = K_HH − K_HR K_RR⁻¹ K_RH. The proper conditional negative twice log density is residualᵀ S⁻¹ residual + logdet(S) + n_H log(2π). Include mean conditioning and covariance conditioning together. Equivalent joint-minus-R density requires exactly identical cavity calibration and shared model in both terms.

Existing helper ports:

- `ds23_predictive_linear.linear_geometry` constructs the predictive view, values, fixed-window sigma, path groups and slices.
- `ds23_height_problem.geometry_features` constructs physical prediction features at the fixed position and phase reference.
- `ds23_frequency_events.attach_event_predictive` documents the training-weighted G construction and appended event columns. Preserve full prior precision where a correlated calibrated model supplies it.
- `ds23_orphan_joint_predictive.condition_gaussian` conditions unit shared latent coordinates on other predictive paths with grouped constants, returning latent mean/covariance and original joint density. This Gaussian integral factorization need not change curved calibration.
- `ds23_family_cavity.predictive_density_reference` provides an independent dense/economy-SVD density replay.

For a whole-family cavity, remove all that family's curved calibration observations before computing G/mean and refresh phase using training data only. Identity alternatives must receive symmetric cavity treatment. Fixed full-parent positions remain conditional diagnostics, not full geographic cross validation. Native points must never be fed back into the curved calibration normal equations. Native unseen-noise convention remains D_ii = 2 sigma_i²; uncertainty in a whole-path mean belongs in B, not a raw residual-RMS estimate.
