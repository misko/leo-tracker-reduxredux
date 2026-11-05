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
