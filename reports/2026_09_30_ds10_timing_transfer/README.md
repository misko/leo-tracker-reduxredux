# Fine timing search does not improve the fixed DS10 N24 fit

The DS8-derived fine timing search finds **no material training improvement on any of the 24 fixed DS10 recordings**. Total improvement is only **1.70e−9 log-score units**, with maximum timing movement **0.000000396 s**. The declared 0.01-unit trigger is not reached, so no joint refit is launched.

The existing DS10 zero-height N24 estimate remains **1091.847 m from the supplied reference**, conditional on the unconfirmed installation continuity. This test does not improve that result. It narrows the diagnosis: missed timing peaks at the existing fitted location do not explain its larger reference distance under the tested model.

| Measure | Result |
|---|---:|
| Frozen scans profiled | 24/24 |
| Timing grid | 401 points, −5 to +5 seconds |
| Detected local maxima | 35 |
| Independently qualified scalar refinements | 28 |
| Rejected boundary refinements | 7 |
| Total training log-score gain | +0.000000001704 |
| Total held log-score gain | +0.000008638 |
| Maximum selected timing movement | 0.000000396 s |
| Runtime | 46.05 seconds |
| Joint refit triggered | No |

All seven rejected refinements lie at the global timing boundary and have large nonzero timing derivatives, despite scalar-optimizer success. Each is also substantially worse than its inherited timing: training-score deficits range from 1740.750 to 3309.177. No stronger boundary solution is hidden by qualification. Among qualified peaks, maximum absolute derivative is 0.000512 and maximum finite-difference discrepancy is 0.00000239.

## Method and verification

The [protocol](PROTOCOL.md) freezes the complete existing N24_h0 panel and its best qualified training fit. Every scan receives the same grid and bracketed scalar search used to validate the DS8 alternatives. Highest qualified training score competes against the inherited timing; held scores are evaluated but never select timing. Location, height, likelihood, candidate banks and recording membership stay fixed.

The experiment verifies cached input and implementation hashes, exact membership, scalar replay of the best grid point, and aggregate baseline training/held score replay to 1e−7. All 24 scan records were saved and the process finished before its 180-second cap, with no substitutions or retries. [summarize.py](summarize.py) checks each saved row, training-only selection, qualification counts and the declared refit trigger. [results.json](results.json) retains complete grids and all peak refinements; [summary.json](summary.json) contains the aggregates.

## Decision

Do not spend another joint optimization on these effectively unchanged DS10 timings. The DS8 timing/solver diagnosis does not transfer as a useful refinement at this DS10 endpoint. This rules out only the tested explanation: fine-grid local peaks can still be missed between grid points, and another joint geographic/timing mode may exist elsewhere.

Further sub-km work should return to model/data mismatch and independent physical constraints rather than continued optimizer variants on these panels. In particular, fixed-location residual diagnostics on separate recording groups can test whether systematic frequency evolution remains after timing is optimized. Keep antenna height and installation continuity uncertainty explicit; do not infer calibration parameters from reference-distance improvements.

This is transfer to exposed DS10 observations, not research-blind validation. No new geographic accuracy, satellite identity or absolute timing accuracy is demonstrated. No RF collection, export, propagation, production change or remote publication occurred.

```bash
python3 reports/2026_09_30_ds10_timing_transfer/summarize.py
cd reports/2026_09_30_ds10_timing_transfer
sha256sum -c evidence.sha256
```
