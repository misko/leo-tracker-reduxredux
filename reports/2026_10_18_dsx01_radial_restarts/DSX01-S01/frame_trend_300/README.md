# DSX01-S01: frame_trend_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 1.013 / 1.048 / 5.186 | 2,532–2,742 |
| fitted_c | 13 | 3 | 0.997 / 1.036 / 5.188 | 2,532–2,742 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
