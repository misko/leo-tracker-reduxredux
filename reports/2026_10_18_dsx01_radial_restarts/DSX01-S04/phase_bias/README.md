# DSX01-S04: phase_bias independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 8 | 1.889 / 2.416 / 3.642 | 2,177–2,275 |
| fitted_c | 13 | 8 | 1.890 / 2.419 / 3.644 | 2,177–2,275 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
