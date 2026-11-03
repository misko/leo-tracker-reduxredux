# DSX01-S04: quality_rate_1 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 8 | 1.476 / 2.244 / 6.707 | 2,301–2,330 |
| fitted_c | 13 | 9 | 1.508 / 2.278 / 6.712 | 2,284–2,330 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
