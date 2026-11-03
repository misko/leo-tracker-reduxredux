# DSX01-S03: rate_1 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.041 / 1.097 / 1.805 | 2,287–2,287 |
| fitted_c | 13 | 2 | 1.081 / 1.137 / 1.868 | 2,287–2,287 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
