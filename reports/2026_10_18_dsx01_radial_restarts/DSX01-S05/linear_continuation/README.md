# DSX01-S05: linear_continuation independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.807 / 1.841 / 2.359 | 1,943–1,943 |
| fitted_c | 13 | 2 | 1.790 / 1.824 / 2.340 | 1,943–1,943 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
