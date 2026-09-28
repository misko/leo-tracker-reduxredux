# Better reception prediction did not improve location error

All four fixed-grid runs completed successfully in 437.5–466.3 seconds. Each prior evaluated its own exact 289 saved coordinates with one shared frequency fit per point across reception calibrations. The whole-cohort reporter validated all four runs before calculating reference distances. No selected solution touches a grid edge or prior boundary.

Distances below are kilometers to the operator-supplied roof coordinate, not surveyed ground truth. This is an already-unblinded development cohort.

| Recording | Prior | Doppler-only | Original geometry | Matched mean calibration | Mixture calibration |
|---|---|---:|---:|---:|---:|
| 339af | Sacramento | 2.4237 | 1.9585 | 1.9585 | 1.9585 |
| 339af | Reno | 2.4662 | 1.6095 | 1.6095 | 1.6095 |
| 53ce | Sacramento | 5.5377 | 5.5132 | 6.0323 | 6.5309 |
| 53ce | Reno | 5.7088 | 5.7013 | 6.2344 | 6.7316 |
| e76c | Sacramento | 3.0003 | 3.0003 | 3.0003 | 3.9510 |
| e76c | Reno | 3.0138 | 3.0138 | 3.0138 | 4.0054 |
| c9db | Sacramento | 5.4166 | 5.4166 | 5.4166 | 5.4166 |
| c9db | Reno | 5.4218 | 5.4218 | 5.4218 | 5.4218 |

| Prior | Mean Doppler-only | Mean original geometry | Mean matched-mean geometry | Mean mixture geometry |
|---|---:|---:|---:|---:|
| Sacramento | 4.094565 | 3.972148 | 4.101923 | 4.464221 |
| Reno | 4.152652 | 3.936606 | 4.069868 | 4.442068 |
| Combined | 4.123608 | 3.954377 | 4.085896 | 4.453144 |

Against Doppler-only, mixture geometry improves two cases, worsens four, and leaves two unchanged. Mean error worsens by 9.03% for Sacramento and 6.97% for Reno, or 7.99% overall. Combined median worsens from 4.215211 to 4.710970 km.

Against the matched mean-direction calibration, mixture improves zero cases, worsens four, and leaves four unchanged. The same counts hold against original geometry. The fitted reception mixture should therefore not be promoted as a location-accuracy improvement.

## What changed at the selected points

The four regressions relative to matched mean are eastward shifts on each prior's search grid. Under the mixture-calibrated geographic objective, the incremental reception contribution outweighs a worse Doppler score:

| Case | Grid shift east/north, km | Change in Doppler NLL | Change in joint NLL | Change in joint-minus-Doppler contribution |
|---|---:|---:|---:|---:|
| 53ce Sacramento | +0.5 / 0 | +0.000639 | -0.001626 | -0.002265 |
| 53ce Reno | +0.5 / 0 | +0.001302 | -0.000912 | -0.002214 |
| e76c Sacramento | +1.0 / +0.5 | +0.007467 | -0.006862 | -0.014329 |
| e76c Reno | +1.0 / 0 | +0.004929 | -0.006307 | -0.011236 |

Each change compares the mixture objective at its selected point with the mixture objective at the matched-mean model's selected point. Lower score wins. Joint-minus-Doppler is the incremental reception term under shared-identity marginalization, not a separately marginalized reception fit. These values explain the ranking changes; they do not establish which physical modeling error caused them.

## Scientific conclusion and next diagnostic boundary

Candidate-mixture calibration passed the conditional reception holdout gate, yet failed this geographic test. Predicting reception at known locations is not equivalent to discriminating nearby receiver positions. The new calibration changes a weak local score preference in the wrong direction on two recordings, consistently across both priors. Search coverage cannot explain this contrast because the coordinate inventory is identical.

Potential contributors include antenna/pose response mismatch, frequency–reception dependence, and location-dependent satellite identity changes. They remain hypotheses. The 5 MHz e76c recording also uses a sample-rate level absent from calibration; 53ce is 10 MHz, so that alone cannot explain all regressions.

Do not tune reception weights, reverse orientation, replace recordings, or silently restore a preferred model using these distances and call that validation. A scoped next diagnostic can decompose track contributions and candidate identities at the existing selected positions and the reference coordinate, without launching another broad location search. Any successful estimator still needs disjoint confirmation before a general resolution claim.

Artifacts: `mixture-geometry-distances.json`, four `mixture-geometry-replay-scan-fw-*.json` files, and `MIXTURE_GEOMETRY_PROTOCOL.md`. The reporting and experiment suite passed 111 tests. No production estimator changed and no new RF was collected.
