# DSX01-S05: tail_4 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.626 / 1.966 / 2.400 | 1,934–1,985 |
| fitted_c | 13 | 2 | 1.605 / 1.952 / 2.385 | 1,934–1,985 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
