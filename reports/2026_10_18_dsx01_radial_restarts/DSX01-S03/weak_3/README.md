# DSX01-S03: weak_3 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.870 / 0.924 / 1.067 | 2,259–2,315 |
| fitted_c | 13 | 1 | 0.869 / 0.923 / 1.068 | 2,259–2,315 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
