# Measured results

All timings below are physical PLUTO+ CPU0 measurements. The primary workload
is 2.5 MS/s, a 120 ms dual-RX dwell, and **two first-20-ms receiver-windows**.
Every row uses the identical 152 saved dwells × 10 repetitions. Times include
input preparation; first calls are retained. Quantiles use nearest rank, with
the usual median for p50. The control is a fresh matched 152-dwell measurement,
not the earlier 32-dwell panel's 119.56 ms mean.

## Matched detector wall time

| ARM build / experiment | Mean ms | p50 ms | p95 ms | Maximum ms | Calls ≥120 ms | Native positive candidates retained |
|---|---:|---:|---:|---:|---:|---:|
| Published computation, full-preparation control | 117.95 | 116.34 | 154.20 | 203.22 | 595/1,520 | 461/461 |
| Prepare only the consumed 20 ms | 59.94 | 58.47 | 96.77 | 146.20 | 10/1,520 | 461/461 |
| Add exact irregular-rotation cache | 59.60 | 58.25 | 96.68 | 120.83 | 1/1,520 | 461/461 |
| Rotation cache + original 32-context PGO | 51.55 | 49.98 | 80.17 | 109.17 | 0/1,520 | 461/461 |
| Four-frequency tile, per-call input allocation, no PGO | 59.71 | 58.32 | 96.98 | 125.03 | 10/1,520 | 461/461 |
| Tile + retained input buffers + 32-context PGO | 49.31 | 47.70 | 77.93 | 112.93 | 0/1,520 | 461/461 |
| **Final source: tile + lazy buffers + persistent fine plan, no PGO** | **49.64** | **48.19** | **78.22** | **96.05** | **0/1,520** | **461/461** |
| **Final source + tail-aware 33-context PGO** | **48.45** | **47.00** | **77.45** | **93.93** | **0/1,520** | **461/461** |

These are measured branches/ablations, not an additive accounting of each
optimization. Compiler and allocation/layout interactions matter: the naive
tile and the undertrained PGO combination did not meet the preferred gate.
The final non-PGO source also meets it, so the source improvement does not
depend on compiler training. PGO adds a modest further improvement.

## CPU and broader timing boundaries

| Interval / build | Mean ms | p50 ms | p95 ms | Maximum ms |
|---|---:|---:|---:|---:|
| Control detector CPU | 117.90 | 116.31 | 154.10 | 203.22 |
| Final non-PGO detector CPU | 49.63 | 48.19 | 78.22 | 96.05 |
| Final PGO detector CPU | 48.44 | 46.99 | 77.45 | 93.81 |
| Final non-PGO persistent-client cycle wall | 50.69 | 49.20 | 79.49 | 97.23 |
| Final PGO persistent-client cycle wall | 49.49 | 48.00 | 78.73 | 95.15 |

The client cycle includes monitoring, JSON formatting and flush, but excludes
file preload, process startup, context creation and final destruction. It is
not capture-to-result latency. Final PGO context setup alone averages
**101.44 CPU ms / 101.48 wall ms**, maximum **103.20 wall ms**, across the ten
primary batches. Loading each 8/16-dwell batch from saved files averages
**2.01 wall seconds**; this file I/O is outside the RAM detector boundary.
Starting a process and constructing a context per dwell cannot use the
persistent detector result as its end-to-end budget.

## What consumes the time

Disjoint outer **mean CPU ms per dual-RX dwell**, control → final PGO:

| Phase | Control | Final PGO |
|---|---:|---:|
| Small bookkeeping allocations | 0.013 | 0.012 |
| Input preparation, including any buffer allocation | 60.694 | 8.682 |
| Proposal generation and ranking | 16.246 | 15.256 |
| Search and scoring | 31.723 | 24.116 |
| Cleanup | 8.808 | 0.008 |

Remaining outer overhead includes validation, clock reads and result copying.
Nested final counters are: proposal folding **6.60 ms**, correlation
**5.90 ms**, ranking **2.66 ms**; coarse search **7.58 ms**, acquisition
**4.40 ms**, conditioned scoring **5.91 ms**, and final GLRT **5.97 ms**.
Fine FFT time is **4.31 ms within acquisition**, so do not add it again.

The earlier link-wrapped diagnostic measured **2.91 ms** of allocator activity,
**2.50 ms** creating two FP32 FFT plans per dwell, **8.23 ms** of FP32 FFT
execution and **2.02 ms** of FP64 FFT execution. These measurements are
inclusive, instrumented, and partially nested inside the phases above.
They cover link-visible calls, not every allocation inside shared libraries
or all allocator entry points. The final source retains its fine plan in
the context instead of recreating it twice per dwell.

## Scientific output and the correct denominators

Counts below cover **152 unique dwells**, not ten repeated copies. The timing
run executes 3,040 receiver-window calls; it represents **304 unique windows**.
All eight measured builds have identical ordered candidate fields, scores,
window placement and row counters after removing timing fields.

| Quantity | Native control | Every optimized build |
|---|---:|---:|
| Unique 20 ms receiver-windows searched | 304 | 304 |
| Windows with a native positive candidate | 144 | 144 |
| All native candidate entries | 470 | 470/470 unchanged |
| Positive native candidate entries | 461 | 461/461 unchanged |
| Frozen original positive candidates recovered in scheduled windows | 392/409 | 392/409 (95.84%) |
| Frozen original positive scheduled windows with ≥1 matching recovered candidate | 143/148 | 143/148 (96.62%) |
| Frozen original dense positive candidates recovered | 392/4,573 | 392/4,573 (8.57%) |
| Diagnostic downstream projected entries | 461 | 461, identical values |

The dense reference searched **3,344 windows**, of which **1,682** were positive.
The sparse schedule never searches most of those windows. These optimizations
lose no additional native detections; they do not turn sparse coverage into
dense coverage. Native candidates unmatched to the oracle are not automatically
false detections. The frozen matcher is the historical one-to-one timing/CFO
matcher, not an assertion of exact numerical equality to the original scorer.

Downstream comparison exercises the unchanged public overlap projector with
the same diagnostic adapter as the stride report: **zero fractional offsets
and synthetic UTC authority**. Exact projected equality does not qualify live
timestamp authority, fractional refinement, track associations, or satellite
identities. Raw candidates and projected observations are separate counts.

## Compiler training and compatibility

Tail-aware PGO trains on 33 explicitly listed contexts, including the measured
clipped-grid outlier. The remaining **119 contexts / 1,190 calls** have wall
mean **48.76 ms**, p95 **78.42 ms**, maximum **93.06 ms**. The 33 trained contexts
have mean **47.31 ms**, p95 **71.61 ms**, maximum **93.93 ms**. Both sets retain
every native candidate. This is compiler training, with no detector-parameter
tuning. See the declared [protocol amendment](PROTOCOL.md) and
[training panel](pgo-training-panel-v3.json).

Additional rates use eight saved dwells each, two repetitions, the same
120/120 geometry and final PGO build. They are compatibility spot checks,
not a sustained high-rate deadline qualification:

| Rate | Calls | Mean wall ms | p95 / maximum wall ms | Meets 120 ms? |
|---|---:|---:|---:|---|
| 2.5 MS/s | 1,520 | 48.45 | 77.45 / 93.93 | Yes, measured RAM panel |
| 5 MS/s | 16 | 180.12 | 217.09 / 217.09 | No |
| 7.5 MS/s | 16 | 265.49 | 327.66 / 327.66 | No |
| 10 MS/s | 16 | 302.71 | 424.70 / 424.70 | No |

All candidate fields and row counters also match on these 24 higher-rate
dwells. Primary peak process RSS is **51,828 KiB (50.61 MiB)**, including up
to **38.4 MB of preloaded IQ**, with final PGO XADC temperature averaging
**73.62°C**, maximum **75.42°C**. No frequency/throttling interface was
available; temperature stability is not proof of an unchanged clock.

The measured intermediate retained-buffer build failed the 7.5-MS/s × 360-ms
memory check. The final implementation releases sparse buffers before larger
geometries. The [final bounded rerun](hardware-geometry.json) passes
**7.5 MS/s × 360 ms and 10 MS/s × 240 ms** for all three strides. The
10-MS/s × 360-ms case still returns `NOMEM` under the 220,000 KiB cap.
All 36 geometries pass host tests and sanitizers; the final physical rerun
targets these memory boundaries, not a new full 36-case ARM campaign.
Longer-dwell science is tested synthetically; saved-data comparisons here
use 120 ms dwells.

## Sustained candidate-heavy qualification and process cost

A separate post-hoc stress panel takes the 16 slowest control dwells sharing
the worst case's upper-edge template pair and replays them 100 times in
shuffled order in **one persistent process**. This is deliberately difficult
input, not an unbiased held-out sample. All **1,600 calls** preserve the
control's ordered candidate values, and both CPU and wall maxima remain below
100 ms:

| Final tail-aware PGO interval | Mean ms | p50 ms | p95 ms | Maximum ms |
|---|---:|---:|---:|---:|
| Detector CPU | 74.98 | 74.43 | 91.75 | 94.17 |
| Detector wall | 75.00 | 74.44 | 91.75 | 94.17 |
| Persistent-client cycle wall | 76.36 | 75.70 | 92.94 | 95.34 |

The detector therefore retains **25.83 ms / 21.5% of the 120 ms period at the
worst observed call**, and the broader client cycle retains 24.66 ms. The run
contains about 120 seconds of detector execution and 122 seconds of complete
client cycles. It has no excluded warm-up calls or deadline misses.

Stress XADC temperature averages **74.09°C**, maximum **75.67°C**. Peak process
RSS reaches **69,212 KiB (67.59 MiB)** within the first 16 calls and remains at
that high-water mark through call 1,600. This includes the larger 1,600-entry
qualification manifest and 38.4 MB of preloaded IQ; it is not a detector-only
heap measurement. See [stress summary](stress-summary.json) and the raw archive.

Five fresh-process native CLI cases, including three expensive and two
no-candidate dwells, take **0.21–0.36 seconds wall time** using device-side
`time -p` (10 ms display granularity). They include file input, context setup,
detector work, output and exit, exclude SSH transport, and do not flush the
filesystem cache. These are process-start measurements, not cold-boot or
cold-storage measurements. **The one-process-per-dwell path misses 120 ms.**
It needs a persistent RAM caller to use the qualified detector throughput.
CLI scientific comparison normalizes only its existing `glrt_complete: 0/1`
representation to the diagnostic client's Boolean; every numeric score and
candidate coordinate remains exactly equal.

The final separately instrumented 20-call worst-dwell check measures **zero
per-call FFT plan creations** and mean **0.17 ms** of link-visible allocator
activity. Its maximum is 101.49 ms because it includes diagnostic wrappers;
that distinct binary is not the qualified release or a headline timing.

The preferred detector gate is met on the representative panel and sustained
stress. This permits stopping the optimization iteration without adding
approximate early rejection, lower precision, reduced candidate budgets or
concurrent dwell execution. It remains a saved-IQ, single-core qualification,
not proof of hard-real-time behavior or simultaneous capture losslessness.
