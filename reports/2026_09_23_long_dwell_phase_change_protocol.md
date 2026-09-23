# Frozen protocol: 105915 long-dwell phase-change diagnostic

**Frozen before evaluation.** This reuses the corrected upper-edge 20 ms phase
artifact for `cap-20260825T105915-2770b84587cc`, stream 0, RX0/RX1. It does not
read additional IQ and does not assert satellite identity or geometry.

Select 16 window rows at fixed evenly spaced indices over the full 704-row
interval, without consulting qualification or phase. Assign eight whole windows
to training and eight to held using NumPy RNG seed 20260923. Preserve failed
windows as abstentions. Fit one global circular intercept and phase rate on
qualified training windows. Do not fit per-window phase or rate. Compare held
circular absolute error with (a) a train-only constant-phase model and (b) a
frozen random permutation of held times. Report coverage and every selected row.

This tests repeatability of the restored model-coordinate double difference.
The extraction independently fits residual carrier rotation for each source and
receiver inside each 20 ms window, then restores the frozen carrier-model phase
at the common center. A predictive rate is therefore conditional on those
models; it is not an independently measured physical phase rate. The unknown
0.10--0.30 m baseline cannot be fitted to motion without an authoritative source
association. No geometric or positioning gate is defined.

