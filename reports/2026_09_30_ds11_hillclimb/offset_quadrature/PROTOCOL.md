# Full-retained-candidate quadrature benchmark

Evaluate every retained candidate of every eligible track in original scans0
and16 at the original IID endpoint, using training observations only. Include
currently invisible candidates in numerical convergence statistics, retaining
the original visibility mask in the final mixtures. No candidate pruning.

Vectorize Gauss-Legendre quadrature separately between residual centers/flanks;
map each infinite tail with u/(1-u), u in(0,1). Compare32 and64 nodes per
interval for candidate log integrals and posterior-expected gradients. Reuse
the baseline CFO profiler only as a quadrature anchor, not as a substitute for
the integral. Compare the24 previously frozen leading candidates against
their adaptive scalar/vector values and gradients.

Require every candidate finite, maximum candidate value difference<1e-6,
maximum candidate gradient difference<1e-3, and adaptive-oracle value/gradient
differences below those same limits. Report full-mixture training score and
gradient at the original point, but do not optimize or score geographic error.
Record complete per-order timings and all failures. A numerical failure stops
this implementation before fitting; do not silently discard weak candidates.
One thread and90second process cap. No held observations, IQ or orbit updates.
