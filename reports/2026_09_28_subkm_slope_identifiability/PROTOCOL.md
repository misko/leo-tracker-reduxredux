# Position/timing/slope local identifiability

Use the eight chronological DS7 records already exposed in the slope shadows,
without choosing records by gain. At the frozen full88 position/timing and each
record's training-selected ±20 slope, evaluate the actual full-mixture profiled
training likelihood in four coordinates: east km, north km, timing s and native
slope Hz/s. No held values or geographic reference errors select an analysis.

Compute observed negative Hessians by central differences of the envelope
gradient, with steps (0.01 km, 0.01 km, 0.001 s, 0.001 Hz/s), then half steps.
Prediction derivatives use (1e-4 km, 1e-4 km, 1e-5 s). Check score gradients
independently with central score differences at the main steps. Record visibility
changes, timing-knot crossings, symmetry and step sensitivity; retain failures.
Matrix comparisons use relative Frobenius difference, and >1% is a warning.
These points are not per-record joint optima: retain gradient vectors and do not
interpret inverse observed Hessians as calibrated location uncertainty.

Also compute optimistic complete-label expected Fisher information using the
Student-t(4,100 Hz) location coefficient 5/(7*10000), training responsibilities
and candidate-specific constant-offset profiling. This ignores missing-label
information. Compare position Schur complements with timing free/slope fixed
versus timing and slope both free, at the same expansion point. Report generalized
information-retention eigenvalues and worst-direction conditional standard-error
inflation only for positive blocks. Do not add a spatial penalty or tune a slope
prior. The inherited geographic center is a coordinate origin here.

A local matrix is a diagnostic, not an accuracy or global-identification result.
Substantial information loss motivates a constrained nuisance or different
observable before broader fitting; optimistic positive curvature alone cannot
promote a model. DS8/DS9 and geographic scoring remain subsequent stages.

Bind sources and original shadows before launch. Eight sequential records, each
at most 120 seconds and 4 GiB, one numerical thread, nice19; no retries, IQ,
orbit propagation, RF or source-store writes. Preserve all terminal receipts.
