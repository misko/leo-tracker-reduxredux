# DSX01-S03: corr_4_0p9 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.865 / 0.926 / 1.774 | 2,252–2,252 |
| fitted_c | 13 | 2 | 0.925 / 0.987 / 1.851 | 2,252–2,252 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
