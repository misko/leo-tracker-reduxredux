# Root source and mathematics review

Preparation only; no tests or model calls have run. Iteration 151 continues to
occupy both numerical worker slots.

The smooth-clock precision and ±2000 coefficient bounds agree with
`hard60_dynamic_rf.py`. `SatelliteCorrection` preserves the smooth block and
`SlopePrior` changes a separate satellite-slope block. The mixture Hessian's
negative responsibility-covariance term and normalized-prior determinant ratio
are consistent with differentiating the displayed likelihood.

One correction was required: constant design gives an exact profiling/integration
no-op only for the unbounded Gaussian integral. A finite box contributes minus
the log posterior mass inside the box, which can vary even with an interior mode
and unchanged design/domain. PLAN now distinguishes that effect, and a source-only
synthetic counterexample was added. It has not been executed. A conditional slice
must still not be renormalized by its varying prior mass.

Before recording work, an adapter must match the actual wrapped likelihood,
component weights, all fixed penalties, and exact bounds. The finite-mixture
helper alone does not establish production likelihood parity. Quadrature and
mode-search coverage still require a frozen, bounded protocol. No inference or
accuracy benefit is established by this review.

The current receiver-indicator design supplies a further simplification: with
other parameters fixed, these two amplitudes belong to disjoint observation
sets and have independent priors and interval bounds. The conditional integral
factorizes exactly into two bounded one-dimensional integrals. PLAN records this
so a future oracle does not pay for unnecessary two-dimensional quadrature.
This is conditional separation, not independence of jointly inferred receiver
clocks and position. It has not yet been checked numerically.
