# Saved-input solver experiments

On the full DS30-0374 detection packet, causal TLE reuse and coarse salvage statistics reduced solver CPU time from **34.01 to 29.71 seconds (1.14×)**. Both calibration arms selected the same positions and final owners, and every sampled grid score matched. The solver experiment begins at saved two-scan detections and ends after building the full diagnostic grid. It does not measure I/Q acquisition, PNG encoding, or end-to-end speedup.

## Changes tested

- The scan-scoped parser stores validated snapshot catalogues and deduplicates identical element pairs. Preparation still reads each archive reference through the digest-verifying reader and runs the existing cutoff, newest, previous and genuine-previous selection policies. Only preparation receives shared Satrec objects. The accelerated bulk propagator copies those records, which the component test also checks against fresh records. The parser falls back to the stock parser on nonaccelerated builds and when estimated retained payload exceeds 256 MiB. This estimate excludes map entries and allocator overhead. [Parser](../../../tools/pipeline_eval/variants/algo08_causal_reuse.py)
- Coarse salvage profiles the existing 81 phases with weighted per-track squared terms and the existing alias and Gaussian bias priors. Each candidate and phase still participates. The coarse evaluator runs the direct profile near a native-alias rounding boundary or a shortlist cutoff tie, including ties among invisible candidates. The dynamic fallback margins are numerical guards. The remaining gates and fine salvage use the existing research port of the stock procedure. [Salvage statistics](../../../tools/pipeline_eval/variants/algo08_salvage_statistics.py)

The short DS30-0016 profile attributed 8.16 of 11.49 profiled CPU seconds to the initial sky and phase history. Across their 99 parser calls, the stock profile constructed about 1.16 million Satrec objects. The unprofiled reuse trial constructed 92,697, and preparation alone fell from 5.44 to 2.81 CPU seconds. The variational solver already reuses group Gram matrices within each likelihood call. Its native bound accounted for 0.31 profiled seconds on this short case. No change was made to variational iteration budgets or to the grid.

## Matched measurements

Runs used separate processes on CPU 2, low CPU and I/O priority, one numerical thread and the deployed release's pinned assets and runtime. Stock ran first on DS30. The causal trial ran first on the regional simulations. Wall timings varied more than CPU timings on Gauss. All inference inputs were the offered region, saved detections and capture-era TLE archive. The regional cases come from the published synthetic regression fixtures. [Regional release evidence](../regional-release/README.md)

| Saved input and change | CPU seconds | Wall seconds | Grid seconds, wall | Grid points |
|---|---:|---:|---:|---:|
| DS30-0016, causal reuse | 7.39 → 4.75 | 7.46 → 4.79 | 0.28 → 0.28 | 179 |
| DS30-0374, combined | 34.01 → 29.71 | 35.11 → 33.36 | 4.38 → 4.29 | 179 |
| North containing, causal reuse | 9.42 → 7.10 | 9.51 → 8.23 | 0.83 → 0.82 | 179 |
| South containing, causal reuse | 8.48 → 6.43 | 8.53 → 6.48 | 0.46 → 0.47 | 179 |
| North far, causal reuse | 13.72 → 11.53 | 13.78 → 11.61 | 0.60 → 0.60 | 137 |
| North far, salvage statistics | 13.72 → 13.53 | 13.78 → 13.65 | 0.60 → 0.60 | 137 |
| North far, combined | 13.72 → 12.14 | 13.78 → 12.24 | 0.60 → 0.60 | 137 |

The north-far statistics trial spent 0.28 CPU seconds in salvage versus 0.50 stock and evaluated nine coarse windows via statistics. The full DS30-0374 combined trial evaluated 38 such windows and selected seven trims from twelve tracks inspected for salvage. Full-case peak RSS fell from 1.22 to 0.97 GiB. Peak RSS rose by about 31–38 MiB on the containing simulations. These single pairs measure process-level effects including memory allocation.

All seven comparisons returned the same decisions, coordinates, solver frequency RMS, final owner summaries, objective replay, and position paths. Every diagnostic grid point agreed, including its position, scores and failure fields. The differences in the grid payload were confined to its elapsed time field. This checks sampled parity with stock. The salvage statistic uses a different floating-point reduction, and the numerical guard has not been qualified across the full corpus.

| Saved input | c = 0 solver RMS (Hz) | Fitted-c solver RMS (Hz) | c = 0 simulated error (km) | Fitted-c simulated error (km) |
|---|---:|---:|---:|---:|
| DS30-0016 | 109.375 | 109.479 | — | — |
| DS30-0374 | 101.536 | 101.520 | — | — |
| North containing | 5.380 | 5.173 | 0.745 | 0.711 |
| South containing | 6.503 | 6.392 | 0.826 | 1.109 |
| North far | 37.951 | 37.533 | 52.455 | 52.491 |

Simulation errors come from the previously published scorer, after the matched endpoints were checked. Both north-far arms still returned false fixes on the region edge. At the south site, fitted c lowered frequency RMS while increasing position error. [Simulation scores](../regional-release/blind-scores.csv)

At the 16-recording panel's historical 43.9% solver CPU share, the full-case savings would give about 1.06× pipeline speedup in isolation if the measured solver ratio transferred. Under the same arithmetic, reaching 2× would require about 4.8× faster acquisition alongside this solver ratio. These measurements support keeping the causal reuse and salvage work as bounded research candidates. [Historical CPU split](../single-core-directions.md)

## Reproduction

Run `solver_trial.py` once per arm with `stock`, `causal-reuse`, `salvage-statistics` or `combined` followed by the saved detections JSON path, frozen TLE archive path, deployed ALGO08v2 asset directory, offered region JSON path, and detection file SHA-256. Invoke it with the release's Python and the deployed `src` and research worktree on `PYTHONPATH`. Its manifest validator binds the exact release paths and SciPy provider. The output retains both calibration results, stage timings, trim evidence, ownership summaries, and full position path and grid. Thirty targeted tests passed. [Trial runner](solver_trial.py)
