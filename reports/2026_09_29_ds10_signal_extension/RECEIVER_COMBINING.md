# Improving DS10 sign recovery with both receivers

Simple equal receiver averaging improves the known-sequence benchmark in all
three tested DS10-F010 visits. This is a recovery improvement, not a new message
field or a count of additional independent information bits.

## Independent regions and fixed splits

Use the existing two-receiver state classification on symbols 194–225. Keep only
qualified classified frames, with the existing chronological discovery/evaluation
split. Fit models and amplitude thresholds on discovery-frame symbols 226–257;
evaluate on later-frame symbols 258–289. Thus the test samples do not fit the
state, combining coefficients or thresholds. Expected signs are generated from
the inferred state, not independent transmitter truth. The result is disagreement
with an inferred sequence, not a verified transmitter BER.

The visits supply 16/16, 3/3 and 4/7 classified discovery/evaluation frames, with
28 carriers × 32 evaluated symbols per frame. State selection may favor cleaner
frames and does not describe every frame in the recording.

## All evaluated signs

| Visit | Decisions | RX0 disagreement | RX1 disagreement | Equal average | Fitted weighted average |
|---|---:|---:|---:|---:|---:|
| v1085 | 14,336 | 16.62% | 13.43% | **7.53%** | 11.66% |
| v1150 | 2,688 | 18.30% | 10.60% | **8.97%** | 6.51% |
| v1162 | 6,272 | 20.66% | 14.00% | **10.51%** | 13.84% |

The weighted model fits a bias and gain per receiver/carrier and a regularized
2×2 receiver residual covariance, then normalizes its weights to unit fitted
gain. It outperforms equal averaging in only one visit. Do not select a different
model per visit using these test outcomes and then call that selection validated.
Equal averaging is the simpler consistently beneficial method in this sample.

## Fixed confidence selection

The amplitude thresholds are predetermined discovery quantiles, not fitted to
evaluation success. With equal averaging and the discovery median absolute
amplitude threshold:

| Visit | Retained decisions | Disagreements | Fraction |
|---|---:|---:|---:|
| v1085 | 7,226 | 30 | 0.415% |
| v1150 | 1,384 | 13 | 0.939% |
| v1162 | 3,129 | 34 | 1.087% |

The 75th-percentile thresholds retain 3,705/707/1,625 decisions with 1/5/5
disagreements respectively. The 90th-percentile thresholds retain 1,593/278/652
with 0/0/2 disagreements. Zero disagreements in a selected finite sample is not
proof of error-free decoding. Frames, carriers and repeated sequence slots are
dependent; these counts are not independent new bits.

## What this enables

Both equal and weighted early-symbol soft estimates are exported for all
header-evaluation frames, preserving frame IDs, symbol order and native FFT bins.
They are **unvalidated early scores**, not probabilities or corrected message
bits. The tail confidence/error relation cannot simply be transferred to the
early header, whose signal structure and noise may differ. No parity constraint
was used to force any early signs.

This establishes useful receive diversity on a checkable part of DS10 and gives
a reproducible starting point for further early-sign analysis. It does not
identify satellite ID, timing, orbit, FEC, CRC or message bytes. The tail signs
remain explained by the existing T-code generator.

## Artifacts and validation

`receiver_combining.py` writes ignored `local/within-visit/receiver-combining/`
containing `summary.json` and per-visit NPZs with equal/weighted early scores,
weights, offsets, carrier bins and frame indices. Summary records source hashes,
script hash, all frame selections, thresholds and error counts. Sources are
verified against the paired-cache receipts. The synthetic test confirms that a
fitted combiner downweights a deliberately noisy receiver on new samples.
The test and Ruff pass. No new RF, commits or publication occurred.
