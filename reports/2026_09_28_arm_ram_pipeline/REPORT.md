# ARM GLRT with concurrent capture-to-RAM replay

The existing optimized native GLRT worker keeps up at 2.5 MS/s on CPU0 while
CPU1 supplies saved IQ through a bounded RAM ring. It completed all 720
concurrent 2.5-MS/s dwells without drops or detectable queue growth. Its mean
analysis CPU cost was 69.24 ms per 120-ms dual-receiver dwell under continuous
arrivals: about 42.3% of the nominal analysis-core CPU budget remains.

This is **not proof of 40% whole-system headroom during real radio capture**.
The running kernel's tick-based CPU accounting aliases with the replay timing,
and the experiment does not execute DMA, IIO capture, or the adaptive scanning
front end. It also uses the existing reduced native detector, not the full
server GLRT search whose individual-detection recovery targets are 80%/90%.

## What ran

Physical PLUTO+ `192.168.1.15`, two ARM cores online, approximately 495 MiB RAM.
Inputs are the same 28 frozen DS7 dual-RX, 120-ms visits: sixteen at 2.5 MS/s
and four each at 5, 7.5, and 10 MS/s. All selected targets are upper edge.
Source hashes, compiler commands and binary hashes are retained beside this
report. The unchanged qualified native D and goal40mag kernels were rebuilt
with the same scientific flags and a new producer/consumer harness.

CPU0 runs GLRT sequentially. CPU1 writes twelve paced 10-ms chunks per dwell
into a three-slot ring; GLRT reads the actual produced slot. Inputs, templates
and ring buffers reside in RAM before timing. A full queue drops the incoming
dwell but still performs its writes into a discard buffer. All outputs are
buffered until measurement ends, apart from the pre-timing ready record.
No RF collection, firmware changes, service changes, or SD formatting occurred.

The 32 completed phases comprise isolated analysis and concurrent replay for
each method/rate, with three repeats of each concurrent schedule at 2.5 MS/s.
The continuous schedule starts captures every 120 ms. The other schedule uses
DS7 sample-counter start offsets; continuation beyond the finite saved block
uses the mean observed gap at the seam. It is a replay, not additional data.

## Four-rate results

CPU values are mean milliseconds per complete dual-RX dwell, from isolated
runs with three executions of every saved case. Drop counts are from the
concurrent optimized worker; they retain every scheduled dwell in the denominator.

| Rate | Baseline D CPU | Optimized CPU | Speedup | Continuous replay drops | Counter-paced replay drops |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 108.79 ms | 67.25 ms | 1.62× | 0 / 360 | 0 / 360 |
| 5 MS/s | 208.71 ms | 127.63 ms | 1.64× | 6 / 60 | 0 / 60 |
| 7.5 MS/s | 322.70 ms | 202.73 ms | 1.59× | 26 / 60 | 20 / 60 |
| 10 MS/s | 416.59 ms | 259.48 ms | 1.61× | 34 / 60 | 32 / 60 |

Concurrent optimized CPU costs rise to 69.24, 135.63, 221.21 and 293.87 ms
under continuous arrivals. The higher-rate concurrent means cover only
processed jobs, so their dropped-job selection is not an unbiased speedup
comparison. Use the complete isolated inventory for the speedup column.
At 5 MS/s the saved cadence is roughly 140 ms; its zero-drop result has little
spare capacity. At 7.5 and 10 MS/s this single worker cannot sustain either
tested arrival schedule. A larger ring would defer overload, not resolve it.

## 2.5 MS/s latency, memory, and CPU reserve

Under continuous replay, the optimized worker uses 69.24 ms CPU versus its
67.25-ms isolated mean, an approximately 3% contention cost. Mean service
wall time is 69.26 ms. The 95th percentile from buffer readiness to result is
approximately 72.2 ms; capture-start-to-result adds the 120-ms capture itself.
Maximum queue wait is 0.101 ms. Counter-paced replay has a 68.93-ms mean CPU
cost and a 0.142-ms maximum queue wait. Peak resident memory is 51.4 MiB.
No 10-ms producer chunk was more than 1 ms late in any optimized 2.5-MS/s run.

The producer uses approximately 10.16 ms of thread CPU per continuous dwell,
or 8.5% of CPU1's nominal budget. This is the CPU-copy simulator's cost, not a
measurement of real capture. It does not quantify DMA/interrupt overhead,
the existing adaptive scan analysis, or their combined memory traffic.

CPU0 `/proc/stat` headroom estimates for the three continuous repeats are
41.46%, 41.81%, and 37.01%, despite almost identical precise GLRT thread costs.
CPU1 illustrates the problem more starkly: the same roughly 8–9% producer
thread load appears as 0.6%, 0.6%, and 100% in tick-based whole-core accounting.
The post-run kernel configuration confirms `CONFIG_TICK_CPU_ACCOUNTING=y`,
`CONFIG_HZ_PERIODIC=y`, and `CONFIG_HZ=100`; the replay's 10-ms chunk cadence
matches that tick. Virtual CPU accounting, IRQ-time accounting and scheduler
statistics are disabled. The discrepancy is consistent with timing aliasing;
these counters cannot certify robust inclusive CPU headroom for this workload.

Use the precise thread measurements to budget the analysis work, and keep
whole-core/IRQ/background reserve unqualified. The experiment establishes
zero drops and a bounded queue for this saved-IQ workload, not a robust 40%
production headroom gate. Short repeated phases also do not establish long-run
thermal or worst-case capacity.

## Scientific scope and next priorities

The native workload ranks six windows and confirms one per receiver. It is
different from the full server eleven-window/eight-candidate search. Native
output parity is evaluated independently from dropped-work accounting; a
correct output for an executed job does not recover a dropped dwell.
Across all 28 unique dwells / 56 receiver results, the optimized kernel retains
31/31 native-baseline positives, adds none, and preserves all decisions and
2,962 checked categorical/selection values. Maximum absolute final score
delta is 2.34e-15, CFO is unchanged, and the maximum timing difference is
9.10e-14 microseconds. Each method is science-bit-exact across repeated cases
and between resident input and consumed RAM slots, excluding instrumentation.
These are native-profile receiver positives, not full-search individual
candidate detections. All 32 phases close their accounting: 2,328 planned
jobs, 2,011 processed, 317 explicit drops, and zero detector failures.
See `summary.json`, `AUDIT.md`, and `SOL_AUDIT.json` for the independent checks.
No full-search individual-detection recovery percentage is inferred here.

Keep one ARM analysis core as the primary optimization target, with CPU1
reserved for capture and the adaptive front end. Prefer eliminating repeated
work, unnecessary RAM copies, and scalar DSP overhead before adding analysis
threads. This measurement shows the current native optimization survives RAM
contention at 2.5 MS/s; it does not justify spending the second core on GLRT.

Next, benchmark the actual adaptive front-end processing on saved RAM inputs
alongside this worker, and bring the complete candidate inventory onto ARM so
speed can be scored against the original individual-positive detections.
Final live-capture validation should then measure loss, queue stability, and
end-to-end latency with trustworthy CPU accounting. It remains separate from
this no-RF experiment and requires a bounded authorized collection.

Reproduction commands for all four rates are in `EXAMPLES.md`. `run01/run.json`
binds all phase outputs and staged inputs; host sanitizer receipts cover both
kernels at all four rates in both modes.
