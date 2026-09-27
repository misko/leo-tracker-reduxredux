# DS5 joint mixture: full evaluation

Completed 42/42 scans, 1739 tracks.

All settings frozen from the original three-scan prototype. Seven completed scans reused after hash checks; remaining 35 evaluated with identical numerical core and calibration. Independent site-specific shortlists; no geographic search, new RF collection or production changes.

Lower composite predictive NLL is better. Gaps are known-location minus estimate: negative favors known location. These are not RMS values, geographic fixes, or calibrated location probabilities.

| Scope | Noise Hz | Model | Comparison | Known wins | Mean gap | Median gap |
|---|---:|---|---|---:|---:|---:|
| all42 | 100 | frozen_no_clock | reno | 30/42 | 0.5978 | -0.1911 |
| all42 | 100 | frozen_no_clock | sacramento | 25/42 | 0.8001 | -0.0434 |
| all42 | 100 | joint | reno | 28/42 | -0.1849 | -0.0456 |
| all42 | 100 | joint | sacramento | 31/42 | -0.1688 | -0.0393 |
| all42 | 100 | joint_no_clock | reno | 27/42 | -0.1770 | -0.0422 |
| all42 | 100 | joint_no_clock | sacramento | 26/42 | -0.1439 | -0.0369 |
| all42 | 200 | frozen_no_clock | reno | 30/42 | 0.1490 | -0.0499 |
| all42 | 200 | frozen_no_clock | sacramento | 26/42 | 0.1976 | -0.0113 |
| all42 | 200 | joint | reno | 27/42 | -0.0439 | -0.0088 |
| all42 | 200 | joint | sacramento | 29/42 | -0.0498 | -0.0081 |
| all42 | 200 | joint_no_clock | reno | 26/42 | -0.0375 | -0.0077 |
| all42 | 200 | joint_no_clock | sacramento | 28/42 | -0.0397 | -0.0073 |
| error_ge100km | 100 | frozen_no_clock | reno | 4/6 | 6.9635 | -1.0675 |
| error_ge100km | 100 | frozen_no_clock | sacramento | 0/1 | 50.1036 | 50.1036 |
| error_ge100km | 100 | joint | reno | 5/6 | -0.3598 | -0.5713 |
| error_ge100km | 100 | joint | sacramento | 1/1 | -0.5493 | -0.5493 |
| error_ge100km | 100 | joint_no_clock | reno | 4/6 | -0.2766 | -0.2790 |
| error_ge100km | 100 | joint_no_clock | sacramento | 0/1 | 0.2839 | 0.2839 |
| error_ge100km | 200 | frozen_no_clock | reno | 4/6 | 1.7414 | -0.2676 |
| error_ge100km | 200 | frozen_no_clock | sacramento | 0/1 | 12.5338 | 12.5338 |
| error_ge100km | 200 | joint | reno | 5/6 | -0.0978 | -0.1341 |
| error_ge100km | 200 | joint | sacramento | 1/1 | -0.1455 | -0.1455 |
| error_ge100km | 200 | joint_no_clock | reno | 4/6 | -0.0616 | -0.0794 |
| error_ge100km | 200 | joint_no_clock | sacramento | 0/1 | 0.1474 | 0.1474 |
| new35 | 100 | frozen_no_clock | reno | 23/35 | 1.0905 | -0.1742 |
| new35 | 100 | frozen_no_clock | sacramento | 21/35 | 1.0465 | -0.0405 |
| new35 | 100 | joint | reno | 23/35 | -0.1960 | -0.0439 |
| new35 | 100 | joint | sacramento | 27/35 | -0.2056 | -0.0406 |
| new35 | 100 | joint_no_clock | reno | 22/35 | -0.1919 | -0.0402 |
| new35 | 100 | joint_no_clock | sacramento | 22/35 | -0.1810 | -0.0380 |
| new35 | 200 | frozen_no_clock | reno | 23/35 | 0.2718 | -0.0438 |
| new35 | 200 | frozen_no_clock | sacramento | 22/35 | 0.2589 | -0.0139 |
| new35 | 200 | joint | reno | 22/35 | -0.0457 | -0.0052 |
| new35 | 200 | joint | sacramento | 24/35 | -0.0592 | -0.0088 |
| new35 | 200 | joint_no_clock | reno | 21/35 | -0.0383 | -0.0051 |
| new35 | 200 | joint_no_clock | sacramento | 23/35 | -0.0477 | -0.0070 |

## Inference reliability

| Noise Hz | Scans with different chain winners | Scans with max assignment TV >0.9 | Largest chain score spread |
|---|---:|---:|---:|
| 100 | 10/42 | 28/42 | 7.4765 |
| 200 | 3/42 | 18/42 | 1.8741 |

**Do not interpret nominal win counts as validated accuracy.** Equal pooling of chains with different modes does not estimate correct mode probabilities when sampling has not converged. Averaging predictive densities can yield an attractive pooled score even when individual chains disagree badly. The no-clock joint control has only one chain.

The model still conditions historical timing priors on ±120 seconds, uses an uncalibrated scan-clock prior and Gaussian 100/200 Hz block noise, and retains correlated train/evaluation time bins and receiver/track dependence. All published location estimates and original masks are reused. No parameters were tuned on these scores.

Full per-scan/site/track results and provenance are in full_results.json. full_summary.json additionally records sample-rate strata, development exclusions, large-error cases, score gaps and chain diagnostics. Per-scan logs and return codes are retained.
