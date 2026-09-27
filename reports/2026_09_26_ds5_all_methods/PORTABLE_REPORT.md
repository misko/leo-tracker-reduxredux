# DS5 portable raw-track methods

All inference was sealed without a reference coordinate. Horizontal error was added only by the post-seal evaluator. The matrix contains 416/416 completed fits.

| Method | Single median km | Group8 median km | Full km | Rate-full median km | Complete |
|---|---:|---:|---:|---:|---:|
| Baseline | 17.727 | 8.579 | 8.329 | 7.800 | 52/52 |
| Shared time | 8.329 | 7.330 | 8.329 | 6.725 | 52/52 |
| Per-scan time | 8.329 | 7.330 | 8.329 | 6.725 | 52/52 |
| Per-track time | 5.791 | 4.599 | 4.231 | 5.332 | 52/52 |
| Per-NORAD rate | 75.929 | 7.463 | 7.286 | 10.746 | 52/52 |
| Time + rate | 8.329 | 7.330 | 7.286 | 6.119 | 52/52 |
| Soft identity | 37.541 | 7.463 | 7.286 | 7.800 | 52/52 |
| Soft identity + time | 12.038 | 7.330 | 7.286 | 6.725 | 52/52 |

The rate × active-time heatmap uses the sealed truth-blind active-time terciles and preserves each scan's recorded sample rate. Chronological group8 membership was not reordered by rate.
