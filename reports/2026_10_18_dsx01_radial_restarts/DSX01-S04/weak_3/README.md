# DSX01-S04: weak_3 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 7 | 0.343 / 1.632 / 3.016 | 2,177–2,275 |
| fitted_c | 13 | 7 | 0.336 / 1.631 / 3.018 | 2,177–2,275 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
