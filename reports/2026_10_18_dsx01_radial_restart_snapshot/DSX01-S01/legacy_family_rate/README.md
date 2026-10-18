# DSX01-S01: legacy_family_rate independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.944 / 1.944 / 2.015 | 2,354–2,354 |
| fitted_c | 13 | 1 | 1.857 / 1.857 / 1.938 | 2,354–2,354 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
