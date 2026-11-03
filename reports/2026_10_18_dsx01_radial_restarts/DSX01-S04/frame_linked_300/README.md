# DSX01-S04: frame_linked_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 6 | 1.751 / 2.127 / 2.938 | 2,276–2,330 |
| fitted_c | 13 | 6 | 1.777 / 2.178 / 2.964 | 2,276–2,330 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
