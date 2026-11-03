# DSX01-S04: balance_50 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 7 | 0.720 / 1.958 / 2.853 | 1,925–2,278 |
| fitted_c | 13 | 7 | 0.691 / 1.949 / 2.888 | 1,925–2,282 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
