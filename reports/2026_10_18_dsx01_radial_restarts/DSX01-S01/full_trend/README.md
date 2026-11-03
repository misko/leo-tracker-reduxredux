# DSX01-S01: full_trend independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 1.002 / 1.035 / 5.236 | 2,592–2,742 |
| fitted_c | 13 | 3 | 0.986 / 1.023 / 5.240 | 2,592–2,742 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
