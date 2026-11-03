# DSX01-S01: frame_pooled_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.517 / 0.553 / 4.732 | 2,478–2,665 |
| fitted_c | 13 | 3 | 0.503 / 0.542 / 4.729 | 2,478–2,665 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
