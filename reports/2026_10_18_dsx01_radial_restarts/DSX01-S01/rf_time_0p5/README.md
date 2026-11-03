# DSX01-S01: rf_time_0p5 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.508 / 0.536 / 4.924 | 2,532–2,706 |
| fitted_c | 13 | 2 | 0.493 / 0.524 / 4.929 | 2,532–2,706 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
