# Constant residual RMS: zero versus ±1 second satellite timing

All 39 tracks at 08:10 and all 51 at 10:30, 2026-09-26. The latter restores two tracks that could not support the previous quadratic fit. Both weighting schemes use the same fitted parameters. Values below are uncapped evaluation RMS in Hz.

| UTC | Fixed location | Zero, equal-track | Zero, size-weighted | ±1s, equal-track | ±1s, size-weighted |
|---|---|---:|---:|---:|---:|
| 08:10 | Reno | 433.0 | 554.2 | 367.9 | 471.6 |
| 08:10 | Sacramento | 343.7 | 354.0 | 285.8 | 289.7 |
| 08:10 | Known location | 370.6 | 402.7 | 309.4 | 323.6 |
| 10:30 | Reno | 369.4 | 433.2 | 300.6 | 338.3 |
| 10:30 | Sacramento | 441.9 | 534.6 | 368.8 | 438.4 |
| 10:30 | Known location | 584.0 | 769.6 | 494.5 | 644.4 |

Equal-track RMS = sqrt(mean(per-track evaluation MSE)). Size-weighted RMS = sqrt(sum(N_i * evaluation MSE_i) / sum(N_i)), where N_i is the total training-plus-evaluation observation count. This is not strictly pooled evaluation-observation RMS and is not the older occupied-second weighting. No averaging of RMS magnitudes.

## Timing protocol

Each fixed location retains its independently selected training-only zero-timing satellite IDs from the earlier DS5 diagnostic. For each track and timing grid value, fit an independent constant frequency offset by ordinary least squares on training observations. For each satellite, minimize the sum of training squared errors over all its assigned tracks. Grid is -1 to +1 seconds inclusive at 0.1-second resolution (21 values); ties prefer the smallest absolute timing. No TLE-age prior is used. One correction is shared across that satellite's tracks within the scan and location, not one correction per track. Other satellites/sites/scans fit independently.

Timing and offsets never use evaluation values. No linear/quadratic residual correction, candidate reassignment, new geographic search or cross-site proposal sharing. Persisted winners and evaluation masks are reused, so this is retrospective rather than fresh validation.

The ±1 second limit is restrictive: endpoint selections are reference 11/15, Sacramento 6/12, Reno 10/16 satellites at 08:10; reference 15/21, Sacramento 15/22, Reno 13/21 at 10:30. These are constrained fits; endpoint hits alone do not identify the physical cause or prove that widening support will improve held-out scores.

All six RMS values decrease after timing fitting, but the ordering of locations is unchanged under both weighting schemes. Sacramento remains lowest at 08:10 and wrong Reno remains lowest at 10:30. Neither treatment selects the known location in these cases.

`small_timing_results.json` retains all 270 track/site results, satellite timings, boundary counts, zero-offset parity checks and evidence/snapshot/source hashes. It also includes summaries for the original 39/49 plotted tracks, evaluated using the same all-track-fitted timings. Zero-offset per-track RMS reproduces the preceding experiment within 1e-6 Hz. Two new tests verify training-only selection, satellite sharing, tie handling and RMS aggregation.

Reproduce with `run_small_timing.py` using the installed API Python environment and single-threaded BLAS. Only these two scans are run; production and source data are unchanged.
