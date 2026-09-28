# ARM RAM pipeline audit

## Scope fixed before the pipeline run

This experiment replays cached DS7 IQ through the ARM worker while a separate
RAM-resident producer supplies paced chunks.  It is a bounded implementation
and contention experiment.  It does not collect RF, change firmware, or
establish an integrated live adaptive-feedback pipeline.

The 80% and 90% quality targets refer to **individual original-positive GLRT
detections recovered**, not milliseconds of service time and not confirmation
recovery.  This reduced ARM harness has not established those recovery gates
against the complete server scanner, so it must not report either target as
passed or failed.  Completion, drops, queueing, output identity, service CPU,
and latency remain separate outcomes.

## Frozen antecedent evidence

`goal40mag` is the qualified ARM candidate.  Its probe binary is
`2f3d90978343b7e51bfe039e5a20fa9090b35ebccb26992d132f6a9c4d82f249`; the
source/compiler receipt is
`../2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/arm.build.json`.
The original-D comparison is the strict assessor receipt in
`../2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/arm-all/assessments.json`.
The full ARM receipt completed 104 cases and passed.  Its manifest has 38,
38, 14, and 14 cases at 2.5, 5, 7.5, and 10 MS/s respectively: 80 real saved
IQ cases plus 24 constructed controls.  The corresponding detailed statement
and numeric bounds are in
`../2026_09_27_plutoplus_static_arm/optimize/GOAL40MAG_SCIENCE_AUDIT.md`.

That antecedent proves the candidate retained the assessed D decisions,
selection diagnostics, and bounded floating values on its saved-IQ corpus. It
does not make the new DS7 inputs a continuation of that corpus.  This run must
therefore compare baseline D and goal40mag directly for every executed DS7 job
and retain the prior gate as context only.

The selected goal40mag build retains both receivers, six ranking windows, one
confirmation attempt per receiver, and its original frame and known-symbol
support.  It does **not** implement the server scanner's complete eleven
20-ms-probe by eight-candidate inventory.  Thus a passing RAM-pipeline
comparison supports exact output preservation for the specific ARM workload;
it cannot claim full-server candidate, probe, or confirmation recovery.

## Inputs and pacing

The new workload uses the frozen DS7 plan:
`../2026_09_28_ds7_glrt_benchmark/plan.json`, membership
`47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.
It specifies 28 chronological dual-receiver 120-ms visits: 16 at 2.5 MS/s and
four at each of 5, 7.5, and 10 MS/s.  Each row's
`sample_start_counter` is the authoritative source-time coordinate.  The
pipeline must derive the producer schedule from consecutive counter deltas at
that row's native rate; for the 2.5-MS/s sequence these are approximately
120.02--140.47 ms.  Producer readiness at +120 ms is a separately recorded
implementation condition, not permission to substitute a fixed 120-ms arrival
schedule.

The older `concurrent/arrival-offsets.txt` file is deliberately excluded. It
records network-publication bursts from a different scan and contains gaps
below 120 ms; it is not the DS7 RAM-pipeline cadence.

## Required receipt checks

The evaluator will reject a run unless it supplies a terminal completion
record, a unique planned job identity for every baseline/optimized and
isolated/concurrent cell, and explicit producer/consumer accounting.  It will
keep the following denominators distinct:

* planned jobs;
* producer emitted and dropped jobs;
* consumer executed and completed jobs; and
* jobs eligible for each paired scientific and latency comparison.

Scientific equality will canonicalize a job result after removing timer and
queue fields only.  It will compare isolated and concurrent outputs for the
same binary, then D and goal40mag for the same condition.  Missing, dropped,
failed, duplicate, or mismatched jobs remain visible and fail an exact-pair
claim; dropped jobs are included in the planned-detection accounting rather
than discarded from the denominator.  CPU and latency summaries use completed
jobs only and report their denominator alongside p50, p95, and maximum.

Queue trend reporting will retain chronological first/last buckets and the
maximum, rather than infer stability from a mean.  Headroom will use measured
per-core busy counters over the actual producer/consumer overlap; it must not
use whole-machine CPU averages or include pre-start/quiet-tail monitor deltas.

`/proc/stat` is a whole-core, 100-Hz jiffy-granularity measure.  It includes
unattributed kernel and other-process activity, whereas the producer and
consumer thread clocks measure only this benchmark's threads.  The 10-ms
producer cadence can alias that 10-ms tick accounting.  A repeated phase may
therefore have materially different core-busy estimates despite near-identical
per-job consumer CPU.  Whole-core headroom is consequently not reliable for a
robust 40% gate in this experiment.  The final report must preserve the
per-repeat range and report the precise consumer-thread CPU divided by the
producer window as a benchmark-thread budget, explicitly not as full-system
headroom.

## Route to a broader server comparison

A feasible future ARM scorer would feed the same 28 cached payloads through a
portable runner that serializes all eleven probe outputs and all eight
candidates per receiver, then applies the frozen DS7 `scoring.py` associations
on the host.  It requires an explicit ARM-compatible adapter and source seals;
it is not part of this RAM experiment.  Until then, the result is correctly
limited to the ARM rank-six/one-confirmation workload.

## Observed run01 receipt

`run01/run.json` completed all 32 declared phases with zero command exits.  Its
phase SHA-256 inventory, the ready/complete envelopes, cyclic case ordering,
and terminal counters all validate in `summary.json`.  Across all phases there
were 2,328 planned jobs, 2,011 completed jobs, 317 explicit queue-full drops,
and zero detector failures.  By native rate, the accounting was:

| Rate | Planned | Completed | Queue-full drops |
|---:|---:|---:|---:|
| 2.5 MS/s | 1,536 | 1,536 | 0 |
| 5 MS/s | 264 | 213 | 51 |
| 7.5 MS/s | 264 | 147 | 117 |
| 10 MS/s | 264 | 115 | 149 |

At 2.5 MS/s every same-binary isolated-versus-concurrent comparison passed
exactly after timer fields were removed: D and goal40mag each passed all three
fixed-period and all three source-counter-cadence concurrent repeats.  The
inherited D-to-goal40mag gate also passed in isolated mode and in every 2.5
concurrent repeat: no structural identity failure, no decision difference,
and no added positive in the reduced native profile.

For 5, 7.5, and 10 MS/s, every **produced pair** passed the inherited identity
and decision checks and no exact same-binary mismatch was observed.  Those
phases nevertheless fail a complete paired claim because D and goal40mag drop
different scheduled jobs.  The summary retains each unavailable index.  It
does not convert successful surviving rows into all-job recovery or an 80%/90%
full-server detection claim.

goal40mag at 2.5 MS/s had concurrent service p95 71.6--72.9 ms and maxima
73.1--74.7 ms across the six runs.  Fixed-period queue maxima were
0.08--0.10 ms; source-counter-cadence queue maxima were 0.09--0.14 ms.  Its
consumer-thread CPU divided by the producer window was 57.7--57.8% under
fixed arrivals and 51.7--51.8% under source-counter arrivals.  These are
precise benchmark-thread budgets.

The corresponding whole-core `/proc/stat` producer-window estimates were
41.46%, 41.81%, and 37.01% CPU0 unused for the three goal40mag fixed-period
repeats, and 47.94--48.78% for the three source-counter repeats.  The fixed
third repeat simultaneously reported CPU1 busy for all 1,440 100-Hz ticks
while its producer thread used only 1.282 seconds of CPU over a 14.47-second
window.  The target's saved kernel configuration confirms periodic 100-Hz tick
accounting and lacks virtual CPU accounting, IRQ-time accounting, and
schedstats.  These whole-core estimates are therefore retained as observations
only and do not establish a robust 40% headroom gate.
