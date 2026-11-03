# DSX01-S03: linear_white_joint independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.185 / 1.251 / 1.947 | 2,700–2,700 |
| fitted_c | 13 | 2 | 1.204 / 1.270 / 1.984 | 2,665–2,700 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
