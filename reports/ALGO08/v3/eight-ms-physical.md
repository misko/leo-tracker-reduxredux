# Raw 8 ms primary transfer on DS30-0016 and public North

The 8 ms primary cut native detector CPU by **14.5% on DS30-0016** and **12.1% on public North**. Whole-process CPU fell from **9.242 to 8.637 s** on the physical recording and rose from **13.607 to 13.746 s** on North. The physical case passed the frozen 250 m per-arm position gate against both 12 ms and named ALGO08v3. North failed in fixed calibration by **292 m against 12 ms** and **576 m against v3**. These two raw development pairs end the fixed 8 ms transfer. [Frozen protocol](eight-ms-physical-protocol.md) · [DS30-0016 receipt](measurements/eight-ms-physical.json) · [North receipt](measurements/eight-ms-north.json)

| Recording | Primary | Whole CPU / elapsed (s) | Error fixed / fitted (km) | Conditional RF RMS fixed / fitted (Hz) |
|---|---|---:|---:|---:|
| DS30-0016 | Named v3, archived | 10.797 / 10.831 | 1.644 / 1.661 | 109.38 / 109.48 |
| DS30-0016 | 12 ms, fresh | 9.242 / 9.251 | 1.311 / 1.694 | 121.53 / 120.29 |
| DS30-0016 | 8 ms, fresh | 8.637 / 8.639 | 0.501 / 0.997 | 134.03 / 133.74 |
| North containing | Named v3, archived | 18.480 / 18.514 | 0.106 / 0.141 | 5.41 / 5.17 |
| North containing | 12 ms, fresh | 13.607 / 13.633 | 0.390 / 0.121 | 69.40 / 70.86 |
| North containing | 8 ms, fresh | 13.746 / 13.788 | 0.682 / 0.158 | 96.75 / 97.68 |

Both 8 ms runs raised RF RMS in both calibration arms relative to the fresh 12 ms controls. DS30-0016 still moved closer to the survey in both arms. Its fitted-calibration estimate had 496 m more position error than the fixed arm while RF RMS was 0.28 Hz lower. North’s fitted estimate had 524 m less position error than the fixed arm while RF RMS was 0.93 Hz higher. [Original physical pair](weak-combined-raw.md) · [Original northern measurements](measurements/north-combined.json)

## Raw coverage and graph ownership

Each launch decoded and authenticated the original 20 ms signed stereo waveform. The two acquisitions per case used the original chronological stream schedule and admitted exactly the same opportunities. At every nonanchor, the 80,000-sample primary used five pilot origins and the 120,000-sample primary used eight. Both used the installed two-scan 20 ms receiver every eighth admitted visit per RF, channel and edge. All full-anchor factors and empty anchor lanes reproduced exactly. The compact graph took every selected measurement with the original weights, region and solver rules. North also kept the pinned native regional likelihood from its original full short run. [Reviewed 8 ms build](eight-ms-primary.md) · [Raw entry](full_short_run.py)

| Recording | Issued / admitted visits | Unchanged selected anchor lanes | Selected nonanchor lanes, 12 / 8 ms | Jointly matched nonanchor lanes | Prior owned lanes detected / matched at 8 ms | Owners, 12 / 8 ms |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 808 / 713 | 74 of 186 | 401 / 432 | 285 of 334 shared | 115 / 111 of 116 | 116 / 115 |
| North containing | 1,200 / 1,200 | 82 of 304 | 996 / 1,513 | 474 of 861 shared | 347 / 346 of 347 | 347 / 377 |

Joint matches require rank-zero factors within 2 samples modulo the pilot period and 250 Hz signed CFO. Owner counts were the same in both calibration arms. DS30-0016 kept 112 graph owners, dropped four and added three. North kept 300 graph owners, dropped 47 and added 77. No shared owner changed satellite. Eighteen shared North rows changed conditional or predictive roles. Almost all original North owner measurements survived the receiver change, alongside 517 additional net selected nonanchor lanes and substantial graph turnover. [Physical ownership and opportunity checks](measurements/eight-ms-physical.json) · [Northern ownership and opportunity checks](measurements/eight-ms-north.json)

## Complete process cost

| Recording | Primary | Native search CPU (s) | Authenticated acquisition CPU (s) | Numerical solve CPU (s) | Remaining process CPU (s) |
|---|---|---:|---:|---:|---:|
| DS30-0016 | 12 ms | 1.648 | 3.453 | 2.860 | 2.929 |
| DS30-0016 | 8 ms | 1.409 | 3.141 | 2.561 | 2.935 |
| North containing | 12 ms | 2.778 | 6.645 | 3.647 | 3.315 |
| North containing | 8 ms | 2.443 | 6.242 | 4.005 | 3.499 |

Native search is included in acquisition. Remaining CPU includes startup, publication and verification. On North, acquisition saved 403 ms while numerical solve and other work grew by 358 and 184 ms. On DS30-0016 both acquisition and solve fell in this one launch pair. The identical physical recording started each measured launch with all 242,128 compressed input pages resident. An earlier residency preflight found zero pages and stopped before any child launch. The input was fully resident at retry, so the permitted read-only prewarm did not run. North’s original input was on tmpfs. Each pair ran once, 12 ms then 8 ms, on Gauss CPU 2 under the shared low-priority slot with a prepared font cache. The archived v3 clocks provide context. [Launch order, CPU and cache receipts](measurements/eight-ms-physical.json) · [North stage clocks](measurements/eight-ms-north.json)

## Publication and reproduction

All four fresh runs published both calibration arms, their standard position paths and complete numerical grids (179 physical points, 137 North points). Independent readback verified all eight PNGs per run by both encoded and decoded digest. Both fresh 12 ms launches reproduced the original detections, terminal, assigned owners, scientific path and grid, and all PNG hashes. The fresh publications and exact output identifiers are in the receipts. [Physical 8 ms standard publication](/dev/shm/leo-eight-ms-DS30-0016-warm/8ms/fast-scan-standard-v2/algo08-v2-883a63295203d552291d028ab1a6e70a/final-error-v7/manifest.json) · [North 8 ms standard publication](/dev/shm/leo-eight-ms-north/8ms/fast-scan-standard-v2/algo08-v2-df4c8fa0fffe769536a7c742f73f51c9/final-error-v7/manifest.json)

Use the [paired physical driver](weak_combined_raw.py) with `OUTPUT GEOGRAPHIC_SO --paired-eight-ms EIGHT_SO`, then the [read-only scorer](eight_ms_physical_score.py) with `OUTPUT SCORE_JSON`. The [North driver](eight_ms_north.py) takes `run OUTPUT PHYSICAL_SCORE_JSON TWELVE_SO EIGHT_SO GEOGRAPHIC_SO REGIONAL_SO` and then `score OUTPUT PHYSICAL_SCORE_JSON NORTH_SCORE_JSON`. Run launches as the archive-readable account through the same `gauss.lock`, `ionice -c2 -n7`, `nice -n15`, `taskset -c 2` and one-thread environment as the original small raw pair. Put this checkout on the driver import path and its `src` first for read-only scoring. Each worker binds the pinned installed payload before import. The native libraries and commands are recorded in the receipts. Forty focused tests passed. [Raw callback tests](../../../tests/pipeline_eval/test_full_short_run.py) · [Position gate tests](../../../tests/pipeline_eval/test_eight_ms_physical.py)
