# DSX01-S05: weak_3 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.576 / 2.815 / 3.345 | 1,926–2,113 |
| fitted_c | 13 | 3 | 0.577 / 2.815 / 3.344 | 1,896–2,113 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
