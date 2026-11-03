# DSX01-S01: phase_bias independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 3 | 0.327 / 0.372 / 5.574 | 2,296–2,742 |
| fitted_c | 13 | 3 | 0.327 / 0.372 / 5.574 | 2,245–2,742 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
