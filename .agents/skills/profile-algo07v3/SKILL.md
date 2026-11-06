---
name: profile-algo07v3
description: Profile, optimize and exactly qualify the standalone ALGO07v3 native-GLRT-to-publication pipeline. Use for ALGO07v3 runtime iterations; use profile-algo07 for the historical worker chain or IQ detector.
---

# Profile standalone ALGO07v3

Read the Run/Limits/Timing sections of [the CLI contract](../../../docs/operations/algo07v3-cli.md)
and the current summary at the top of the [runtime scorecard](../../../docs/operations/algo07-runtime-scorecard.md).
Follow the report for the chosen hotspot; historical experiments are references,
not a requirement to repeat every earlier run.
Work in the checkout containing those documents; confirm its Git state before
editing. Earlier workers and results are external numerical references only.

On the current host, the worktree is `/srv/bulk/leo-dev/algo06-promotion-20261101`;
use `/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python` with its `src`.
DS26-0002's reusable request is
`/srv/bulk/leo-dev/algo07v3-initialqueue-native-0002-20261106/candidate-request.json`.
Its frozen inputs are in `/srv/bulk/leo-dev/algo07v3-isolation-20261105`.
These are fixture locations, not inference priors; verify they still exist and
match their bindings. The profiling command never reuses that request's results.

Use an existing content-bound native request and a fresh private output root.
The profiling command creates its own request with only `output_root` changed:

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 taskset -c 0,1,2 python -B \
  tools/profile_algo07v3.py --request /absolute/native-request.json \
  --output /absolute/fresh-profile --timeout 1200
```

It runs the actual owned worker under its process-group supervisor, records
top-level stages and recovery substages, parent and child CPU accounting, source
bindings, host pressure and per-process cProfile files. Inspect `profile.json`
and `worker.log`. Use `python -m pstats profile-PID.pstats` for call detail.
Substages are nested within top-level stages; never add both. Child profiles
overlap in wall time; their cumulative function times are not exclusive CPU.
Profiling perturbs timing: choose a hotspot from these results, then measure
speed in separate unprofiled sequential runs. Do not edit bound sources while
a run is active. A failed, interrupted or resumed run is not a speed result.

Read `stage-resources.json` and `worker-resources.json` for independent monotonic
wall and parent/reaped-child CPU counters. Check cProfile accounting before
ranking functions: self time exceeding cumulative time or summed exclusive time
exceeding the measured process window invalidates that trace. The complete
November 5 fork/render profile exhibits this problem; pausing parent tracing
around forks did not fix it. Preserve the rejected trace digest and use stage
counters plus isolated targeted instrumentation instead. Do not blame functions
named by an inconsistent trace or sum overlapping child profiles into wall time.

Freeze the baseline modules before making one focused change. Prefer removing
measured repeated work or concurrently executing independent fits with the
existing bounded execution port. Keep targets, variant order, rejection masks,
phase rounds, optimizer budgets, priors and acceptance unchanged. Numerical
policies with mutable ordered receipts must stay serial unless their state is
explicitly and exactly reconciled. Never turn a child failure into rejection.

Run component-owned tests, then fresh isolated baseline/candidate runs using
`tools/qualify_algo07v3_cli.sh` and compare with
`tools/compare_algo07v3_runs.py`. A working sequential pair recipe is in
`reports/2026_11_05_algo07v3_family_integration/run_pair.py`; adapt its declared
baseline module list and namespace bindings to the actual change. It is an
external reference harness, not a runtime dependency. Require exact scientific
audit, both c arms, ownership, all eight PNGs and public grid/path. Declare all
changed loaded modules. Keep failing comparisons and timing regressions.

Use DS26-0002 for a short native canary and DS26-0066 for accepted reassociation;
choose further scans by exercised branches, not position accuracy. Full DS26
has 159 fast members, of which 158 native inputs were available in the recorded
inventory; retain missing cases in the denominator. A subset is not population
qualification. GPS enters presentation only; use causal frozen TLEs.

Publish a Markdown report with measured stage breakdown, matched unprofiled
times, CPU/RSS, exact comparison receipts, source/input bindings, tests and a
figure. Distinguish incremental from original-ALGO07 speed; do not multiply
ratios from separate trials. Native GLRT extraction, capture and queue delay
are outside the owned CLI clock. Report the observation as scoped, not an
end-to-end capture speedup. Push code and report to remote main when authorized;
deployment is a separate action. Select the next hotspot from the new profile.

## Choose a focused experiment

Use [experiment recipes](references/experiments.md) only for the relevant target.
That reference preserves commands, failure lessons and qualified historical
results; its opening search guide helps locate the needed section.

| Measured target | Recipe search term / starting tool |
| --- | --- |
| Residual screening or geometry | `screen_parts`, `nomination`, `immutable-bank`, `scalar-phase`, `endpoint` |
| Guarded reassociation | `benchmark_algo07v3_reassociation` |
| Predictive fitting | `only-stage predictive`, `annotation`, `posterior`, `likelihood` |
| Initial search | `initial_queue`, `initial_priority`, `discovery_schedule`, `initial-cache` |
| Independent paired fits | `conservative`, `numerical` |
| Diagnostic figures and publication | `grid`, `encoding` |

The latest fitting experiment is in
[the initial-queue report](../../../reports/2026_11_05_algo07v3_initial_queue/README.md);
the preceding [azimuth report](../../../reports/2026_11_05_algo07v3_screen_azimuth/README.md)
has complete screen/projection checks. Verify each report's final status and
receipts before treating a candidate as integrated. The initial-queue report
preserves the rejected fitted-c-first schedule as well as FIFO results.
Preserve negative results from likelihood hashing, variance buffers and gradient
scheduling. A small kernel improvement is not a full-pipeline speedup.
