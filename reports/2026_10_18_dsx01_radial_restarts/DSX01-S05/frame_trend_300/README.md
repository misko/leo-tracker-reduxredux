# DSX01-S05: frame_trend_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.614 / 2.160 / 2.552 | 1,934–1,934 |
| fitted_c | 13 | 2 | 1.589 / 2.141 / 2.530 | 1,934–1,934 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
