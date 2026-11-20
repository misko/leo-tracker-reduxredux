# Union of paired receiver epoch proposals

The epoch union matched **43 of 47 capture-era positive candidates**, exactly the same per-visit, per-RX candidate ranks as the pinned wide detector. It recovered no additional archived positives in 31 authenticated dual CI16 windows and lost none. Mean native CPU rose from **15.28 to 16.78 ms** per dual window, a **9.8%** increase. The union changed the returned candidate payload in all 31 windows. Detections outside the archive match fell from 51 to 48. Archive matches are the recall reference, and the out-of-reference count has no truth label. [Recall, cost and receiver timing](recall-and-cost.png) · [Per-receiver rows](per-lane.csv)

| Capture | Processed windows | Archive positives | Matched by either detector | Own-RX / union mean native CPU |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036, development | 8 | 16 | 16 | 15.16 / 16.66 ms |
| DS29-0082, development | 8 | 7 | 5 | 14.86 / 16.12 ms |
| DS26-0122, held | 8 | 10 | 8 | 15.54 / 17.28 ms |
| DS29-0247, held | 7 | 14 | 14 | 15.62 / 17.11 ms |

The eight planned DS29-0247 windows include one acquisition excluded from the original capture-era factor stream on both receivers. The other 31 had decoded CI16 hashes, source manifest and index hashes, matching acquisition counters, RF, and independent receiver IDs 0 and 1. The matching tolerance was 2 samples modulo a frame and 1 kHz modulo the symbol ambiguity, with the original 0.025 fractional gate and one-to-one assignment. The four missed archive rows represent two duplicate-ranked peak pairs on RX0. Their fractional archive epochs remained **1,185 and 723 samples** from the nearest union member at DS29-0082 visit 5127 and DS26-0122 visit 2053. The archived peaks were outside the neighborhoods supplied by either scout. [Missed epochs and aggregate counts](summary.json)

## What changed

The overlay changes the compiled 10 MS/s dual-RX short-window entry point. Both calls to the original top-four scout run before any regional scoring. For each receiver, the kernel marks the original clipped ±1 neighborhoods and the other receiver’s clipped ±1 neighborhoods, then enumerates the exact union in ascending order. Candidate scoring, the eight-slot output cap, the wide CFO range and the fractional gate use the same code as the pinned wide detector. This changes epoch acquisition scope, whereas the earlier paired-peaks study combined candidates after native GLRT. [Build and source delta](build.json) · [Earlier paired-peaks experiment](../../integration/paired-peaks/README.md)

Each original receiver evaluated 12 distinct epochs. Both lanes evaluated 21–24 after union. Own-lane neighborhoods were fully disjoint in 24 of 31 windows. The archived co-epoch and relative-CFO checks found four comparable stereo pilot pairs in these actual test windows. Their fractional RX1 minus RX0 timing ranged from **−0.260 to +0.011 samples**, about −26 to +1 ns at 10 MS/s. This estimate is conditional on the co-epoch and CFO association. The common hardware counter aligns each sampled instant. The small signal-level deltas describe only the four matched pilots. [Physical pair observations](summary.json)

## Same-IQ controls and compatibility

The disabled overlay matched the pinned wide binary’s canonical candidate payload byte for byte at every archived window. Identical zero-delay stereo lanes also matched byte for byte with the union enabled on both pilot edges. Independent zero-delay oscillators and a planted +37-sample stereo separation preserved both planted pilot detections. The +37-sample specimens widened the evaluated sets from 12 to 24 per lane, with some differences among other returned candidates. Both noise specimens returned zero positive detections. At the same time, the ordinary 120 ms dense and sparse APIs, 10 MS/s single RX and 5 MS/s dual RX cases matched the pinned binary byte for byte. An early preflight confirmed that the existing ordinary API rejects 40 ms. The final controls use the supported 120 ms layouts. [Exact canary outputs](canary.json)

Wall means across four rotated repeats were 16.22 ms for the original wide binary, 17.36 ms for the disabled overlay and 19.20 ms for union. Native CPU means were 15.28, 15.23 and 16.78 ms, respectively. Native timing excludes Python receipt conversion and qualification trace reads. The ABI-1 union library builds from the exact staged wide source and runs through the normal whole-IQ short-window entry without a CLI change. This report covers the raw detector stage. Complete position replay belongs to the separately scheduled whole-recording benchmark. [Prospective schedule](PROTOCOL.md) · [Library receipt and digest](build.json)
