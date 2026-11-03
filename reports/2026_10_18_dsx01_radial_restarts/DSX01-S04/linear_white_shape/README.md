# DSX01-S04: linear_white_shape independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 6 | 2.008 / 2.536 / 3.494 | 2,701–2,807 |
| fitted_c | 13 | 6 | 2.041 / 2.587 / 3.514 | 2,701–2,851 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
