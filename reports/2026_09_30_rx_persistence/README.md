# Longer persistence does not rescue signed receiver geometry

The training-selected persistence extension fails the predeclared direction gate. Signed geometry remains worse than unsigned geometry and the simpler receiver-response model on later observations. Do not advance this response model to a new confirmation panel or geographic fit.

All three arms choose 30 seconds in folds 0, 1 and 3, and 10 seconds in folds 2, 4 and 5. No arm selects 1, 100 or 300 seconds. This replaces an apparent preference for the previous upper bound with an interior grid choice in three folds, but later predictive performance gets worse.

| Model | Mean later score change versus original fitted persistence, nats/window |
|---|---:|
| P: receiver, sample rate and elapsed time | −0.006057 |
| U: P plus unsigned geometry | −0.009882 |
| O: U plus signed receiver contrast | −0.008776 |

| Comparison after training-only selection | Mean later gain, nats/window | Positive records above 1e-6 |
|---|---:|---:|
| O − U | −0.002526 | 2/6 |
| O − P | −0.045324 | 2/6 |
| O − swapped signed geometry | −0.000394 | 2/6 |
| O − reversed signed geometry | +0.000657 | 3/6 |
| O − permuted signed geometry | +0.003110 | 3/6 |

Every comparison fails the declared requirement of a positive equal-record mean and at least four positive records. Positive values against selected corrupted controls cannot compensate for worse prediction than the matched unsigned comparator. The tiny 6.34e-9 O−U difference in one fold is a numerical near-tie and is not counted as a direction win.

## Scope and verification

The [protocol](PROTOCOL.md) was written before execution. This is a conditional persistence test on the original six development recordings, not a full model refit or independent confirmation. All reception coefficients, occupancy, priors, candidate sets and preprocessing remain frozen. Each fold selects its time using only the original other-five-record training reception scores, then scores the omitted record sequentially before each update. The role named `held_frequency` here contains binary receiver-state outcomes, not a frequency-error measurement.

[run.py](run.py) checks dataset hashes and exact training/held membership and replays every original P/U/O role score within 1e-8 nats/window before evaluating alternatives. Two new tests cover training-score selection, deterministic tie handling and rejection of nonfinite scores. The pre-existing model tests and scalar audits are documented in the [original experiment](../2026_09_28_rx_paired_state_cv/README.md). All six folds complete in 4.25 seconds under a 120-second execution cap, with one BLAS thread. [results.json](results.json) retains every training grid, selected time, role score, signed control and source hash.

This narrows the next action: do not pursue longer persistence alone. Stable receiver sensitivity, target identity and measured installation geometry remain unresolved. A different sensitivity-calibration model must be declared and evaluated on development data before an association bridge or later-dataset test. Current evidence does not establish geographic improvement.

The preceding [sampling audit](../2026_09_30_rx_order_sampling/README.md) reproduced a finding already present in the [earlier detailed sequence follow-up](../2026_09_28_rx_sequence_followup/README.md); it is not new independent evidence. This persistence experiment is a distinct test of the later four-state model's boundary behavior.

No new RF collection, IQ processing, production change or remote publication occurred.
