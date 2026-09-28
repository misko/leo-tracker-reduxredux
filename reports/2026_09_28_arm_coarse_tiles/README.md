# Four-epoch ARM coarse tile

This report-local experiment evaluates four adjacent coarse epochs together
while preserving every hypothesis. For each of three four-CFO blocks, NEON
lanes hold epochs and the tap loop retains the existing multiply/add grouping
for each epoch/CFO hypothesis. Scalar denominator calculation, support counts,
frame/symbol accumulation order, scalar tails, and sparse-cell refinement are
unchanged. Non-unit epoch strides retain the original scalar path.

Host qualification passes. The pure kernel is bit exact against the prior
kernel for tap counts 1, 2, 3, 4, 11, 17, 22, 33, 44, and 45, including four
zero-energy lanes. A separate full-grid harness compares the original and
tiled presence implementations at all four rates using full 20 ms inputs,
partial tails of `2*n+17` samples, and zero IQ; every grid byte matches. The
metadata-balanced saved-IQ cohort also retains 1,669/1,669 positive candidates
with no ordered-field errors across 1,408 windows.

ARM builds use the FP64 FFTW backend. Completed hardware unit tests, matched
probe timings, build receipts, and executed sources are under `arm-results/`.
The tile variants are not selected; the unchanged coarse kernel with a scoped
compiler option is the preferred result.
# Measured decision

The four-epoch tiles are correct on the tested cases but slower on ARM.
Four-CFO tiles measured 2,953.03 ms/window with default flags and 2,971.95 ms
with prefetch disabled. A two-CFO tile reduced register spills but still took
2,260.68 ms/window. All three retained exactly the baseline coarse grids and
candidate objects on the four matched 2.5 MS/s probes, three repetitions each.

The best measured approach retains the original kernel and disables compiler
prefetching only around that kernel: **1,681.06 ms/window**. See
`PERFORMANCE_REPORT.md` for qualification and full-dwell results. ARM evidence
and source snapshots are under `arm-results/`. This decision supersedes the
implementation-stage notes below.
