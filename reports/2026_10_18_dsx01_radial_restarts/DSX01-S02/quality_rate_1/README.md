# DSX01-S02: quality_rate_1 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 0.769 / 0.903 / 1.145 | 1,882–1,973 |
| fitted_c | 13 | 2 | 0.738 / 0.940 / 1.171 | 1,882–1,973 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
