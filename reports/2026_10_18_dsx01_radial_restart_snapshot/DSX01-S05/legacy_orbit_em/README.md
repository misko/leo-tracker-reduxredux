# DSX01-S05: legacy_orbit_em independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 4.051 / 4.051 / 4.055 | 1,624–1,624 |
| fitted_c | 13 | 1 | 4.089 / 4.089 / 4.105 | 1,624–1,624 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
