# DSX01-S03: legacy_receiver_smooth independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.944 / 1.825 / 2.160 | 2,212–2,277 |
| fitted_c | 13 | 2 | 0.966 / 1.858 / 2.200 | 2,212–2,277 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
