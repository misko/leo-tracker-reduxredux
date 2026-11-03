---
name: profile-algo07
description: Profile and accelerate the standard fast-scan ALGO07 pipeline while checking frozen scientific results. Use for runtime bottlenecks, queue throughput, exact numerical optimization, and performance regression checks in this repository.
---

# Profile ALGO07

Use the repository CLI `python -m leo.cli.algo07_profile`. Read
[the benchmark protocol](../../../docs/operations/algo07-runtime-benchmark.md)
before freezing a baseline or interpreting a speedup.

For numerical replays, `tools/profile_algo07_numerics.py snapshot` obtains a
prepared input through the public evidence port, relocates and freezes it;
`run --mode capture` records real likelihood tensors, while `run --mode replay`
executes the full guarded ALGO07 worker over those prepared inputs. Compare
intermediate screens and optimizer histories with
`tools/compare_algo07_runtime_replays.py`. Historical research reconstruction
uses the separate `profile_algo07_research_snapshot.py` adapter and must not be
reported as a public-terminal or whole-pipeline replay. Concurrent trials' read
audits must be separated by recorded process ancestry.

Use `tools/profile_algo07_glrt.py` for bounded native-GLRT fixtures. Select the
actual installed native worker root: the research checkout's older fast-scan
adapter may accept only 2.5 MS/s, while production processes 10 MS/s. Snapshot
whole paired-receiver windows using a recorded random seed within each channel,
freeze their verified IQ and implementation bytes, and compare every published
candidate field. These small fixtures locate hotspots; they do not establish a
whole-scan or position speedup.

The production chain includes GLRT, ALGO02 graph localization, then ALGO03–07
recovery stages. Improving only the final reassociation worker is not an
end-to-end speedup. Separate active computation, discovery/validation overhead,
queue delay, and acquisition duration. Attribute child-worker time separately:
a parent cProfile file does not profile its children.

`tools/profile_algo02_prepared.py` profiles fresh ALGO02 fitting and family
comparison from a frozen public `FastGraphPositionStore.export_analysis` export.
Its allowlist copies prepared graph observations, noise and causal inputs; it
excludes every prior fitted answer and family nomination. It uses the installed
runtime, production process structure and read guard. Match the installed Python
when launching it. This replay does not reconstruct graph tracklets from GLRT,
refresh the catalogue, or run ALGO03–07. Inspect both-arm scientific parity
separately; a complete execution is not an accuracy-comparison result.
Use its `compare-pair` subcommand for two new prepared ALGO02 trials. It verifies
each trial against the frozen public scientific reference and compares all six
output files between trials. It withholds timing ratios for mismatched Python,
host, thread settings, scripts or profiling. Profiled runs locate bottlenecks;
use separate unprofiled sequential trials for deployment timing claims and record
any external sampling. ALGO02 can have older helper APIs than ALGO03: preserve
its installed source, applying only explicitly qualified numerical changes.

Use `algo07_profile sample --pid PID --research-root /srv/bulk/leo/research/CASE
--output OUTPUT --duration 20 --sampler /absolute/path/to/py-spy` to sample a
live private child without code injection. Inspect the target command first.
The bounded sampler records process identity and raw stack errors; it covers
one PID, not descendants. Retain corrupted raw rows and exclude them explicitly
from summaries. Sampling can affect timing; record its use in comparisons.

For complete native replay, use `tools/profile_algo07_full_glrt.py` with the
installed native Python and a 30-minute total bound. Match the production worker
count in both trials (currently sixteen); run baseline and candidate sequentially
and record contention. Earlier eight-worker timings are separate evidence. It
checks every published candidate and invalid window, but does not rerun position
inference. Use `tools/compare_full_glrt_replays.py` to compare complete native
window results, including unpublished hypotheses and invalid windows, between
two finished trials. It verifies frozen runtime/input identities and rejects
missing or duplicate windows. It reports timing ratios only with matched worker,
interpreter, profiling, host and thread configurations.
To reuse an earlier complete native trial, pass `--baseline-snapshot` to the
comparator. It independently revalidates both frozen inventories and requires
exact equality of their input documents. This mode is parity-only and withholds
a timing ratio; use new alternating trials for performance evidence.
For ALGO03 stage replays, `tools/compare_algo03_runtime_replays.py`
requires both arms, exact scientific values, matching file inventories, verified
source receipts and explicitly pinned runtime manifests. Runtime/provenance
accounting is reported separately. `tools/profile_hierarchical_bound.py` captures
real likelihood arrays for alternating-order microbenchmarks; those are not
whole-worker timings.

Before an optimization, freeze input and reference-output hashes with `freeze`
and verify them with `verify`. Include both c=0 and fitted-c, accepted recovery,
rejection/fallback, slow cases, and unavailable cases. Keep causal TLE versions,
native observations/owners, priors, phase quadrature, initial positions, solver
budgets, and acceptance gates matched. Evaluation GPS is for reporting only.

Choose the next change from measured profiles. Prefer eliminating repeated
work or exact algebraic improvements. A smaller candidate set, coarser phase
grid, relaxed acceptance gate, different prior, or earlier timeout is a change
of algorithm, not a runtime-only improvement. Do not update reference results
to make a changed result pass.

Run component-owned tests, then matched baseline/candidate replays. Compare
native owner maps, selected satellites, both endpoints and frequency objectives,
gate decisions, convergence, and fallback reasons. Record numerical tolerances
before the candidate run; investigate any difference that changes a decision.
Passing a saved-result audit is not equivalent to rerunning numerical inference.
Read the registered protocol before interpreting an exact-comparison failure.
Iteration002 explicitly permits bounded contraction roundoff in phase marginals
and orbital MAP coefficients. Preserve the strict receipt and assess those fields
separately with `assess_algo03_kernel_contract.py`; do not describe previously
allowed diagnostic roundoff as a localization regression or silently weaken a
decision/owner/position check. Compare original-kernel ablations against the
original-kernel population reference, not the optimized reference.

Geometry caching must cover copied-family endpoint audits as well as integrated
phase grids. `audit_two_predictive_families.at_phases` shallow-copies a family and
replaces its grid and banks; a constructor-only cache assumption is invalid.
Require an accepted joint-family replay with both endpoint audits. A worker that
finishes faster because an audit fails and it falls back is not a speedup. Bind
cache validity to orbit buffers and exact time/label/phase grids, and test the
actual copy-and-restrict operation against the uncached calculation.

Use bounded runs over existing recordings and isolated output directories.
Production reads go through public storage/export ports. Preserve validation
when new results are consumed; an optimization must still detect changed or
corrupt inputs. Never write beneath `/mnt/qnap01` or benchmark into production
result namespaces. Do not collect new RF data for this task.

For each successful iteration publish code, tests, a Markdown report, timing
data, parity results, and figures to the requested remote. State component and
overall speedups separately, with runtime environment and concurrency. Install
a qualified change only within the user's deployment authorization, then verify
live behavior and retain the previous release for rollback.
For watcher activation, absence of a child PID alone does not prove idleness:
the application holds a per-job ownership lock before launching and while
publishing after exit. Check every thread's children and the observed open job
ownership files, then recheck while the watcher is stopped. Resume immediately
if work is active. `activate_algo03_runtime.py` implements this guarded handoff
for the qualified ALGO03 composition without interrupting a numerical job.

For native GLRT, `tools/stage_native_glrt_runtime.py` packages the exact tested
prototype bytes only after committed matched full-window timing/parity,
downstream both-arm parity, fixture and saved-policy qualifications pass. It
preserves unrelated installed code and performs no rebuild or service mutation.
Its `verify` subcommand supports an explicitly pinned pre-start check. Native
watcher activation needs its own idle proof: its global watcher lock does not
cover individual work, and a thread may be preparing or publishing a recording
without a child PID. Do not reuse the ALGO03 per-job-lock idle rule unchanged.
`activate_native_glrt_runtime.py request` instead uses the tested graceful drain:
verify the exact watcher source and installed canary, stop the main process
briefly to verify its sleep point, configure the pinned package, and send SIGINT
only to the main process before resuming it. The thread-pool context drains
existing jobs. `finish` waits for that original process to exit before an
idempotent service start. Never replace this with a process-group signal or a
service stop/restart that could terminate active numerical children. A pending
drain is not a completed deployment.

For ALGO02, `stage_algo02_runtime.py` binds committed exact six-file/both-arm
parity to the tested runtime manifest and copies only qualified numerical changes
over the installed baseline. Run an installed prepared replay before activation.
`activate_algo02_runtime.py` requires that installed manifest in the canary proof
and checks all watcher threads and per-job owner locks before an idle handoff.
It preserves the installed interpreter and 1,200-second production budget.

Use `profile_algo02_discovery_cache.py --snapshot --limit 0` to freeze a full
public tracking-input inventory, then `--fixture PATH --repeats 3` for a bounded
alternating cold/warm discovery comparison. Report directory enumeration scope,
first-pass hashing and repeated-pass hashing separately. Metadata-based digest
reuse is discovery-only: consumed inputs must retain fresh full hashing, job
statuses must remain live, and tests must cover same-size replacement with
restored mtime, concurrent edits, stale metadata and eviction.
For installation, `stage_algo02_runtime.py stage-discovery` preserves the qualified
numerical package and replaces only the tested storage module. Run the discovery
profiler with `--candidate-runtime` and `--candidate-pin` against the frozen full
inventory, then supply that installed canary to the guarded ALGO02 activation.
The activation binds fixture, storage, package and plan identities and backs up
an existing override. This discovery qualification does not replace numerical
replays when scientific code changes.
