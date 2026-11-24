# Persistent orbital preparation on two chronological saved scans

The second request reused **82 of 9,040 historical orbit transitions (0.91%)**. Including the first request, the cache added **40.53 ms of forecast CPU** and raised the second request’s peak RSS by **9.74 MiB**. Both requests returned exactly the original prepared scientific documents and numerical banks. This missed the preregistered 0.15 CPU s gate and ended at preparation. [Frozen protocol](persistent-orbit-protocol.md) · [Measured receipts](measurements/persistent-orbit-updates.json.gz)

## Measured boundary

The genuine all-visit 8 ms DS30-0016 packet preceded the genuine mixed DS30-0057 packet by 17.698 hours. Both independent processes authenticated each packet, original region and per-scan causal cutoff, then loaded the same already sealed index built from the earlier DS30-0008 inventory. The portfolio index found 19 of 20 and 16 of 26 source bodies, respectively. Both processes still verified the archive reads (99 and 112), reran the original epoch elections and rebuilt the region-dependent bank, noise, forecast split, shrinkage and uncertainty. The archived complete terminal digests are carried for request identification. No position optimizer, withholding decision or image renderer ran in this experiment. [Weak source and scientific control](weak-all8-combined.md) · [Medium source and scientific control](exact-solver-0057.md)

| Scope | Ordinary CPU s | Persistent CPU s | Ordinary elapsed s | Persistent elapsed s |
| --- | ---: | ---: | ---: | ---: |
| Worker setup and checked imports | 0.358 | 0.350 | 0.358 | 0.350 |
| First forecast, DS30-0016 | 0.263 | 0.276 | 0.263 | 0.276 |
| Second forecast, DS30-0057 | 0.333 | 0.361 | 0.333 | 0.362 |
| First preparation, including forecast | 1.610 | 1.347 | 1.662 | 1.347 |
| Second preparation, including forecast | 2.069 | 2.185 | 2.069 | 2.186 |
| Both requests through verified preparation | 4.431 | 4.288 | 4.484 | 4.290 |

The total includes checked artifact loads, input authentication, preparation and digest readout. It ends before writing the final receipt and excludes Python launch and exit. The apparent total CPU benefit is 0.143 s in one ordinary-then-persistent sequence. The first request took 6,878 cache misses and had no hits, so its 0.263 s preparation difference cannot be credited to cross-request reuse. The isolated forecast is slower for each request. The earlier weak model’s 1.895 s elapsed gap is much larger than even the entire 0.263 s first forecast. The 0.333 s second forecast is an inclusive CPU ceiling and includes the independently required split and model fit. At mean inclusive cost per candidate transition, the 82 hits represent about 3 ms before cache overhead. [Earlier weak timing model](weak-all8-combined.md)

## Which work can carry over

The coarse and fine banks use the request’s absolute UTC and elected TLEs, followed by a region-specific visibility screen. The signed probe endpoints are 35.756 s and 120.255 s after their respective starts. Each bank’s minimum-duration grid spans −17 to 317 s; the two absolute grids are disjoint. The previous within-request setup audit already prices shared orbit times and canonical TLE exports. A shared source-body digest alone gives neither the current bank nor the preceding three selected records at their exact original availability stamps. [Live orbit setup audit](live-orbit-setup-audit.md) · [Existing portable index](portable-orbit-index.md)

The prototype retains up to 24,576 immutable scalar transition results, including genuine empty results, keyed by each triple’s exact two lines, epoch and publication time. A hit materializes a fresh result. No Satrec object or position is retained. The pinned installed transition, exact runtime, chronological admission and per-request cutoff checks remain in use. Unsupported source or inputs use ordinary computation, and a non-increasing cutoff clears the cache. The experiment observed no evictions, unsupported calls or compatibility fallback. Earlier portable metadata and import-only worker savings belong to separate interventions. [Prototype](persistent_orbit_updates.py) · [Earlier forecast improvement](exact-phase-forecast.md) · [Import-only worker](preloaded-saved-worker.md)

## Reproduction

With the original staged input account, invoke `persistent_orbit_trial.py ordinary OUTPUT.json` and `persistent_orbit_trial.py persist OUTPUT.json` in separate installed-venv processes, one exclusive Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. The measured study source was frozen at `b8da27a75`. Two launcher attempts stopped before preparation, first on the required lazy-import ordering and then on trusted-index verification before the native parser binding was entered. The corrected pair alone produced both receipts. The 26 component and adjacent tests passed. [Trial driver](persistent_orbit_trial.py) · [Component tests](../../../tests/pipeline_eval/test_persistent_orbit_updates.py)
