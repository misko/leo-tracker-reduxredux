# DSX01-S02: tail_4 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.906 / 0.923 / 0.939 | 1,973–1,973 |
| fitted_c | 13 | 1 | 0.945 / 0.960 / 0.978 | 1,973–1,973 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
