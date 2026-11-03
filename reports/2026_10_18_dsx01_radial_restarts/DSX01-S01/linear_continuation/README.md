# DSX01-S01: linear_continuation independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.515 / 0.544 / 4.865 | 2,570–2,684 |
| fitted_c | 13 | 2 | 0.499 / 0.531 / 4.868 | 2,570–2,684 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
