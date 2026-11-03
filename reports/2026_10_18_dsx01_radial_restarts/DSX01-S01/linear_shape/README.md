# DSX01-S01: linear_shape independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.489 / 0.534 / 5.122 | 3,449–3,629 |
| fitted_c | 13 | 2 | 0.475 / 0.522 / 5.121 | 3,449–3,629 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
