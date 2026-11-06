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
`/srv/bulk/leo-dev/algo07v3-lapack-native-0002-20261106/candidate-request.json`.
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
| Predictive fitting | `only-stage predictive`, `annotation`, `posterior`, `likelihood`, `workspace` |
| Predictive worker utilization | `training_queue`, `tools/profile_algo07v3_training_queue.py` |
| Precision convergence by fold/phase | `training_convergence`, `tools/profile_algo07v3_training_convergence.py` |
| Per-problem cache eviction | `position_cache`, `tools/profile_algo07v3_position_cache.py` |
| Initial search | `initial_queue`, `initial_priority`, `discovery_schedule`, `initial-cache` |
| Independent paired fits | `conservative`, `numerical` |
| Diagnostic figures and publication | `grid`, `encoding` |

The latest fitting experiment is in
[the workspace report](../../../reports/2026_11_05_algo07v3_lapack_workspace/README.md);
the [initial-queue report](../../../reports/2026_11_05_algo07v3_initial_queue/README.md)
retains FIFO and rejected priority scheduling. Verify final status and receipts
before treating candidates as integrated. Preserve negative/flat results from
likelihood hashing, variance buffers, LU workspace, identity layout and gradient
scheduling. A small kernel gain or unmatched clock is not a cumulative speedup.

The [cache census](../../../reports/2026_11_06_algo07v3_cumulative_current/README.md)
finds negligible benefit from larger position caches. The historical reference
failure is now [repaired exactly](../../../reports/2026_11_06_algo07v3_reference_recovery/README.md):
twelve private read-only overlays restore all original manifest commitments.
Preflight both manifests and the full source-only configuration before spending
a candidate run. Do not drop bytecode guards or add bytecode to source-only pins.
Fresh original/current clocks are 886.905 versus 193.899 / 152.529 s on one scan;
retain both observations, harness costs and the open admission/metadata gates.

The [queue profile](../../../reports/2026_11_06_algo07v3_training_queue/README.md)
shows two long training tasks dominate DS26-0066 target 1. A prescient scheduling
bound is not a measured gain; do not turn case-specific task costs into a policy.
Prioritize precision-iteration profiling and exact numerical work, retaining all
folds, both arms, original budgets and complete annotation equality.

The [ordered-assembly experiment](../../../reports/2026_11_06_algo07v3_ordered_assembly/README.md)
is **rejected for default integration**. Its direct extension improves prepared
training, but both full native pairs regress (148.203→169.946 s and
233.069→258.349 s). Default NumPy assembly is restored. Do not revive it based
only on the 4% captured-call or 2.61% fitted-c gains. Candidate source/tests and
native receipts are archived; numerical oracles are unchanged.

The exact [convergence profile](../../../reports/2026_11_06_algo07v3_ordered_assembly/convergence.md)
finds 269 first-round likelihood calls in each hard-fold arm, with 220 reaching
256 precision iterations. Later rounds generally need 10 iterations per call.
Nuisance width is unchanged across folds. Investigate this first-round trajectory
and exact reuse across arms/targets. Lower budgets, different initialization or
different stopping rules change the algorithm; they are not exact runtime fixes.

The [training reuse and covariance investigation](../../../reports/2026_11_06_algo07v3_covariance_reuse/README.md)
finds no duplicate masks in DS26-0002 and only one potential duplicate in
DS26-0066, outside the slow target. Equal masks alone are insufficient for
complete-fit reuse. A symmetric BLAS covariance product fails exactness;
private covariance-buffer reuse is exact but requires complete-fit and native
timing evidence before adoption. Preserve all alternating pairs, including
regressions. The next scheduling diagnostic is the complete recovery timeline
across targets, not another permutation of one target's six jobs. Preserve the
three-slot limit, canonical outputs, stateful fallback and admission semantics.

The [cross-target queue experiment](../../../reports/2026_11_06_algo07v3_cross_target_queue/README.md)
is rejected: prepared annotation improves 14–22%, but both native pairs regress
21–37% with exact science and eight PNGs. Default runtime sources are restored.
Next isolate complete recovery from a common native prefix checkpoint and explain
the discrepancy before integrating another scheduling change. The restored
default passes 1,959 tests; candidate sources and its 1,980-test receipt are archived.

The [common-native-prefix diagnostic](../../../reports/2026_11_06_algo07v3_native_recovery_queue/README.md)
now compares complete recovery in fresh children forked from one native checkpoint.
One DS26-0066 pair improves 180.483→138.434 s with exact stages, selection and prior
native audit. Task CPU/off-CPU costs also change; do not overturn earlier full-run
regressions on this favorable order. The fixed-task scheduling model suggests
18–20 s opportunity, not a measured full-pipeline gain. Use the external native
recovery probe for both-order follow-up. Exact repeated inclusion control fits
are another hypothesis to investigate before adding reuse.
