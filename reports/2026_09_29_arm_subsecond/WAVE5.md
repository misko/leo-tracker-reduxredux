# Fifth ARM optimization iteration

The final combination averages **0.915434 seconds per 120 ms dual-RX dwell**
across 152 physical-ARM dwells. On the common four-dwell timing panel it measures
**0.960375 seconds**, versus 1.686498 seconds for Wave4. It recovers
**19,217/19,581 original individual GLRT detections** on the 704-dwell DS7
mixed-rate cohort. This is 183 fewer than the earlier 19,400-hit method and
nine fewer than Wave4. This crosses one second on the small timing panel;
the 120 ms real-time budget is substantially stricter still. It is not a
concurrent-capture qualification or a worst-case latency guarantee.

The larger physical-ARM run covers **all 152 2.5 MS/s dwells in the DS7
benchmark cohort**, with **3,344 receiver-specific 20 ms windows**. Its mean
is **0.915434 seconds**, median **0.897812**, p95 **1.219146**, maximum
**1.421993**, and minimum **0.708478**. Exactly **105/152** dwells finish below
one second and none within 120 ms. It recovers **4,506/4,573 standard hits
(98.53%)**, emitting **6,030** candidates and executing **6,032** final-scorer
calls. All windows run. This is the selected DS7 cohort, not all DS7 data.
There are 1,079 unmatched native positives, which are not verified false alarms.

Thus the subsecond **average** milestone is reached; a one-second tail bound
and real-time operation are not. Mean CPU remains 7.63 times the 120 ms budget,
before concurrent capture. The 704-dwell mixed-rate quality figures below are
host measurements; the 152-dwell 2.5 MS/s recovery is measured on ARM itself.
Do not compare the larger-panel mean directly with a four-dwell control to
claim a paired speedup. On the identical four-dwell panel, final v1 is 43.1%
less CPU than Wave4's two-run mean.

All methods below run every one of the 15,488 receiver-specific 20 ms windows
(22 per dwell). Gates reject candidates after coarse search, before fine
refinement and final scoring. They do not pretend that rejected candidates
received GLRT evaluation. The full reference inventory is 123,904 candidate
entries; actual emitted entries are reported separately.

Across the same cohort, actual final-scorer executions are 120,197 for
Wave4, 95,823 for gate 0.300, 85,822 for gate 0.312 and 85,821 for gate
0.312 plus the degree-one screen. The final quadratic combination executes
85,822 final-scorer calls, with 14,316 cache hits and 13,699 boundary fallbacks
(`arm_wave5_final/execution-inventory.json`). These differ from emitted candidate counts
because exact cached results avoid calls while boundary refinement can require
another call. Every emitted candidate has completed final GLRT scoring.

| Method | ARM outer seconds/dwell | Standard DS7 hits recovered | Emitted candidates |
|---|---:|---:|---:|
| Wave4 control, two-run mean | 1.686498 | 19,226/19,581 | 123,904 |
| Wider conditioned blocks, 128 samples | 1.627034 | 19,226/19,581 | 123,904 |
| Wider conditioned blocks, 256 samples | 1.619488 | 19,223/19,581 | 123,904 |
| Quadratic conditioned approximation, block 64 | 1.631160 | 19,226/19,581 | 123,904 |
| Four sample lanes for conditioned moments | 1.687492 | 19,226/19,581 | 123,904 |
| Rate gate, 2.5 MS/s threshold 0.300 | 1.459760 | 19,226/19,581 | 97,090 |
| Rate gate, 2.5 MS/s threshold 0.312, two-run mean | **1.170951** | **19,217/19,581** | **86,439** |
| Gate 0.312 + degree-one conditioned approximation | 1.144747 | 19,217/19,581 | 86,439 |
| Gate 0.312 + quadratic block-64 approximation | 1.130646 | 19,217/19,581 | 86,439 |
| Gate + degree-one screen + exact direct CI16 ingestion | 1.053592 | 19,217/19,581 | 86,439 |
| Wave4 + exact linear coarse top-eight selection | 1.692752 | 19,226/19,581 | 123,904 |
| Gate + quadratic screen + exact direct CI16 ingestion | 1.039576 | 19,217/19,581 | 86,439 |
| Gate + quadratic screen + exact sparse peak extraction | 1.086087 | 19,217/19,581 | 86,439 |
| Gate + quadratic screen + direct input with prepared coarse prefix | 1.010502 | 19,217/19,581 | 86,439 |
| Gate + quadratic screen + direct input + sparse extraction | 0.996375 | 19,217/19,581 | 86,439 |
| Above plus prepared coarse input/prefix, final combination | **0.960375** | **19,217/19,581** | **86,439** |
| Final v2, invalid-output argument guard | 0.960455 | 19,217/19,581 | 86,439 |

Unless labeled otherwise, times are single four-dwell measurements on CPU0 of
PLUTO+ 192.168.1.15 at 2.5 MS/s. Larger-cohort recovery is measured by native
host execution, not inferred from the four timing dwells. The four-dwell ARM
runs recover 119/119 reference hits. The outer timer includes proposals,
regions, conversion and search; it excludes file loading, initial workspace
setup and concurrent capture. No RF was run. These remain research prototypes.

The gate thresholds for 5/7.5/10 MS/s are 0.150/0.175/0.152 respectively.
At 2.5 MS/s, 0.312 emits 6,030 of 26,752 candidate entries and recovers
4,506/4,573 standard hits. It removes 77.46% of candidate work at that rate,
but only 31.04% of measured total CPU time: proposal generation and coarse
search still run. Thresholds were selected on DS7, so DS7 is a tuning result.

## Independent recording checks

The independent panels contain 32 DS8 and 32 DS9 dwells, balanced across all
four rates. Each dataset runs 704 receiver/windows. The comparison below
separates losses already present in Wave4 from the new experiments.

| Method | DS8 original hits recovered | DS9 original hits recovered |
|---|---:|---:|
| Ungated Wave4 | 774/785 | 888/908 |
| Gate 0.300 | 774/785 | 887/908 |
| Gate 0.312 | 773/785 | 886/908 |
| Gate 0.312 + degree-one screen | 773/785 | 884/908 |
| Gate 0.312 + quadratic block-64 screen | 773/785 | 886/908 |

The degree-one screen changes five lost and five gained reference-hit
identities on DS7 despite equal aggregate counts. It adds two DS9 misses,
both in the same 2.5 MS/s receiver/window. Equal counts therefore do not imply
identical detections. Unmatched native positives also remain unclassified;
these experiments do not establish false-alarm performance.

The quadratic block-64 combined screen preserves every matched-hit identity
relative to gate 0.312 on all three panels and is faster on the four-dwell ARM
panel than the degree-one combined screen. This is the preferred numerical
approximation among those combinations tested so far.

Direct raw CI16 ingestion removes a temporary FP64 complex array and a second
validation/copy pass. It preserves all candidate objects versus the linear
combined screen, on both host704 and the ARM panel, saving 91 ms/dwell. The
superseded ingestion prototype unnecessarily normalized internal samples; its
evidence remains separate. The accepted v3 stores raw integer-valued FP64
samples exactly like the existing runner, leaving normalization to coarse
search. It also checks stride/index overflow.

Exact linear coarse peak selection did not improve runtime. Its first build
accidentally replaced sparse regional coarse evaluation with a full epoch
search while repairing a test compilation unit. The resulting failed parity
assertion and 21.210-second diagnostic are invalid comparisons and are
preserved separately. The corrected build changes only peak selection and its
test, achieves exact candidate parity, but remains slightly slower than Wave4.

By contrast, extracting peaks only from the already evaluated timing positions
saves 44.6 ms versus the quadratic gate. Inactive grid entries are negative
infinity and cannot qualify as local maxima. The optimized extractor retains
the original ordering, neighbor tests and stable selection; full-cohort and
ARM candidate parity are exact. This removes a full-grid inspection without
changing which candidate positions are searched.

Preparing FP32 coarse samples and the FP64 energy prefix during the direct
CI16 input traversal saves another measured 29 ms relative to direct input
alone. It preserves the original arithmetic order and candidate values.
Explicit prepared-state checks and reset tests prevent stale buffers from
being reused across input counts, invalid calls, or the original complex
entry point.

The final combination in `../2026_09_29_arm_wave5_final` combines the 0.312
gate, quadratic block-64 conditioned screen, raw direct ingestion, prepared
coarse samples/prefix and sparse peak extraction. It retains the original
stable top-eight selection, all 22 windows, all conditioned frames/frequencies,
and FP64 final scoring. On host it exactly preserves every candidate object from the
quadratic gate on DS7, DS8 and DS9. The exact input/extraction changes therefore
add no quality loss. Six component tests passed on host, sanitizer and ARM,
including raw/prefix bit equality, invalid-state reset, stride overflow,
sparse-vs-full extraction and the direct-DFT approximation bound.

The 152-dwell distribution uses sealed final v1. A separate final v2 adds
early rejection of a null output pointer, clearing prepared input state on
that error path. Valid benchmark CLI calls always supply an output structure;
their data path is unchanged. Both builds and their receipts are preserved,
and v2's complete host cohort retains exact candidate parity. Use the v2 build
for further development; do not relabel the v1 distribution as a v2 run.
V2 also passes all six physical-ARM component tests and measures 0.960455
seconds on the common four-dwell panel with exact candidate parity to v1.
Cross-architecture host/ARM scores are not bitwise identical: 1,783 of 3,344
windows have tiny differences, at most 9.03e-8 in coarse score and 4.44e-16
in final score/margin. All 4,506 matched original hit identities are identical
on the same 152 contexts (`ARM_HOST_2500_QUALIFICATION.md` in the final report).

Proposal generation now costs 471 ms/dwell on the larger ARM panel, about
51% of total CPU, exceeding the entire real-time budget by itself. The next
major improvement therefore needs cheaper proposal generation or reuse across
overlapping windows; more final-scorer precision tuning alone cannot close the
remaining factor of 7.63. FLOP counts were not measured: these results establish
CPU-time and execution-count savings.

## Packing and lower precision

Four-sample NEON moment packing did not beat Wave4. Earlier Q15 FFTs and
packed spectrum caches were slower too. Compiler/local-complex tuning already
included in this line reduced the older raw-FP32 search from 4.863 to 4.468
seconds while preserving 19,400 hits; that comparison has a different timing
scope and must not be mixed with the fused outer times above.

The factor-five FIR plus NEON FFT microbenchmark reduced 200-transform time
from 0.219654 to 0.209472 seconds at 2.5 MS/s (4.6%); at 10 MS/s it reduced
1.373258 to 0.871785 seconds (36.5%). These are isolated kernel measurements,
not end-to-end GLRT improvements. The initial output-relative numerical test
failed on strongly cancelling full-scale input. A separately preserved
double-precision oracle and weighted-input forward-error bound subsequently
passed on ARM. The original failure is retained, and no detector-quality
qualification or integration is claimed for this kernel.

Dropping every other input sample for the entire detector failed quality:
551/843 recovered hits on the 32-dwell gate, including just 57/205 at
2.5 MS/s. That prototype is rejected without a larger ARM campaign.

Evidence: `wave5-results.json`, `../2026_09_29_arm_rate_coarse_gate`,
`../2026_09_29_arm_wave5_candidate`, and
`../2026_09_29_arm_rate_gate_transfer/{REPORT.md,WAVE5.md}`. Numerical
approximation tests use direct double-precision DFT references and explicit
Taylor-remainder bounds; the final GLRT scorer remains FP64.
