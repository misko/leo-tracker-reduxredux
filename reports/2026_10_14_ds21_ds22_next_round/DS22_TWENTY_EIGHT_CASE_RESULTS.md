# DS22: 28 completed original development matrices

These are unchanged fitted-c baseline matrices, not a mixture of experimental fixes. The frozen inventory contains 44 available development inputs, one unavailable development member, and 24 locked cases. Sixteen available development matrices remain outstanding. Reference distances use the existing configured station, whose continuity for DS22 remains unconfirmed; they are not verified accuracy measurements.

| Model | Available full estimates | Median configured distance (km) | Below 1 km | Below 0.5 km | Full no worse than both halves | Full worse than both halves |
|---|---:|---:|---:|---:|---:|---:|
| A | 28/28 | 2.306051 | 6/28 | 2/28 | Not a standalone half model | Not a standalone half model |
| B | 28/28 | 1.759836 | 7/28 | 4/28 | 19/28 | 4/28 |
| C | 24/28 | 2.349699 | 4/24 | 0/24 | 5/24 | 7/24 |

C full estimates remain unavailable on 047, 059, 063, and 071 because no eligible accepted estimate was selected. On the same 24 available cases, medians are A 2.938618, B 1.759836, and C 2.349699 km. Availability is retained explicitly rather than replacing failures with favorable estimates.

| Case | A all | B all | B low | B high | C all | C low | C high |
|---|---:|---:|---:|---:|---:|---:|---:|
| 001 | 3.750 | 0.785 | 3.555 | 6.440 | 21.266 | 23.645 | 12.163 |
| 003 | 1.903 | 1.819 | 2.809 | 2.829 | 2.828 | 4.132 | 1.643 |
| 017 | 1.532 | 3.059 | 2.463 | 1.638 | 3.769 | 3.303 | 2.042 |
| 019 | 107.371 | 113.239 | 166.428 | 154.377 | 142.114 | 203.397 | 214.751 |
| 029 | 3.296 | 0.841 | 4.087 | 2.133 | 2.392 | 5.988 | 0.796 |
| 031 | 0.168 | 0.510 | 1.027 | 3.018 | 1.169 | 2.257 | 5.790 |
| 033 | 1.793 | 1.478 | 0.412 | 1.927 | 1.975 | 1.090 | 3.424 |
| 035 | 0.597 | 0.289 | 0.695 | 0.878 | 0.507 | 0.315 | 1.203 |
| 037 | 1.802 | 3.967 | 4.429 | 17.266 | 6.425 | 4.688 | 16.781 |
| 039 | 3.416 | 3.406 | 3.761 | 3.437 | 1.842 | 1.392 | 0.293 |
| 041 | 3.168 | 1.682 | 2.470 | 4.923 | 3.599 | 3.243 | 2.236 |
| 043 | 1.820 | 1.947 | 1.424 | 2.659 | 1.830 | 1.511 | 0.984 |
| 045 | 1.495 | 0.155 | 1.136 | 2.361 | 3.989 | 1.101 | 4.506 |
| 047 | 1.480 | 1.541 | 1.946 | 3.034 | unavailable | 3.216 | 4.601 |
| 053 | 56.742 | 52.954 | 78.290 | 33.185 | 75.782 | 27.083 | 30.492 |
| 055 | 1.871 | 1.700 | 2.355 | 2.830 | 2.335 | 2.766 | 2.729 |
| 057 | 2.709 | 1.394 | 0.530 | 0.999 | 1.659 | 0.829 | 1.253 |
| 059 | 312.411 | 273.125 | 314.147 | 298.257 | unavailable | 312.824 | 307.992 |
| 061 | 15.637 | 14.767 | 3.412 | 1.454 | 3.807 | 4.683 | 3.387 |
| 063 | 0.774 | 0.221 | 4.973 | 5.194 | unavailable | 3.285 | 2.311 |
| 065 | 0.879 | 0.349 | 3.734 | 2.746 | 0.790 | 2.106 | 10.588 |
| 067 | 0.326 | 1.198 | 3.705 | 1.944 | 2.364 | 4.161 | 2.044 |
| 069 | 20.453 | 1.110 | 4.776 | 0.999 | 0.896 | 0.476 | 1.812 |
| 071 | 0.761 | 324.778 | 10.222 | 3.124 | unavailable | 1.257 | 3.395 |
| 073 | 28.895 | 2.602 | 70.565 | 74.499 | 0.741 | 10.604 | 5.738 |
| 075 | 52.123 | 54.362 | 73.686 | 62.206 | 77.587 | 23.428 | 51.146 |
| 081 | 24.064 | 2.722 | 19.066 | 0.837 | 1.069 | 0.723 | 2.342 |
| 083 | 12.119 | 1.851 | 2.358 | 8.811 | 1.145 | 0.941 | 5.473 |

All distances are km. These half controls share full-channel discovery and initialization; they are not independent half-only discovery pipelines. Experimental controls and independently discovered halves are excluded. Each case was sealed before the configured reference join. No locked cases were evaluated, and no sub-kilometer or 0.5 km target is achieved.

Receipts: first seven comparisons reside in `local/ds22-configured-comparison-v1`; 035–041 in `local/ds22-runtime-configured-comparison-v1`; later comparisons in `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-configured-comparison-v1`. Each `comparison.json` binds its evaluator protocol and original matrix seal.
