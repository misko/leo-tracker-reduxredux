# Independent receiver-shift witness audit

Scope: DS24-0017 and DS24-0095, baseline versus frozen RF-scaled RX1 50 Hz addition, both `c0` and `fitted_c`. This audit does not refit positions, inspect GPS for methodological decisions, change source outside this directory, or collect RF.

The scientific distinction is between (1) held-family predictive support for an independently trained position/correction, conditional on inherited full-RF graph selection; and (2) descriptive full-data loss-path/receiver/phase tradeoffs. Neither is independent end-to-end validation of association, noise selection, or accuracy at unseen sites.

## Required implementation checks

- Whole-family folds bind every receiver/channel owner. Train and held likelihood IDs are disjoint; all original predictive factors are removed from curved training, and held predictive factors are not used by train position search.
- Train positions, phase refresh, coefficient moments and Gamma precisions use training likelihoods only. Held phase reference uses the causal prior mean, never the full-data or held-fitted phase.
- Baseline/RX1 and c arms retain identical folds, observations, inherited associations, powers, physical priors, bounds and cold search budgets.
- Held score retains the complete shared training posterior covariance and untouched held-only phase, orbit and fragment-constant priors. Any Gaussian moment approximation to Student phase or Gamma noise must be named; its normalized Gaussian score is exact only under that reference model.
- Retain all Gaussian quadratic, covariance-volume and normalization terms. A dense small-matrix oracle must agree with the low-rank score; testing must exercise cross-family target covariance and prior-only local coordinates.
- Unknown target timing is linearized at its prior reference unless an explicit nonlinear integral is used. A local tangent score is not the original nonlinear model density.
- Separately report predictive mean error and density. Added uncertainty can improve density while worsening prediction. Keep original negative-control context and two-case selection limitations explicit.
- Full-data conditional paths retain normalized objectives and loss decomposition; Gamma-fixed local curvature and information-removal diagnostics are described as local approximations.
- Bind source, baseline, adapter and input hashes, test membership, fold assignments, train endpoints and score results. Independently recompute aggregates from saved primitive results and verify every expected model/case/arm/fold combination.

No publication occurs before the parent report is complete and the parent requests publication. The publisher checkout is separate from the dirty working repository.
