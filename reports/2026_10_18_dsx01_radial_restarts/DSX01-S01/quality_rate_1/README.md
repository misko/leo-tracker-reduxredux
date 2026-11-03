# DSX01-S01: quality_rate_1 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.685 / 0.721 / 5.540 | 2,538–2,706 |
| fitted_c | 13 | 3 | 0.665 / 0.701 / 5.542 | 2,538–2,706 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
