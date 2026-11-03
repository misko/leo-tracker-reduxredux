# DSX01-S01: rate_0p25 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.538 / 0.568 / 5.042 | 2,532–2,646 |
| fitted_c | 13 | 2 | 0.524 / 0.557 / 5.042 | 2,532–2,646 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
