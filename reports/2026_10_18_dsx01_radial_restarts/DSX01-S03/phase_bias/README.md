# DSX01-S03: phase_bias independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.289 / 0.427 / 1.510 | 2,303–2,338 |
| fitted_c | 13 | 2 | 0.291 / 0.430 / 1.514 | 2,303–2,338 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
