# ALGO07 cumulative runtime scorecard

Updated 2026-11-04. **End-to-end speedup since optimization began: not yet
established.** This is an unmeasured ratio, not a measured 1.00× result.
The tenfold active-processing target remains open.

## Primary metrics

| Metric | Starting baseline | Current / candidate | Paired speedup |
|---|---:|---:|---:|
| Recorded input ready → all standard web artifacts published, excluding queue waits | Not measured as one complete matched run | Not measured as one complete matched run | Unavailable |
| Capture start → all standard web artifacts published, including acquisition and queue waits | No matched baseline/current cohort | No matched baseline/current cohort | Unavailable |
| ALGO07* versus its frozen ALGO07 reference, GLRT-ready through publication | 912.576 s observed; grid incomplete | 887.264 s observed; full grid | Unqualified: unequal completed grid work |

The current verification CLI begins at preserved native GLRT evidence. Its
runtime cannot establish raw-IQ-to-publication speedup. Parallel cohort runs
test parity; their contention, checkpoints and reused references prevent a
controlled timing claim. An unchanged final position alone is insufficient:
both calibration arms, associations, intermediate decisions and artifacts must
pass their declared comparisons.

The [fresh GLRT-ready timing trial](../../reports/2026_11_04_algo07_star_glrt_ready_timing/README.md)
retains an incomplete first reference: 562.161 seconds through ALGO06, then a safe
checkpoint before ALGO07. This is not a complete-path baseline. A revised,
predeclared trial advances verified checkpoints within one monotonic timer and
30-minute research bound. Its reference completes inference and eight-artifact
publication in an observed **912.576 s (15.21 min)**, but evaluates only 91/179
diagnostic grid locations and fails the strict completeness gate. The candidate
finishes in an observed **887.264 s (14.79 min)** with 179/179 grid locations.
These are unqualified private GLRT-ready latency observations, not a speedup.
Inference alone takes **817.550 → 821.556 s**; the final ALGO07 invocation takes
**136.173 → 106.075 s**. Upstream timing variation offsets the final-stage saving.
The shared host's load falls during the candidate run. Strict scientific parity
passes, but original publication parity fails. A separate matched 300-second
real-grid-budget replay produces exact 179-location grids and all eight PNGs;
it cannot retroactively qualify the original unequal-work timings.

The next architecture is specified in [the ALGO07v3 plan](algo07v3-plan.md): one
standalone engine without earlier ALGO runtime dependencies. Its 10× complete
processing target remains unachieved.

## Measured improvements within the pipeline

| Scope / experiment | Reference | Candidate | Ratio | Qualification / limitation |
|---|---:|---:|---:|---|
| Final ALGO07 numerical worker, two-family case, iteration 002 | 779.063 s | 420.000 s | 1.855× | Full worker; exact scientific comparison; profiled overlapping runs on shared host |
| Upstream ALGO03 recovery, single-family case, iteration 009 | 557 s | 314 s | 1.77× | Stage only; rounded report values; qualified numerical contract |
| Upstream ALGO03 recovery, joint-family case, iteration 009 | 929 s | 560 s | 1.66× | Stage only; rounded report values; qualified numerical contract |
| ALGO07* terminal-result validation/read, DS26-0170 ABBA means | 10.111 s | 1.618 s | 6.250× | Exact returned result; 8.493 s saved per measured read; experimental |
| Native GLRT tiling, 16 paired-window DS27 fixture | 25.454 s | 16.643 s | 1.529× | Detector-only alternating trial; prototype, not deployed by that report |

These are separate experiments, not one cumulative baseline/current pair.
Do not multiply their ratios or add their savings to claim pipeline speedup.
Stage benefits vary with scan workload. The November 4 profile separately
observed 319.57 s across ALGO02–07 workers and a fresh 454.17 s native replay;
those different executions must not be summed into an end-to-end measurement.

Sources:

- [Final-worker measurement](../../reports/2026_11_03_algo07_runtime_iteration002/README.md)
- [Recovery qualification and deployed release](../../reports/2026_11_03_algo07_runtime_iteration009/README.md)
- [ALGO07* ABBA timings](../../reports/2026_11_04_algo07_star_optimized_smoke/terminal-read-timings.json)
- [Native detector prototype](../../reports/2026_11_03_algo07_runtime_iteration005/README.md)
- [November 4 production/profile inventory](../../reports/2026_11_04_algo07_pipeline_profile/README.md)

## Required update on every optimization iteration

Lead each runtime report with complete-path baseline seconds, candidate seconds,
seconds saved, ratio, matched scan count and parity status. Use **unavailable**
when the complete-path measurement is missing; never replace it with a kernel
ratio. Preserve this original-baseline comparison as well as the immediately
previous-version comparison, so cumulative progress stays visible.

For a qualifying measurement, bind input, causal catalogue, runtime revisions,
hardware, worker/thread counts, cache conditions and budgets. Time baseline and
candidate sequentially in alternating order, with the same raw input through
successful publication of every required artifact. Retain host-load evidence,
failures, timeouts and incomplete outputs. Record acquisition, queue/handoff
waits, native GLRT, position processing and publication separately without
double-counting overlapping intervals. Record the outer monotonic wall timer
even when individual stage instrumentation is unavailable.

Report paired per-scan ratios and baseline/current median and p90 durations
across the same declared workload cohort; include completion and exact-parity
counts. Capture-to-publication latency and processing speed are separate
metrics: queue reductions can improve the former without changing computation.
Historical stage timings do not reconstruct the missing starting full-path
baseline; obtain it by replaying the pinned original implementation.
