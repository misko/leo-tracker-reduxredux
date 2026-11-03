# DSX01-S03: rf_time_2 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.047 / 1.100 / 1.839 | 2,252–2,287 |
| fitted_c | 13 | 2 | 1.085 / 1.139 / 1.905 | 2,252–2,252 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
