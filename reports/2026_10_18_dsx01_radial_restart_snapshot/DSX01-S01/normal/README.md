# DSX01-S01: normal independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.536 / 0.566 / 4.991 | 2,532–2,646 |
| fitted_c | 13 | 2 | 0.522 / 0.554 / 4.991 | 2,532–2,646 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
