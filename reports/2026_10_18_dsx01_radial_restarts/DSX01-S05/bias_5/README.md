# DSX01-S05: bias_5 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.900 / 2.265 / 2.844 | 1,985–2,032 |
| fitted_c | 13 | 2 | 1.899 / 2.264 / 2.843 | 1,985–2,032 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
