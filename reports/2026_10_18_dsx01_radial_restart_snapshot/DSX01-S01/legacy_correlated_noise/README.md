# DSX01-S01: legacy_correlated_noise independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.467 / 2.049 / 2.075 | 2,623–2,671 |
| fitted_c | 13 | 2 | 1.441 / 2.025 / 2.052 | 2,623–2,671 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
