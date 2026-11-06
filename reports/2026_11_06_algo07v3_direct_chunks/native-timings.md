| Scope | Baseline s | Candidate s | Wall reduction |
| --- | ---: | ---: | ---: |
| Complete process | 656.337 | 754.403 | -14.94% |
| native_preparation | 10.933 | 10.741 | 1.75% |
| recovery_catalogue | 2.277 | 2.354 | -3.37% |
| initial | 48.443 | 47.690 | 1.56% |
| conservative | 14.309 | 13.080 | 8.59% |
| family | 11.969 | 12.162 | -1.61% |
| signed | 7.053 | 6.970 | 1.18% |
| cavity | 11.557 | 11.656 | -0.85% |
| inventory | 0.264 | 0.263 | 0.46% |
| predictive | 298.208 | 349.234 | -17.11% |
| numerical | 190.381 | 201.336 | -5.75% |
| gap | 0.002 | 0.004 | -100.44% |
| residual | 0.239 | 0.291 | -21.54% |
| residual_screen | 8.880 | 16.058 | -80.82% |
| addition | 0.001 | 0.001 | -73.29% |
| incumbent | 0.387 | 0.537 | -38.91% |
| ranking | 8.777 | 13.390 | -52.56% |
| admission | 18.042 | 31.858 | -76.57% |
| final | 0.100 | 0.167 | -67.33% |
| plot_evidence | 10.660 | 12.193 | -14.38% |
| png_rendering | 5.320 | 7.261 | -36.48% |
| Kernel optimized (nested) | 58.756 | 83.145 | -41.51% |
| Kernel direct (nested) | 118.852 | 93.561 | 21.28% |

Kernel calls by phase-grid size (nested):

| Mode | Phase pairs/call | Calls per side | Baseline s | Candidate s |
| --- | ---: | ---: | ---: | ---: |
| direct | 1 | 261 | 0.131 | 0.188 |
| direct | 231361 | 298 | 71.487 | 59.233 |
| direct | 923521 | 10 | 9.517 | 7.235 |
| direct | 3690241 | 10 | 37.716 | 26.904 |
| optimized | 1 | 199 | 0.113 | 0.170 |
| optimized | 231361 | 335 | 36.713 | 51.657 |
| optimized | 923521 | 10 | 4.299 | 5.971 |
| optimized | 3690241 | 10 | 17.631 | 25.349 |

Reaped child CPU: 942.40 → 1165.80 CPU seconds. RUSAGE_CHILDREN deltas across completed supervisor waits.

Nested kernel CPU totals:

| Mode | Baseline CPU s | Candidate CPU s |
| --- | ---: | ---: |
| optimized | 58.747 | 83.065 |
| direct | 118.836 | 197.829 |
