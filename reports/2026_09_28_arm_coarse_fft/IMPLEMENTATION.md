# Implementation revisions

## V4: fair qualified baseline

V4 established the stable benchmark contract. The direct path uses the
qualified tap-major, three-vector NEON kernel with two reciprocal-square-root
refinements and scoped prefetch suppression. Both paths accumulate 12-float
epoch-major grids in symbol order. The deterministic fixture is centered at
zero, and zero, impulse, maximum normalized error, and normalized RMS checks
run before success. Process CPU medians exclude template packing, cached
kernel spectra, and planning. The FFT path computes 132 exposed filters while
the direct kernel also executes its known-zero twelfth padding lane.

## V5: explicit spectral multiply

V5 changes only the FFT-domain complex product on ARM. Four bins are loaded
with `vld2q_f32`, multiplied with four vector multiplies plus one add and one
subtract, and stored with `vst2q_f32`. This removed compiler-dependent C99
complex multiplication overhead. All inputs, outputs, correctness limits, and
timing boundaries remain those of V4.

## V6: measured FFT plans

V6 changes only forward and inverse plan creation from `FFTW_ESTIMATE` to
`FFTW_MEASURE`. Plan creation and cached kernel transforms remain one-time
setup reported separately from timed execution. Production code is unchanged;
full integration is intentionally deferred pending the ARM result and later
real-grid/candidate qualification.

ARM V6 completed with passing numerical smoke checks but substantially worse
execution times than V5 at every tested tap length. Reject its planner change.
V5 remains the selected standalone candidate; it is not yet a qualified full
GLRT implementation.

Receipted source snapshots for all three ARM revisions and the V6 sanitizer
build are under `builds/`. The archived build commands refer to the original
`/var/tmp` build paths and the receipts contain the exact source and binary
hashes produced there.
