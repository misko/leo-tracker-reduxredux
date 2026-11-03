# DSX01-S01: frame_linked_100 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.545 / 0.575 / 0.741 | 2,641–2,646 |
| fitted_c | 13 | 1 | 0.529 / 0.562 / 0.730 | 2,641–2,646 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
