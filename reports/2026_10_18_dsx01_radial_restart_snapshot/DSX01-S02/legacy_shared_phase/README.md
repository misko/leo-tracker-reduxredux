# DSX01-S02: legacy_shared_phase independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.174 / 0.174 / 0.174 | 1,682–1,682 |
| fitted_c | 13 | 1 | 0.202 / 0.202 / 0.202 | 1,682–1,682 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
