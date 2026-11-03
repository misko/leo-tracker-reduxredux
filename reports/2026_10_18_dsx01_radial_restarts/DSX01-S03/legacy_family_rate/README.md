# DSX01-S03: legacy_family_rate independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.070 / 1.301 / 1.465 | 2,197–2,234 |
| fitted_c | 13 | 2 | 1.103 / 1.362 / 1.526 | 2,197–2,234 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
