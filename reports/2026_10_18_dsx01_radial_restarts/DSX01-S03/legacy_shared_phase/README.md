# DSX01-S03: legacy_shared_phase independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.231 / 1.231 / 1.231 | 1,957–1,957 |
| fitted_c | 13 | 1 | 1.292 / 1.292 / 1.292 | 1,920–1,920 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
