# DSX01-S01: balance_100 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 1.033 / 1.076 / 4.384 | 2,308–2,489 |
| fitted_c | 13 | 3 | 1.015 / 1.062 / 4.385 | 2,308–2,489 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
