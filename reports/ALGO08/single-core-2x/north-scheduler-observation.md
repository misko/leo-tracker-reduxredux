# Scheduler observation on the northern public pair

## Saved evidence

On the same northern recording and containing offer, the spectral candidate and the `6cdbac…` successor both spent about 3.6 seconds more in elapsed time than on CPU. Their deployed arms spent about 0.4 seconds more. All four arms charged zero input blocks and zero major faults. The candidate in each case recorded eight voluntary switches. Its involuntary switches rose to 1,428 and 1,396, respectively. These counts establish neither time spent runnable nor time spent sleeping. [Spectral pair](measurements/spectral-terminal-north-inside.json) · [Successor freeze](exact-curved-lookahead.md)

| Northern build | First arm | Deployed wall minus CPU | Candidate wall minus CPU | Candidate launch → detections / detections → terminal / terminal → exit |
|---|---|---:|---:|---:|
| Spectral terminal guard | Deployed | 0.414 s | 3.553 s | 8.02 / 9.48 / 1.88 s |
| Exact curved design and lookahead | Deployed | 0.444 s | 3.595 s | 12.24 / 5.66 / 1.90 s |
| Earlier terminal guard | Deployed | 0.559 s | 0.301 s | 8.58 / 5.79 / 2.04 s |
| Batch orbit | Deployed | 0.592 s | 0.270 s | See receipt |
| Same batch-orbit build, reversed | Candidate | 0.499 s | 0.224 s | See receipt |

The candidate's terminal-to-exit interval is about 1.9 seconds in both anomalous pairs. Most of their elapsed differences versus the earlier terminal-guard case appear before the terminal. The earlier raster-layout candidate showed a 3.736 s gap while running first on the same recording. In a separate same-build physical crossover already on record, the short DS30-0016 candidate gap was 3.67 s candidate-first and 0.25 s deployed-first with zero charges in both orders. These archived controls rule out a simple rule based on the arm that runs first. [Northern matched order repeat](batch-publication.md) · [Earlier raster-layout pair](measurements/north-edge-full-search.json) · [Physical order repeat](batch-publication.md#short-physical-repeat-with-deferred-collection)

## Clock and process accounting

The regular harness takes the `RUSAGE_CHILDREN` and monotonic clock snapshots around `subprocess.run`. This includes launch, the child lifetime, stdout and stderr capture, and the wait for reaping. The artifact validator and receipt parsing run after the measured interval. The counter difference includes the leader, its threads and children it reaped. The deployed and frozen candidate shell launchers both exec Python. CPython drains stdout and stderr with a selector and waits for the launcher after both pipes close. Its timed POSIX wait uses sleeps capped at 50 ms, which can overrun if the harness itself is waiting to run. A child retaining a pipe can extend the boundary past the leader's exit. [Benchmark clocks](../../../tools/pipeline_eval/qualification/paired_publication.py) · [CPython subprocess implementation](https://github.com/python/cpython/blob/v3.12.14/Lib/subprocess.py) · [Resource accounting](https://man7.org/linux/man-pages/man2/getrusage.2.html)

With `--observe-scheduler`, the benchmark still drains both capture pipes and uses the same outer clock markers. One selector also waits on the timed leader's pidfd. When it becomes ready, the harness reads the leader's three `schedstat` counters from `/proc` before reaping and records when it observed exit. It records when both output pipes reached EOF, then reaps the same PID with `wait4` to cross-check CPU and read counters. No polling thread runs during acquisition. On timeout, the diagnostic branch kills the launcher's isolated process group and reaps the leader. Linux runnable time is per task, so the leader's reading excludes queues of other threads or subprocesses. Observation timestamps include any delay in scheduling the parent. Its own runnable-wait and CPU counters are in the diagnostic. [Observer source](../../../tools/pipeline_eval/qualification/launcher_observation.py) · [Kernel scheduler counters](https://www.kernel.org/doc/html/v7.0/scheduler/sched-stats.html) · [PID file descriptors](https://man7.org/linux/man-pages/man2/pidfd_open.2.html) · [Waited child usage](https://man7.org/linux/man-pages/man2/wait4.2.html)

Gauss has `CONFIG_SCHED_INFO=y`, and the 7.0 kernel supplies per-task fields independently of the two current `sched_schedstats` and `task_delayacct` runtime toggles. A synthetic check on CPU 23 with both toggles zero detected 1.5 ms of runnable wait during a 240 ms sleep and 198.5 ms while the same CPU also ran an intentional competing spinner. The latter closed the gap between approximately 330 ms elapsed and 131 ms CPU. The monitor used 0.38–0.52 ms of its own CPU across the short probes. Seventy-one targeted tests passed, including large writes to both pipes, a descendant retaining them after leader exit, timeout cleanup, descendants' CPU and the unchanged prelaunch/clock markers. [Linux scheduler configuration check](https://raw.githubusercontent.com/torvalds/linux/v7.0/include/linux/sched/stat.h) · [Test coverage](../../../tests/pipeline_eval/test_launcher_observation.py)

## Prespecified reversed pair

Run one new pair with the **candidate first**, on the public northern recording and original 100 m inside offer. Use the deployed release and the unchanged `sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f` candidate. Reuse only the capture-time archive inventory `sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec`. Use one pinned CPU 2, the Gauss lock and existing low priorities. Cap each launcher at 60 s. Preserve the original deployed-first receipt byte-for-byte under SHA-256 `9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb`. [Frozen launch options](measurements/exact-curved-lookahead-freeze.json)

For each arm, compare `wait4` to the regular CPU and input-block counters. Compare `elapsed − CPU` with the leader's runnable time and separately report the interval from observed leader exit to observed pipe EOF. Treat a gap of at least one second as predominantly runnable delay if the leader accounts for at least 80% of that gap, CPU clocks agree to within 10 ms and the monitor reports no comparable tail. If the large gap does not recur, report the new run's accounting without assigning a cause to the original gap. Record voluntary and involuntary switches and stage timestamps for context. Compare the same build across both orders for raw authority, exact ordered factor rows and scores, both positions and residuals, owners, grid, path and eight decoded figures. This timing uses one existing public waveform and supplies no new location coverage.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
scene=/tmp/leo-regional-qZJKBw4W/public
frozen="$bench/integration-exact-curved-lookahead"
env PYTHONPATH="$PWD:$PWD/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m tools.pipeline_eval.qualification.paired_publication \
  "$scene/0abe7b4514be674d9f5388e3" "$bench/near-edge/0abe7b4514be674d9f5388e3.json" \
  "$scene/tle" "$frozen/reports/ALGO08/single-core-2x/run-candidate" \
  "$bench/exact-curved-lookahead-north-scheduler-reverse" \
  --candidate-config "$frozen/spec.json" --first candidate --cpu 2 --timeout 60 \
  --archive-inventory-sha256 sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec \
  --observe-scheduler
```

The candidate-first repeat finished in 16.051 s elapsed and 15.779 s CPU. Deployment finished in 32.985 s elapsed and 32.442 s CPU. The scheduler measured 0.272 s and 0.542 s of runnable wait respectively, accounting for over 99% of each wall-minus-CPU gap in this repeat. Both arms charged zero input blocks and major faults. The parent observed pipe EOF and process exit within 21 µs of each other, and finished timing within 0.2 ms of the exit observation. Across orders, all 2,400 rows, 456 selected factors, both solutions and eight decoded PNGs agreed for each build. The earlier 3.595 s gap did not recur. Its cause remains unresolved. This repeat contributes no additional recording to the original two-site distribution. [Reverse-order receipt](measurements/exact-curved-lookahead-north-scheduler-reverse.json) · [Accounting and cross-order audit](measurements/north-scheduler-observation-audit.json)
