# DSX01-S04: corr_4_0p9 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 7 | 1.727 / 2.258 / 3.714 | 2,253–2,330 |
| fitted_c | 13 | 7 | 1.746 / 2.286 / 3.707 | 2,253–2,330 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
