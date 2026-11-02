# Independent position reporting review

The postdecision position report passes. `position_reporting_audit.json` binds
the reviewed files: positions SHA
`baf83bb7c2ebdfbfbab059c99eaf9336b1b7485d19fd966fe7859855bafc4365`
and statistics SHA
`908e7253cbba97deec722789c212b690ed01f65d1b81f619bc1fe997157f8a7e`.
No inference, source or result was changed for this audit.

All 205 published ALGO07 baselines were mapped to their authoritative saved
guarded final endpoints: the readiness population audit for DS26/27/28 and saved
candidate outputs for DS24/FRSH. The independent implementation of the documented
east/north chart and spherical distance reproduces all 2,050 case/arm/method
errors within `9.1e-13 m`. Raw input `baseline_arms` can be an earlier seed:
48 arms in 24 recordings differ from their published baseline. This includes the
three accepted association repairs and intervening ALGO06 recovery outcomes.
Using those seed coordinates directly would be the wrong comparator; the report
correctly inherits the published guarded outputs.

Every rejected Age3/Age2 output exactly equals selected A. Every accepted output
is scored at its sealed raw endpoint. ALGO07, A and B retain the previous outputs,
source labels and acceptance flags. Associated counts are identical for every
method and arm, totaling 642,355 per method/arm. The full denominator is 205:
DS24 25, DS26 148, DS27 13, DS28 14 and FRSH 5. All 60 cohort/arm/method statistics
were independently recomputed, including interpolation quantiles, strict 500 m
and 50 m cutoffs, contrasts, tails and association sums. Maximum discrepancy is
`4.55e-13 m`. CSV and JSON summaries agree.

| Fitted-c method | Mean km | Median km | Below 500 m |
| --- | ---: | ---: | ---: |
| ALGO07 | 1.155382 | 0.923383 | 38/205 |
| A | 1.151895 | 0.923381 | 38/205 |
| B | 1.137756 | 0.923381 | 41/205 |
| Age3 | 1.147556 | 0.917704 | 38/205 |
| Age2 | 1.151660 | 0.920795 | 38/205 |

The primary Age3 result changes only five cases. Relative to selected A, its
fitted-c mean improves by 4.338 m across the whole cohort, with three improvements
over 50 m, no regressions over 50 m and a 28.569 m maximum regression. This small
same-site development sample cannot establish a calibrated prior or tail safety.

The exploratory Age2 result changes 27 cases. Its fitted-c mean improves by only
0.235 m relative to A, while c=0 worsens by 0.207 m. Both arms have seven
improvements and five regressions over 50 m relative to A. Fitted-c regressions
include DS26-0315 (+664.121 m) and FRSH-0004 (+586.009 m); DS26-0309 improves by
685.581 m. Age matching therefore does not resolve the prior's localization
sensitivity. Comparisons against B involve substantially different adoption
coverage, so a smaller observed tail is not an independent risk-control result.

These checks support truthful reporting and exact fallback accounting. They do
not support production promotion or a claim of typical 500 m localization.
