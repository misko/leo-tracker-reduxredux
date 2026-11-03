# Recover original-objective basins from causal orbit fits

Use every qualified endpoint of joint_orbit_position on scans 0 and 16,
including zero, orbit and linear arms. Reuse the frozen drift_basin_recovery
deduplication (1m EN and 1ms timing), original IID fitter, qualification,
receipts and training-only selection logic. The original qualified endpoint
remains eligible; replace only for original training score gain >1e-6 nats.
Seal before computing reference errors. No geographic seed selection.

Each unique initializer receives one 90-second fit, at most three single-thread
workers, without retries. Keep all original measurements, masks, candidate
banks, independent Student-t4/100Hz likelihood, bounds and timing treatment.
Source priors and older orbit states affect initialization only. No observation
pooling or later orbit data. This diagnostic closes this particular set of
alternative basins if no improvement is found; it does not prove global
optimality. Report any training-score improvement even if geographic error rises.
