# DSX01-S04: tail_4 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 7 | 0.694 / 1.821 / 3.124 | 2,276–2,330 |
| fitted_c | 13 | 7 | 0.688 / 1.847 / 3.153 | 2,276–2,330 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
