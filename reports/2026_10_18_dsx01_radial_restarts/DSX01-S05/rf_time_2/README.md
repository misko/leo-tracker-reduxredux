# DSX01-S05: rf_time_2 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.849 / 1.899 / 2.400 | 2,031–2,031 |
| fitted_c | 13 | 2 | 1.833 / 1.883 / 2.382 | 2,031–2,031 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
