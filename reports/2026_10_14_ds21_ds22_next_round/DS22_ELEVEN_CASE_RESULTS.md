# Eleven sealed DS22 development cases

The original fitted-c A/B/C pipeline now has complete sealed matrices for 11 development cases. DS22-039 and DS22-041 add coverage using the qualified runtime authority and unchanged scientific model/search budgets. Experimental native-clock and profile controls are excluded from this table. The configured station reference remains unconfirmed: these are conditional distances, not verified position accuracy.

| DS22 | A all | B all | B low | B high | C all | C low | C high |
|---|---:|---:|---:|---:|---:|---:|---:|
| 001 | 3.749661 | 0.785018 | 3.555036 | 6.439582 | 21.266493 | 23.645468 | 12.163078 |
| 003 | 1.902873 | 1.819243 | 2.809257 | 2.828654 | 2.827544 | 4.132040 | 1.642876 |
| 017 | 1.532290 | 3.059303 | 2.463027 | 1.638150 | 3.769500 | 3.303248 | 2.041561 |
| 019 | 107.370561 | 113.239176 | 166.428391 | 154.377371 | 142.113760 | 203.397332 | 214.750950 |
| 029 | 3.295860 | 0.841030 | 4.087276 | 2.133234 | 2.392042 | 5.988144 | 0.796146 |
| 031 | 0.167694 | 0.510263 | 1.027309 | 3.017607 | 1.168599 | 2.257453 | 5.789828 |
| 033 | 1.792648 | 1.478085 | 0.412314 | 1.927076 | 1.975060 | 1.089769 | 3.424093 |
| 035 | 0.597302 | 0.289159 | 0.695143 | 0.877737 | 0.507331 | 0.314609 | 1.203222 |
| 037 | 1.802466 | 3.967119 | 4.429467 | 17.266241 | 6.425482 | 4.687716 | 16.780770 |
| 039 | 3.415945 | 3.406492 | 3.760862 | 3.436588 | 1.841818 | 1.392355 | 0.293043 |
| 041 | 3.168006 | 1.681891 | 2.469795 | 4.922846 | 3.598992 | 3.243279 | 2.235963 |

All values are kilometres. CH1–4 and CH5–8 controls here share discovery/proposals with the full pipeline; they are not the separately computed independent-discovery half controls. A's sequential path has no standalone A-half counterpart.

| Metric | A | B | C |
|---|---:|---:|---:|
| Median CH1–8 distance | 1.902873 | 1.681891 | 2.827544 |
| CH1–8 below 1 km | 2/11 | 4/11 | 1/11 |
| CH1–8 below 0.5 km | 1/11 | 1/11 | 0/11 |
| CH1–8 no worse than both conditional halves | — | 9/11 | 2/11 |
| CH1–8 worse than both conditional halves | — | 1/11 | 3/11 |

DS22-019 remains the largest full-band distance for all three models. Second largest is 001 for A and C, and 037 for B. C is farther than B on 10/11 cases; 039 is the exception. The accuracy targets remain unmet even against the conditional configured reference. This is 11 of 44 available development cases, not the full development or locked cohort, and adding cases is not a matched algorithm improvement.

Evidence: original seven `local/ds22-configured-comparison-v1/DS22-{001,003,017,019,029,031,033}/comparison.json`; qualified-runtime four `local/ds22-runtime-configured-comparison-v1/DS22-{035,037,039,041}/comparison.json`. Each derives only from a complete 12-unit matrix seal; training selectors were frozen before evaluation. No experimental endpoint was substituted.
