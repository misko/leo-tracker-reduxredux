# Adjacent-window GLRT tracking experiment

The current adjacent-window tracker trades substantial detection loss for speed.
It is not a quality-preserving replacement for full acquisition. These are saved
IQ tests; no new RF collection or simultaneous capture was performed.

## Native ARM measurement

PLUTO+ 192.168.1.15, CPU0, qualified static Cortex-A9/NEON binary. Two
metadata-selected 2.5 MS/s dual-receiver dwells (lower and upper edge), each
120 ms, each with 22 receiver-windows of 20 ms at 10 ms stride. Every method
executes all **44 windows**, producing eight retained candidates per window.
Original baseline: **46 individual positive candidates in 26 positive windows**.

| Full-search interval (windows) | CPU seconds / dwell | Speedup over full search | Individual hits recovered | Positive windows recovered | Added positive candidates |
|---|---:|---:|---:|---:|---:|
| 1 (full search throughout) | 60.217 | 1.00x | 46/46 (100%) | 26/26 | 0 |
| 2 | 33.997 | 1.77x | 38/46 (82.6%) | 23/26 | 8 |
| 3 | 23.543 | 2.56x | 28/46 (60.9%) | 18/26 | 13 |
| 5 | 18.302 | 3.29x | 15/46 (32.6%) | 12/26 | 13 |
| 11 | 7.754 | 7.77x | 13/46 (28.3%) | 13/26 | 9 |

Timings include each receiver's cold full search and every periodic refresh.
One measured invocation per method/dwell; these are small-sample ARM timings,
not large-cohort recovery estimates. Even the fastest variant consumes 7.754
CPU seconds per 0.120 seconds of dual-RX input: about 64.6 times the available
single-core budget, before capture overhead. The 40% headroom goal remains unmet.

`arm-results/` retains raw window records, commands, hashes, build receipt,
executed Python snapshots, and reconciled totals. `summarize_arm.py` asserts
all expected window identities, success states, eight candidates per window,
and agreement of window totals with native CPU/attempt/mode summaries.

## What tracking does

Each receiver has separate state. Full search initializes eight candidate
epochs and acquired CFOs. The next window shifts each epoch by exactly 10 ms
modulo the nominal frame period. Tracking evaluates the original FP64 GLRT at
the propagated epoch and its two integer-sample neighbors, retaining one result
per seed by margin. It retains acquired CFO and uses the original 64 pilot
symbols, 512-bin FFT, and up to 16 frames. No windows are dropped. No
zero-positive fallback is enabled in these sweeps.

The three-epoch selection changes the search procedure and can create new
positives; those are explicitly reported as added candidates, not counted as
recovered original hits or asserted to be real signals.

## Recovery definition

Positive means original margin >= 0.025. Recovery uses maximum-cardinality
one-to-one matching within the same dwell, receiver, and window, with epoch
difference <= 2 samples and tracking CFO difference <= 8 kHz. Thus these are
exact counts under a stated association tolerance, not bitwise numerical
equivalence. A positive window is recovered only if at least one original
positive candidate in that window is matched. Missing windows remain in the
baseline denominator.

The prior full-search optimization has separate, stronger large-cohort
evidence: 704 dwells, 15,488 windows, 19,581/19,581 individual positive hits
and 7,007/7,007 positive windows recovered. See
`../2026_09_28_arm_full_optimization/FULL_COHORT_SUMMARY.md`.

## Mixed-rate development cohort

64 dwells (eight from each rate/edge combination), 1,408 receiver-windows,
11,264 retained candidate slots. All methods execute every window. These
quality measurements ran with the qualified native host binary; ARM timing
comes from the separate matched two-dwell experiment above.

| Full-search interval | Original individual hits recovered | Positive windows recovered | Added positive candidates |
|---|---:|---:|---:|
| 1 | 1,669/1,669 (100%) | 691/691 | 0 |
| 2 | 1,444/1,669 (86.5%) | 634/691 | 254 |
| 3 | 1,298/1,669 (77.8%) | 587/691 | 387 |
| 5 | 1,206/1,669 (72.3%) | 574/691 | 482 |
| 11 | 1,072/1,669 (64.2%) | 523/691 | 623 |

Only interval 2 clears the 80% development target; none of the approximate
variants clears 90%. These thresholds refer to individual candidates, not
positive-window recall. Interval 2 was therefore selected for larger-cohort
qualification. This is an exploratory selection, not an untouched holdout.

## Implications

Simple timing/CFO reuse is too lossy to be the default. Increasing the full
refresh gap gives a misleading impression of benefit if only total positive
counts are compared: new positives partly replace missed original identities.
For quality-preserving work, prioritize sharing input conversion and overlapping
coarse-search calculations, or a provably conservative candidate screen with
full fallback. Both require new implementation and measurement; no speedup is
claimed for those ideas here.

## Larger DS7 qualification: refresh every second window

Completed 704 dwells spanning all 88 recordings, eight metadata-quantile
dwells per recording: **0.361% of DS7's 194,934 dwells**, not full DS7.
The selection overlaps the development set. All **15,488** scheduled 20 ms
receiver-windows succeeded; 123,904 candidates were retained after 236,544
individual GLRT evaluation attempts (including neighboring epochs).

| Rate (MS/s) | Dwells | 20 ms windows run | Original positive windows recovered | Original individual hits recovered | Added positive candidates |
|---|---:|---:|---:|---:|---:|
| 2.5 | 152 | 3,344 | 1,548/1,682 | 3,898/4,573 (85.2%) | 677 |
| 5 | 216 | 4,752 | 1,770/1,874 | 4,828/5,466 (88.3%) | 684 |
| 7.5 | 184 | 4,048 | 1,780/1,933 | 4,539/5,186 (87.5%) | 652 |
| 10 | 152 | 3,344 | 1,424/1,518 | 3,811/4,356 (87.5%) | 584 |
| **Total** | **704** | **15,488** | **6,522/7,007** | **17,076/19,581 (87.2%)** | **2,597** |

This misses **2,505** original individual hits despite returning 19,673
positive candidates in total. Thus raw positive totals alone would be a poor
quality metric. The method passes the exploratory 80% individual-hit target
on this subset at every rate, but fails 90%. The 1.77x ARM speedup was measured
on the separate two-dwell 2.5 MS/s timing set; it is not a 704-dwell ARM timing
claim. Neither experiment includes simultaneous capture overhead.
