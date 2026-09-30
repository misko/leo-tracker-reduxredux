# Reference parity equations tested on local recordings

Eleven of the 1,497 distinct reference-derived equations fit within the carrier
coverage of some existing DS7/DS8 decoder caches. None fits either of the two
cached DS9 visits. This is a cache coverage statement, not an exhaustive survey
of the underlying recordings.

`local_reference_parity.py` freezes the reference coordinates and parity values;
no equation or polarity is fitted to local bits. It uses the later local frame
subsets reserved by `local_header_recovery.py`, with both receivers' held-pilot
coherence above 0.5. Those frames have been used for other exploratory tests, so
this is cross-recording transfer, not an untouched final validation set.

S01 and S02 each cover one equation and supply 22 and 21 frames. S13, S22, and
S23 each cover eleven and supply 10, 16, and 21 frames. S06/S07 cover the same
carriers but have no eligible paired frames. The other caches cover no equation.

All equations below use OFDM symbol 2. Bits are template-relative real signs,
with nonnegative mapped to one. The table pools observations within each equation
and receiver. Parentheses give the visit-weighted independent-sign baseline,
calculated from constituent sign frequencies within each visit. This controls
for fixed-sign bias; it does not establish independence or statistical significance.

| Native FFT bins in XOR | Expected XOR | Frames per RX | RX0 agreement (baseline) | RX1 agreement (baseline) |
|---|---:|---:|---:|---:|
| 484,486,487,496 | 0 | 90 | 63.3% (55.8%) | 63.3% (54.3%) |
| 499,506,507 | 1 | 47 | 72.3% (62.4%) | 70.2% (58.0%) |
| 487,506,507 | 1 | 47 | 68.1% (59.8%) | 61.7% (59.1%) |
| 499,505,506 | 1 | 47 | 74.5% (62.7%) | 70.2% (53.1%) |
| 487,505,506 | 1 | 47 | 66.0% (58.9%) | 53.2% (53.5%) |
| 482,504,505 | 1 | 47 | 78.7% (66.6%) | 59.6% (56.0%) |
| 499,500,503,504 | 0 | 47 | 61.7% (58.3%) | 70.2% (56.1%) |
| 496,500,503 | 1 | 47 | 57.4% (59.2%) | 70.2% (55.3%) |
| 487,500,503,504 | 0 | 47 | 66.0% (58.3%) | 61.7% (56.9%) |
| 479,500,501,503 | 0 | 47 | 63.8% (56.6%) | 70.2% (55.3%) |
| 479,496,501 | 1 | 47 | 72.3% (64.1%) | 70.2% (61.6%) |

Some equations show descriptive excess over the baseline in both receivers,
but none is a verified local parity check. Receiver errors accumulate in XORs,
and shared calibration or conditional templates can also produce dependencies.
The eleven equations share positions and are not independent trials. Pooling
must not hide substantial visit-to-visit variation retained in the detailed file.

An additional gate requires `abs(real(z))/abs(z) > 0.9` for every participating
bit, independently within each receiver and without selecting for parity success.
No visit/equation/receiver combination retains ten observations under that gate.
Therefore the stricter subset does not provide enough support to resolve the
ambiguity in this test. No failed equation was repaired by flipping local bits.

The ignored `local/local_reference_parity.json` contains all coverage results,
per-visit and pooled statistics, counts, confidence-gated results, and input
hashes. Synthetic tests verify the baseline for constant signs and a balanced
three-bit parity relation, including empty support. Tests and Ruff checks pass.
No new recordings or downloads were made. The next useful step is to check
whether the shared equations can jointly improve held-out bit prediction,
without treating them as established transmitter code constraints.

## Joint prediction test

`local_parity_prediction.py` enumerates bit assignments satisfying all available
reference equations. S01/S02 have eight allowed assignments of four bits.
S13/S22/S23 have 64 allowed assignments of fourteen bits: their eleven equations
are not independent. For each local frame and receiver, the predictor chooses
the allowed assignment with the largest sum of template-relative directional
scores, `real(z)/abs(z)`, with signs supplied by the assignment. These scores
are not calibrated log likelihoods. The opposite receiver is used only for
evaluation, never for prediction or candidate selection.

A second prediction omits the target bit's own score to test whether the other
positions can predict it. Tied target signs are unresolved. The constant-bit
baseline takes each coordinate's majority sign from that predictor receiver's
discovery frames. No local parity, weight, or polarity is fitted.

The following values are agreement with the opposite receiver, not transmitter
bit accuracy. Each RX column identifies the receiver supplying the prediction.

| Visit | Decisions per direction | Original agreement | Constrained RX0 / RX1 | Target omitted RX0 / RX1 | Discovery-majority RX0 / RX1 |
|---|---:|---:|---:|---:|---:|
| S01 | 88 | 68.2% | 68.2 / 68.2% | 59.1 / 54.5% | 79.5 / 72.7% |
| S02 | 84 | 71.4% | 71.4 / 69.0% | 57.1 / 61.9% | 71.4 / 66.7% |
| S13 | 140 | 70.0% | 69.3 / 67.9% | 61.4 / 62.1% | 66.4 / 62.1% |
| S22 | 224 | 73.7% | 71.0 / 70.5% | 67.4 / 66.1% | 61.2 / 65.2% |
| S23 | 294 | 78.9% | 82.3 / 85.7% | 78.2 / 80.3% | 85.7 / 83.3% |

The constraints improve agreement in S23 but not consistently across visits.
Most predictions made without the target's own evidence perform worse than
the direct observations. In S23, the constant-bit baseline is already strong,
so the gain cannot simply be described as recovery of changing information.
The equations should not currently be applied as validated correction rules.
This test does not prove that the equations are absent from the transmitted
signal: wrong weights, local sign errors, or conditional layouts can also hurt
prediction. It does show that this concrete fixed-constraint predictor fails
to provide a consistent decoding improvement.

All detailed counts and changed-bit counts are in ignored
`local/local_parity_prediction.json`, with input hashes. Synthetic tests verify
correction of an injected weak sign error, target-score exclusion, and an
unresolved omitted bit when no constraint covers it. Tests and Ruff checks pass.
Native decoder outputs and raw observations remain unchanged.
