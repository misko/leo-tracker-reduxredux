# Independent-error CFO marginalization: two-scan geographic gate fails

The full retained-candidate marginal likelihood produces qualified estimates
on both pilot scans, but geographic changes are small and mixed. The frozen
requirement to improve both scans fails; this version does not advance to a
wider screen or replace the profiled IID default.

| Original scan | Profiled IID error m | Marginal CFO error m | Change m |
|---|---:|---:|---:|
|0|765.072|762.928|-2.145|
|16|2153.140|2167.100|+13.960|

Every retained candidate is integrated under independent Student-t4/100Hz
errors and the normalized1MHz Gaussian CFO prior. The model preserves the
original observations, masks, times, visibility rules, causal orbit banks and
search bounds. Order32 quadrature drives optimization, with order64 checks at
every final endpoint. No source/candidate pruning or receiver drift correction
is introduced.

All eight starts qualify, with no retries or timeouts. The maximum process wall
time is49.15seconds under a90second cap. Endpoint32/64-order score differences
are at most1.82e-12nats and gradient differences at most5.10e-11 per optimizer
coordinate. Finite-difference endpoint qualification also passes. Both
training-score selections were sealed before either reference error was scored.
Profile and marginal objective values were not compared for model selection.

Two component tests pass for the full-mixture gradient, held-observation
isolation, candidate permutation and quadrature-order agreement. Independent
verification rehashes sources, checks all process receipts and qualification
rules, reproduces training-only selection and recomputes geographic errors.
It does not independently rerun optimization. No held predictive score is
claimed: that requires joint/training CFO integrals rather than a fitted
training CFO.

The result narrows the error diagnosis: replacing profiling with integration
has only a small geographic effect in these two exposed recordings. It does
not prove profiling is harmless everywhere or establish an orbit-error floor.
The numerical implementation remains a useful research comparator, not a
demonstrated accuracy improvement. No new IQ, RF collection, orbit update or
cross-scan pooling occurred.

Plan SHA256: `05ab5b5ebbe85202582e65a7b1b7bdc2b8a8d844ea0e0be14f3c95bbabe1a9f4`.
