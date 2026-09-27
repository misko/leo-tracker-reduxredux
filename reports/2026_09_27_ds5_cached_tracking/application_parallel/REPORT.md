# Parallel complete scanner analysis

The persistent 22-worker prototype reduced complete single-dwell wall latency
by 8.20x at 2.5 MS/s and 10.69x at 5 MS/s on the two selected development cases.
It preserved every full analysis field in every warmup and measured call. This
is parallel processing of the 22 receiver/probe tasks within one dwell, not
queuing future visits or dropping candidate evidence.

| Rate | Mode | Median wall | Wall speedup | Aggregate CPU |
|---|---|---:|---:|---:|
| 2.5 MS/s | Serial | 1,385.62 ms | 1.00x | 1,385.57 ms |
| 2.5 MS/s | 8 workers | 209.59 ms | 6.61x | 1,427.29 ms |
| 2.5 MS/s | 22 workers | 168.92 ms | 8.20x | 1,987.75 ms |
| 5 MS/s | Serial | 3,992.34 ms | 1.00x | 3,991.92 ms |
| 5 MS/s | 8 workers | 566.80 ms | 7.04x | 4,081.12 ms |
| 5 MS/s | 22 workers | 373.45 ms | 10.69x | 5,162.46 ms |

The 22-worker mode increased CPU consumption by approximately 43% and 29%
respectively. Eight workers used about 3% and 2% more CPU. The 10.69x observation
is therefore a wall-latency result on one case, not a 10x compute reduction,
universal speedup, or completed qualification. Both resulting wall times still
exceed a 120-ms dwell duration.

## Method and scientific scope

The two cases are the same previously profiled v1077 visits, selected initially
by metadata, and now outcome-exposed development examples. Both are positive.
Each comparison uses ten acquisition candidates, eleven overlapping probes and
both receivers. Each worker invokes the unchanged repository analyzer on one
20-ms receiver probe. The parent reconstructs chronological probe/RX order and
applies the original decision-history fold. Equality includes every candidate
response, first detection, decision and final maxima, and reason.

There is one warmup per mode and rate followed by three cyclically
counterbalanced repetitions. The serial baseline and parent run on CPU 0.
Eight workers occupy performance cores 0..7; 22 occupy cores 0..21, including
14 efficiency cores. The parent shares core 0 with one worker. Numerical
library thread limits equal one. The whole experiment, including process pool
startup and shutdown, completed in 53.55 seconds.

Timed calls include CI16 conversion, a shared-memory dwell upload and its
create/close/unlink lifecycle, per-worker probe copies, descriptor/result IPC,
all DSP, and the serial decision fold. Persistent process creation and shutdown,
file IO/hash checks, configuration construction and response validation are
outside per-call timing. Raw inputs were checked unchanged. No production code,
holdout, RF access or thresholds were changed.

Aggregate CPU is parent process CPU plus worker `/proc/PID/stat` user/system
tick deltas. Worker accounting has 10-ms resolution per process; it is adequate
to expose the material extra CPU cost, not sub-millisecond precision. The
separately recorded worker-detector clocks are diagnostics and are not added
again. These medians have only three repetitions and do not estimate p95,
long-run scheduling contention or a deployment service-level guarantee.

Nine component tests compare the decision fold with the repository oracle for
early/late/no confirmation, overlap, competing candidates, ties and CFO
boundaries, and verify the shared-memory worker's receiver/probe coordinates.
Full-process serialization and actual scientific behavior are exercised by
the paired recorded-IQ run. Broader recorded and constructed cases remain
necessary before integration.

Frozen result SHA-256:
`ac0bcaa26e80125ea569143337c7a86a95c0a268acafdbcf0096795cf70de303`.
Source-lock SHA-256:
`b0c089048b6b1be0d861fedddae7098823299b11513494453cce9e33025e1cf4`.

The next useful comparison is a scientifically validated track-guided detector
that reduces acquisition work, alongside broader qualification of this latency
option. Do not multiply the parallel gain with separately measured early-exit
or native-detector gains.
