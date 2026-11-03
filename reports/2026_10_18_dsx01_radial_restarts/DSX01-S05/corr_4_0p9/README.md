# DSX01-S05: corr_4_0p9 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 2.034 / 2.402 / 2.680 | 1,934–2,053 |
| fitted_c | 13 | 2 | 2.022 / 2.391 / 2.668 | 1,934–2,053 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
