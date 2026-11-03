# Independent Student-t CFO integral is numerically feasible on sampled tracks

All24 predetermined training-MAP cases pass the numerical feasibility gate.
The run completes in3.067seconds; adaptive quadrature at1e-8 and1e-10 agrees
to reported floating precision (maximum log discrepancy0). The normalized
marginal log likelihood differs from the profiled score by-11.126 to-9.919nats.
These absolute corrections include track-length and prior-normalization terms;
their variation across tracks is not evidence of changed satellite rankings
or a position improvement.

The integral retains independent Student-t4/100Hz errors and the baseline's
1MHz Gaussian CFO prior. It integrates over real CFO, including the Gaussian
normalizer that the profiled optimization omits as a constant. Integration
intervals split at every residual center and its flanks to expose separated
offset modes. It does not replace independent errors with a shared scale, use
frequency contrasts, or impose a shared receiver offset. Existing experiments
with those models do not directly test this likelihood.

The first12 lexicographically ordered eligible tracks in each of scans0 and16
are used at their original training-selected IID endpoints. Only the highest
training-scoring visible candidate is examined here. No held residual, new
position optimization, geographic reference, IQ or orbit update is used.
No claims of full-candidate or position-space numerical coverage follow.

Two tests pass: a coincident-observation analytic broad-prior limit, and a
separated-mode example evaluated from opposite integration anchors. Source
bindings rehash successfully. No integration warning occurs. Adaptive error
estimates and tolerance agreement are numerical checks, not independent proof
against every possible integrand pathology.

The next useful audit is within-track sensitivity across candidate hypotheses
and nearby positions, followed by a derivative check. A complete model must
integrate every retained candidate and use the joint/training integral ratio
for conditional held prediction. Reusing the training-best offset in the
joint likelihood would not be this marginalized predictive distribution.
No DS11 estimator is promoted by this feasibility result.
