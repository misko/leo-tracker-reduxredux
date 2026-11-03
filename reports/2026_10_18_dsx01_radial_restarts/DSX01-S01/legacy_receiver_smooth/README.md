# DSX01-S01: legacy_receiver_smooth independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.790 / 1.815 / 3.001 | 2,030–2,471 |
| fitted_c | 13 | 2 | 1.792 / 1.816 / 2.995 | 2,030–2,471 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
