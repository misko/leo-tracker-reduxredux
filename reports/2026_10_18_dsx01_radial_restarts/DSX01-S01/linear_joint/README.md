# DSX01-S01: linear_joint independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.533 / 0.621 / 5.054 | 3,449–3,629 |
| fitted_c | 13 | 2 | 0.513 / 0.599 / 5.049 | 3,449–3,629 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
