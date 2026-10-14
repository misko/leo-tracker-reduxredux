# DS22: 21 original development matrices sealed

Twenty-one of 44 available development captures now have complete original A/B/C matrices and post-seal configured-reference comparisons. Three C-all estimates are unavailable because no start passed unchanged stationarity: 047, 059 and 063. All three failures remain in the coverage denominator; no prototype results replace these matrices.

| Model | Available full estimates | Median configured distance km | Below 1 km | Below 0.5 km | Full no worse than both halves | Full worse than both halves |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 21/21 | 1.820246 | 5/21 | 2/21 | Not a standalone-half comparison | Not a standalone-half comparison |
| B | 21/21 | 1.681891 | 7/21 | 4/21 | 16/21 | 2/21 |
| C | 18/21 | 2.609793 | 2/21 | 0/21 | 4/18 available pairs | 5/18 available pairs |

Medians use available estimates, whereas threshold counts retain all 21 attempted cases. On the same 18 cases with all three full estimates available, medians are A 1.845663, B 1.691160 and C 2.609793 km. C's available median must not be compared as if its three failed cases were successful. The halves share discovery and initialization; they are not independent half-only controls. DS22 station continuity remains unconfirmed, so these are configured-reference distances, not verified accuracy or evidence that the target is achieved.

The five new captures are:

| DS22 case | A all | B all | B low | B high | C all | C low | C high |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 059 | 312.411408 | 273.125376 | 314.147091 | 298.257056 | Unavailable | 312.824461 | 307.991885 |
| 061 | 15.637126 | 14.766866 | 3.411536 | 1.453740 | 3.806665 | 4.683200 | 3.386833 |
| 063 | 0.774075 | 0.221429 | 4.973095 | 5.194115 | Unavailable | 3.284823 | 2.310748 |
| 065 | 0.878663 | 0.348599 | 3.734339 | 2.745941 | 0.789613 | 2.106012 | 10.587531 |
| 067 | 0.326204 | 1.198228 | 3.705449 | 1.944119 | 2.363963 | 4.160763 | 2.044262 |

059 is now the most severe observed development failure; 019 is second. 059 is poor across all available full and half estimates, which makes shared discovery, candidate and search-domain evidence a priority before attributing its failure to combining bands. This is a hypothesis, not a demonstrated cause. 061 separately adds a clear B full-view regression relative to both halves. 063 combines good A/B results with a C optimization failure, so it requires a different diagnosis from 059.

All six C-all starts were ineligible for both 059 and 063. Their KKT ranges were 82.789–2432.304 and 196.888–11062.130, respectively; the 0.001 acceptance threshold was not relaxed. The matched original models used fitted c throughout. The B053 endpoint continuation and all native-clock/calibration prototypes remain separate experiments.

Complete evaluated labels: 001, 003, 017, 019, 029, 031, 033, 035, 037, 039, 041, 043, 045, 047, 053, 055, 059, 061, 063, 065, 067. The new five matrices and comparisons are under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-models-v1` and `ds22-runtime-configured-comparison-v1`. Their 30 B/C units completed the finite six-worker wave in 457.407 seconds, with all process receipts complete. Scientific nonstationarity remains distinct from successful process completion.
