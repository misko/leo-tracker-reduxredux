# DSX01-S05: native_rx independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.594 / 2.059 / 2.523 | 2,032–2,035 |
| fitted_c | 13 | 2 | 1.577 / 2.045 / 2.508 | 2,032–2,035 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
