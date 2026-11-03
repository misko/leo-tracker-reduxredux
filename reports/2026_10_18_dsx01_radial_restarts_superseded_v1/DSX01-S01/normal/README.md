# DSX01-S01: normal independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 2 | 1 | 0.566 / 0.651 / 0.735 | 2,605–2,646 |
| fitted_c | 2 | 1 | 0.554 / 0.640 / 0.725 | 2,605–2,646 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
