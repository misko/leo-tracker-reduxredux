# Discrete amplitudes and neighboring-symbol explanations

The shared early real-axis structure is not yet a demonstrated discrete symbol
alphabet. Re-evaluating frozen paired models directly from the existing DS10
soft-symbol arrays reproduces all 12 held likelihood comparisons. Neither a
two-level nor a four-level model consistently beats the continuous Gaussian
baseline. Independently inventorying the neighboring-symbol experiment finds
all 36 held prediction scores below the constant baseline.

## Frozen likelihood checks

Three DS10-F010 excerpts (v1085/v1150/v1162), two symbols (4/6), two alphabets
(2/4 levels). NPZ hashes match the original receipts. Earlier-frame per-carrier
centering/scaling is reconstructed separately for each receiver. The recorded
amplitudes and noise levels are used without refitting. A separate implementation
computes held likelihoods and reproduces every frame delta within 1e-10.

| Physical symbol | Levels | Mean held log-likelihood advantage over Gaussian, equal excerpt weight |
|---|---:|---:|
| 4 | 2 | −.07433 |
| 4 | 4 | −.15529 |
| 6 | 2 | −.05539 |
| 6 | 4 | −.04321 |

These are descriptive means, not confidence tests: all three excerpts share a
session and carriers/frames are dependent. Of the 12 comparisons, only three
have positive advantages, all small. The discrete model assumes uniform equally
spaced shared levels with independent Gaussian receiver noise; the baseline is
a full bivariate Gaussian. Failure does not exclude a different alphabet,
nonuniform occupancy, distorted discrete modulation or shared noise.

The raw-axis experiment's 12 local and two historical public rows are also
inventoried, and their means checked against saved frame deltas. Local gains
range from −.01089 to +.02568; public-reference gains are much larger but come
from published soft estimates, not independent raw truth. No public IQ was
processed in this audit. The raw-axis fits use scalar rather than per-carrier
normalization, so these are different comparisons, not interchangeable scores.

## Neighbor associations

The saved predictor uses fixed ridge regularization, discovery-only fitting,
and the same target carriers for adjacent-carrier, adjacent-symbol and combined
models. Across three excerpts, two symbols, three models and two receivers,
all **36 held MSE reductions are negative**, ranging from −.26621 to −.01478.
Training-shift ranks are recomputed and retained in the receipt, but beating
a shuffled model would not rescue performance worse than a constant predictor.
The neighbor models were not refitted or searched again.

This rules out support from these particular linear predictors, not physical
leakage generally. Nonlinear dependence, unobserved carriers, changing channel
coefficients and coded relationships remain possible. Receiver covariance can
persist while neither a discrete alphabet nor neighbor predictability is resolved.

## Firmware link and consequence

Firmware MCS tables constrain possible codeword accounting, but do not select
an alphabet for physical OFDM symbols 4/6. Neither device-role configuration
nor the threshold-mask tables map these amplitudes to a software field. Rank
shared received variation first; distorted modulation and shared channel effects
remain alternatives; a decoded header or satellite identity remains unsupported.

Reproduce with:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/amplitude_audit.py
```

`local/amplitude-audit.json` retains all scores and source hashes. The component
test compares the density against an explicit two-Gaussian calculation and
checks receiver-exchange invariance. This adds 62 ledger entries, including
historical public provenance; it does not add 62 discoveries.
