# DSX01-S02: weak_3 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 2.022 / 2.201 / 2.246 | 1,932–1,937 |
| fitted_c | 13 | 1 | 2.028 / 2.204 / 2.250 | 1,932–1,937 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
