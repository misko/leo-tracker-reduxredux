# Three-scan replay with reduced monitoring overhead

Status: **all three recorded scans completed losslessly and passed numerical
comparison**. This demonstrates the finite three-scan execution; stable
longer-run throughput remains an open gate because the loaded downstream jobs
both exceed 300 seconds and waiting grows slightly.

| Scan | Positive observations | Dropped dwells | Detector queue peak | Maximum dwell latency s | Downstream wait s | Downstream wall s |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 16,191 | 0 | 7/16 | 1.085 | 0.0004 | 302.261 |
| 2 | 16,191 | 0 | 16/16 | 2.221 | 2.364 | 300.643 |
| 3 | 16,191 | 0 | 13/16 | 1.829 | 2.777 | 257.454 |

All **6,645 dwells / 48,573 positive observations** match the frozen detector
and projection controls. Every seed/track output, all 400 ARM search points,
and final associations match their controls exactly. Independent host search
comparison passes the unchanged 1e-9 Hz tolerance (maximum difference
5.684342e-13 Hz). This is parity with these controls; native tracking still
differs from server memberships, as documented by the independent tracker
comparison. The full search still exhausts its budget, not global convergence.

| Stage/workload wall seconds | Scan 1 product | Scan 2 product | Scan 3 product |
|---|---:|---:|---:|
| Detector, from scheduled origin to observed exit | 300.627 | 300.524 | 300.756 |
| Seed generation | 3.990 | 3.908 | 3.592 |
| Track reconstruction | 4.150 | 4.316 | 3.867 |
| Conversion + orbit + full search + associations | 294.076 | 292.377 | 249.949 |
| Whole downstream, measurement wrapper | 302.253 | 300.636 | 257.439 |

Controller-observed downstream durations in the first table include small
launch/reap overhead beyond the stage wrapper. Detector whole-process wrapper
times are about 305.5–305.7 seconds because they include the five-second
initialization lead. Scan origins are exactly 300 seconds apart; they are not
rebased to match those process durations. Detector CPU is 275.180 / 287.610 /
288.338 seconds; downstream CPU is 285.650 / 285.959 / 257.373 seconds.

The last downstream result is an unloaded drain and cannot establish loaded
throughput. The first two loaded jobs average **301.452 seconds**, and the
waiting time rises from 2.364 to 2.777 seconds. There is insufficient evidence
of a stationary backlog or comfortable real-time reserve. Detector queue 2
also reaches its full capacity, although nothing is dropped. Reduce measured
downstream overhead and test further loaded intervals before declaring the
overall sustained-cadence goal complete; keep the original interval and gates.

The controller uses at most two detector processes and one pending completed
scan. Sampled aggregate RSS peaks at **230,780 KiB (225.37 MiB)**. Per-process
high-water RSS is at most 67,044 KiB for detection and 151,676 KiB for positioning.
Whole-device counters over an approximate loaded 330.3-second interval show
0.34% idle and 0.59% I/O wait. They include activity outside measured child
processes and are not per-stage attribution. See `device-cpu-interval.json`.

`evaluation.json` records all per-scan checks, timings and evidence/reference
hashes. `execution.json` confirms controller success; `controller.stdout`
preserves fixed origins and complete process accounting. Host benchmark tests
pass **94/94**, and replay contract tests pass **66/66**. Their logs are included.
`cadence.png` and `cadence.pdf` visualize latency, process overlap and sampled
memory, with the final unloaded drain shown explicitly.

This repeats the failed `../cadence-three-v1/` load experiment with two observer
changes: the measured cheaper `/proc/PID/stat` parser and aggregate process-tree
RSS sampling every five seconds. Scientific binaries, their inputs, the
16-dwell detector queues, downstream capacity, priorities, and fixed 300-second
origins are unchanged. Each stage still records high-water RSS with `measure-run`.
Five-second aggregate samples can miss transient peaks; they are diagnostic,
not a precise aggregate maximum. This combined change does not isolate parser
improvement from sampling-frequency effects.

The repeated recording produces three independent scan products, with no new RF
collection and no IQ transfer. The first scan has no downstream contention;
the next two overlap downstream work from preceding scans; the final downstream
job drains after the last arrivals. Each chain consumes its own successful
detector's fresh observations/support, then runs seed generation, tracking,
conversion, TLE propagation, full 400-point search, and associations.

`protocol.json` pins payloads and explicitly records the monitoring interval.
The native controller admits at most two overlapping detector lifecycles, one
downstream worker and one pending completed scan. Failure is explicit and
cancels remaining child process groups. `source/`, deployed binaries and the
ARM build log preserve this experiment's implementation.

Preparation: `tools/prepare_arm_cadence.py` with the preceding full-chain
protocol, fixed-clock detector, current controller and `--memory-sample-ms 5000`.
Execution: `PYTHONPATH=src:tools python tools/run_arm_cadence.py REPORT_DIRECTORY`.
The runner verifies local/device hashes, requires a fresh device directory,
preserves execution receipts, and retrieves only allowlisted scientific/timing
products after termination. An SSH timeout is not interpreted as remote failure;
inspect the existing remote job before restarting anything.

After successful termination, run `tools/evaluate_arm_cadence.py` with explicit
frozen detector/checkpoint references and independent host seed, track, search,
and association controls. It also verifies fixed origins, dependencies, queue
capacity, memory-policy receipts and completed process inventory. An incomplete
or failed run cannot pass through the combined evaluator.
