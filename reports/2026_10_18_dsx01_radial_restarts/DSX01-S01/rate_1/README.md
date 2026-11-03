# DSX01-S01: rate_1 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.576 / 0.606 / 5.405 | 2,592–2,667 |
| fitted_c | 13 | 3 | 0.560 / 0.594 / 5.408 | 2,592–2,667 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
