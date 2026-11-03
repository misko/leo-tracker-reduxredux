# DSX01-S02: legacy_correlated_noise independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 1 | 1.052 / 1.052 / 1.052 | 2,183–2,183 |
| fitted_c | 13 | 1 | 1.031 / 1.031 / 1.031 | 2,183–2,183 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
