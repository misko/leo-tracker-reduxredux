---
name: profile-algo07
description: Profile and accelerate the standard fast-scan ALGO07 pipeline while checking frozen scientific results. Use for runtime bottlenecks, queue throughput, exact numerical optimization, and performance regression checks in this repository.
---

# Profile ALGO07

For the owned standalone ALGO07v3 pipeline, use
[profile-algo07v3](../profile-algo07v3/SKILL.md). The commands below primarily
cover the historical worker chain and native IQ detector.

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

Use `tools/profile_algo07_publication.py --bulk-root ROOT --job JOB --output NEW_DIR`
to profile a fresh prediction/grid/PNG replay into a private publication store.
It records evidence reads, reconstruction, grid, plotting and publication costs,
alongside the original public ALGO02–07 worker durations. The grid duration is
inside reconstruction, not additive. Use an external timeout of at most 30
minutes and distinguish profiled research timings from recorded production
timings. Optional evaluation coordinates enter presentation only. A fresh native
replay plus historical position times is not one measured end-to-end execution.

Profile distinct workload classes before selecting a numerical optimization.
Some ALGO07 scans call the two-family phase kernel zero times and are instead
dominated by catalogue interpolation and phase-shifted orbit states. Geometry
reuse must bind immutable orbit buffers, satellite selections, times and phase
grids while retaining query-domain checks and copy/restrict behavior.

For coarse-screening research, `build_native_screen_probe.py` builds an isolated
approximate kernel, and `probe_native_screen.py --selection` measures its grid
cost and tests an interval selector against exact baseline scores. Approximate
scores never enter that diagnostic's actual detector path. `interval_coarse_selection.py`
is correct only if its supplied intervals cover the exact scores: an empirical
maximum error or unchanged winners on a fixture is not a general error bound.
Oracle lookup time is not native exact-rescoring time. Before promotion, require
conservative runtime bounds (including exceptional floating-point cases), actual
sparse exact evaluation with a full fallback, complete detector parity, both-arm
downstream parity and matched runtime measurements. Do not install the FP32 probe.

`probe_native_screen.py --selection --native-rescore --computed-bound` measures
actual sparse scoring through `native_exact_columns.py` and the input-derived
candidate bound in `native_screen_bounds.py`. Sparse scoring reuses the deployed
FP64 kernel with shifted frame bases and unchanged IQ/prefix arrays; dense
requests call the original full grid. Every requested value is compared bitwise
against the complete reference. The bound and combined path remain research-only:
the diagnostic still supplies baseline scores to the actual detector. Summed
component timings are not a fresh full-detector or end-to-end benchmark.
Use `check_native_screen_numerics.py` for the bounded amplitude/cancellation
stress cases; a passing stress suite does not replace qualification of the
integrated detector, unsupported-input fallback and both calibration arms.

`build_screened_detector_runtime.py` composes the separate FP32 extension with
the original FP64 kernel in an isolated research detector. Its acquisition
adapter consumes screened maps only after restoring exact retained peaks and
refinement neighbors. General full-grid APIs remain unchanged. Use
`check_screened_detector_numerics.py`, complete receiver-output paired fixtures,
the full-recording comparator and a fresh prepared downstream comparison.
The builder checks component helper copies against the tested research sources;
analysis code never imports tools. This builder does not stage a production
package. Full fixture parity does not alone certify the proposed error bound.

`build_native_screen_probe.py --integer` builds a separate AVX-VNNI research
screen for exactly integral signed IQ. `probe_native_screen.py` automatically
requires its input-derived quantization bound and binds that bound to the native
transform hash. Quantized correlations are proposals, never exact evidence.
`build_screened_detector_runtime.py` can compose this screen with exact FP64
rescoring and fallback; it verifies the component bound against the tested
research function. Test fractional/out-of-range IQ and missing VNNI hardware
fallbacks, int32 overflow controls, quantization bounds and complete outputs.
One changed approximate row maximum is not a failure if interval selection and
exact rescoring restore the complete original result; unchanged approximate
winners alone are insufficient. `stage_screened_native_runtime.py` verifies the
committed domain review, native stress receipts, complete native parity, fresh
downstream parity, frozen policy audit and three paired detector comparisons
before staging the tested bytes. Its default dry run does not modify services.
Require an installed canary before the guarded native-watcher handoff below.

`build_native_sparse_probe.py` builds an optional FP64 batched-column extension
from the pinned original native kernel. `probe_native_screen.py --sparse-root`
compares each batch bitwise with the complete original grid and times the prior
single-column oracle in alternating order on identical requests. Control and
validation times are excluded from candidate selection costs. Use
`check_native_sparse_numerics.py` for actual native tail, duplicate/order, CFO
tiling and invalid-vector checks. `build_screened_detector_runtime.py --sparse-root`
composes the optional extension without replacing the original full-grid kernel.
The paired-window driver accepts `--comparison` for a direct comparison with
another verified screened runtime sharing the same deployed baseline; do not
infer incremental speedup by subtracting times from separate experiments.

`probe_integer_epoch_pair.py` and `evaluate_integer_epoch_pair.py` evaluate
two-epoch reference reuse against the pinned installed integer screen. Require
actual native boundary checks with `check_integer_epoch_pair.py`, complete
receiver-output comparisons, then a bounded full-recording comparison. Their
grid timings and whole-detector timings are distinct measurements.

`probe_shared_lu.py` is a research-only experiment using the installed NumPy
ILP64 OpenBLAS provider to reuse DGESV factors for the determinant. Its temporary
process-local interception must not be used in production. It checks matrix
outputs bitwise and complete phase-likelihood outputs, but neither establishes
full-worker parity. A production candidate needs an explicit numerical backend,
provider/ABI qualification, fallback handling and both-arm worker replays.

`algo07_profile chain --bulk-root ROOT --job ALGO07_JOB --output FILE` reads a
validated public terminal and reports exclusive ALGO02–07 worker durations.
It checks each cumulative relationship instead of summing nested total fields.
Native GLRT, acquisition, queue waiting and watcher work outside worker timers
are explicitly excluded; its end-to-end value remains unavailable. Use this
as observational attribution, not as a paired speed benchmark. The public
native report currently supplies window count but no processing duration.

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

For exact fractional-weight reuse, `stage_native_glrt_runtime.py stage-fractional`
requires committed complete native parity, three faster alternating cohort-window
comparisons, fresh exact downstream both-arm parity and the saved-policy audit.
It verifies that only the qualified interpolation module differs from the
deployed native baseline. A reused full baseline establishes parity only; the
paired window trials supply timing evidence. Run an installed 16-window canary
before the same guarded native drain, then verify the replacement live runtime.

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
