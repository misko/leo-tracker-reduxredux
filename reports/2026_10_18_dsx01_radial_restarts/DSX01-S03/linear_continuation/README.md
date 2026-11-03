# DSX01-S03: linear_continuation independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.037 / 1.090 / 1.825 | 2,265–2,300 |
| fitted_c | 13 | 2 | 1.075 / 1.128 / 1.893 | 2,265–2,300 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
