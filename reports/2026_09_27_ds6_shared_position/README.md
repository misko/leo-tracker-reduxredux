# DS6 shared stationary-position experiment

A shared position across the four frozen development scans is **2.627 km** from
the operator reference. It does not achieve the sub-kilometre goal. Omitting
each scan in turn gives 1.778–3.814 km errors and degrades the omitted scan's
held prediction in every case after adapting its timing on training visits.

| Omitted scan rate | Position error (km) | Omitted held log-score change vs independent fit |
|---|---:|---:|
| None | 2.627 | — |
| 10 MS/s | 1.778 | -279.15 |
| 2.5 MS/s | 2.606 | -101.99 |
| 5 MS/s | 2.599 | -115.20 |
| 7.5 MS/s | 3.814 | -243.48 |

All four included scans' held log scores sum to a 510.38-unit decrease relative
to their independent fits. A common physical station position is appropriate
for the stationary dataset, but the current likelihood does not reconcile the
scan-dependent biases. These results do not justify adopting the shared point
as an accurate location or selectively excluding scans based on their errors.

The protocol and source/input hashes were frozen before fitting. Each fit uses
one common east/north location and independent scan timing offsets, frozen
training-calibrated per-track scales, inherited catalogue mixtures, and random
whole-visit partitions. Two starts use the mean included training locations and
the donor-scan center. Training likelihood alone selects the winner. For an
omitted scan the shared position is frozen; only its timing adapts to its
training visits. All held predictions are audited with exact propagation.
Only the separate post-selection summarizer loads the operator coordinate.

All five selected winners converge inside their bounds. These remain local
development fits with approximate catalogue shortlists and plug-in training
calibration. Omitting a scan here is a sensitivity audit with training-time
adaptation on that scan, not a completely untouched blind evaluation. Four
development scans do not cover the full 43-scan DS6 dataset.

Two tests cover synthetic common-position/independent-clock recovery, held-score
isolation, frozen dependencies, scan membership, and training-only winner and
timing-adaptation selection. No production change or RF collection occurred.

The companion `2026_09_27_ds6_cfo_dataset` export prepares the existing numerical
evidence for all 43 scans, retaining failed/unavailable cases rather than
replacing them. The remaining work is full-dataset validation and resolving
systematic track/scan errors; an aggregate point does not satisfy that work.
