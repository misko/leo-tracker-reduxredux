# DSX01-S01: frame_linked_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.546 / 0.577 / 4.641 | 2,532–2,646 |
| fitted_c | 13 | 2 | 0.531 / 0.565 / 4.641 | 2,532–2,646 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
