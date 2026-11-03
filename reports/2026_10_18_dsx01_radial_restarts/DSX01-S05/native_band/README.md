# DSX01-S05: native_band independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.537 / 1.549 / 1.686 | 2,266–2,266 |
| fitted_c | 13 | 1 | 1.526 / 1.538 / 1.673 | 2,266–2,266 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
