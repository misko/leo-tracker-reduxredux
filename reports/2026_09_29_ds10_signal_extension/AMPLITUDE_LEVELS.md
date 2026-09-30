# Are the shared amplitude changes discrete symbols?

This test follows the reproducible I-component changes identified in symbols 4
and 6. It compares explicit noisy discrete-level models with continuous shared
variation, using the existing three DS10-F010 paired visits. No RF was collected.

## Method

Each carrier and receiver is centered and scaled using only discovery frames.
The paired normalized I samples are pooled within each OFDM symbol. Three models
are fitted on these earlier frames and evaluated on the later frames:

- A full bivariate Gaussian, allowing continuous correlated variation.
- Two equally spaced, equally probable shared levels plus independent Gaussian
  noise in each receiver.
- Four equally spaced, equally probable shared levels with the same noise model.

The discrete models fit separate positive amplitudes and noise standard deviations
for the two receivers. Three fixed initializations are optimized; the converged
fit with best discovery likelihood is selected. Evaluation likelihood never
selects a fit or changes its parameters. This is a restricted model comparison,
not a generic test for every possible modulation alphabet.

Discovery/evaluation frame counts are 22/23, 9/9 and 10/11. Each frame supplies
28 paired carrier values per symbol. These samples and frames are dependent, so
likelihood scores are descriptive; no independent-sample significance is claimed.
Evaluation frames were used in prior analyses and are not an untouched validation
dataset. Pooling assumes a common distribution after discovery normalization,
which may not hold if carriers have different symbols or noise levels.

## Held-out results

The table gives mean log-likelihood difference in natural-log units per paired
sample: discrete model minus continuous Gaussian. Positive favors the discrete
model; negative favors continuous variation.

| Visit | Symbol | Two levels | Four levels |
|---|---:|---:|---:|
| v1085 | 4 | +0.0081 | +0.0150 |
| v1085 | 6 | −0.0136 | −0.0052 |
| v1150 | 4 | −0.2319 | −0.3321 |
| v1150 | 6 | −0.1162 | −0.1008 |
| v1162 | 4 | +0.0008 | −0.1488 |
| v1162 | 6 | −0.0364 | −0.0237 |

Nine comparisons favor the continuous model; three give small positive differences.
These are not twelve independent trials. There is no consistent held-out evidence
for assigning binary or four-level symbols to these amplitude changes. The result
does not exclude nonuniform alphabets, different level spacing, per-carrier
structure, non-Gaussian noise or time-varying channel distortion.

The shared amplitude variation remains an observation, not additional decoded
message bits. Neither receiver agreement, arbitrary clustering, nor a small
likelihood improvement on a single region justifies adding a new bit stream to
the dataset. No ID, time, position, CRC, FEC or message field is identified.

## Current implication for the decoding goal

The recent DS10 tests have localized changing signal structure and separated it
from the known T-code, but have not established its alphabet or a transferable
redundancy rule. Semantic decoding still requires that missing mapping. Further
claims should be checked against a better-resolved reference or a independently
validated waveform model, rather than treating residual signs as decoded payload.
Conditional satellite association alone cannot provide this mapping.

## Artifacts and checks

`amplitude_levels.py` writes normalized discovery/evaluation paired samples and
`summary.json` under ignored `local/within-visit/amplitude-levels/`. The summary
contains source and script digests, frame indices, converged-fit counts, fitted
amplitudes/noise levels, likelihoods and per-frame likelihood differences.

Two synthetic tests verify that an actual shared binary source beats the
continuous model on new samples, while a continuous correlated source beats the
binary model. Both tests and Ruff pass. Existing manifests and analysis seals
are unchanged; no commits or publication occurred.
