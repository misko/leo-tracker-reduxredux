# A stronger observational reference for receiver geometry

**Select the pooled joint receiver-count model with uniform frequency density.** It improves predictive density on all six held-out calibration recordings. This addresses an important weakness in the reference used by the geometry experiments; it is not evidence of satellite identity or a receiver-tilt benefit.

Each fold fits five complete calibration recordings and predicts the sixth, using reception windows only. The experiment uses 1,356 paired windows, including empty receiver views. Evaluation recordings, the confirmation panel and calibration-held windows do not enter selection. The [protocol](PROTOCOL.md) fixes all smoothing constants, model choices and tie handling before execution.

| Observational reference | Mean improvement over recalibrated Poisson | Positive recordings |
|---|---:|---:|
| Independent Poisson counts, uniform frequencies | 0 (reference) | — |
| **Joint RX counts, uniform frequencies** | **+0.665675** | **6/6** |
| Joint RX counts, pooled frequency histograms | +0.395181 | 5/6 |
| Rate-specific joint counts, uniform frequencies | +0.596186 | 6/6 |
| Rate-specific joint counts and frequency histograms | −0.261988 | 2/6 |

Scores are equal-record mean nats per paired window; higher is better. The comparison Poisson means are refitted inside every training fold, rather than borrowed from the earlier signal model.

| Held calibration recording (scan-fw suffix) | Windows | Joint counts − Poisson |
|---|---:|---:|
| 39ac2b14d1bb5f0f | 118 | +0.508724 |
| 3ebf3526172258af | 227 | +1.384516 |
| 4c56320fb5ca6994 | 217 | +0.618997 |
| 851486cc2a1acd99 | 340 | +0.573448 |
| 9d7b6a0db558703a | 225 | +0.047481 |
| c559f436d578c9bd | 229 | +0.860887 |

The pooled frequency histograms lose to their matched count-only model on every fold (mean −0.270494 nats/window). Rate-specific frequency histograms also lose on every fold (mean −0.858174). Marginal frequency nonuniformity observed in the earlier audit therefore does not justify a learned histogram here: it fails to transfer between these recordings. Rate conditioning of counts also loses to pooled counts on average. Two rates occur in only one calibration recording each, so their held folds necessarily use the declared pooled fallback.

## What is frozen

The selected model in `results.json:selected_model` is refitted on all six calibration reception recordings. It stores a joint RX count histogram with 32 pseudowindows from a product-geometric distribution. This preserves positive support beyond observed counts. Frequencies remain uniform on each lane's canonical alias circle. The count model retains dependence between RX0 and RX1, including coincident empty observations.

This is an unconditional reference fitted to mixed observations. It may include real signals or omitted emitters; it is not verified target-free clutter. Its cross-validation score selected the model and is therefore development evidence, not independent validation of a later satellite model.

## Connection to geometry

The [presence experiment](../2026_09_28_rx_presence_geometry/README.md) found that receiver geometry did not beat Doppler-only once target absence was permitted. The next comparison must give D/S/T the same frozen joint-count reference, fit their presence/emission parameters using calibration data only, then evaluate frequency-alignment, receiver-swap and reversed-trajectory controls.

A joint count distribution cannot simply replace the Poisson normalization in the old signal likelihood. Adding one signal candidate changes the count probability as well as its frequency density. For receiver signal indicators s0,s1, use the ratio P(n0−s0,n1−s1)/P(n0,n1), with a factor (sum_j g(x_j)/f(x_j))/n_r for each receiver with s_r=1. Mix all four signal patterns with normalized reception probabilities; impossible negative counts have zero weight. This construction recovers the previous Poisson likelihood as a special case and preserves a meaningful absent reference.

The implementation is now available in `tools/rx_empirical_signal.py`, with component-owned tests for direct four-pattern sums, normalized count tails, empty receivers, visibility, vectorization and Poisson equivalence. This is preparation for the next fit; no new satellite/geometry score was produced by this kernel in the present experiment. The reference selection and its frozen sources were not changed by this addition.

## Evidence and validation

- [Frozen protocol](PROTOCOL.md), [review](REVIEW.md), [launch hashes](launch.json)
- [Full folds and selected model](results.json)
- [Independent arithmetic and membership audit](audit.json)
- [Per-record visualization](mode-improvement.png)

All 17 empirical-background and cross-validation tests passed, along with Ruff. The independent result audit passed. Normalization, infinite-tail support, Poisson equivalence, empty observations, receiver/candidate permutation, rate fallback, whole-record separation and extraction isolation are covered by component tests. Execution took 0.30 seconds with peak RSS 79,528 KiB. The run reads derived JSON only; it performs no RF collection, raw-IQ analysis or QNAP writes.
