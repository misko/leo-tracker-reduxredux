# DS22 original models: fifteen sealed matrices, one unavailable full estimate

DS22-047 and DS22-053 bring the original fitted-`c` campaign to fifteen sealed development matrices. C-all is unavailable on 047 because all six starts fail the unchanged stationarity requirement. No rejected estimate replaces it, and no failed start was retried. Distances remain configured-unconfirmed; station continuity with DS22 has not been verified.

| Model | Full estimates / attempted cases | Median available full distance (km) | Below 1 km / attempts | Below 0.5 km / attempts | Full no worse than both / comparable | Full worse than both / comparable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 15/15 | 1.820246 | 2/15 | 1/15 | — | — |
| B | 15/15 | 1.681891 | 5/15 | 2/15 | 11/15 | 1/15 |
| C | 14/15 | 3.213268 | 1/15 | 0/15 | 2/14 | 5/14 |

The fourteen common-complete cases exclude 047 for all three models; their A/B/C medians are 1.861560 / 1.750567 / 3.213268 km. The available-case table has different denominators and must not be interpreted as a matched model comparison.

| New case/model | CH1–8 (km) | CH1–4 (km) | CH5–8 (km) |
| --- | ---: | ---: | ---: |
| 047 A | 1.479757 | — | — |
| 047 B | 1.540625 | 1.945996 | 3.033974 |
| 047 C | unavailable | 3.216082 | 4.600712 |
| 053 A | 56.741900 | — | — |
| 053 B | 52.953753 | 78.290403 | 33.184760 |
| 053 C | 75.781770 | 27.083146 | 30.491824 |

On 047, all six C-all calls reached the 20-second bound after 233–278 evaluations, with KKT residuals 1813–9226. Their complete receipts and failed acceptance outcomes remain preserved. The pipeline itself completed and sealed before evaluation. Wall-clock capped fits were run during the authorized parallel campaign; no claim is made that scheduling has zero effect on convergence.

Within this early original-model cohort, 019 remains the worst full estimate for A/B/C and 053 becomes the second worst for all three. This is descriptive configured-reference ranking, not a seed or hyperparameter selection rule. Mechanistic experiments on 001 remain separate from cohort results.

The fifteen labels are 001, 003, 017, 019, 029, 031, 033, 035, 037, 039, 041, 043, 045, 047 and 053. The frozen inventory has 44 available development cases, one unavailable development member (137), and 24 locked fast-scan members. No locked member was evaluated. B/C half views share full-band discovery and initialization; they are not independent half-only discovery controls. A requires both bands.

The first thirteen records are documented in `DS22_THIRTEEN_CASE_RESULTS.md`. New matrices and postseal comparisons are under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-models-v1/DS22-047` and `DS22-053`, with corresponding `ds22-runtime-configured-comparison-v1` directories. No experimental native-clock, transport, prior or expanded-calibration fit is mixed into these original-model results.
