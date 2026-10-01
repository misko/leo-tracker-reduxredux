# Local satellite-group influence across window sizes

Hypothesis: residual location sensitivity is concentrated in a few satellite groups and reduced by additional scans; nuisance coupling may weaken apparent geometric information. Diagnose this before proposing any group rejection or reweighting model.

Use the accepted optimized one-start cold fits for the first single, first pair and first quad of each of DS9, DS10 and DS11 (nine fixed cases). Freeze state, identities, covariance and Student-t4 IRLS weights. No geographic reference or error is used to select cases, groups or thresholds. A group is (scan ID, assigned NORAD), including both receivers; grouping across scans is not justified by independent scan nuisance blocks and potentially distinct orbit artifacts.

For track residual r and prediction Jacobian J, accumulate g_i=-w J' C^-1 r and H_i=w J' C^-1 J with w=(4+d)/(4+r'C^-1r). Add the unchanged Gaussian prior gradient and precision. Retain only position, nonzero state entries and nonzero Jacobian columns. Verify the assembled full scaled gradient satisfies g'H^-1g<1e-5, consistent with the accepted baseline audit. H is the positive IRLS approximation, not the exact posterior Hessian.

For each group G, compute delta_G=-(H-H_G)^-1(g-g_G). Report its horizontal norm in meters and direction, the maximum generalized leverage eigenvalue of (H_G,H), and remaining matrix definiteness. This is one frozen-weight local deletion step, not a refitted position or an estimated location error. Do not silently regularize singular remaining systems. Preserve failed outcomes. Compare maximum and median group sensitivity across the nine cases, with all group values visible.

Profile nuisance directions using the Schur complement S=H_pp-H_pn H_nn^-1 H_np. Report its eigenvalues, condition number, and eigenvalue ratios to the fixed-nuisance position block. No confidence coverage claim: inverse IRLS curvature is already known to be uncalibrated. Synthetic tests cover exact quadratic deletion, nuisance Schur equivalence, and singular deletion handling. Use sequential single-thread processes, shared lock and 90 seconds per window, with immutable source/input receipts.

There is no preauthorized outlier rejection rule. If sensitivity is concentrated, a subsequent bounded exact group-deletion refit on the most influential group selected without geography should first test whether the linear approximation predicts the actual motion. That would diagnose model sensitivity, not prove improved accuracy. No production promotion.
