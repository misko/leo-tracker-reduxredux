# Exact reuse in the standalone compact cavity receiver

The original 78-source standalone package ran as a fresh control. Two 79-source overlays changed one operation each. Both overlays returned identical positions, calibration-specific conditional RF RMS, frequency scores, and solver decision and work counters on the two ordinary inputs. The projection-call counter decreases by exactly the number of column cache hits. Both RF arm results are preserved independently in `scores.csv`.

## Where the time went

An instrumented stock run found 7 repeated fixed-phase requests across initial branches or ranking on each ordinary recording, out of 152 requests on DS26-0036 and 162 on DS29-0082. The initial ranking and branches together made 4,617 and 2,349 native projection calls. Other geometry work where the subsequently selected aliases were already supplied took 0.396 and 0.192 profiled CPU seconds over the whole worker. The diagnostic profile incurred instrumentation overhead. The six fresh uninstrumented solves supply the performance comparison.

The column overlay reuses an initial-ranking projection on the same immutable nominal orbit stencil, with the same projection function, exact observer coordinates, altitude, RF and ordered track column indices. Phase overlays receive private copies from the original track field. The cache is bounded at 48 MiB of accounted data and 512 entries. Its lifetime ends as soon as initial ranking has produced the three candidate seeds. The independent fits proceed unchanged.

The TLE overlay caches the original checksum calculation for identical 68-column prefixes during native preparation, with at most 32,768 entries. Original line shape and trailing checksum validation, verified snapshot bytes, catalogue selection, SGP4 objects and causal timing remain in the original path. It is independent of the orbit-column overlay.

## Ordinary inputs

Each row is one same-core pair against a fresh original worker, with one numerical thread, nice 10 and an enforced 512 MiB resident charge limit with zero swap. Launch-to-exit wall includes the systemd service supervisor. Process peak RSS and charged cgroup peak are separate measured quantities. Collection and IQ detection occurred before these frozen ordinary-factor replays.

| Recording | Overlay | Effective native work | CPU s, stock → overlay | Wall s, stock → overlay | Charged peak MiB, stock → overlay |
| --- | --- | --- | ---: | ---: | ---: |
| DS26-0036 | Orbit columns | 1,332 fewer of 4,872 projections | 57.53 → 55.53 | 59.80 → 62.32 | 265.8 → 311.0 |
| DS29-0082 | Orbit columns | 1,082 fewer of 2,494 projections | 43.75 → 39.06 | 80.55 → 68.92 | 264.5 → 296.6 |
| DS26-0036 | TLE checksum | 441,229 repeated checksums skipped | 57.53 → 61.48 | 59.80 → 71.90 | 265.8 → 265.5 |
| DS29-0082 | TLE checksum | 524,830 repeated checksums skipped | 43.75 → 38.58 | 80.55 → 65.29 | 264.5 → 266.5 |

Orbit column reuse cut initial-stage wall from 17.71 to 13.97 s and 21.22 to 14.88 s. Total launch-to-exit wall moved in opposite directions on the two inputs. The checksum cache also had mixed end-to-end timing despite frequent hits. The measured absolute position errors stayed 0.218/0.180 km for DS26-0036 and 2.789/2.654 km for DS29-0082, in zero-`c`/fitted-`c` order. All four original v5 policies appear in the position charts. The archived originals use capture-era observations. The fresh paired controls in this table use the same ordinary factors as the variants.

The [both-arm position charts](charts/index.html), [resources](resources.csv), [scores](scores.csv) and [profile](profiling.json) retain the original measurements. The archived measured runner and exact file hashes permit checking the release and overlays. The active runner adds reserve support and lint changes outside the locked ordinary run.

## Capture-era reserve

The reserve roster came from the standalone release's previously sealed capture-era selection. Its stock and column-cache runs retain the same science comparison and effective cap as the ordinary panel. The TLE overlay was only measured on the ordinary panel.

| Recording | Effective native work | CPU s, stock → overlay | Wall s, stock → overlay | Charged peak MiB, stock → overlay |
| --- | --- | ---: | ---: | ---: |
| DS26-0112 | 1,147 fewer of 6,855 projections | 94.45 → 95.52 | 111.91 → 95.95 | 328.6 → 390.2 |
| DS29-0127 | 1,258 fewer of 4,558 projections | 49.65 → 42.33 | 52.82 → 49.06 | 284.9 → 303.7 |

Both calibration arms, RF scores and conditional RMS, solver decisions, and native-call accounting matched exactly. The position errors remained 1.027/1.049 km on DS26-0112 and 0.633/0.579 km on DS29-0127, in zero-`c`/fitted-`c` order. The reserve has separate sealed [resources](holdout/resources.csv), [scores](holdout/scores.csv) and [comparisons](holdout/comparison.json).

Across the four recordings, initial-stage wall improved on each, with summed launch-to-exit wall 9.45% lower and summed cgroup CPU 5.27% lower. CPU rose on DS26-0112 and elapsed wall rose on DS26-0036. Every overlay completed under the effective cgroup limit without OOM or swap. Relative timings include host scheduling variation, with one measurement of each method per recording. The [performance figure](resources.png) shows each measured delta and uses a black tick for the stock charge. The faster ranking and bounded cache support an optional column overlay. The modest whole-worker improvement and increased charge leave the default unchanged. The checksum result has no consistent speed benefit across its measured pair.

## Reproduction

Use the pinned optional local overlay to install a fresh standalone package. The original public installer and default 78-source release stay unchanged.

```sh
python -m tools.pipeline_eval.qualification.cavity_reuse_trial \
  install /path/to/new/standalone --profile columns
```

With the released data but no replay inputs, rescore the packaged ordinary results and verify all file digests. Add `--pack` only when providing the original paired scratch directory and its separately recorded profiles.

```sh
python -m tools.pipeline_eval.qualification.cavity_reuse_results \
  reports/2026_11_19_receiver_screening/detector-origins/compact-reuse \
  --out /path/to/scored
```

Score the reserve the same way using `compact-reuse/holdout` as the source. These host measurements cover the standalone native-to-position boundary under the stated cap. A system-wide receiver and board timing require their own measurements.
