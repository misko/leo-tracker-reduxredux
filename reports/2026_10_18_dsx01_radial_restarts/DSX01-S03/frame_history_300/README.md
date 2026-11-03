# DSX01-S03: frame_history_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.929 / 0.952 / 1.651 | 2,252–2,287 |
| fitted_c | 13 | 2 | 0.955 / 0.975 / 1.704 | 2,252–2,287 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
