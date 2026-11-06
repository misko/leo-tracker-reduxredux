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
  --output /absolute/fresh-profile --timeout 1200 --timers-only
```

It runs the actual owned worker under its process-group supervisor and records
top-level stages, recovery substages, per-task wall/CPU windows, parent and child
CPU accounting, source bindings and host pressure. Inspect `profile.json`,
`stage-resources.json`, `profile-PID.json` and `worker.log`. Task windows include
pipe transfer and overlap stages. `--timers-only` avoids the known inconsistent
aggregate cProfile trace and produces no pstats files. Omit it only when a
targeted function trace is needed; validate that trace before ranking functions.
Use `python -m pstats profile-PID.pstats` for valid call detail.
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
| Duplicate inclusion controls | `inclusion_controls`, `tools/probe_algo07v3_inclusion_controls.py` |
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

The [inclusion-control census](../../../reports/2026_11_06_algo07v3_inclusion_control_reuse/README.md)
confirms three duplicate paired fits in DS26-0066. Prepared recovery improves
9.63% and native predictive stages improve 8.56–10.01%, with exact outputs, but
both complete native pairs regress 7.25–11.41%. The candidate is archived and
the default restored. DS26-0002 has no duplicates and about 1.5 s of key overhead.
Do not claim a complete-scan gain from the stage clocks. Reduce dependency-key
overhead and measure duplicate incidence before another integration; retain all
controls, stateful fallback, both arms and complete audit/PNG equality.

The successor [control-view implementation](../../../reports/2026_11_06_algo07v3_control_geometry_view/README.md)
is retained in development: exact native DS26-0066 is 480.981→394.960 s and
DS26-0002 is 247.723→245.940 s, with 2,012 tests passing. Short-scan predictive
and prepared clocks regress; do not claim a universal speedup. Controls run on
a view without unused discovery geometry, with every retained field key-bound.
The [full timer profile](../../../reports/2026_11_06_algo07v3_full_profile/README.md)
compares this code's complete science and eight PNGs against its unprofiled run.
Use `--timers-only` for reliable stage/child accounting; frequency snapshots are
diagnostics, not timing corrections. Retain separate unprofiled speed clocks.

The [covariance-buffer native qualification](../../../reports/2026_11_06_algo07v3_covariance_native/README.md)
rejects that prototype after exact native regressions: 400.994→416.279 s on
DS26-0066 and 233.729→251.925 s on DS26-0002. Original allocation is restored.
The initial-branch profile identifies the second fitted-c phase round: all 279
likelihood calls reach the 256-iteration cap. Exact repeats offer little work;
one captured recovery likelihood has no repeated loop state. Next investigate
spare-capacity derivative work, preserving a shared three-worker cap, cancellation
and exact histories. Do not revive unrestricted nesting or the rejected
owner-only gradient policy. Commands and both observer tools are in the report.

The [idle derivative follow-up](../../../reports/2026_11_06_algo07v3_idle_derivatives/README.md)
is also not adopted. A helper thread only in the last surviving initial fit
preserves complete prepared search outputs but regresses on both scans:
29.870→30.543 s and 105.318→111.901 s. Runtime is unchanged; these are stage-only
pairs, not native qualification. Use the existing full profile for stage ranking.
Next compare captured likelihood costs and noise-group precision trajectories
between slow initial and recovery phases before another exact kernel experiment.
The external probe retains bounded-capacity, failure and cancellation tests.

The [initial precision attribution](../../../reports/2026_11_06_algo07v3_initial_precision/README.md)
adds `--capture-capped` to the initial observer. It owns the first capped in-fit
input per arm and preserves full fit signatures. Group 53 dominates 242/256
updates in the captured fitted-c phase; an exact reconstruction maps it to
RX2 CH6 T002 under the branch's 58109 hypothesis. This is an intermediate-model
diagnostic, not evidence of incorrect final association. Inverse solve, covariance
and factorizations dominate both initial and recovery captures. Fortran root
layout stays external after mixed sub-percent timings; twenty focused tests pass.
Investigate shared-parameter precision coupling, preserving the original solver.
Hardware counters are available through privileged `perf` on this host, but only
a trivial command was checked: verify child inheritance and measurement scope
before making any pipeline counter claim. Frequency snapshots alone cannot
explain component/native timing discrepancies.

The [hardware-counter and coupling report](../../../reports/2026_11_06_algo07v3_perf_coupling/README.md)
now verifies fork inheritance and complete native accounting. Use
`tools/profile_algo07v3_perf.py --request REQUEST --reference-timing SUPERVISOR
--output FRESH` for the unchanged-code counter baseline. It requires privileged
perf/namespaces, explicitly pins the perf launcher to P cores before creating
counters, and compares with empty changed/added-module lists. `--verify-only`
checks inheritance cheaply. The counters include harness/preflight/supervisor;
report their wider scope separately from the worker clock. DS26-0066 is exact
at 398.576 s; perf records 656.458 CPU s over 400.069 s, not a new speedup.
No native work should be rerun merely because post-run comparison failed;
retain the failure and use the exact explicit comparison as in `finish.py`.

The precision-map observer reproduces all 512 captured transitions before
estimating Jacobians. Local expanding directions do not prove global divergence.
Inactive-column posterior compression fails byte equality and stays rejected.
Next process-helper experiment must differ from the rejected thread policy:
borrow one helper only in the sole remaining outer fit, preserve the three-slot
cap, handle helper failure and parent death, and require exact native outputs
plus complete wall/CPU/counter comparisons before adoption.

The [process-helper comparison](../../../reports/2026_11_06_algo07v3_idle_process/README.md)
is now **not adopted**. Complete native science and eight PNGs are exact, but
initial search is flat at 104.724→104.473 s and queue CPU rises 8.13%.
Whole-worker 462.319→393.222 s mostly reflects unchanged-stage variation;
instructions are nearly equal and CPU-pressure/cycle costs change. Prepared
gains do not override this result. The measured sources are archived; a later
serial-fallback race fix passes 21 focused tests but has no native qualification.
Do not integrate or claim cumulative gain. Next focus on the shared likelihood
matrix work, or explicitly separate a numerical-convergence candidate from the
identical-output path. Avoid another queue experiment without a new measured
mechanism and preserve the negative evidence.

The [fixed-prior shortcut](../../../reports/2026_11_06_algo07v3_fixed_priors/README.md)
is also **not adopted**. Empty learned-prior operations cost about 1.45–1.65% of
two captured calls. Both complete hard-fold arms improve slightly and all outputs
are exact, but native pairs regress 394.319→496.700 s and 221.677→250.945 s with
host-pressure variation. Runtime remains unchanged; candidate is an external
probe/overlay. Candidate/default suites pass 2,160/2,161 tests respectively.
The precision-map observer now seeds pre-loop precision when extracting a step;
its transition tests cover both previous and archived candidate implementations.
Do not revive this shortcut on component gains alone. Next test dense-kernel
BLAS threading cheaply on captured calls, verifying actual thread counts and
every output byte. Only if exact and faster should a complete-fit/capacity policy
be considered, retaining at most three active CPU slots across outer and inner
work. No larger thread count, numerical tolerance or scientific policy change
is already qualified by these measurements.

The [BLAS thread gate and full-profile review](../../../reports/2026_11_06_algo07v3_blas_threads/README.md)
rejects all six two/three-thread configurations across NumPy/SciPy together or
separately. Both actual loaded libraries are queried and binary-bound. NumPy-only
preserves the recovery capture but changes the initial capture; all other
multi-thread configurations change both. Keep one BLAS thread and preserve the
raw unfavorable clocks. Eight tests pass; no runtime change or native gain.
All 937 bindings from the full timer profile remain current. Next attribute the
first differing primitive cheaply before another kernel policy, and measure
remaining exact repeated work across a bounded branch-diverse subset. Numerical
convergence redesign remains separate from the identical-output contract; do
not repeat full native trials for a candidate that fails the captured-call gate.

The [primitive and covariance-thread follow-up](../../../reports/2026_11_06_algo07v3_blas_primitives/README.md)
now identifies the differences: factorization changes at the first call; all
covariance products remain exact on both captures. Covariance-only threading
is still not adopted. Fresh-process two-thread means improve captured wall
2.54–2.72% but consume about 95% more CPU; three threads regress. Reducing the
helper wait regresses wall 19–31%. Same-process baseline CPU can contain helper
carryover; use fresh processes for configuration comparisons. Preserve NumPy
operand aliasing in observers, while owning mutable LAPACK RHS copies. Seventeen
tests pass; no complete-fit or native qualification was warranted. Next census
remaining exact complete-fit duplicates across a bounded branch-diverse subset
before another cache or scheduling change. Keep numerical convergence work
separate from the byte-identical contract and do not revive generic BLAS trials.

The [bounded fit census](../../../reports/2026_11_06_algo07v3_fit_census/README.md)
extends stage observations to DS26-0084/0170 and observes joint recovery on 0102.
Only two of sixty training masks per arm repeat across the first four cases;
that is not proof of reusable fits or a time-saving percentage. The 0102 joint
controls exactly match fifteen core fields of earlier individual controls,
including histories and phase references. Two stages total 8.867 s; do not
double-count their four pairwise matches or treat all stage time as removable.
Next prove complete input-key equivalence, retain joint-specific diagnostics,
and time-box any narrow reuse prototype. No runtime change is qualified by this
observation. For larger gains, investigate precision convergence in a separate
scientific candidate without relaxing byte-identical v3's existing gates.
The observed 0102 worker finishes at 718.702 s, including 192.959 s numerical
recovery. Profile its new-family/joint replay fits and audits next; the centered
optimizer and reference-limit policy can change dependencies, and its ordered
numerical receipts must be preserved. Do not treat all replay time as redundant.
