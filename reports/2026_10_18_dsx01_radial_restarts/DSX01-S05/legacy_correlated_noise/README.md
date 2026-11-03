# DSX01-S05: legacy_correlated_noise independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 3.272 / 3.350 / 3.350 | 2,282–2,282 |
| fitted_c | 13 | 1 | 3.304 / 3.383 / 3.383 | 2,282–2,282 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
