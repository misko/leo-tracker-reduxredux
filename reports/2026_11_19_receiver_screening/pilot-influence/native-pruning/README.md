# Write only the GLRT grid cells the search reads

The exact coarse-grid change preserved every public detector field, hint, support mask and gate on **96 held dual-receiver visits** in all three modes. For fifth-center on both receivers, summed coarse CPU fell from **2.02 to 1.32 ms** median, and complete decoded CPU fell from **16.75 to 15.98 ms**. Complete wall p50/p95 fell from **10.36/20.64 to 9.64/18.71 ms**. [Stage chart](stage.png) · [PDF](stage.pdf) · [Timing records](stage.csv)

## Exact scope

The wide regional detector already runs its 21-CFO correlation bank only at the at-most-15 epochs nominated by the stock and optional fifth regions. Its scratch epilogue still wrote a dense 13,333-epoch grid and zeroed every accumulator. Within the pinned 20 ms, 10 MS/s regional path, only peak extraction and local refinement consume that grid. Their read set is the active epochs and their immediate neighbors. The new port zeros the active accumulators, writes the same 21 scores at each active epoch, and writes the original negative-infinity sentinel at every inactive read neighbor. A sorted, matching active set, fixed input geometry and the original coarse arithmetic all gate this path. Other geometry uses the dense branch.

The original accumulation still uses binary32 per CFO, and the published quotient divides after promotion to binary64. A development smoke caught an early version that divided at binary32 and rounded the coarse scores differently. The final source restores the original promotion point and was sealed before the full comparison. A compiled unit witness explicitly covers previous-call stale values, disjoint active sets, holes, both boundary epochs and unsupported sets.

The earlier triangle and tap-prefix tests found no useful safe rejection of ordinary nonzero correlation cells. This study removes unobservable scratch traffic while evaluating every active 21-CFO hypothesis. Across the 96 distinct five-on-both visits, the exact source-level count was **53,758,656 → 95,340 published grid writes** and **255,993,600 → 274,000 cleared bytes**. All 57,540 active CFO cells remained. These counts describe the executed loop geometry. Measured latency and CPU are separate. [Magnitude-bound experiment](../../support-preserving/capture-bound/README.md) · [Active support and work counts](work-parity.csv)

## Paired detector timing and science

The fixed held roster was the first 24 windows in segments 6 and 9 of DS26-0197 (lower edge) and DS29-0316 (upper edge). All 96 scheduled visits were valid. The control and candidate used separate mapped libraries, caller CPU0 and persistent helper CPU1. Each mode used three warmed interleaved repetitions. Timings start with already-loaded CI16 and end after decoding both public receiver rows. CPU includes both active threads. Warm baseline profiling put the fractional stage above coarse CPU even on these same host cores, so smaller coarse cost affects just part of the complete call.

| Measured boundary | Four control → active-set | Five control → active-set | Staggered control → active-set |
| --- | ---: | ---: | ---: |
| Coarse CPU p50 / p95, ms | 1.78/2.09 → 1.06/1.26 | 2.02/2.39 → 1.32/1.57 | 1.92/2.24 → 1.23/1.43 |
| Complete CPU p50 / p95, ms | 13.22/17.00 → 12.38/15.85 | 16.75/20.02 → 15.98/18.89 | 15.13/18.28 → 14.36/17.45 |
| Complete wall p50 / p95, ms | 8.35/22.94 → 7.82/16.46 | 10.36/20.64 → 9.64/18.71 | 9.49/20.52 → 9.12/22.71 |
| Complete wall at or below 20 ms | 269 → 279 / 288 | 273 → 276 / 288 | 271 → 270 / 288 |

In five mode, the paired median savings were 0.71 ms coarse CPU, 0.87 ms complete CPU and 0.33 ms complete wall. Staggered p95 wall rose on this host pass. The output contained exactly the same 1,536 ordered candidates in each matched mode. Gated counts were 293 four, 312 five and 305 staggered in each build. The two previously difficult real targets remained misses, and both previously recovered targets remained recovered in the five control and candidate. Both sides recovered their signed plants, and noise and zero controls emitted no gated factors. Both mixed choices and absent hints were checked. [Timing and control summary](summary.json) · [Full receipts](measurements.json.gz)

## Reusable native build

The candidate directory `/var/tmp/leo-native-pruning-20261119/build/candidate` contains the recompiled `libleo-adaptive-detector.so.1` and the unchanged `libleo-staggered-native.so` wrapper. The existing stock, fifth, staggered and absent modes use the same ABI. The sibling library is selected through the wrapper's relative runtime path. `tools.pipeline_eval.qualification.native_pruning_build` rebuilds the overlay against the sealed combined release. `native_pruning_eval` freezes and replays the held input, and `native_pruning_results` publishes the receipts. The measurements cover x86 host RF detection from stored IQ. [Feature gate and binary hashes](feature-gate.json) · [Build receipt](build.json) · [Result seal](result-lock.json)
