# DSX01-S02: linear_joint independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.936 / 0.953 / 0.967 | 2,334–2,334 |
| fitted_c | 13 | 1 | 0.989 / 1.006 / 1.020 | 2,334–2,334 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
