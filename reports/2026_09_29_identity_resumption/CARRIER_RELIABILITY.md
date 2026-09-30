# Are the additional carriers simply less recoverable?

The wider 10 MS/s header feature weakened the identity-similarity effect. This
follow-up tests a specific explanation: whether the extra carriers have broadly
worse recovery quality. It uses the inferred known T-code as a benchmark on
disjoint symbols, not candidate identity labels.

## Method

Use the same 709-observation fixed-rate set and the same 26 nonpilot carriers
per edge as `BANDWIDTH_EXTENSION.md`. Verify each cache hash and each word receipt
against the previously saved receipt bindings. An accepted known word ending at
OFDM symbol 257 supplies the frame's state; score only symbols 258–289. Do not
infer state from the scored region. Compare the original four core carriers with
the other 22 on the same frames and symbols.

The first reserved frame provides per-carrier discovery estimates; the second
provides evaluation. A frame without an accepted known state abstains. This
conditions the benchmark on recoverable known-pattern frames and does not estimate
quality for every frame in the corpus. The state is inferred, so mismatch is
disagreement with a model, not independently verified transmitter BER. A genuine
state transition in the test region would also contribute disagreement.

## Result

| Edge | Held-out frames | Recording groups | Core-carrier disagreement | Additional-carrier disagreement |
|---|---:|---:|---:|---:|
| Lower | 375 | 80 | 18.079% | 18.250% |
| Upper | 131 | 65 | 19.191% | 19.254% |

The extra-minus-core differences are only +0.171 and +0.063 percentage points.
Descriptive 95% bootstrap intervals, resampling whole recording groups, are
−0.235 to +0.561 points for lower and −0.583 to +0.691 points for upper. These
intervals do not establish equivalence or account for every possible dependence
across recordings; they show the scale of uncertainty in this sample.

Per-carrier held disagreement spans 17.06–19.89% on the lower edge and
18.13–20.42% on the upper edge. There is no large pooled falloff in the additional
carriers under this known-tail assay. Therefore broadly poor recovery outside
the four core carriers is not supported as the immediate explanation for the
weaker wide-header identity score.

The result does not prove that header and tail have equal reliability. Modulation,
interference, channel evolution or the location of actual header content may
differ. The short-term sign lead could still be a localized header property or
a nuisance structure near the pilots. No new identity field or corrected message
bits are established by this comparison.

We do not add a reliability-weighted identity search here: the measured carrier
differences are small and do not justify another weight-tuning sweep on the same
inspected observations. The recovered per-carrier discovery estimates remain
available if a future independent waveform constraint motivates such a test.

## Reproduction and validation

`carrier_reliability.py` writes ignored `local/carrier-reliability.json` with
recording/track/frame IDs, state choices, per-carrier counts and disagreements,
first-frame reliability estimates, recording-cluster bootstrap intervals and
all source-receipt hashes. The synthetic test verifies per-carrier disagreement
accounting and that irrelevant quadrature values do not alter real-sign scores.
The test and Ruff pass. No new RF, changes to frozen fixtures, commits or remote
publication occurred.
