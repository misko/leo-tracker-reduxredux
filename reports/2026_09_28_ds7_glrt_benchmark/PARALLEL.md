# Four-worker method and concurrent startup-smoke record

The four-worker arm reuses the frozen complete-window adapter from
`2026_09_27_ds5_cached_tracking/application_parallel/parallel_scanner.py`
(SHA-256 `5ca243da1e11e8d5654272d8529242266072a5e37d99af3d5444255eb1f637ff`).
It runs all receiver/probe tasks, reconstructs chronological probe/receiver
order, and applies the existing decision fold. It does not drop candidates or
use future visits. Workers are persistent and pinned one each to CPUs 0, 1, 2,
and 3; numerical-library thread environment variables equal one.

Pool creation and worker readiness are outside per-dwell measurements and are
reported in `creation_diagnostics`. Each dwell reports parent process CPU,
worker CPU from `/proc/PID/stat` tick deltas, their aggregate, task-local worker
detector CPU, and wall time. Worker tick resolution is 10 ms on this host.

## Startup smokes during the first serial replay

The first serial replay started at **2026-09-28 00:36:54 UTC** and remained
active during these smokes. There was no exclusive CPU reservation: its parent
was pinned to CPU 0, which one parallel worker also used. These exercises can
therefore add scheduler and cache noise to overlapping serial rows. No timing
is discarded on that basis; both serial replays remain evidence, and modest
differences are treated as uncertain on the busy shared host.

| UTC evidence | Exercise | Shell wall | Measured inner work | Result |
|---|---|---:|---|---|
| Script mtime `00:40:29.487343546` | Initial pool startup | 1.766 s | CPU not recorded | No DSP call. The strict check observed two workers before their affinity initializer completed and rejected startup. Shutdown completed; the four observed PIDs were later confirmed absent. |
| Bounded by final source mtime `00:42:08.505213867` and abort-script mtime `00:42:45.388906253` | Corrected startup plus one zero 20-ms, dual-RX analysis | 3.048 s for Ruff, three tests, startup, and smoke | Pool creation wall 0.891178608 s; parent creation CPU 0.003928674 s; readiness wall 0.889841495 s. Dwell wall 0.041109639 s; parent CPU 0.001245253 s; worker CPU 0.080000000 s; aggregate CPU 0.081245253 s; worker detector CPU 0.077231219 s. | Complete two-response negative result; four unique workers pinned to CPUs 0..3; normal close completed. Input was generated zeros, not DS7 or saved radio IQ. |
| Script mtime `00:42:45.388906253`; shell returned within 1.640 s | Startup then immediate public `abort()` twice | 1.640 s | CPU and inner creation timing not printed | No DSP call. All four owned worker PIDs were absent after abort; the second call was a no-op. |

The successful zero-data smoke only establishes process spawning, affinity,
shared-memory transfer, response folding, accounting fields, and cleanup. The
separate post-serial paired replay is the scientific exact-output and latency
comparison on the frozen 28-visit workload.

Final source hashes:

- `methods_parallel.py`:
  `280122c0accd29ea538b5c1188bfbbc1b4b19f02d7ed47d0acfdcd7d78af155c`
- `test_methods_parallel.py`:
  `2a3fb7163d7a52d0016758b055290905caa6c577ecea64f85ea0d0a15e55c0ca`

Ruff passed and all three component tests passed. The public `abort()`
terminates only the method-owned worker processes, joins for a bounded period,
kills survivors, closes executor and queue resources, and is idempotent.
