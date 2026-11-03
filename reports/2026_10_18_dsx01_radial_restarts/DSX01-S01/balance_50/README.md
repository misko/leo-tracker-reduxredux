# DSX01-S01: balance_50 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.992 / 1.023 / 10.231 | 2,154–2,489 |
| fitted_c | 13 | 3 | 0.973 / 1.007 / 10.231 | 2,154–2,489 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
