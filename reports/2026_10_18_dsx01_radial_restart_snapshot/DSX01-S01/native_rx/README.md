# DSX01-S01: native_rx independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 1 | 1 | 0.519 / 0.519 / 0.519 | 2,706–2,706 |
| fitted_c | 1 | 1 | 0.507 / 0.507 / 0.507 | 2,706–2,706 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
