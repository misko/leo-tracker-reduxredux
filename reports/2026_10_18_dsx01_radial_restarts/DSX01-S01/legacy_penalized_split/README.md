# DSX01-S01: legacy_penalized_split independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.104 / 1.104 / 1.108 | 1,994–1,994 |
| fitted_c | 13 | 1 | 1.111 / 1.111 / 1.115 | 1,994–1,994 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
