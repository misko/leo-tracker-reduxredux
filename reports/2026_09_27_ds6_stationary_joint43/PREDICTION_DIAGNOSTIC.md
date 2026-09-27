# Within-subset pooled versus independent prediction

The corrected independent and subset-pooled fits use the same training visits, candidate lists, scalar offset profiler, and exact propagation at evaluation. The held-out score differences below are pooled minus independent. No geographic reference is used in this diagnostic. It is a descriptive comparison on reused DS6 observations, not a new validation set or a causal sample-rate experiment.

| Random subset | Rate MS/s | Scans | Total held-out log-score difference |
|---|---:|---:|---:|
| A | 2.5 | 8 | -561.00 |
| A | 5 | 3 | -127.65 |
| A | 7.5 | 3 | -370.41 |
| A | 10 | 8 | -686.56 |
| B | 2.5 | 7 | -174.15 |
| B | 5 | 6 | -264.18 |
| B | 7.5 | 2 | +2.70 |
| B | 10 | 6 | -683.00 |

All 22 subset-A scans and 17 of 21 subset-B scans have lower held-out scores under the shared position. Median per-scan differences are -46.831 and -24.715, respectively. Thus 39/43 scans worsen, spanning all rates; the aggregate loss is not confined to one pathological scan. Totals depend on observation counts and are not normalized cross-rate effect sizes. Rate also varies with capture time and available satellites, so these values do not establish a rate-dependent calibration error.

The subset positions are geographically closer to the reference than many independent estimates, but the physical likelihood prefers different scan-specific geometries even on held-out visits. This supports investigating transferable physical residual structure (for example, orbit- or satellite-associated errors) before adding a strong position prior that merely forces individual outputs toward the pooled estimate. It does not identify the cause or prove that a particular residual correction will improve geography.

Source: the per-scan `held_gain_vs_independent` fields in A.json and B.json, grouped using the rate_hz fields in the element-freshness result files frozen by protocol.json. Whole-visit masks are unchanged. Both subset fits and their independent gradient audits have passed; the full-data fit remains a separate pending result.
