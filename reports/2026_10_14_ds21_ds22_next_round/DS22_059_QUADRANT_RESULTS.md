# DS22-059: preserved starts plus training-selected quadrant coverage

All 27 new fits were strictly accepted, but expanding training-derived basin coverage did not repair the combined estimate. Both half selectors changed to the same added basin; the full selector retained an original basin. No model or baseline was promoted.

The prespecified policy retained six original starts and added the best existing coarse training point in each geographical quadrant. The northeast point duplicated an original center, leaving three additional starts. Their candidate union contains 61 satellites, including all original 50. Each of the three views used the same union and original calibration frame, clock basis, priors, and exact transported satellite timing. Domains remained the respective original 25 km disks. Neither reference nor held observations selected seeds or winners.

Qualification used 41 objective calls and zero optimizer fits per view: exact physical transport, orbit and calibration closure, gradient checks, domain feasibility, and an independent audit of the transported original winner. Original winners were not stationary in the new union and therefore were not grandfathered into eligibility. The unchanged original matrices remain separate controls.

| View | Six-start union objective | Nine-start union objective | Six-start configured distance (km) | Nine-start configured distance (km) |
|---|---:|---:|---:|---:|
| CH1–8 | 47092.676013 | 47092.676013 | 271.245859 | 271.245859 |
| CH1–4 | 27474.791498 | 26731.840704 | 364.993160 | 138.188405 |
| CH5–8 | 20158.780989 | 20032.794316 | 206.296755 | 140.759736 |

All 9/9 fits in each view passed strict acceptance. The added northwest start (ordinal 6, coarse center −50, +50 km) won both halves. Its full-view objective was 47164.886647, 72.210635 worse than the retained full winner. Thus this coverage addition reaches a shared half-preferred basin but does not make it win the combined objective. This does not establish that another basin or nuisance initialization cannot improve the result.

Each fit retained 20 seconds and 600 original optimizer iterations; these are iteration caps, not a 600-total-objective-call claim. Nine three-fit units ran on four workers in 98.136 seconds wall time. All 27 calls and their strict audits were sealed before the configured reference join. The two selectors are nested subsets of the same 61-satellite fit results; objectives are not compared across the original 50-satellite and new 61-satellite banks.

Source commits: qualification `b2e8c1e11`, control `995ffed06`, evaluator `ac9d59287`. Namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-059-quadrant-control-v1`; terminal SHA256 `33de394aa8647bf7909e2048a6a005d2ab124d7dfc0e341ce00e413a7b9345e8`. Comparison: adjacent `ds22-059-quadrant-comparison-v1/report.json`.

Distances use the existing configured station, unconfirmed for DS22. This is shared-discovery channel comparison, not independent half discovery. Added search cost is 27 fits, and no accuracy-target claim is permitted.
