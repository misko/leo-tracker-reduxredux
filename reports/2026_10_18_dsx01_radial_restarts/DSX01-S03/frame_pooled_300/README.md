# DSX01-S03: frame_pooled_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.065 / 1.129 / 1.893 | 2,338–2,338 |
| fitted_c | 13 | 2 | 1.102 / 1.166 / 1.955 | 2,338–2,338 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
