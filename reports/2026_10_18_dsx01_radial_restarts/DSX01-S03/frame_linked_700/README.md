# DSX01-S03: frame_linked_700 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.015 / 1.067 / 1.800 | 2,252–2,287 |
| fitted_c | 13 | 2 | 1.051 / 1.104 / 1.864 | 2,252–2,287 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
