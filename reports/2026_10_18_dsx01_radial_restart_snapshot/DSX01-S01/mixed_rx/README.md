# DSX01-S01: mixed_rx independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 1 | 1 | 0.550 / 0.550 / 0.550 | 2,706–2,706 |
| fitted_c | 1 | 1 | 0.538 / 0.538 / 0.538 | 2,706–2,706 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
