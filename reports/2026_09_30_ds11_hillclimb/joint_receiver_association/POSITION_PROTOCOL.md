# Conditional joint-position pilot

The signed conditional receiver screen passed its frozen donor transfer gate.
Freeze this next pilot before fitting positions. Use original causal candidate
banks and the already prepared DS11 scans 0 and 16. No orbit corrections, height
fit, reference-based tuning or new data. Retain same-RF simultaneous-training
edges, exact partial matching, catalogue identity mixtures and observation
ownership alternatives from the Doppler pilot. Keep the original per-track CFO
profile and uniform normalized matching prior.

Add the frozen donor-0 conditional receiver-state likelihood once per source
window in each single/pair hypothesis. A pair uses the union of its retained
windows; shared windows have state both. Receiver support must be observed in
both views. Evaluate LOS at the original observation time, using the first
track deterministically for shared windows. Candidate states interpolate the
original timing bank exactly. The three-state factor is conditional on source
detection: full-scan absence, clutter, temporal lifetime and other-catalogue
objects remain outside this pilot. It is a conditional association objective,
not a completed generative discovery model. Fragmented tracks remain a limit.

Fit Doppler-only, receiver-only and signed geometry separately on training
visits; signed receiver-swap and seeded candidate-row permutation are controls.
First verify zero-receiver parity against the existing Doppler pilot and check
analytic mixture/matching gradients against full-objective finite differences.
Use each original IID endpoint as the single initial seed, bounded EN +/-12 km
and timing +/-5 s, L-BFGS-B maxiter 100, ftol 1e-12, gtol 1e-5. Each child gets
90 seconds. A single-start result is local pilot evidence only. A fit qualifies
only with successful convergence, interior margin >=.001, max gradient <=.01
and derivative discrepancy <=.02. Seal all fits before geographic scoring.

Report training, held conditional score, expected matched pairs and physical
identity uncertainty. Evaluate reference position only after training selection.
Require signed geometry to lower error on both pilots relative to both original
IID and new Doppler-only fits, and improve median over receiver-only; otherwise
do not promote or broaden. Fixed-position swap/permutation checks are diagnostic
when controls fail optimization. Run broader confirmation only after a passing
qualified pilot. Preserve timeouts and failed fits.
