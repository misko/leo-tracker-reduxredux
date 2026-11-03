# DSX01-S01: quality independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.628 / 0.664 / 5.264 | 2,507–2,706 |
| fitted_c | 13 | 2 | 0.609 / 0.645 / 5.264 | 2,507–2,706 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
