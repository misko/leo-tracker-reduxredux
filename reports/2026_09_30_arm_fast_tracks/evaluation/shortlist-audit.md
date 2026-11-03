# Physical 151/8/512, cap-16 shortlist audit

Status: independently checked comparison evidence; final receipt is pending the
seed-expansion result and the producing binary/source closure.

The physical ARM output
`../grid/physical-standard151-cap16.tsv` is byte-identical to
`../grid/arm-standard-151-8-512-cap16.tsv`. Both are 731,588 bytes with SHA-256
`0f3d42176c76f3d21f8c933793c6e26e389849d5493b9f9bbd38193b94d335be`.
It contains 9,728 input observations, 3,636 used observations, and 94 native
tracklets. The eight exact lanes contain 6, 8, 9, 12, 12, 15, 16, and 16
tracklets, consistent with the configured cap of 16. The research output has no
published config or tracklet identity digest; the comparator reports those
identity fields as unavailable rather than treating them as parity evidence.

The physical timing receipt (SHA-256
`8fe4d896ccef10a1f9ff382f3d9e93acba21d4d6ac4d3158a3b3503192327415`)
records 151 slope bins, 8 peak hypotheses, 512 intercept bins, minimum support
8, minimum span 4 seconds, maximum gap 4 seconds, and 16 tracks per lane.
Reconstruction took 1.637786333 seconds and the whole tracking process took
2.145223827 seconds. This is saved-observation tracking time. It excludes IQ
capture and GLRT detection and is not a continuous pipeline latency result.

Re-running the frozen comparator against the physical path produced
`physical-standard151-cap16.comparison.json` (SHA-256
`89524d8de60116d84fb96ce6a52a853648c4b413cc8ac614d41e4bddf6a06cb9`).
Apart from the bound input path/hash, it is semantically identical to the
host-output comparison.

| association | matches | supported reference misses | unsupported references | unmatched native tracklets |
|---|---:|---:|---:|---:|
| strict | 42 | 20 | 1 | 52 |
| relaxed | 57 | 5 | 1 | 37 |

All 42 strict pairs and all 57 relaxed pairs share canonical recording sources
and have modulo-alias CFO-consistent GLRT evidence. The strict pairs share 2,147
such sources, at least 12 per pair. The relaxed pairs share 2,688, at least 8
per pair. Strict pair extrema remain inside the frozen thresholds: interval
Jaccard at least 0.819246, shorter-track coverage at least 0.915859, slope
difference at most 101.241 Hz/s, and alias-aligned curve difference at most
1,110.874 Hz. Relaxed extrema are respectively 0.531912, 0.830409,
204.049 Hz/s, and 1,737.285 Hz.

The 37 unmatched native tracklets are **extras relative to this maintained
tracklet oracle**, not adjudicated false positives. Thirty share at least one
canonical source with an oracle track, 19 share CFO-consistent GLRT evidence,
and 10 share at least six consistent sources. Most fail association because
their time support is fragmentary: for the best same-lane/source-consistent
comparison, 34 fail the relaxed overlap requirement, two first fail its slope
gate, and one first fails its curve gate. The server result also contains graph
hypothesis structure while this native TSV contains reconstructed tracklets.
That representational difference and the pending graph/seed-expansion analysis
must be resolved before any false-positive or full-recovery claim.
