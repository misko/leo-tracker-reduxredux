# Toward subsecond single-core GLRT

## Status

**The subsecond objective remains unmet.** The strongest completed large-cohort
tradeoff in this checkpoint takes approximately **2.010 CPU seconds per 120 ms
dual-RX dwell** at 2.5 MS/s, including separately measured proposals. It recovers
**19,249/19,581 standard GLRT detections (98.30%)**, versus 19,400 previously:
151 additional misses, or 0.77 percentage points of the standard denominator.
It is about 2.65 times faster than the previous 5.319-second stage sum.

This is a research result from saved IQ on CPU0 of PLUTO+ 192.168.1.15. It is
not a fused pipeline measurement, not concurrent capture, and not real time.
The goal includes proposal generation; the 1.280-second search alone also
does not meet it. No production service, RF collection or scientific fixture
was changed.

## Progress with actual GLRT recovery

ARM timings use four saved 2.5 MS/s dwells. Large-cohort quality uses actual
host execution of the ARM-targeted algorithm on 704 mixed-rate DS7 dwells,
88 recordings, 15,488 receiver-specific windows and 123,904 candidate entries.
This is not every DS7 dwell. Stage sums do not multiply independent speedups.

| Method | ARM search s/dwell | Proposal s/dwell | Stage sum | Standard hits recovered |
|---|---:|---:|---:|---:|
| Previous compiler-tuned raw FP32 baseline | 4.468 | 0.852 | 5.319 | 19,400/19,581 |
| Full-frame moment-based conditioned screen, with exact near-max rechecks | 3.715 | 0.852 | 4.567 | 19,400/19,581 |
| Two-frame fine-frequency estimation alone | 2.539 | 0.852 | 3.390 | 19,243/19,581 |
| Combined two-frame search, radius 2, raw conditioned screen | 1.416 | 0.729 | 2.145 | 19,249/19,581 |
| Above, with exact duplicate-result reuse | **1.280** | **0.729** | **2.010** | **19,249/19,581** |

The final row's two ARM search runs measured 1.280100 and 1.280762 seconds;
the mean is 1.280431. Proposal timing is 0.729167 seconds, averaged across
three runs on the same four unique dwells. Repeats do not enlarge the sample.
Both cached ARM runs recover 119/119 original hits, with 155 unmatched positives
on that small timing panel. These counts do not replace the larger host audit.

| Sample rate | Previous recovered hits | New recovered hits | Additional misses | New unmatched positives |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 4,551/4,573 | 4,521/4,573 | 30 | 5,277 |
| 5 MS/s | 5,420/5,466 | 5,366/5,466 | 54 | 5,820 |
| 7.5 MS/s | 5,137/5,186 | 5,098/5,186 | 39 | 5,597 |
| 10 MS/s | 4,292/4,356 | 4,264/4,356 | 28 | 4,861 |
| Total | 19,400/19,581 | 19,249/19,581 | 151 | 21,555 |

All 15,488 windows still run. Of 7,007 originally positive windows, 6,926
retain a matched hit. The 21,555 unmatched positives exceed the previous
18,328; these are neither verified physical detections nor established false
alarms. Recovery alone does not establish output equivalence.

The cached implementation makes **123,940 actual GLRT kernel calls**, versus
143,300 logical calls (123,904 candidates plus 19,396 fallback requests).
It reuses 19,360 identical GLRT results and 2,387 conditioned results. All
candidate objects are identical to the uncached combined method on all 704
dwells. Both caches reset on every window and receiver invocation.

## What changed

1. **Two-frame fine-frequency estimation:** evenly spaced first/last available
   frames estimate fine CFO. Final GLRT still uses all available original
   scoring frames and symbols. This creates most of the new recovery loss;
   one-frame estimation was worse on the small panel.
2. **Conditioned moments:** replace the narrowband CZT screen with cached
   fourth-order block moments and phase factors. All conditioned frames and
   frequency bins remain. With FP64 near-max rechecks, v3 preserves all
   123,904 candidate objects on the larger cohort and cuts the measured ARM
   conditioned stage from 1.375 to 0.622 seconds. The fast combined variant
   separately skips these rechecks and uses the approximate screen directly;
   its actual hit counts above qualify that additional approximation.
3. **Fixed CI16 scaling:** use the known 32768 input bound instead of scanning
   each window for its maximum. This saves about 101 ms/dwell and preserves
   19,400/19,581 hits in its independent 704-dwell run. All 16 coarse frames
   and all 12 anchor symbols remain in the preferred combination.
4. **Smaller timing regions:** search +/-2 rather than +/-4 samples around
   each of four proposals. The full 32-dwell control preserves 838/843 hits;
   the complete combined method is audited separately above.
5. **Exact reuse:** cache identical final-scoring and conditioned calls using
   epoch, exact CFO bits and sample count, without collapsing candidate
   multiplicity. Physical and logical call counters are separate.
6. **Proposal implementation:** stable radix ranking plus NEON folding reduces
   full-resolution proposal CPU from 852 to 729 ms. The host full-cohort
   proposal rows match the existing FP32 proposal rows; the ARM fold test
   verifies bit-exact per-frame parity across all rates, lags and receivers.

The final scorer remains FP64. Raw FP32 fine FFTs still have no fine-FFT FP64
fallback. The residual-boundary conditioned fallback remains enabled. The new
raw-conditioned option omits only its frequency-screen near-max rechecks; it
does not remove residual-boundary detection or the final GLRT rerun.

## Rejected and exploratory alternatives

The small panel contains 32 mixed-rate dwells, 704 windows and 843 original
hits; its reference recovers 838/843. Do not compare that denominator directly
with the larger cohort. Component timings below are not complete detectors.

| Experiment | Observation | Decision |
|---|---|---|
| Exact padded proposal correlation | 878 ms proposals versus 852 ms reference | Slower |
| FFTW MEASURE proposal planner | 1,061 ms proposals versus 729 ms NEON/radix | Slower; planning time also reported separately |
| Four coarse frames | 623/843 hits | Reject quality loss |
| Six of twelve coarse anchors | 795/843 hits | Reject quality loss |
| Two conditioned frames with two fine frames | 757/843 hits | Reject quality loss |
| One fine-estimation frame | 827/843 hits | Worse than two frames; not expanded |
| Integrated direct-CI16 FP64 scorer alone | 4.462 s search versus 4.468 s | No material independent speed gain |
| FP32 final matched-filter dots | 4.549 s search; scoring 476 ms versus 369 ms | Slower on ARM |
| FP32 128/512-point GLRT FFTs | 4.457 s search; scoring 362 ms versus 369 ms | Small single-run difference; no promoted speed claim |
| Factor-two proposal resolution | 612 ms proposals; 836/843 hits with otherwise unchanged search | Exploratory |
| Factor-four proposal resolution | 398 ms proposals; 825/843 hits independently; combined larger run 18,884/19,581 | More recovery loss than preferred combination |
| Factor-four reciprocal normalization | 390 ms proposals | Small additional gain; not part of preferred method |
| Full-resolution features resampled to power-of-two grids | 659 ms proposals; 838/843 hits | Promising smaller-panel result; larger combined audit pending |
| Omit power from the four-feature proposal | 836/843 hits on the small panel | ARM timing and larger combined audit pending |

The initial moment prototype recomputed the same block sums inside the
frequency loop and was slower (6.550 s search). V2 hoisted that work but used
an overly broad recheck guard (4.210 s). V3 caches phase factors, accumulates
block totals in FP64 and restores the original guard (3.715 s). Earlier
snapshots remain evidence; only the measured v3 is used above.

## Verification and remaining work

Matching uses the sealed standard pipeline, same receiver/window, one-to-one
maximum-cardinality matches, margin >=0.025, timing distance <=2 samples and
tracking CFO <=8 kHz. Timing counts preparation, conversion, scaling,
per-window allocations/plans and cleanup within search. File loading and
initial workspace/template setup are outside the reported timed kernels.

Host and sanitizer component tests cover all four rates, partial/full/zero
input and relevant extreme numerical cases. The preferred combined and
exact-reuse component suites also passed on the physical ARM. Exact reuse
tests cover adjacent but unequal CFOs, count changes and reset boundaries.
Complete cohorts, frozen receipts, row hashes and standard audits are indexed
in `results.json`. Full row/IQ files remain in local experiment storage.

The next barrier is shared across proposal generation, fine estimation,
conditioned refinement and final scoring. No single remaining stage removal
proves the full objective. Remaining work includes further proposal/search
optimization, preservation checks on the complete 704-dwell cohort, a fused
CPU measurement, repeated ARM qualification, and later DS8/DS9 transfer and
concurrent capture tests. The goal remains active; this report is a measured
checkpoint, not a claim of subsecond completion.
