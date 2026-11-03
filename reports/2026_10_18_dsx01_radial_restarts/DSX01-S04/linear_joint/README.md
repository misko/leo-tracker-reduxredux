# DSX01-S04: linear_joint independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 6 | 1.751 / 2.264 / 3.620 | 2,701–2,807 |
| fitted_c | 13 | 6 | 1.771 / 2.296 / 3.637 | 2,701–2,807 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
