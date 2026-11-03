# DSX01-S04: diag_6 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 8 | 1.892 / 2.284 / 3.148 | 2,247–2,330 |
| fitted_c | 13 | 8 | 1.950 / 2.307 / 3.192 | 2,247–2,374 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
