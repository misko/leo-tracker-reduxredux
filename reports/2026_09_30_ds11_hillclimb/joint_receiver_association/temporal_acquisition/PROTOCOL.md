# Calibration-only persistence screen after posterior diagnosis

The exact posterior diagnostic finds 40 original identities losing majority
probability in either receiver model, including 24 with original Doppler
confidence ≥0.99. This does not prove wrong labels, but motivates testing
whether repeated receiver states provide less independent information than
the current likelihood assumes.

For each of the six validated acquisition families, keep the newly rebuilt
independent receiver/elevation/signed coefficients fixed. Fit only one common
refresh timescale on receiver-only training rows of calibration donors. Use
the existing normalized transition rho*I+(1-rho)*p(t), rho=exp(-dt/tau).
With constant receiver-only p per source/RF, unobserved rows can be integrated
exactly, giving a closed-form transition likelihood over training observations.
Bounds tau=[0.01,60] seconds, Gaussian prior SD3 on log(tau), scalar bounded
optimization. Require projected gradient ≤0.001 and finite-difference gradient
discrepancy ≤0.00001. No beam-coefficient refit, target-error tuning or arbitrary
receiver evidence weight is allowed in this screen.

Validate the fixed-coefficient temporal likelihood on held visits of separate
validation donors, conditional on their training states. Compare receiver-only,
elevation, signed, swapped-RX and deterministic same-RF permutation controls.
Report the existing independent held scores as a timing-model comparison.
Passing requires qualified tau, signed beating all four controls, and a strict
majority of source-group wins against receiver-only. Count only source groups
with at least one held known nonempty detection. Preserve every failed family;
the two unvalidated 2.5MS/s settings remain explicitly unsupported.

This is a constrained persistence diagnostic using independently fitted
emissions, not full joint parameter estimation and not evidence of improved
DS11 position. Validate the closed form against the normalized forward filter
with missing rows before fitting. Each family child ≤90 seconds, at most three
single-thread workers. No new RF or modification of prior results.
