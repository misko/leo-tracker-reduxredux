# DSX01-S03: balance_100 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.285 / 1.327 / 2.076 | 2,252–2,252 |
| fitted_c | 13 | 2 | 1.328 / 1.369 / 2.154 | 2,252–2,252 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
