# CFO marginalization has small within-track position effects in this sample

All24 fixed cases pass the numerical sensitivity gate in7.33seconds. Scalar
and vector quadrature log values agree within1.14e-13nats, and the posterior-
expected gradient agrees with centered finite differences within2.81e-7 per
optimizer coordinate. Two component tests pass for expected-score derivatives
and a constant prediction direction. Source bindings and summaries verify.

For the original training-MAP candidate, +/-100m EN perturbations change the
correction to the profiled likelihood by at most0.01538nats. The median of each
track's maximum absolute change is0.00527nats. These within-track differences
remove track-length constants and establish that the correction is not wholly
constant in position. They do not quantify a total position displacement or
demonstrate improved accuracy.

Comparing each track's two best visible candidates under the original profile,
the candidate log-likelihood gap changes by at most1.7952nats. None of the24
pairs reverses order. Other candidates are not integrated by this diagnostic,
so this is not a full-mixture association or catalogue-completeness test.

The derivative is the posterior expectation, over the unknown constant CFO,
of the independent Student-t observation score times the predicted Doppler
Jacobian. It includes CFO uncertainty without selecting a single fitted offset
as exact. Geometry derivatives and scalar integral differences use1e-4km EN
and1e-5seconds timing steps. No position reference, held measurements, new IQ,
orbit update or optimizer fit enters the audit.

The numerical result supports implementing a full-candidate evaluation, but
the small sampled position dependence lowers expectations for a large gain.
Before a bounded fit, benchmark an accurate full-mixture integral and gradient;
do not drop candidates merely because they were weak at one endpoint. Any
accelerated quadrature needs comparison against these adaptive scalar/vector
oracles and convergence checks across the retained candidate population.
No new estimator is promoted by this audit.
