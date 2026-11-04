# ALGO07*: fresh GLRT-ready-to-publication timing trial

**Whole raw-IQ-to-publication speedup remains unmeasured.** This trial measures
the current ALGO07* scope: prepared native GLRT input through all six scientific
stages and publication of all eight standard figures. It excludes acquisition,
native detection, production queue waits, initial input cloning, preflight
checks and the subsequent equivalence comparison. It includes subprocess startup,
runtime validation inside the pinned drivers, terminal reads and publication.
It is a private replay, not a live production latency measurement.

The timing protocols use **DS26-0084**, the first optimized case with a complete
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

A failed process, incomplete figure/grid set or changed runtime produces no
qualified complete-path time. Preserve the first result without retrying failed
work or rerendering it until it passes. A successfully timed path is labeled
`completed_unqualified`; the existing strict CLI must then verify both scientific
arms, every intermediate stage, owners, process provenance, grid and PNGs before
the pair is eligible for a scoped timing comparison. This trial does not clear
failures in the main DS26 cohort or qualify deployment.

## First protocol: retained incomplete attempt

The reference completed ALGO02 through ALGO06, then checkpointed before ALGO07.
The inference invocation took **562.161 seconds**. This is a partial-path time,
not a complete processing time or a speedup. No scientific worker failed or
timed out. The reference coordinator reserves the full 1,200-second stage budget
plus 60 seconds before admitting the next stage. The 1,800-second invocation
therefore stops admitting new work after roughly 540 seconds, even when the
next stage usually completes much sooner. The first timing runner treated that
safe checkpoint as incomplete. Its candidate was not run; that first pair
cannot supply a ratio.

The [first timing receipt](first-reference-timing.json),
[original protocol](protocol.json), [archived first runner](first_runner.py) and
[hash bindings](first-attempt-evidence.json) preserve this attempt. The archived
runner matches its launch-time source digest. The current tool has since gained
an explicit checkpoint-continuation mode; the old protocol's original source
path is historical, and its source bytes are retained in that archive.

## Revised protocol: one timer across verified checkpoints

The second pair uses new, independent native-only stores under `timing002`.
Reference still precedes candidate. The optional `--resume-completed-checkpoints`
mode retains one monotonic timer across coordinator invocations and publication.
Each continuation must increase the number of completed public stages, identify
the expected next stage, and leave it not started. Active, failed, inconsistent
or non-progressing states stop the trial. At most six advancing invocations are
allowed. All original scientific worker budgets remain 1,200 seconds.

The complete timed path has a **1,800-second research bound**, including
publication. External subprocess timeouts are capped by the remaining research
time; a resulting interruption is incomplete and never supplies a timing ratio.
Each successful stage still uses the original scientific budget. There is no
human checkpoint gap and no retry of failed numerical work. This corrects the
timing harness's admission limitation without changing the algorithm.

The runner's **19 tests** cover fresh paths, shared CLI locks, command integrity,
failed/checkpointed runs, verified forward progress, stalled/active checkpoints,
total deadline exhaustion, incomplete publication, changed pins and the
distinction between timing and scientific parity. No numerical worker changed.
The [revised protocol](protocol-002.json) binds the new source and fresh inputs.
The revised reference has finished; its observed timing and qualification failure
are reported below. The planned candidate is running. Independent equivalence
checks remain pending.

## Revised reference: measured latency, incomplete diagnostic grid

The revised reference executes all six scientific stages and publishes eight
artifacts in an observed **912.576 seconds (15.21 minutes)**. Its 30-second
diagnostic-grid allowance admits only **91/179 locations**, so the runner retains
`state: incomplete` and no qualified complete-path time. This is a real latency
observation for this private run, not a qualified before/after speedup. The
reference is not rerendered to obtain a favorable grid outcome. The planned
candidate runs next on its own fresh native-only store.

| Exclusive interval in this reference | Seconds |
|---|---:|
| ALGO02 watcher/worker invocation | 363.560 |
| ALGO03 invocation | 80.536 |
| ALGO04 invocation | 17.555 |
| ALGO05 invocation | 22.518 |
| ALGO06 invocation | 86.859 |
| ALGO07 invocation | 136.173 |
| Other inference orchestration and verification | 110.348 |
| Publication process, including startup and terminal validation | 95.025 |

The six invocation timers total **707.202 seconds**. The complete inference
interval is **817.550 seconds**; the difference includes frozen-runtime checks,
public terminal validation and verified checkpoint continuation. These are
exclusive intervals from this one run. The renderer's internal publish timer
is 70.986 seconds and is already inside the 95.025-second publication process;
do not add it again. Small parent bookkeeping separates the summed intervals
from the observed outer timer.

The host's one-minute load average changes from 36.63 to 34.19 during this trial.
The raw CPU and wall receipts are preserved; this single shared-host observation
is neither a workload distribution nor an isolated-machine estimate. Original
scientific stage budgets, causal inputs and numerical code remain unchanged.
Native GLRT, capture and production queue waiting are outside this measurement.

Evidence: [reference timing receipt](reference-timing-002.json),
[bound interval breakdown](reference-breakdown-002.json).

The [cumulative scorecard](../../docs/operations/algo07-runtime-scorecard.md)
remains the authoritative headline and must distinguish this GLRT-ready metric
from the still-missing original raw-IQ-to-publication baseline comparison.
