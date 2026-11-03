# DSX01-S05: phase_bias independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.662 / 2.053 / 2.632 | 2,032–2,104 |
| fitted_c | 13 | 2 | 1.661 / 2.052 / 2.631 | 2,032–2,104 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
