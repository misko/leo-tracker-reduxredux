# Further proposal and FFT experiments

The subsecond goal remains unmet. These follow the published 2.010-second
checkpoint; they are research experiments using saved IQ, with no RF capture
or production changes.

Best completed full-path result: **1.866 seconds per 120 ms dual-RX dwell**,
with **19,225/19,581** original standard hits recovered (98.18%). Two ARM runs
measured 1.864160 and 1.867225 seconds, averaging 1.865693 seconds. This is
about 12.2% faster than the fused four-feature comparison below, still about
15.5 times the 120 ms real-time budget. The headline uses an actual outer
timer, not a sum of separately timed stages.

| Fused method | ARM outer CPU s/dwell | Standard hits recovered |
|---|---:|---:|
| Four-feature proposal, original moment screen (V2) | 2.125040 | 19,249/19,581 |
| Omit-power proposal (V3) | 1.961313 | 19,225/19,581 |
| Omit-power plus improved NEON moment layout (V4), two-run mean | **1.865693** | **19,225/19,581** |

ARM times below use CPU0 on PLUTO+ 192.168.1.15, four 2.5 MS/s 120 ms dual-RX
dwells, 88 receiver-specific windows and 704 candidate entries. Proposal times
are measured separately from search. The stage sums exclude initial setup,
file loading and simultaneous capture, and are not fused measurements. They
also exclude the outer CI16-to-FP64 window conversion and proposal-region
construction; the earlier report's conversion scope has been corrected.

Quality is actual host execution on 704 mixed-rate DS7 dwells from 88
recordings: 15,488 windows, 123,904 candidate entries, 19,581 standard hits.
Matching uses the same sealed standard pipeline and one-to-one matcher as
the preceding report. This is not the entire DS7 dataset.

| Method | Search s/dwell | Proposal s/dwell | Stage sum s/dwell | Standard hits recovered | Unmatched positives |
|---|---:|---:|---:|---:|---:|
| Published four-proposal exact-reuse checkpoint | 1.280431 | 0.729167 | 2.009598 | 19,249/19,581 | 21,555 |
| Three proposal regions | 1.259394 | 0.729167 | 1.988560 | 19,209/19,581 | 23,234 |
| Four proposals from power-of-two resampled features | 1.299038 | 0.658604 | 1.957641 | 19,249/19,581 | 21,576 |
| Omit power feature, retain three lag features | 1.294460 | 0.570501 | 1.864961 | 19,225/19,581 | 21,418 |
| Batched two-frame fine FFTs | 1.296940 | 0.729167 | 2.026106 | 19,249/19,581 | 21,555 |
| Packed Q15 final matched-filter dots | 1.371701 | 0.729167 | 2.100868 | 19,249/19,581 | 21,555 |
| Four-frequency FP32 NEON moment screen, v1 | 1.323542 | 0.729167 | 2.052709 | 19,249/19,581 | 21,555 |
| Above, with precomputed frequency powers and contiguous phase loads, v2 | 1.228289 | 0.729167 | 1.957456 | 19,249/19,581 | 21,555 |

The new search timings in this table are single runs except omit-power
(1.296148 and 1.292771 seconds, averaged); the published reference also uses
two runs. Proposal timings average three executions per unique dwell.
Repeated execution does not enlarge the quality sample. All listed new ARM
search variants recover 119/119 standard hits on their small timing panel;
the larger host audits above remain the relevant recovery comparison.

Three proposal regions lose 40 more standard hits for only about 21 ms saved
in search, so four remain preferred. Resampled proposals preserve the total
recovery count but change candidate outputs; equal totals do not mean equal
hit identities. Omitting power saves 159 ms in proposals relative to the
current NEON/radix implementation, with 24 additional misses on the larger
cohort. Its total stage sum improves by about 7.2% relative to the checkpoint.

Batching preserves every candidate object on the full cohort and physical
ARM panel, but shows no runtime improvement. Its all-rate host, sanitizer
and physical ARM component tests pass. The half-length folded FFT is rejected
earlier: its coarser frequency grid recovers 805/843 hits on the 32-dwell
panel versus 835/843 for the preferred two-frame method. No ARM speed claim
is made for that rejected approximation.

`wave2-results.json` records completed summaries and exact standard audits.
Proposal receipts and numerical tests remain in the sibling resampled and
feature-ablation report directories. Packed Q15 final dots preserve aggregate
recovery but slow the GLRT stage from about 303 to 415 ms/dwell; this variant
is rejected for speed. The first NEON moment-screen implementation is also
slower despite retaining aggregate recovery. Neither result demonstrates a
general advantage for reducing floating-point operation counts on this ARM.
The fused four-feature V2 benchmark measures **2.125040 seconds/dwell** using
one outer process-CPU timer around proposals, region construction, conversion
and search. Its internal stage sum is 2.072791 seconds: **52.249 ms/dwell**
falls outside those internal timers. It preserves every candidate object on
the four-dwell ARM panel. Fused V1 used an arithmetic sum labeled `fused_total`;
that historical field must not be interpreted as an outer measurement. V2
retains the sum explicitly as `stage_sum` and measures `fused_total` directly.
The omit-power fused V3 benchmark measures **1.961313 seconds/dwell**, with
1.336930 seconds of search, 0.572192 seconds of proposals and 52.191 ms outside
the internal timers. It retains all candidate objects from the standalone
omit-power method on the complete 704-dwell host cohort and the four-dwell ARM
panel: 19,225/19,581 host hits, 119/119 ARM-panel hits. The earlier 1.864961-second
stage sum is not a complete RAM-processing runtime. Fusion also changes code
generation/cache behavior: its search timing is higher, so external conversion
alone does not account for the difference between separately built methods.

The revised NEON moment screen precomputes frequency powers and transposes the
phase table for contiguous loads. It cuts the measured conditioned stage to
256.259 ms and search to 1.228289 seconds while preserving aggregate recovery.
Its component suites pass on host, sanitizer and physical ARM at all rates;
all candidate outputs equal V1 on the full host cohort and small ARM panel.
The combined omit-power plus revised-NEON fused V4 benchmark measures
**1.864160 seconds/dwell** in its first ARM run. Its actual host execution on
the full 704-dwell cohort recovers **19,225/19,581** standard hits, with 21,418
unmatched positives; all 15,488 windows and 123,904 candidate entries run.
That is 175 fewer hits than the earlier 19,400-hit restricted-search result,
or 356 misses against standard analysis. The physical ARM timing panel retains
119/119 standard hits, with 148 unmatched positives.

V4 uses an outer timer and includes region construction and CI16 conversion.
It measures 1.246889 seconds of search and 0.565660 seconds of proposals,
with 51.611 ms outside those internal timers. Compared with fused V2's
2.125040 seconds, its two-run mean saves about 12.2%. Its host/sanitizer component tests and
physical ARM all-rate component suites pass. FP32 moment accumulation changes
candidate numerical values; matching hit totals are not bitwise equivalence.

The V4 build separates the proposal translation unit from LTO and avoids the
global aliasing relaxation used by earlier fused builds. An FFTW LTO type
declaration warning remains recorded in the build receipt. The tests and
actual candidate comparisons qualify these experimental artifacts; no general
compiler-semantic equivalence or production readiness is claimed. The
subsecond objective remains unmet, and capture is still excluded.
