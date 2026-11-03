# DSX01-S04: frame_pooled_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 8 | 1.256 / 2.476 / 3.965 | 2,188–2,374 |
| fitted_c | 13 | 8 | 1.223 / 2.516 / 3.978 | 2,188–2,374 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
