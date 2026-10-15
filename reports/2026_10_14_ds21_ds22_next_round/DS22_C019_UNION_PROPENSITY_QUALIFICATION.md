# DS22-019 expanded-bank propensity qualification

The actual 67-satellite propensity wrapper passed four source-bound qualifications, with 139 objective evaluations per state and no localization fits. Each state was chosen by accepted training objective within its model × original/coarse group. This establishes the implementation and derivative checks required for the bounded profile/release experiment; it does not demonstrate improved localization or prediction.

| Native model | Source ordinal | Qualification seconds | Maximum theta FD discrepancy | Zero-tail full KKT |
|---|---:|---:|---:|---:|
| No common clock | original 0 | 54.232 | 1.092e-7 | 116.666 |
| No common clock | coarse 16 | 52.094 | 1.013e-7 | 143.587 |
| Common clock | original 0 | 55.188 | 1.073e-7 | 127.436 |
| Common clock | coarse 12 | 54.459 | 1.043e-7 | 238.058 |

All 66 orthonormal propensity coordinates were centrally differenced at nonzero theta=0.1*cos(index), step1e-4. Checks include original objective/NLL, legacy wrapper physical/nuisance gradients and posteriors, conditional normalization, zero-tail objective/gradient/posterior nesting, dense prediction gradients, the basis-transformed theta gradient and its prior, zero-sum logits gradient, original domains and exact initialization. All original conditional incumbents retain strict stationarity. Every zero-tail expanded state fails the full expanded KKT gate: they are feasible objective bounds, not eligible expanded-model winners.

The first qualifier for no-clock coarse16 stopped before any objective or fit because the original fitter introduced its inward timing margin, a 9.109371e-10 chart-coordinate change. That failed receipt and the three successful original qualifiers remain unchanged. A distinct frozen recovery first ran a zero-objective physical-delta diagnostic: the absolute satellite timing change was 1.000004793e-9 seconds, below the declared1.1e-9 cap; geography, calibration and nuisance were exactly unchanged, and applying the initializer again was bitwise stable. Raw constraint minimum was −3.55e-15, within the original feasibility tolerance. Only this recovered state was qualified again. Its maximum source replay discrepancy was 3.207242e-8, below the unchanged1e-7 source threshold; the other three maximum closure discrepancies were at most6.013e-12.

The authoritative set therefore contains 556 objective evaluations, zero fits, one preserved pre-objective failure and one explicit zero-objective timing diagnostic. Original source states are reused except for the disclosed existing-fitter timing normalization on coarse16. No candidate, receiver alias, domain, prior, KKT threshold or reference-derived choice changed.

Sources: original qualifier `3d001e27f`, separate recovery and numerical driver `633f7cd68`, evaluator binding `4d8a44dfd`. Fifteen original qualifier/wrapper tests, nine recovery/profile tests and seven profile/evaluator tests passed; Ruff was clean. Namespaces under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/`: `ds22-c019-union-propensity-qualification-v1`, `ds22-c019-propensity-margin-recovery-v1`, and separately frozen numerical `ds22-c019-union-propensity-profiles-v1`.

Four fixed-geography propensity profiles are now authorized under the published protocol. All four must finish before any accepted-source free release. No reference, held or locked data were read by qualification. No fit outcome is asserted in this report.
