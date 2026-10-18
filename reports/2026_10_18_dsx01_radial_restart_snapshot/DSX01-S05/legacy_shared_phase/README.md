# DSX01-S05: legacy_shared_phase independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 3.653 / 3.653 / 3.653 | 1,689–1,689 |
| fitted_c | 13 | 1 | 3.715 / 3.715 / 3.715 | 1,689–1,689 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
