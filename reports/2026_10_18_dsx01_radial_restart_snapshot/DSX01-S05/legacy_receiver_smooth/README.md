# DSX01-S05: legacy_receiver_smooth independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 2.155 / 2.155 / 2.957 | 2,062–2,140 |
| fitted_c | 13 | 2 | 2.175 / 2.175 / 2.985 | 2,062–2,140 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
