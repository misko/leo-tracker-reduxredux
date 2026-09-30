# Neighboring known symbols do not explain the lower-edge residual

A held-symbol test of local known-pattern mixtures leaves the DS9-middle
lower-edge residual largely intact. Restoring the physical source/target phase
relationships reduces its correlation modestly, from 0.246 to 0.237. This does
not establish extra message bits: it eliminates only the tested small, linear,
frame-local mixtures as a sufficient explanation.

## Model and validation

Use the same hash-verified expanded atlas inputs and known-state labels as
[the scalar residual assay](STATE_RESIDUALS.md): S23 has 42 qualified frames,
DS9-middle has 45, with 28 shared nonpilot carriers. States are selected at
symbols 194–225. Fit complex least-squares coefficients independently for each
receiver and frame, using only symbols 226–257; evaluate at symbols 258–289.
The latter has 896 complex observations per frame and receiver.

Four models are reported, without selecting a winner and claiming a new blind
validation:

- One scalar gain multiplying the known pattern, reproducing the preceding assay.
- Five compact-carrier shifts of that pattern, offsets −2 through +2.
- Fifteen combinations of compact-carrier offsets −2 through +2 and symbol-time
  offsets −1 through +1, in the template-removed representation.
- Fifteen physical carrier/time neighbors with their source/target phase-template
  ratios restored. Physical neighbors can include known pilots; their pilot
  sequence replaces the data-pattern prediction. SSS is supplied at symbol 1
  where needed for early-region extrapolation. No frame wrapping is performed;
  out-of-frame source symbols are zero and do not enter the fitted or held late
  windows. Physical neighbors use native FFT bins, not compact indices.

The physical model matters because cached symbols have already been multiplied
by a conjugated reference template. Simple shifts of those cached predictions
would omit deterministic phase differences associated with physical leakage.
All coefficients are shared over the 28 target carriers within a frame; this is
not an exhaustive frequency-dependent channel or nonlinear-distortion model.
Predicted neighbors outside the measured slice are hypotheses from the known
pattern, not newly observed carriers.

Rank is recorded for every fit. The fifteen template-removed features have
rank 12–15 in S23 and rank 15 in DS9-middle. The physical features have rank 15
throughout both visits. Least squares uses a relative singular-value cutoff of
1e-6; no ridge parameter or other hyperparameter is tuned on validation.

Residual correlation centers each coordinate across frames before aggregation.
Controls cyclically mismatch RX1 frames but retain the target frame's feature
matrix with the mismatched frame's fitted coefficients. Thus the controls retain
correlation that a shared wrong subtraction could manufacture.

## Held-window results

| Visit | Model | Residual correlation | Maximum mismatch control | Energy removed RX0 / RX1 |
|---|---|---:|---:|---:|
| S23 | Scalar | 0.0068 | 0.0085 | 37.88% / 30.29% |
| S23 | Five compact neighbors | 0.0068 | 0.0076 | 37.54% / 30.03% |
| S23 | Fifteen compact/time neighbors | 0.0068 | 0.0082 | 36.91% / 29.23% |
| S23 | Fifteen physical neighbors | −0.0116 | 0.0074 | 38.90% / 30.52% |
| DS9-middle | Scalar | 0.2463 | 0.0059 | 40.04% / 38.95% |
| DS9-middle | Five compact neighbors | 0.2463 | 0.0062 | 39.81% / 38.65% |
| DS9-middle | Fifteen compact/time neighbors | 0.2458 | 0.0053 | 39.20% / 37.95% |
| DS9-middle | Fifteen physical neighbors | 0.2365 | 0.0051 | 40.34% / 39.04% |

The physical model offers a small held-energy improvement. Most lower-edge
shared residual persists. The upper residual remains near zero; its small
negative value is not a new anti-correlated message or a demonstrated zero-noise
floor. These are descriptive results from two previously studied visits, with
shared calibration and dependent frames, not population-wide significance tests.

## What remains unresolved

Neither a new bit alphabet nor an independent field boundary follows from these
correlations. Remaining candidates include an unmodeled deterministic component,
time-varying channel effects, residual calibration structure, and additional
transmitted modulation. The next useful distinction is whether the residual
occupies a stable constellation or predictable quadrature component and whether
that structure survives in another lower-edge visit. Satellite identity does not
disambiguate those alternatives in this two-visit experiment.

`neighbor_model.py` saves all coefficients, residual arrays, ranks, input/method
hashes, and region summaries in ignored `local/neighbor-model/`. Early-region
summaries are exploratory extrapolations, not a valid early-header subtraction
model. Four synthetic tests cover mixture transfer without early-region leakage,
rank deficiency, restoration of the center prediction, and adjacent-pilot phase.
All 25 tests in the research folder pass, as do Ruff checks. No RF collection,
download, commit, or deployment was performed.
