# DS22: 24 original development matrices

Twenty-four of 44 available development captures now have complete original matrices and post-seal configured-reference comparisons. A and B each have 24 available full estimates; C has 20, with 047, 059, 063 and 071 unavailable under unchanged stationarity. Experimental endpoint and clock results are excluded.

| Model | Available full estimates | Available median km | Below 1 km | Below 0.5 km | Full no worse than both halves | Full worse than both halves |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 24/24 | 1.845663 | 6/24 | 2/24 | Not a standalone-half comparison | Not a standalone-half comparison |
| B | 24/24 | 1.611258 | 7/24 | 4/24 | 16/24 | 4/24 |
| C | 20/24 | 2.378003 | 3/24 | 0/24 | 4/20 available pairs | 6/20 available pairs |

On the same 20 complete cases, median distances are A 1.886977, B 1.579988 and C 2.378003 km. Threshold counts retain all 24 attempted captures, while medians exclude unavailable estimates. The reference is configured but DS22 station continuity remains unconfirmed: these are not verified accuracy measurements. Halves share original full discovery and initialization.

| New case | A all | B all | B low | B high | C all | C low | C high |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 057 | 2.709229 | 1.393711 | 0.529779 | 0.999292 | 1.658898 | 0.829477 | 1.252635 |
| 069 | 20.452789 | 1.109896 | 4.776220 | 0.999127 | 0.895536 | 0.476486 | 1.811900 |
| 071 | 0.761270 | 324.778372 | 10.222348 | 3.123934 | Unavailable | 1.257135 | 3.394758 |

071 now has the worst observed single full-model distance, driven by B's combined fit despite much better halves and A. 059 remains the broadest severe failure across available full and half estimates. 019 and 053 remain important earlier failures, while 061 and now 057 add combined-view regressions. These distinct patterns require separate diagnosis; a single worst-case ranking should not obscure which model or channel comparison failed.

The prior 21 labels and results are retained in `DS22_TWENTY_ONE_CASE_RESULTS.md`; this update adds 057, 069 and 071. Their original models and post-seal evidence are under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-models-v1` and `ds22-runtime-configured-comparison-v1`. No original failures were retried or replaced, and no accuracy-target success is claimed.
