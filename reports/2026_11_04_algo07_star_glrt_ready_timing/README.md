# ALGO07*: fresh GLRT-ready-to-publication timing trial

**Whole raw-IQ-to-publication speedup remains unmeasured.** This trial measures
the current ALGO07* scope: prepared native GLRT input through all six scientific
stages and publication of all eight standard figures. It excludes acquisition,
native detection, production queue waits, initial input cloning, preflight
checks and the subsequent equivalence comparison. It includes subprocess startup,
runtime validation inside the pinned drivers, terminal reads and publication.
It is a private replay, not a live production latency measurement.

The first pair uses **DS26-0084**, the first optimized case with a complete
ordinary-clock scientific/artifact pass. This makes it a completed-path smoke
case, not a random sample or a runtime distribution. Both paths start from fresh
public-port native exports. Neither adopts a completed scientific reference.
Reference runs first, then candidate; they never overlap each other. Production
and other qualification work continue on the shared host. OS cache and host load
are uncontrolled and recorded as limitations. One pair cannot separate a small
optimization benefit from shared-host timing variation.

The [runner](../../tools/benchmark_algo07_star_case.py) invokes the existing
independent production-watchers reference and optimized coordinator. The numerical
workers retain their original 1,200-second budgets. Both coordinator invocation
windows are 1,800 seconds instead of the cohort wrapper's 1,500 seconds, so this
short case can attempt the complete chain without a human checkpoint gap.
The inference subprocess still has the original external 1,785-second timeout.
The first publication has a separate 600-second timeout and the original
30-second diagnostic-grid budget. These are declared orchestration settings,
not changed scientific search limits.

A checkpoint, failed process, incomplete figure/grid set or changed runtime
produces no qualified complete-path time. Preserve the first result without
restarting or rerendering it until it passes. A successfully timed path is labeled
`completed_unqualified`; the existing strict CLI must then verify both scientific
arms, every intermediate stage, owners, process provenance, grid and PNGs before
the pair is eligible for a scoped timing comparison. This trial does not clear
failures in the main DS26 cohort or qualify deployment.

The runner's 12 tests cover fresh-path enforcement, shared CLI locks, unchanged scientific budget
commands, failed/checkpointed runs, incomplete publication, changed pins and the
distinction between recorded time and scientific parity. No numerical worker was
changed. Initial status: protocol and fresh inputs prepared; measurements pending.

The [cumulative scorecard](../../docs/operations/algo07-runtime-scorecard.md)
remains the authoritative headline and must distinguish this GLRT-ready metric
from the still-missing original raw-IQ-to-publication baseline comparison.
