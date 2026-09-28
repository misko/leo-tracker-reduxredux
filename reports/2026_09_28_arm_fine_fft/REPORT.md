# Guarded FP32 fine-FFT experiment

The corrected guarded screen passes the bounded host scientific qualification.
The exact FP64 FFTW backend remains the preferred first optimization because it
has no approximation guard and already provides a large ARM speedup.

The report-local kernel screens the unchanged fine-acquisition bins with an
FP32 FFTW transform. It recomputes every bin within
`256 * FLT_EPSILON * max(1, screen_max)` and its interpolation neighbors using
FP64 sparse direct transforms. More than 64 verification bins triggers the
original FP64 FFT. The guard is empirical rather than a formal error bound.
All frames, windows, candidates, and final FP64 GLRT evaluations remain.

The metadata-balanced 64-dwell host cohort covered 1,408 windows and all four
sample rates. It recovered all 1,669 original positive candidates with zero
strict ordered-field errors. Against the qualified full-search binary, maximum
differences were 4.60e-9 Hz for acquired/tracking CFO, 7.53e-14 for exact
score, 6.82e-15 for control score, and 7.08e-14 for margin; epochs were exact.

An earlier verifier incorrectly accumulated frame energy only where the exact
template was nonzero. The original fine stage includes every sample in each
selected symbol even when its template cell is zero. A component test now
constructs exactly that geometry and rejects the old score of one. The prior
buggy build and rows remain explicitly labeled under `results/` rather than
being overwritten or presented as screen error.

Host mean fine-stage CPU per window was 3.48, 6.19, 10.68, and 13.93 ms at
2.5, 5, 7.5, and 10 MS/s. These are host diagnostics, not ARM timing. A static
ARM binary and component test were built successfully but not executed. No
hardware or RF was accessed by this experiment.

The remaining scientific risk is a true FP64 winner falling outside the
empirical FP32 guard on an unseen input. The exact double-precision FFTW backend
removes that risk and should be selected unless a measured ARM comparison shows
that this guarded screen offers a material additional gain. Saved-IQ rows,
source/build receipts, and hashes are retained under `results/`.
# ARM timing decision

The corrected screen was measured on four 2.5 MS/s probe-zero windows,
three repetitions per window. Mean CPU time was **2,121.53 ms/window**;
last-repetition mean fine-stage time was **284.16 ms**. All comparable
downstream scientific fields met the frozen oracle tolerance. Raw strict
audit failures are limited to the inherited FP32 coarse scores and grid.
The raw failed audit receipt is retained in `results/screen-arm-b/`.

The independently measured FP64 FFTW implementation takes approximately
**1,996 ms/window**, with **175 ms** in the fine stage, and has stronger
704-dwell qualification. The guarded screen is therefore **not selected**:
it adds an empirical guard and is slower on the target. See `FFTW_REPORT.md`
for the chosen path and full-dwell ARM measurements.
