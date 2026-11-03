# DSX01-S02: linear_shape independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.047 / 1.063 / 1.080 | 2,334–2,334 |
| fitted_c | 13 | 1 | 1.085 / 1.102 / 1.116 | 2,334–2,334 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
