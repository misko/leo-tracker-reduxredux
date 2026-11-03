# DSX01-S05: linear_shape independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.861 / 0.869 / 1.362 | 2,471–2,551 |
| fitted_c | 13 | 1 | 0.859 / 0.867 / 1.355 | 2,471–2,551 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
