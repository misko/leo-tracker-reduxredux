# DSX01-S05: frame_eccentric_300 independent-start results

Each start independently reruns satellite discovery/association and localization on fixed archived GLRT observations and graph tracks. This is a basin-of-attraction experiment, not a pointwise loss or probability surface. GPS is used by this reporter only.

| Arm | Starts | Endpoint groups | Error min / median / max (km) | Associated points min–max |
| --- | ---: | ---: | --- | --- |
| c0 | 13 | 2 | 1.930 / 2.016 / 2.537 | 1,934–2,100 |
| fitted_c | 13 | 2 | 1.917 / 2.003 / 2.517 | 1,934–2,100 |

![Independent-start endpoint groups](restart_basins.png)

![Final objective by start](restart_loss.png)
