# Causal receiver response baseline

Evaluate a normalized four-category predictor with exponentially decaying past category counts and 20 fixed background pseudo-observations. At each observation, decay counts by the actual elapsed seconds, predict and score the current category, then add it. Empty outcomes are observed categories; observation gaps only decay history. Keep reception history across the later-period boundary.

Choose decay time from 1, 10, 30 and 100 seconds using equal-record mean reception score on the original other-five calibration records. Use each fold's original training-only background. The omitted record and every later category are excluded from this choice. Evaluate all six omitted records and compare full later log densities with saved P/U/O models, training background and the preceding frozen local categorical model. All models score before updating; this predictor uses no geometry, frequencies, candidate identity or margins.

Report every training grid, chosen time, per-window predictions and equal-record later contrasts. Regard it as a useful stronger response control only if it beats P on average and at least four of six records. This development criterion does not establish geographic accuracy or satellite identity. No confirmation panel, RF or raw IQ is read. Execution cap 60 seconds; no optimization or grid expansion after outcomes.
