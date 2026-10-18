# DSX01-S02: legacy_penalized_split independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 0.032 / 0.135 / 0.140 | 1,644–1,747 |
| fitted_c | 13 | 1 | 0.064 / 0.096 / 0.105 | 1,614–1,747 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
