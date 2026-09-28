# Exact refinement reuse

V2 caches conditioned/verification results within one window only, keyed by
epoch and the exact bit patterns of the generated grid's start and final bin,
plus its bin count. The final GLRT cache uses epoch and exact acquired-CFO
bits. The eight original candidate entries remain present and in the same
order; a cached scalar result substitutes computation, not evidence inventory.

V1 is rejected: start plus count did not distinguish differing appended
nonregular final bins when the grid clipped at -400 kHz. V2 includes the tail
and tests a real clipped-grid collision. V1 timings must not support promotion.

## CPU0 ARM measurement

Static saved IQ on PLUTO+ 192.168.1.15; no RF or simultaneous capture.
Four complete dual-RX 120 ms dwells execute 88 overlapping 20 ms windows.

| Quantity | Verification fusion baseline | Cache V2 |
| --- | ---: | ---: |
| Total CPU seconds per dwell | 33.728123 | 33.166615 |
| Conditioned stage seconds per dwell | 7.785452 | 7.383502 |
| Verification seconds per dwell | 1.486407 | 1.391491 |
| Final GLRT seconds per dwell | 0.481264 | 0.452031 |
| Original individual hits recovered | 119/119 | 119/119 |
| Original positive windows recovered | 49/49 | 49/49 |

All 704 candidate objects are identical. Total speedup is **1.01693x**,
or **1.66% less CPU time** (0.562 seconds saved per dwell). There are 46
conditioned/verification cache hits and 46 final-GLRT cache hits in this
sample. All 704 candidate results remain represented; only 658 final-GLRT
kernel executions are needed. Candidate-hit counts must not be confused with
the number of uncached kernel executions.

Normal host, sanitizer, and ARM units pass exact-key/reset, adjacent-double,
signed-zero and clipped-tail tests. The 64-dwell host cohort also matches all
11,264 candidate objects, all 1,669 hits, and all 691 positive windows.
The completed host704 audit matches all **123,904 candidate objects**, all
**19,581/19,581 original hits**, and all **7,007/7,007 positive windows** in
15,488 windows. It serves all 123,904 candidate results with 116,122 actual
final-GLRT kernel calls: 7,782 repeated evaluations are reused. The original
baseline's inherited four negative ordered-candidate differences in one
7.5 MS/s window remain unchanged. Both paired and direct-original audits
are stored in host704-v2/. This is 704 dwells from all 88 DS7 recordings,
0.361% of published DS7 dwells, not full DS7.

The opportunity analysis reports 7,782 repeated final epoch/CFO keys among
123,904 full-baseline candidates (6.28%). The rate is 7.70% at 2.5 MS/s.
That explains why a small whole-pipeline gain is plausible. Fine FFTs remain
uncached. This exact implementation is separate from sparse proposals and
direct-GLRT experiments; no combined speedup is claimed.

At 33.17 CPU seconds per 120 ms dual-RX dwell, this does not meet the 72 ms
budget for 40% headroom. Simultaneous capture is not qualified by these runs.
