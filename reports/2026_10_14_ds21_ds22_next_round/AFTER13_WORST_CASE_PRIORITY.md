# Priorities from 13 matched DS21 development samples

This ranking uses the expanded-discovery CH1–8 fitted-c results in histograms-runtime-009. It excludes subsequent experimental solver, disk-release, and native-clock changes. The companion JSON records all 39 full-band errors, available half-band errors, and source hashes. These are development diagnostics, not untouched validation.

| Model | Largest full-band error | Second largest | Largest excess over best half | Second largest excess |
|---|---|---|---|---|
| A | 029: 116.683 km | 023: 7.759 km | Independent halves unavailable | Independent halves unavailable |
| B | 029: 63.287 km | 031: 6.214 km | 029: +5.778 km | 007: +1.923 km |
| C | 029: 100.199 km | 031: 5.504 km | 029: +25.782 km | 003: +4.310 km |

B and C half-band comparisons share the respective candidate bank; they are conditional comparisons. Do not substitute these for model A's independent half-band controls.

Sample 029 is the highest priority across all models. Its B half-band errors are 84.384 and 57.509 km; its C half-band errors are 85.926 and 74.417 km. Combining bands adds error, but cannot explain the large errors already present in both halves. Candidate coverage and geographic search basins therefore warrant investigation alongside calibration and band combination.

Continue the already frozen model A 023/025 strict-offset experiment, then prioritize 029. For C, the planned all-start boundary screen of before029, before037, and after029 tests whether local geographic constraints obstruct improvement. Keep original outcomes and select subsequent fits by the frozen training criterion, never by reference distance.

The matched cohort remains 13 of 34 development samples. Median errors before → after are A 2.492 → 2.670 km, B 5.044 → 2.390 km, and C 1.957 → 3.323 km. These results do not meet the 0.5 km target.
