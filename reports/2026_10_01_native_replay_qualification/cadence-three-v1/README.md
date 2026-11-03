# Three-scan fixed-cadence recorded load test

Status: **failed** on PLUTO+ 192.168.1.15. The second detector rejected 13 dwells;
the controller cancelled the active downstream chain and third detector.
This does not qualify sustained cadence.

| Scan | Completed dwells | Rejected | Positive observations | Queue peak |
|---|---:|---:|---:|---:|
| First, no downstream contention | 2,215 | 0 | 16,191 | 2/16 |
| Second, concurrent downstream | 2,202 | 13 | 16,093 | 16/16 |
| Third | Cancelled | Not a completed replay | Not evaluated | Not evaluated |

All processed GLRT candidates and emitted observation/support rows remain exact.
First-scan seed and track outputs equal host controls. Its search emitted 396 of
400 points, all exactly equal to the qualified ARM trace; it was cancelled before
completion and associations. The second-scan losses occurred at approximately
101–125 and 171–181 seconds; maximum dwell completion latency was 2.605 seconds.
Sampled aggregate process-tree RSS peaked at 242,216 KiB. The full per-scan
comparisons and `failure-analysis.json` retain the incomplete result explicitly.

First/second detector CPU times are 275.999508 / 288.695250 seconds. Their
whole-process wall times include approximately five seconds of scheduled
initialization lead (305.699354 / 305.641812 seconds); these must not be
interpreted as delayed scan origins. The actual detector clock receipts honor
the requested origins exactly, 300 seconds apart. Cadence timing was not rebased.

An idle ARM follow-up measured the controller's original process-tree memory
sampler at about 11.2 ms CPU per sample. At one sample per second that is roughly
3.3 CPU seconds per scan, excluding any increase from active workload processes.
This is a plausible contributor given the earlier two-second margin, not an
isolated attribution of the observed failure. `../cadence-sampler-cost-v1/`
and `../cadence-sampler-fast-v1/` preserve calibration and a cheaper parser test.

The native controller schedules three repeats of the same 300-second DS9
recording against one Linux monotonic origin. Each detector initializes five
seconds before its assigned origin; a missed initialization deadline fails
instead of shifting arrivals. At most two detector processes may coexist to
cover initialization and final drain at scan boundaries. Each keeps the
qualified bounded 16-dwell queue. The controller permits one active downstream
process and one waiting completed scan; exceeding either lifecycle or backlog
capacity fails explicitly and terminates remaining child process groups.

Each downstream chain consumes observations/support produced by its own
successful detector process. It reruns seeds, tracking, in-memory conversion,
TLE propagation, the full 400-point search, and associations. The first scan
has no prior downstream workload. The next two include downstream contention;
the final downstream job drains after the last arrivals. These phases must be
reported separately. Three repeats are a finite load test, not a genuine
900-second history, proof of indefinite capacity, or live-RF qualification.

No new RF is collected and IQ remains local to PLUTO+. Timing receipts and
scientific products will be downloaded for evaluation after their producers
finish. Numerical thresholds, search extent, TLE, tracking policy, and GLRT
are unchanged from the preceding qualified candidate.

`protocol.json` and `verified-payloads.txt` pin all executables, source inputs,
generated chain scripts and the measurement wrapper. `plan.tsv` is the native
controller input. Every output has a unique scan directory and existing outputs
are rejected. `controller.stdout` records launch/finish times, origins, queue
occupancy and one-second samples of aggregate process-tree RSS. RSS sums can
double-count shared pages and sampling can miss transient peaks; stage wrappers
also capture per-process high-water RSS, CPU and wall time. Controller sampling
and orchestration overhead are included in this load experiment.

Preparation is reproducible with `tools/prepare_arm_cadence.py`, using
`../fullchain-index-pgo-overlap-v1/protocol.json`, the fixed-clock detector from
`../fixed-clock-v1/`, and the controller built from `source/cadence.cpp`.
The controller is built with the existing ARM cross-compiler, C++17, `-O2`,
`-fno-fast-math`, Cortex-A9/NEON/hard-float flags, pthread, static libstdc++ and
libgcc. Sources, ARM executable and build log are preserved here.

The full benchmark suite passes 82 host tests at this run's source state.
They cover fixed origins, completed-product dependencies, bounded overlapping
processes, backlog overflow, child failure, cleanup, output preservation,
and rejection of missing/shifted/failed receipts. Test subprocesses use a
400 ms initialization lead so Python startup does not mask the intended
backlog failure; the physical protocol uses five seconds.

On completion, run `tools/evaluate_cadence_schedule.py REPORT`. Additionally
evaluate every scan with `evaluate_recorded_pacing.py`,
`compare_projection_subset.py`, and `compare_regional_results.py`, and compare
seeds, tracks, and associations against the independent host controls.
Schedule success alone does not establish scientific correctness.
