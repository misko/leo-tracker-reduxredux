# Fixed early receiver response does not transfer to later windows

A simple early-window calibration does not explain away the failed receiver-geometry results. The local categorical predictor is worse than the existing P, U and O models on all six omitted recordings. It also loses slightly to the other-five-record background on the equal-record mean. Do not replace the current response baseline with this recipe.

| Later full predictive comparison | Equal-record mean gain, nats/window | Positive records |
|---|---:|---:|
| Local calibration − training background | −0.014794 | 2/6 |
| Local calibration − P receiver/rate/time model | −0.337650 | 0/6 |
| Local calibration − U unsigned geometry | −0.298676 | 0/6 |
| Local calibration − O signed geometry | −0.295045 | 0/6 |

| Omitted recording suffix | Later windows | Local − background | Local − O |
|---|---:|---:|---:|
| 39ac2b14d1bb5f0f | 117 | −0.044733 | −0.293339 |
| 3ebf3526172258af | 235 | +0.640193 | −0.271747 |
| 4c56320fb5ca6994 | 218 | −0.047160 | −0.025421 |
| 851486cc2a1acd99 | 331 | +0.005372 | −0.200080 |
| 9d7b6a0db558703a | 243 | −0.364838 | −0.412360 |
| c559f436d578c9bd | 219 | −0.277598 | −0.567319 |

## Tested method

For each recording and RF lane, count the four receiver outcomes in the early reception period: neither, RX0 only, RX1 only and both. Add 20 pseudo-observations distributed according to the other-five-record training background, then normalize. Freeze those probabilities for every later observation. Empty outcomes remain included; no frequency, candidate identity or geometry enters this predictor.

The shrinkage strength and comparison were fixed in the [protocol](PROTOCOL.md) before execution. Each recording's early period is valid calibration information for its later period; later categories never enter the fitted probabilities. Baseline P/U/O filters also process the early observations and update sequentially during the later period. This is therefore a comparison of predictive policies, not an isolated ablation with identical adaptation. A frozen categorical predictor cannot identify whether any failure is due to varying sensitivity, target turnover or other temporal structure.

The negative result rejects this fixed early-frequency calibration recipe, not all receiver calibration or geometric information. It establishes no physical antenna gain or satellite identity. The data are the six reused calibration recordings from the [paired-state experiment](../2026_09_28_rx_paired_state_cv/README.md), not a fresh confirmation panel. The role named `held_frequency` supplies receiver-state categories here, not frequency residuals.

## Verification and next action

[run.py](run.py) verifies strict early-before-later timestamps, reproduces every saved P/U/O later full-score total and denominator, and records each early/later source-window ID with the frozen lane probabilities. [results.json](results.json) retains source hashes and all comparisons. Three tests pass for prior retention, finite support for unseen categories, and invalid-category rejection. Execution completes within a second under its 60-second limit.

Together with the [persistence test](../2026_09_30_rx_persistence/README.md), this argues against another static offset or persistence-only adjustment. A next response baseline should update causally and score before each update, so geometry must add information beyond ordinary changing occupancy. That is a new experiment, not a post-hoc replacement of this frozen result. The separate requirement for independent pose and RX mapping remains open.

No RF collection, IQ processing, geographic fit, production change or remote publication occurred.
