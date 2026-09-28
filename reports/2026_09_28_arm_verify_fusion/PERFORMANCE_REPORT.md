# Exact verification fusion: measured ARM result

The fused scorer shares odd-symbol sample energy and CFO phasors between
exact and control verification. Every per-result accumulation order and
normalization is preserved; no window, frame, candidate, or final GLRT is
removed. The isolated build is based on screen-rotation V1, not the higher-rate
FFT coarse proposal.

## CPU0 measurements on PLUTO+ 192.168.1.15

Saved static IQ is processed from RAM. No RF collection or concurrent capture
was running. Transfers and workspace creation are outside the search timing.

| 2.5 MS/s measurement | Screen rotation V1 | Verification fusion V1 | Speedup |
| --- | ---: | ---: | ---: |
| Four windows, three repeats | 1.542867 s/window | 1.532125 s/window | 1.00701× |
| Four dual-RX 120 ms dwells, 88 windows | 33.912983 s/dwell | 33.728123 s/dwell | 1.00548× |
| Verification stage in those dwells | 1.700789 s/dwell | 1.486407 s/dwell | 1.14422× |

The observed full-dwell saving is **0.185 CPU seconds (0.55%)**. Verification
itself takes about 12.6% less CPU. This is a small measured improvement, not
a statistical confidence bound or a real-time result. Other stages vary
slightly between runs. The four-window repeated probe test supports the same
direction as the complete-dwell measurement.

## Numerical qualification

Host normal and ASAN/UBSAN tests and the ARM unit pass exact parity against
the original three verification calls for all four rates, full/partial inputs,
zero samples, multiple CFOs and epochs. Source and binary receipts are in
`builds/`, and the ARM unit receipt is in `arm-unit-v1/`.

The 88-window ARM full-dwell run preserves every one of 704 candidate objects,
all **119/119 individual positive hits**, and **49/49 positive windows**.
The repeated ARM probe grids and candidates also match exactly.

The 64-dwell host run preserves all 11,264 candidate objects, **1,669/1,669
hits**, and **691/691 positive windows**. The completed 704-dwell host run
preserves all **123,904 candidate objects**, **19,581/19,581 hits**, and
**7,007/7,007 positive windows**, with zero added hits. This covers 15,488
overlapping 20 ms windows across all 88 recordings (0.361% of DS7 dwells).
Both the paired audit and direct original-baseline independent summary are
in `host704-v1/`. The original baseline has the same previously recorded
four negative candidate-order differences in one 7.5 MS/s window; this
change adds none and loses no positive hits.

The generic probe runner reports a frozen-original-oracle mismatch because
the preceding FP32 coarse baseline already differs from that older oracle.
The paired receipts compare the actual successive builds and are the evidence
for this change's exact candidate identity; the runner's exit status alone
is not treated as a pass.

## Remaining goal

At 33.728 CPU seconds per 120 ms dual-RX dwell, the exhaustive pipeline is
about 281 times slower than continuous arrival, or 468 times the 72 ms budget
needed for 40% CPU headroom. This change does not establish simultaneous
capture feasibility. The higher-rate FFT gains are separate and have not
been combined with this build.

The next discovery strategy must sharply reduce the frequency of exhaustive
search. The companion `2026_09_28_arm_causal_feasibility` experiment shows why
simply alternating full search and previous-window tracking is insufficient;
those retrospective coverage numbers are not actual detector recovery.
