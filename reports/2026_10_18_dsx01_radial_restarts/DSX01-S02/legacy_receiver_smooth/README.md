# DSX01-S02: legacy_receiver_smooth independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.649 / 0.649 / 1.109 | 1,967–2,027 |
| fitted_c | 13 | 1 | 0.606 / 0.606 / 1.064 | 2,003–2,063 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
