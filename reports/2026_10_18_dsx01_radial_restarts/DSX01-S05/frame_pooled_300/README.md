# DSX01-S05: frame_pooled_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.709 / 2.423 / 2.437 | 1,878–2,045 |
| fitted_c | 13 | 2 | 1.683 / 2.401 / 2.415 | 1,878–2,045 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
