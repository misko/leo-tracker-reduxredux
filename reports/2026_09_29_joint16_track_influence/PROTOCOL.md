# Local track influence in all nine joint16 fits

Analyze all selected joint16 fits from the equal-budget association control. Do not select tracks or fits from reference error. At each saved fit, obtain each scan's training gradient and observed negative Hessian, auditing half-step derivatives and symmetry with the established 0.01 tolerance. Profile its timing by the Schur complement and sum the 16 profiled geographic Hessians.

For each track, compute its training gradient separately and transform it using the **full scan's** timing-profile operator. Require per-track gradients and scores to sum to each scan's evaluation within 1e-7. Require whole-scan sums to replay the selected fit score within 1e-7. The pooled profiled Hessian must be positive definite.

The first-order response to infinitesimal downweighting of track i is `-H_total^-1 g_i_profiled`. Report its norm, maximum track norm, top-ten share of summed norms, and the vector sum for the ten largest norms. The latter is only a linear extrapolation toward deletion: it ignores curvature changes and nonlinear association response and is not a new fitted location or an accuracy bound.

Also aggregate response vectors by receiver and source/target window. Retain all rows and numerical failures. Compare summaries against reference error only after calculation. No automatic track removal, no new geographic fits, no RF collection. Per-dataset subprocess cap 300 seconds, BLAS1.
