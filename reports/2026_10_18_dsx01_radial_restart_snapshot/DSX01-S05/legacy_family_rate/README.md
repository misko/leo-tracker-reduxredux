# DSX01-S05: legacy_family_rate independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 5.301 / 5.388 / 5.447 | 1,574–1,574 |
| fitted_c | 13 | 2 | 5.348 / 5.446 / 5.514 | 1,574–1,574 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
