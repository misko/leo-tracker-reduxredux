# Extraction review and raw-axis positive control

The previous residual-level test does not establish whether the original
template-relative sign axis is binary. Its per-carrier centering/scaling and
uniform mixture weights can obscure unequal binary populations when carriers
are pooled. This follow-up retains the original axis and fits an unequal-weight
two-level model, with the full-bandwidth public soft estimates as a positive
control.

## Extraction/indexing review

The existing `native_rate_decode.py` first demodulates 301 symbols. Its first
row is SSS; returning `frames[:, 1:]` makes output row 0 physical OFDM symbol 2.
Therefore rows 2 and 4 in the DS10 cache are physical symbols 4 and 6, as used
in the analyses. Template multiplication uses the corresponding `template[:, 1:]`
slice. The public full-frame cache includes SSS, so its matching rows are 3 and 5.

The decoder fits per-frame frequency/phase from known pilots, estimates timing
drift from pilot slopes, and estimates the SSS channel on separately reserved
frames. It does not use candidate data signs to choose those fits. However, pilot
slope/clock fitting uses pilot observations throughout the excerpt: our later
header splits are held out from subsequent data-model fitting, not from all
synchronization operations. The cached values are calibrated soft estimates,
not independently validated message bits.

## Test

For each receiver and OFDM symbol separately, retain all 28 common nonpilot
carriers. Apply one scalar mean/standard-deviation normalization to the complete
discovery population, preserving carrier-specific occupancy differences. Fit a
two-Gaussian mixture with free midpoint, spacing, mixture weight and common noise
variance. Compare held-out likelihood against a single Gaussian fitted on the
same discovery population. Six fixed starting points are tried; discovery
likelihood selects the converged fit. No test data select parameters.

DS10 uses the established chronological split. The public soft reference uses
frames 0–5 for discovery and 6–12 for evaluation, on exactly the same native FFT
bins, with the published template rotation removed. This public cache is an
existing published soft estimate, not a new independent raw demodulation or
ground-truth packet. It nevertheless supplies a useful positive control for
visible binary amplitude structure in the same coordinate convention.

## Results

Mean held-out log likelihood advantage over a Gaussian, natural-log units per
scalar sample:

| Source | Symbol | RX0 | RX1 |
|---|---:|---:|---:|
| DS10 v1085 | 4 | +0.0036 | +0.0065 |
| DS10 v1085 | 6 | −0.0037 | +0.0257 |
| DS10 v1150 | 4 | −0.0005 | +0.0018 |
| DS10 v1150 | 6 | −0.0015 | −0.0109 |
| DS10 v1162 | 4 | +0.0073 | +0.0098 |
| DS10 v1162 | 6 | −0.0016 | +0.00002 |
| Public soft reference | 4 | +0.8153 | — |
| Public soft reference | 6 | +0.9534 | — |

The public fits recover level centers near −1/+1: −1.006/+0.986 for symbol 4
and −0.977/+0.951 for symbol 6. DS10's advantage is weak or negative, and some
fits use both means on one side of zero, approximating a skewed distribution
rather than finding a balanced sign constellation. Mixture fitting alone cannot
be treated as a successful symbol decode.

This corrects a possible overinterpretation of `AMPLITUDE_LEVELS.md`: rejection
of its centered, uniform-level models was not evidence that the transmitter's
raw sign alphabet is continuous. The public reference clearly supports binary
structure here; DS10 provides much weaker statistical separation. Noise,
calibration and propagation differences remain possible explanations. This test
does not prove the format is unchanged between acquisitions or identify a field.

## Consequence and artifacts

Keep DS10's early values as uncertain soft observations. Do not infer an extra
amplitude-coded bit per carrier from the residual correlations. Better symbol
reliability or a validated coding/interleaving relation is still needed before
interpreting message bytes. The satellite candidate alone does not supply it.

`raw_axis_levels.py` writes ignored `local/within-visit/raw-axis-levels.json`,
including every source hash, exact bins, all fitted means/noise/weights,
convergence counts and per-frame likelihood differences. Its synthetic test
confirms recovery of a deliberately unequal binary population on held-out data.
The test and Ruff pass. No new RF, manifest edits, commits or publication occurred.
