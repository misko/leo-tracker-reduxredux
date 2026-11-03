# Drift-derived starts do not improve the unchanged IID solution

All28 deduplicated starts complete,27 qualify, and none improves the original
training score by the frozen1e-6-nat replacement threshold. All eight original
positions remain selected. Median reference error stays3,108.162m exactly.
This closes this particular optimizer-recovery path; it is not proof that the
original objective has a global optimum at every selected endpoint.

Seeds comprise every qualified endpoint of the prior three-allocation drift
experiment, deduplicated within each scan at1m EN and1ms timing in original job
order. No geographic error enters seed or final endpoint selection. Every fit
restores the original uncorrected measurements, causal banks, likelihood,
timestamps and masks. The existing original qualified endpoint remains eligible
and cannot be replaced by a worse training solution.

The distinct basins exposed by the corrected models therefore do not yield a
better uncorrected solution under this bounded search. This result does not
advance the drift correction that failed its geographic gate, nor justify
additional starts along the same path. It also does not show that more flexible
measurement models or different independent evidence cannot improve positions.

Two component tests pass for spatial/time deduplication, scan separation,
qualification filtering and independence from geographic error. Source bindings,
seed provenance, all28 process receipts, endpoint qualification and the sealed
training-only replacement decisions verify. All worker processes exit0 with no
timeouts or retries; one optimizer endpoint is unqualified. No independent
optimizer rerun is claimed. The final selections were sealed before geographic
scoring; every retained coordinate and reference error equals the original.

Plan SHA256: `66affa155d7692925fe0f7344ee7e4c395396fc7a5bab3ca220511002221a4dd`.
No new IQ, RF collection, orbit update or cross-scan position pooling.
