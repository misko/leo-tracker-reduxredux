# Adaptive capture and GLRT resource budget

Original planning document. The user's subsequent request authorized execution;
see [completed benchmark and ranked options](concurrent/REPORT.md). This plan
alone did not authorize new RF acquisition. The earlier saved-IQ measurements
isolated GLRT compute; the follow-up measures adaptive capture concurrently.

## Budget and scope

For consecutive 120-ms dual-RX visits on one shared CPU core, require:

    scan CPU + GLRT CPU + other CPU + reserve < 120 ms per visit

The optimized GLRT uses 108.06 ms mean CPU. It leaves only 11.94 ms for
everything else before saturation, with no reserve. For example, a measured
20% core load from capture/other work consumes 24 ms per visit. Reserving
another 10% (12 ms) leaves an 84-ms GLRT CPU budget. These percentages are
illustrative, not measurements of the radio.

CPU budget is necessary but insufficient: I/O stalls, preemption, memory
bandwidth and scheduling also affect elapsed service and feedback age.
Measure per-core utilization; 50% machine utilization on a two-core radio can
hide saturation of the one GLRT core. GLRT remains single-threaded/pinned to
CPU0. If capture can execute on CPU1, evaluate that as a separate deployment
arrangement, retaining shared-memory, IRQ and I/O contention measurements.

The local capture runner uses Ci16EnergyDetector, archives both receivers,
configures 120/240/360-ms active visits and 120-ms quiet visits, and publishes
feedback every eight completed visits. Its classifier is asynchronous, selects
one physical receiver, and can mark visits UNKNOWN when its queue fills.
These source findings are not a verification of current hardware state on .15.
Host-side classification/archival CPU must not be charged to the ARM unless
those components are actually moved there. Radio IIO/kernel/network/scheduler
work must still be measured.

## Paired measurement matrix

| Phase | Workload | What it establishes |
|---|---|---|
| Idle | Existing services, no new capture | Background load and profiler overhead |
| Scan only | Exact intended acquisition/storage/transport configuration, no GLRT | Base capture CPU and I/O demand |
| GLRT only | Paced resident saved IQ, persistent worker, one visit per 120 ms | GLRT queue and latency without capture contention |
| Combined | Same scan configuration plus single-core GLRT | Actual contention, queue stability and feedback age |

For initial radio-free work, replace the source with paced saved IQ and label
the scan-only/combined phases as replay. Read identical inputs in paired phases;
include required copies, queueing, output publication and actual intended sink.
Use existing immutable IQ and a separate local SD output directory. Bound each
phase to 60 seconds of measurement plus 10 seconds of warmup. Reuse a persistent
GLRT worker: repeatedly launching the current microbenchmark would include
per-process warmup/planning and would not reproduce the intended service.

Replay cannot establish DMA, RF retune, driver/IRQ or actual acquisition CPU
cost. A live scan-only/combined phase requires separate explicit RF authority,
or passive observation of an independently authorized running capture. Do not
start capture, change affinity of existing capture services, or alter radio
configuration as part of this plan. Preserve the prior no-RF scope on .15.

## Measurements

- Sample /proc/stat per core and per-process/thread CPU deltas at one-second
  intervals. Record affinity, threads, context switches, faults and RSS.
  Include kernel/IRQ/softirq time; do not sum process CPU again on top of total
  core busy time. Report I/O wait separately from executing CPU time.
- Record /proc/interrupts and softirqs where exposed, storage/network counters,
  CPU frequency/temperature where available, and profiler CPU overhead.
- Record each visit's source interval, enqueue, processing start, completion,
  publication and actual feedback-application time when observable. Keep CPU
  service, elapsed service, queue delay and capture-to-result age separate.
- Record input gaps, dropped visits/samples, classifier UNKNOWN/overflow,
  confirmations/fallbacks, queue depth and backlog slope. Report CPU mean and
  elapsed p50/p95/p99/max with sample counts, including expensive visits.
- Preserve configuration, binary/input hashes, raw receipts and original
  arrival timestamps. Use 120-ms pacing as a stress case and replay recorded
  variable-dwell arrivals separately. A 300-second capture's later idle period
  is not processing headroom for real-time feedback during capture.

## Acceptance and follow-on

Combined operation must preserve scientific comparisons and capture integrity,
with no silent skipped analysis, no sustained backlog growth, and a declared
feedback-age limit met at the scheduler boundary. If requiring every result
before the next 120-ms arrival, measure that explicitly as a stricter deadline.
Queue buffering can absorb bursts but cannot cure sustained CPU overload.

Derive the GLRT target from measured scan demand and an explicit reserve;
80 ms remains a provisional target, not proof of sufficient capacity. Prioritize
2.5 MS/s, then repeat the same protocol at 5/7.5/10 MS/s. Higher-rate support
does not currently imply real-time dual-RX compute at those rates.

Source references: tools/run_adaptive_capture_cycle.py;
../2026_09_27_ds5_cached_tracking/review/ARM_BASELINE.md;
/home/mouse9911/gits/pluto-plus-utils-feature-103/src/pluto_plus/adaptive_scan_shadow.py.
