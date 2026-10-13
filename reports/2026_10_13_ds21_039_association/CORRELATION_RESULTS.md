# DS21-039 fixed-state residual structure

Receiver-band block structure persists at both sealed endpoints, while several cross-receiver and cross-band products reverse sign. This does not identify a stable common-clock or constant covariance model. Large channel-level ratios often describe almost unsupported conditional tails, rather than strong residual evidence. No model change is selected from this audit.

The root audit completed in 28.191 seconds with zero optimizer calls, using the original all-view winner and sealed refinement winner on the same 2,798 original training windows. Receipt-only verification passed for all 327 live/archive source pairs, six ancestor bindings, both endpoint outputs, the input, endpoint definitions and sealed terminal. The objective and both source/native NLL replay deltas are zero; posterior replay differences are below 7e-16. No held observations, reference positions or new predictor/likelihood calls were used for this report.

All four receiver-band strata have the same 12 observed and supported blocks, `[0,1,3,4,5,7,8,9,10,11,13,14]`, and eight actual adjacent pairs. Missing blocks 2, 6 and 12 remain gaps. Posterior signal mass rises from 2,068.045 to 2,167.248 and positive-mass window counts from 2,392 to 2,403; these counts and fractional masses are not effective sample sizes.

The table compares equal-block mean squared centered residual means with the matched nominal independent-window proxy, `sigma² sum(m²)/(sum m)²`, using the frozen sigma of 125 Hz. Each group is centered by its own signal-weighted pooled mean. Values are Hz²; the proxy is not calibrated sampling variance.

| Group (windows) | Original square / proxy (ratio) | Refinement square / proxy (ratio) | Minimum block signal mass, original → refinement |
|---|---:|---:|---:|
| All (2,798) | 455.726 / 93.608 (4.868) | 268.449 / 89.569 (2.997) | See receiver-band rows |
| RX0 low (1,069) | 1,229.114 / 295.613 (4.158) | 1,323.783 / 285.740 (4.633) | 31.934 → 26.991 |
| RX0 high (722) | 625.664 / 564.024 (1.109) | 551.945 / 435.297 (1.268) | 8.902 → 16.971 |
| RX1 low (623) | 1,306.457 / 452.985 (2.884) | 875.080 / 514.508 (1.701) | 16.987 → 9.022 |
| RX1 high (384) | 2,913.722 / 978.078 (2.979) | 2,761.187 / 855.023 (3.229) | 3.988 → 4.983 |

RX0-low and RX1-high retain elevated descriptive ratios with non-negligible block support. Their lag-one products also retain their respective signs: RX0-low −396.133 → −499.762 Hz², RX1-high +713.438 → +493.057 Hz², each on eight genuine adjacent pairs. The all-window lag product is −37.624 → −5.442 Hz², so the result is not uniform positive serial correlation.

Cross-products differ substantially despite identical time-bin support. Each entry below uses 12 common supported blocks; a shared time bin does not establish simultaneous measurements or a shared emitter.

| Centered block cross-product | Original Hz² | Refinement Hz² |
|---|---:|---:|
| RX0 low × RX1 low | +161.664 | −153.496 |
| RX0 high × RX1 high | −373.793 | −7.679 |
| RX1 low × RX1 high | +405.107 | −253.883 |
| RX0 low × RX0 high | +627.320 | +441.155 |

Channel stratification exposes a stronger support caveat. Exact-positive mass, including subnormal mass, was retained without a new threshold; equal-block averages give a practically unsupported conditional mean the same block weight as a well-supported mean. RX0/channel 3 retains a ratio of 596.176 → 588.835, but block 8 has only 3.65e-206 → 1.80e-204 signal mass and conditional means −3,870.663 → −3,854.884 Hz. RX0/channel 5 has ratios 219.985 → 265.339, with block 0 mass 3.64e-317 → 4.29e-302 and means −4,792.622 → −4,678.112 Hz. Those large ratios cannot be treated as measured physical correlation.

Other channel summaries change sharply with the endpoint: RX0/channel 6 ratio 24.009 → 177.292, RX1/channel 6 105.215 → 0.643, and RX1/channel 8 97.846 → 0.078. RX1/channel 8 has only 20 windows, two supported blocks and no adjacent pair; its original block 8 mass is 4.07e-20. Cross-receiver channel 1 changes +621,304.147 → −10,013.674 Hz² on eight common blocks; channel 8 changes −61,254.584 → +1,092.061 Hz² on only two. Receiver-channel support ranges from two to twelve blocks and zero to eight adjacent pairs. The accompanying JSON preserves the support counts and minimum positive-mass block for every stratum.

The association state also changes: for example, posterior occupancy of catalogue 68021 moves from 0.451 to 109.586, while 62128 moves 3.502 → 40.996 and 62420 moves 35.273 → 0.734. These are descriptive latent allocations, not transmitter identifications. Together with unstable cross-products, they make a fixed physical covariance interpretation unestablished.

Posterior-selected in-sample residuals share fitted intercept/drift constraints, and model misspecification can create centered patterns. The audit retains all tails and failures; it does not tune support thresholds, fit covariance, infer receiver clock noise, estimate confidence or claim localization improvement. A covariance intervention requires a separately specified model and comparison; this audit alone does not justify one.

Execution authority: root `local/correlation-v1/freeze.json`, SHA256 `5ecf99ad99929164a522f8cd17d550f8e1f4723af25b27df107273367075482f`; sealed terminal SHA256 `82145bc77d7de768b4c2e5ff63524dc553fef163a3d75421d82d5f8b92519323`. Exact receipt bindings, summary values and audit counts are in [CORRELATION_RESULTS.json](CORRELATION_RESULTS.json). The predeclared definitions are in [CORRELATION_PROTOCOL.md](CORRELATION_PROTOCOL.md).
