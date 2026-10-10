# Two conditional mechanisms to investigate after discovery

Report/source synthesis only. No current 151 outcomes, newer-22 data, reserves, recordings or model calls were accessed. Neither idea is frozen or ready for positioning trials. Neither has evidence of reaching the standalone 0.4 km target.

## What the completed evidence narrows down

[140](../2026_10_10_position_error_iter140/DECISION.md) improved typical phase-model errors but worsened the full fitted-c mean and the largest failure; two phase fits also failed qualification. [150](../2026_10_10_position_error_iter150/RESULTS.md) changed discovery and repaired an arm-transition qualification failure on one consumed catastrophic case. These are different mechanisms. A better search region cannot by itself establish that the typical residual bias is solved, and phase plus repaired search is not an evaluated combined policy.

[145](../2026_10_10_position_error_iter145/DECISION.md) found negligible fitted-c benefit and worse c=0 performance from fixed paired-emission correlation. [144](../2026_10_10_position_error_iter144/DECISION.md) found catalogue perturbations almost entirely inside the unconstrained nuisance derivative span, but deliberately omitted prior/bound costs and finite nonlinear reassignment. [141](../2026_10_10_position_error_iter141/PLAN.md) documents why adding receiver contrast or differencing balanced simultaneous pairs is not a new common-position information source. More nuisance flexibility, another correlation coefficient, or a fixed directional position correction is not justified by this evidence.

## 1. Integrate a small proper-prior nuisance block instead of only optimizing it

**Hypothesis:** profiling a weakly identified calibration block can favor a narrow nuisance optimum over a position supported across a broader range of physically allowed calibration. This is not additional sensor information. It changes how the existing proper nuisance prior contributes to position inference, potentially affecting ordinary local minima as well as search ranking.

The first bounded mathematical target is a small, full-rank Gaussian-prior block already present in B7, with all other parameters, candidate bank and observation support held matched. For nuisance coefficients b, prior precision Λ, and an interior conditional optimum, the Laplace expression is

`L_marginal(x) ≈ L_MAP(x,b_hat) + 0.5 log det H_bb − 0.5 log det Λ + constant`.

Do not apply this blindly to unregularized affine clocks or static c: those do not supply a proper normalized prior for this integral. Do not use the complete-label curvature from 117 as if it were the observed mixture Hessian. Negative curvature, singular blocks, active bounds, visibility changes and mixture-mode changes invalidate the simple formula and must be detected, not hidden with an arbitrary ridge. Exact quadrature in a synthetic one/two-dimensional block is the appropriate first oracle.

This differs from changing slope-prior widths, receiver-pair corrections, correlation likelihoods and linear nuisance optimization: those still select a point estimate of calibration. The bounded reviewed reports did not show a completed normalized nuisance-marginalization comparison; this is a review finding, not a claim about every repository experiment.

**Cheap falsification:** in a fixed linear Gaussian model with position-independent design and precision, the determinant contribution is constant, so this must produce the same position score differences as profiling. Test that exact no-op, change of nuisance units/basis, and agreement with analytic Gaussian integration. Only if a subsequent reference-free endpoint diagnostic shows a material, well-defined position-dependent volume term should a matched position trial be considered. A constant, numerically unstable or assignment-dominated term rejects the proposed simple approximation before expensive fitting.

Cost is one small factorization, O(d³) for the chosen nuisance block, plus obtaining its correct curvature. Dense full-nuisance differentiation is not an embedded-cost promise. No per-recording block choice, width tuning or determinant weighting based on reference error is acceptable. Both final c arms remain required; c itself can remain profiled while the same proper block is integrated in each arm.

## 2. Test the estimator's frequency time reference under chirp and partial support

**Hypothesis:** the existing CFO estimator may measure frequency at an amplitude/estimator-dependent effective time rather than the arithmetic support centre supplied to the position model. A varying Doppler signal over partially occupied pilot support could then produce a structured frequency mean error that is not repaired by sub-bin interpolation alone.

This is an unresolved mechanism already identified in [118's support audit](../2026_10_09_position_error_iter118/INTEGRATION_SUPPORT.md), not a newly discovered omission. The positioning preparation uses the arithmetic pilot support centre. The published 120/122/125/127 synthetic studies established partial-support and frequency-bin behavior; their constant-frequency tests do not establish the estimator's response to a time-varying carrier. The matched real-data refiners in 133 changed measured CFO, not this time-reference model. This proposal must not be presented as another completed successful refinement.

For ideal symmetric constant-amplitude support, linear frequency variation averages to the centre frequency. The leading uniform-support difference then depends on curvature and support variance, which may be too small to matter. Partial amplitude/support can create a first-moment displacement. Sparse pilot intervals, normalization and conditioning mean that an arithmetic occupancy fraction is not automatically an estimator weight, as 118 explicitly cautions.

**Cheap falsification:** before any recording replay, use the actual estimator on bounded synthetic chirps with fixed full and asymmetric pilot support, and compare its conditional CFO with the known centre frequency and analytically computed support moments. Preserve every admission failure. Reverse the chirp sign and support orientation to separate bin rounding from an effective-time effect. A fixed grid of chirp/curvature values must be set from a declared physical scale before results, not selected from position errors. If deviations are only bin rounding already addressed by 125/127, or a rigorous maximum time/moment correction is negligible, stop.

Only a verified estimator influence rule could justify changing the predicted frequency from a point value to a support-weighted value. Public support metadata already exist; no new RF is needed. A useful correction would be a few support moments and orbit derivatives, with no new per-satellite free parameter. It would still need matched c arms and unaltered observation admission. Without an adequate influence rule, adding an arbitrary per-window time offset would merely let calibration absorb Doppler and is rejected.

## Priority

Finish the frozen discovery pilot first. Of these two ideas, start with the small synthetic marginalization identity test; it asks a distinct identifiability question without new RF or a larger fitted mean model. The chirp/support test is a bounded check of an explicitly unresolved measurement approximation, with a strong stop condition if the scale is negligible. Neither warrants a new recording optimization or parameter sweep yet. Any later comparison must preserve full membership, use one global rule, report typical and tail errors separately, and keep closed validation data closed.
