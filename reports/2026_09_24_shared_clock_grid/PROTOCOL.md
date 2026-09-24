# Frozen shared receive-clock sensitivity on the local grid

The export records a roughly millisecond host bracket around a device counter,
but it does not provide a calibrated bound on absolute RF sample epoch or buffer
age. Therefore this is a sensitivity experiment, not a calibrated clock prior. The existing
state caches provide at least 5.007 seconds of margin after every eligible
observation and 5.015 seconds before every observation across the twelve frozen
TRAIN scans. Freeze a symmetric shared receive-time shift range of -5 to +5
seconds from cache support alone.

Use the 165 geographic points sealed in
`reports/2026_09_24_local_cone_grid/inference.json`; perform no new geographic
proposal or refinement. At each point fit one scalar tau shared across every
track, candidate, receiver, and all twelve scans. Evaluate tau on the integer
grid -5,-4,...,+5 seconds, then evaluate 0.25-second steps within +/-1 second of
the training-best integer value, clipped to [-5,+5]. Deterministic ties prefer
the smallest absolute tau and then the smaller signed tau. This coarse-to-fine tau grid is a sensitivity discretization,
not an uncertainty distribution.

For each tau, query the original cached satellite ECEF position and velocity at
recorded receive time plus tau. Recompute Earth-fixed receiver-to-satellite
geometry and Doppler at that shifted UTC. Do not apply an orbital phase offset,
learned orbit correction, scan-specific shift, or satellite-specific shift.
Use the original causal catalogue snapshots and candidate policy unchanged.

For every track and tau, fit one constant CFO from randomized TRAIN rows and
select the ordinary visible candidate with minimum TRAIN RMS. Minimize the same
occupied-second weighted all-track capped squared-RMS cost at 800 Hz over one
global tau. Only after tau and candidate IDs freeze, evaluate held rows using
the training-fitted CFO. Primary comparison is tau=0 ordinary baseline versus
the fitted shared-clock ordinary baseline. Cone arms are omitted to keep the
full 165-point run below 20 minutes.

Before launch benchmark the two frozen region centers and their midpoint using
the full tau procedure serially, then project four-worker wall time with one BLAS thread each. Verify
tau=0 parity with the sealed local-grid baseline, cache bounds, candidate cohort,
and held-value isolation. Hard fail if projected wall time exceeds 20 minutes.

Write complete TRAIN-only inference and seal it before any reference-coordinate
evaluation. Report boundary hits as evidence that the chosen sensitivity range
does not identify an interior clock shift, not as a clock estimate. Use no
truth, VAL/TEST, future orbital elements, new RF, QNAP write, or deployment.
