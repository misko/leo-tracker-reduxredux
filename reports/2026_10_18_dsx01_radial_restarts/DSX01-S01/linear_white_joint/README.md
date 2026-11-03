# DSX01-S01: linear_white_joint independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.492 / 0.515 / 5.046 | 3,449–3,629 |
| fitted_c | 13 | 2 | 0.479 / 0.502 / 5.044 | 3,449–3,629 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
