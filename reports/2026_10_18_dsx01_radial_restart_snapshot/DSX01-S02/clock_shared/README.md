# DSX01-S02: clock_shared independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.693 / 1.703 / 1.729 | 1,973–1,973 |
| fitted_c | 13 | 1 | 1.704 / 1.714 / 1.739 | 1,973–1,973 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
