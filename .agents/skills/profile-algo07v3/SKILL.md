---
name: profile-algo07v3
description: Profile, optimize and exactly qualify the standalone ALGO07v3 native-GLRT-to-publication pipeline. Use for ALGO07v3 runtime iterations; use profile-algo07 for the historical worker chain or IQ detector.
---

# Profile standalone ALGO07v3

Read [the CLI contract](../../../docs/operations/algo07v3-cli.md) and
[runtime scorecard](../../../docs/operations/algo07-runtime-scorecard.md).
Work in the checkout containing those documents; confirm its Git state before
editing. Earlier workers and results are external numerical references only.

On the current host, the worktree is `/srv/bulk/leo-dev/algo06-promotion-20261101`;
use `/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python` with its `src`.
DS26-0002's reusable request is
`/srv/bulk/leo-dev/algo07v3-cumulative-20261105/after-reference/request.json`.
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

For residual-screen changes, `tools/benchmark_algo07v3_screen_geometry.py`
reads a completed owned request through the public evidence store and alternates
the frozen original screen with the current one. Run with `--request REQUEST
--output NEW_JSON --repeats 3`, BLAS pinned to one, one-core affinity and an
external `timeout -k 2 360`. It checks every complete screen against the saved
result and verifies inputs remain unchanged. Its prepared-component times do
not replace a fresh complete-pipeline comparison.

For reassociation screening, use `tools/benchmark_algo07v3_reassociation.py`
with `--request REQUEST --output FRESH_DIRECTORY --repeats 3 --timeout 1200`.
It runs fresh native inference, captures each live family-omitted screen, then
alternates the frozen serial implementation and the current one on one CPU.
Every complete screen must match the original invocation. It also profiles
conservative recovery separately. The overall instrumented clock includes
repeated screens and cProfile overhead, so it is not a full-pipeline speed
benchmark. Verify its final science and eight PNGs against the unchanged owned
request using the explicit entry-point-alias audit in
`reports/2026_11_05_algo07v3_recovery_arms/profile_parity.py`. Keep numerical
inputs and runtime sources unchanged until both the run and parity check finish.

For conservative recovery, `tools/benchmark_algo07v3_conservative.py` loads owned
native preparation and initial-fit evidence, builds a fresh scan context for
each trial, and alternates the frozen serial stage with concurrent arms. Use
`--request REQUEST --output NEW_JSON --repeats 3`, CPUs 0–2, one BLAS thread and
an external `timeout -k 2 600`. It compares every complete stage against the
saved serial result and records parent plus reaped-child CPU. This is prepared
stage evidence, not fresh full inference. The complete-run recipe in
`reports/2026_11_05_algo07v3_conservative_arms/run_pair.py` supports
`--candidate-first`; run a fresh normal pair followed by a fresh reversed pair
to record ABBA order. Retain all four complete timings and cross-pair exactness.

To isolate predictive recovery, add `--only-stage predictive` to the profiler.
The full pipeline still runs, but cProfile is active only during that stage and
its forked children. Each child has a matching `profile-PID.json` naming its
target/substage, arm or fold seed, and control/new-family variant where applicable.
Do not combine later numerical-replay substage rows with predictive timings.
Use the unchanged-source parity helper above to verify science and eight PNGs.
See `reports/2026_11_05_algo07v3_predictive_profile/README.md` for the qualified
example and a renderer that exports compact child summaries and a stage plot.

For exact-family gate replay, `tools/benchmark_algo07v3_family_gates.py` runs
fresh native inference and alternates complete old/new inclusion audits on each
live context. Use `--request REQUEST --output FRESH_DIRECTORY --repeats 3
--timeout 900` with CPUs 0–2 and one BLAS thread; audit trials pin one CPU and
restore affinity afterward. Require every full audit fingerprint to match,
then compare final science/eight PNGs with the unchanged-source parity helper.
Repeated trials copy the numerical policy so their problem/refresh receipts
cannot append to the normal run's ordered log; keep this isolation and its test.
The overall clock contains repeated audits and is not a pipeline speed result.
Keep these trials sequential with fresh full-run timing comparisons.

The external `tools/probe_algo07v3_position_geometry.py` experiment compares
fixed-phase prepared geometry with the original `JointMarginal.calculate`.
Use `--request REQUEST --output FRESH_JSON`, one CPU and one BLAS thread, outside
full-pipeline timing runs. It alternates three pairs for each c arm over 50 fixed
seeded regional points, requiring exact full geometry/features. Timing includes
first preparation but excludes problem construction, fitting and publication.
Its historical geometry-only timings do not qualify a pipeline speedup. The
owned calculator now includes the qualified fixed-phase cache; this external
probe retains the frozen original calculator and experimental function explicitly.
Inspect phase/grid/buffer invalidation tests and native receipts when changing it.

For complete fixed-phase geometry impact, use
`tools/benchmark_algo07v3_position_geometry.py --request REQUEST --output NEW_JSON`
with one CPU, one BLAS thread and an external `timeout -k 2 360`. It alternates
three old/new pairs for each c arm, executing all five phase-refresh rounds with
48 optimizer iterations per round on a saved initial hypothesis. Each trial
builds a fresh scan context outside the timer. Full fit/history/state/calculation
fingerprints must match; the temporary calculator substitution is restored even
on failure. Keep this benchmark sequential with full-pipeline timing runs.
This measures a prepared position fit, not discovery, recovery or publication.

To investigate discovery scheduling without changing runtime, use
`tools/probe_algo07v3_discovery_schedule.py --request REQUEST --output FRESH_DIRECTORY`
with three CPUs, one BLAS thread and an external `timeout -k 2 600`. It extracts
the unchanged per-seed body, uses batches of at most three existing workers,
and alternates three complete initial-search pairs. Every search must exactly
match the saved owned initial result; both sides keep existing paired-arm fits.
Fresh context construction is outside the timer. Report nested discovery time,
whole-stage time and parent-plus-child CPU separately. The current prototype
saves 1.649 stage seconds but adds 2.449 CPU seconds on DS26-0002 and remains
external. Do not equate reduced latency with better queue throughput.

For the slow predictive annotation fold, the external
`tools/probe_algo07v3_annotation_arms.py --request REQUEST --output FRESH_DIRECTORY
--target 1 --fold 1 --repeats 3` compares serial with paired training. Pin three
CPUs, one BLAS thread and an external `timeout -k 2 900`. Each trial rebuilds
owned context before timing; both arms retain five phase rounds and 48 position
iterations. Child results carry final-problem recipes, and reconstruction must
match full calculation/state fingerprints before nomination. Every complete
fold output must match. Numerical-policy replay is excluded, not silently
parallelized. This remains a single-fold experiment, not whole-pipeline speed
evidence. The owned worker now uses a bounded queue across fold/arm tasks, then
separate fold scoring; it never nests arm workers under three fold workers.
The annotation-training report records exact native DS26-0002 and DS26-0066
qualification. Use its `run_pair.py`/`run_baseline.sh` for seven
declared module overlays and its renderer for complete timing receipts. Profiler
child metadata now identifies training tasks as `[seed, arm]`. Keep numerical
replay/callbacks serial and preserve the three-live-worker cap when iterating.

For posterior-loop changes, measure complete fits as well as array kernels.
`tools/probe_algo07v3_posterior_assembly.py --request REQUEST --output FRESH_DIRECTORY`
alternates three full five-round initial fits per arm; the ordered-bincount
prototype is exact but slower on DS26-0002 and remains external.
`tools/benchmark_algo07v3_training_kernel.py --request REQUEST --output FRESH_DIRECTORY
--repeats 2` targets the previously profiled slow DS26-0066 target-1/fold-1
training fits. Pin one CPU and one BLAS thread, with a 900-second external bound.
It preserves optimizer histories, final state and complete likelihood in both
arms, constructs fresh contexts outside timing and restores kernel aliases on
failure. Its covariance-index candidate is now integrated after exact DS26-0002
native qualification and 727 tests; prepared DS26-0066 training gains are
4.54–5.99%. The helper uses the frozen pre-index oracle so future runs remain
old/new comparisons. The posterior-followup report retains the measured helper
bytes and both source strings, and provides the private-overlay native runner.
Prepared-fit gains do not establish a capture-to-publication or population gain.

For repeated initial calculations, use the observation-only
`tools/profile_algo07v3_initial_repeats.py --request REQUEST --output FRESH_DIRECTORY`
on one CPU and one BLAS thread. It executes every call and checks repeated full
results rather than assuming identical coordinates imply a fixed model. Then
`tools/probe_algo07v3_initial_cache.py --request REQUEST --output FRESH_DIRECTORY
--repeats 3` compares bounded one-entry reuse on three CPUs, alternating complete
initial searches against frozen pre-cache references. Use external bounds of
300 and 600 seconds respectively. The cache is experimental: six searches and
one native pair are exact, but the full native pair regresses 244.609 → 301.029 s
despite a small prepared-stage improvement. Retain that regression and keep the
runtime unchanged until repeated full-pipeline evidence supports integration.
The initial-cache report includes source overlays and a native runner. Do not
treat its archived candidate as deployed or its prepared timings as cumulative.
