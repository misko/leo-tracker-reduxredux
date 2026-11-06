# Standalone ALGO07v3 run and publication recovery

The [latest cumulative comparison](../../reports/2026_11_06_algo07v3_reference_recovery/README.md)
observes original ALGO07 at 886.905 s versus current v3 at 193.899 / 152.529 s
on DS26-0002 (4.57–5.81×), preserving both arms, scientific audits, ownership,
public grid/path and eight PNGs. These bracketed, shared-host observations reuse
one reference; they are not dataset-wide or capture-to-publication guarantees.
The original worker-plus-publication subtotal is 811.989 s (4.19–5.32×).
Reference manifests pass unchanged after exact private restoration. See the
[new stage/queue profile](../../reports/2026_11_06_algo07v3_training_queue/README.md)
for the remaining fit bottlenecks. No CLI contract or production change.

The [inverse-solve workspace](../../reports/2026_11_05_algo07v3_lapack_workspace/README.md)
reuses one private Fortran-order array within each likelihood call, resetting it
before the same LAPACK solve. **1,332 tests** and complete native DS26-0002
publication pass exactly. Four complete DS26-0066 training pairs improve; the
fitted-c mean falls 1.79%, while the smaller reverse c=0 pair falls 0.72%.
Native time is 264.628 → 213.191 s, but large variation in unchanged stages
prevents crediting the whole difference to workspace reuse. The report retains
all alternatives and regressions. No CLI contract or production admission changes.

The [initial-fit queue](../../reports/2026_11_05_algo07v3_initial_queue/README.md)
uses at most three workers across all nominated branches and both calibration
arms. **1,203 tests** and a complete native DS26-0002 comparison preserve exact
science, audits, point ownership, public grid/path and all eight PNGs. Initial
search is **20.744 → 18.877 s**; complete native time is **152.602 → 151.305 s**,
with CPU **224.770 → 227.200 s**. Prepared searches on two DS26 scans improve
about 8% on average. The alternative fitted-c-first schedule is not integrated:
its means regress on both scans. Production and full-cohort admission are unchanged.

The [screen-azimuth optimization](../../reports/2026_11_05_algo07v3_screen_azimuth/README.md)
omits unused azimuth calculations while retaining exact elevation and Doppler
arithmetic. **1,162 tests**, twelve complete screens and 99 real-projection
comparisons pass. Fresh native DS26-0066 preserves complete science/eight PNGs,
including accepted reassociation, and matches its earlier qualified output.
Native time is 469.957 → 404.752 s, but only 1.633 s of that difference is in
residual screening; unchanged stages vary. Component means improve 12.39%/12.70%.
Production and full-cohort qualification remain unchanged.

The [endpoint-reuse optimization](../../reports/2026_11_05_algo07v3_endpoint_reuse/README.md)
gathers each lower orbital interpolation sample once while preserving arithmetic
and array layout. Twelve complete screens and 99 real-state comparisons are
exact; **1,132 tests pass**. Screen means improve 13.38%/8.74% on two DS26 scans.
Fresh native DS26-0002 is **161.006 → 153.129 s** with exact science/eight PNGs;
screening alone saves 1.144 s and other stages vary. The report accounts for every
stage and ranks next experiments. This is development integration; production
and full-cohort qualification are unchanged.

The [scalar-phase optimization](../../reports/2026_11_05_algo07v3_scalar_phase/README.md)
shares interpolation indices across satellites only when their requested phase is
scalar. State arithmetic, rotation vectors, per-satellite phases and empty-bank
behavior remain exact. All twelve complete screen trials improve, all 99 real
coarse-state checks match, and **975 tests** pass. Native screening improves
9.394 → 8.862 s; the complete native pair is 165.924 → 154.351 s, with other-stage
variation. Full science and eight PNGs match; production is unchanged.

The [immutable-bank iteration](../../reports/2026_11_05_algo07v3_bank_validation/README.md)
validates a private immutable snapshot once per residual screen. Mutable callers
and every per-call phase/time check retain validation. The twelve final prepared
screens are exact, with means 12.397 → 11.871 seconds and 26.394 → 23.015 seconds
on DS26-0002/0066. The slower DS26-0002 third candidate is retained. **845 tests**
pass; the report includes the fresh native science/eight-PNG comparison. This
is development integration, not production or full-cohort qualification.

The [nomination geometry optimization](../../reports/2026_11_05_algo07v3_nomination_points/README.md)
projects only the union of points already selected by the original coarse folds;
all full-data finalist fits and acceptance gates are unchanged. Twelve complete
screens on two DS26 scans, 99 selected-projection checks, 796 tests and a fresh
native DS26-0002 comparison pass exactly. Native screening falls 12.622 →
10.587 seconds; the complete pair is 165.230 → 158.773 seconds with host variation.
The final formatted source has a separate exact publication replay. This is
development integration, not deployment or full-cohort qualification.

The [direct Cholesky iteration](../../reports/2026_11_05_algo07v3_likelihood_repeats/README.md)
preserves exact numerical outputs and all eight PNGs on fresh native DS26-0002
qualification, with **772 tests** passing. Controlled full training fits on
DS26-0066 improve 1.05–1.59% in both c arms. The complete native pair is
184.748 → 158.609 s, but unchanged-stage host variation prevents assigning the
whole difference to this implementation change. The measured candidate module
is integrated in development; production and full-cohort qualification remain
unchanged. No priors, candidates or numerical iteration budgets were changed.

The [recovery catalogue cache change](../../reports/2026_11_05_algo07v3_catalogue_cache/README.md)
reuses validated TLE text from initial preparation, retains all archive checks
and causal selection, and constructs fresh SGP4 objects. The cache is released
before inference. **722 tests**, twelve preparation trials on two DS26 scans
and a fresh complete DS26-0002 comparison pass exactly, including both arms and
eight PNGs. Catalogue latency falls 55–63% in alternating trials. The full pair
is 280.056 → 245.043 s, but unchanged stages account for most of that difference.
This is development qualification; production remains unchanged.

The [paired numerical-replay change](../../reports/2026_11_05_algo07v3_numerical_arms/README.md)
uses the existing recovery-arm executor for independent replay fits, then merges
their numerical receipts in the original c=0/fitted-c order. Annotation replay,
selection callbacks and control/addition ordering remain serial. **716 tests**
and a fresh DS26-0002 complete comparison pass, including both arms and eight
PNG bytes. Native time is **171.653 → 169.742 s**; numerical replay falls
**12.438 → 7.208 s**. This is development qualification, not deployment.

The external [native gradient scheduling trial](../../reports/2026_11_05_algo07v3_native_gradients/README.md)
preserves complete science and all eight PNGs, but its targeted fits regress
4.445 → 5.392 s and consume 72.7% more CPU. It is rejected for integration;
the owned CLI remains unchanged. The complete 291.515 → 229.841 s observation
is driven by unchanged-stage variation, not an established optimization benefit.

The [covariance-index optimization](../../reports/2026_11_05_algo07v3_posterior_followup/README.md)
precomputes covariance gather indices once per likelihood call while preserving
every numerical operation and convergence rule. It passes 727 tests and a fresh
exact DS26-0002 native comparison, including both arms, all science, eight PNGs
and public grid/path. Controlled DS26-0066 training fits are 4.54–5.99% faster.
Observed full native time is **312.944 → 232.515 s**, with host variation;
this is development qualification, not deployment or a population speed claim.

The [bounded annotation-training queue](../../reports/2026_11_05_algo07v3_annotation_training/README.md)
schedules fold/arm training fits through at most three live workers, followed
by the original fold scoring. Numerical replay and callbacks remain serial.
It passes 672 component tests and a fresh exact DS26-0002 native comparison,
including both arms, all eight PNGs and public grid/path. Observed complete time
is **270.401 → 195.246 s**, with shared-host improvements in unchanged stages.
DS26-0066 also passes the complete exact comparison, including accepted guarded
reassociation: **691.997 → 441.193 s**, again with host variation in unchanged
stages. This is development code, not deployment or a population speed claim.

The [fixed-phase geometry iteration](../../reports/2026_11_05_algo07v3_position_geometry/README.md)
reuses position-independent orbital interpolation inside each position problem.
It preserves every position projection, derivative operation, prior, optimizer
budget and phase refresh. DS26-0002 matches both arms, all science, eight PNGs
and publication exactly; 636 broad tests pass. Observed complete time is
**258.526 → 188.557 s**, with shared-host variation in unchanged stages.
This is development qualification, not deployment or a population speed claim.

The latest [family-gate reuse iteration](../../reports/2026_11_05_algo07v3_family_gate_reuse/README.md)
computes unaffected residual gates once per fixed inclusion-audit problem and
updates only the satellite whose orbit is being replayed. All saved gates,
failures, diagnostic witnesses and ordering are retained. A fresh DS26-0002
pair matches both calibration arms, scientific audits, eight PNGs and public
grid/path exactly. Its complete times are **281.351 → 315.061 s**; unchanged
stages slow substantially, so this is not a pipeline-speedup claim. The report
separates alternating audit measurements from this full-run observation.
Production and ordinary-admission qualification remain unchanged.

The owned CLI now maps conservative c=0/fitted-c fits through its existing
ordered executor. Rejection masks, salvage and callbacks remain sequential;
only compact fit/metric records cross the process boundary. The
[qualification report](../../reports/2026_11_05_algo07v3_conservative_arms/README.md)
records 940 passing tests, exact DS26-0066 prepared-stage pairs and four fresh
complete DS26-0002 runs. The stage averages **73.595 → 46.980 s**, with a small
CPU increase. Production and ordinary-admission qualification remain unchanged.
The four full timings are **199.368 / 192.892 / 191.880 / 320.444 s** in ABBA
order, with exact science and all PNGs across all runs. The final baseline's
host-related variation prevents attributing the pooled difference to the change.

The [reassociation timing follow-up](../../reports/2026_11_05_algo07v3_reassociation_benchmark/README.md)
alternates complete screens from live native DS26-0066 inference. Twelve exact
executions average **16.253 → 11.407 s** per two-target screen set. Final science
and eight PNGs remain exact against the unchanged owned result. The new
`tools/benchmark_algo07v3_reassociation.py` also profiles conservative recovery;
its total instrumented time is not a complete-path speed benchmark.

Latest [reassociation geometry reuse](../../reports/2026_11_05_algo07v3_reassociation_geometry/README.md)
shares phase interpolation while retaining independent cavity positions and
the original arm-major nomination order. The report records fresh complete
DS26-0066 qualification, including accepted guarded reassociation, both arms,
science, eight PNGs and publication. The component suite passes 926 tests.
Production and ordinary-admission qualification remain unchanged.
Observed time **549.558 → 653.906 s** is slower on this changing-load host;
exactness passes, but a performance improvement is not established.

Latest [residual-screen geometry reuse](../../reports/2026_11_05_algo07v3_screen_geometry/README.md)
interpolates each phase once for both receiver-position arms, retaining exact
Doppler arithmetic and every candidate/holdout check. A complete isolated
DS26-0002 comparison is exact through science, both arms, eight PNGs and public
artifacts; 918 component tests and three benchmark-tool tests pass. Alternating
prepared-screen time averages **17.997 → 12.203 s**. Complete-run observations
**250.094 → 210.621 s** are affected by host load and cannot establish that
percentage as a pipeline gain. Production and admission qualification are unchanged.

Latest [recovery-arm scheduling change](../../reports/2026_11_05_algo07v3_recovery_arms/README.md)
passes 882 tests and an isolated exact native comparison, including both arms,
eight PNGs and publication. Complete observed time is **229.888 → 202.201 s**;
predictive recovery is **69.319 → 45.570 s**. Original inclusion trials and their
existing retry use two owned children; targets, variants, gates and later
numerical replay remain sequential. Mutable numerical-policy receipts explicitly
force serial fitting. Production and ordinary-admission qualification are unchanged.
Use the [profiling skill](../../.agents/skills/profile-algo07v3/SKILL.md) for the
repeatable measurement/qualification workflow.

Latest [original-versus-v3 evidence](../../reports/2026_11_05_algo07v3_cumulative_repeat/README.md)
now compares fresh complete executions: original **642.886 s**, v3 before/after
**440.510 / 226.531 s**. Both v3 runs match all public fields, both arms, eight
PNGs and all 17 scientific audit mappings exactly. Shared-host variation and
research-harness overhead are explicitly accounted; these are not full-dataset
or production-admission qualifications. An independent audit verifies 21 excluded
metadata fields across five initial policies with 19 passing tests. Later metadata
semantics remain open. Runtime code and production are unchanged by this audit.

Latest development change: [concurrent family fits](../../reports/2026_11_05_algo07v3_family_integration/README.md)
are wired into the owned CLI. All 843 component tests pass, and a fresh isolated
serial/concurrent comparison is exact through both arms, all eight PNGs, grid/path
and publication. Observed total time is **245.714 → 228.848 s (6.86% lower)**;
unchanged stages also improve, so this is not wholly attributable to the change.
Family fitting takes **17.675 → 11.301 s**. The two independent arms use the
existing ordered executor; rejection rounds and acceptance remain sequential.
Production remains unchanged; full DS26 and ordinary admission remain open.

Latest development change: [bounded variance batching](../../reports/2026_11_05_algo07v3_variance_integration/README.md)
is enabled. The module matches the prototype qualified on two native scans;
833 component tests pass. A fresh direct isolated run verifies integration
exactly through all science, both arms, eight PNGs, grid/path and publication.
Production remains unchanged and the command still supports validation-all-work only.

Current qualification: [all 17 mapped scientific audit sections](../../reports/2026_11_05_algo07v3_factor_reuse/README.md)
match on DS26-0002, including explicitly accounted original-worker context
construction counters. This does not qualify other scans, ordinary admission
or excluded operational metadata. The [solver integration](../../reports/2026_11_05_algo07v3_solver_integration/README.md)
now enables upper-root factor reuse and removal of overwritten Gaussian
posteriors in the owned development CLI. The combined isolated execution exactly
matches scientific/publication outputs and 820 tests pass. Its 264.356-second
observation is not a matched speed benchmark. Production remains unchanged.

A second complete isolated comparison, [DS26-0066](../../reports/2026_11_05_algo07v3_native_canary/README.md),
now passes exactly against the pre-optimization standalone engine, including
accepted guarded reassociation, both arms, all eight PNGs and public fields.
Observed times are 900.763 / 761.514 seconds; baseline profiling and shared-host
conditions prevent treating this as a controlled speedup. This broadens native
branch coverage but does not establish whole-population or historical equivalence.

The owned command is `leo-algo07v3` after installing this checkout, or
`PYTHONPATH=src python -B -m leo.cli.algo07v3` from its root. It starts one owned
worker. It does not invoke earlier ALGO executables or consume their results.
Fresh runs now execute each initial branch's independent c=0 and fitted-c fits
in two owned child processes. The parent returns their results in the original
order; branch selection, phase rounds, budgets and zero-phase controls are
unchanged. Direct numerical calls remain serial unless supplied the execution
port. The request schema and published contracts are unchanged.
Ordinary predictive annotation also executes its at-most-three predeclared
randomized grouped folds in owned child processes and merges complete results
in the original seed order. Targets, inclusion trials and adoption remain
sequential. Numerical replays with mutable policy receipts and calls with a
proposal callback keep serial execution. Initial-arm and fold concurrency do
not overlap: at most three fit children are active, each with one BLAS thread
and the job's inherited CPU affinity. Failed or interrupted children abort the
stage and are reaped; incomplete folds cannot become scientific rejections.

Final diagnostic-grid scoring now uses three contiguous process batches through
the same bounded execution adapter, after all inference has finished. Each
location retains both calibration arms and the original score calculations.
Results return in the original point order; the existing 300-second budget is
checked before each paired location. On expiry, publication retains only the
contiguous evaluated prefix. This preserves the grid schema, but timing-dependent
partial-grid counts are not guaranteed identical. Exact qualification requires
complete grids and all eight PNG bytes. Direct presentation calls remain serial
unless supplied the grid execution port. This change does not parallelize the
Matplotlib renderer or change satellite selection.

Grid batching has exact full-science/eight-PNG qualification on DS26-0002 and
DS26-0066. Complete runtime measurements are mixed: the hard-scan pair regresses
564.831 → 585.201 s despite a lower plot-evidence duration. See the hard-scan
report for the retained evidence. The separate parallel-gradient tool is an
experiment only; native position fits do not use it.

The command is currently qualified for **validation-all-work** only. It is not a
deployed service or a claim of equivalence to production wall-clock admission.

## Run

```sh
PYTHONPATH=src python -B -m leo.cli.algo07v3 run \
  --request /absolute/path/request.json \
  --work-dir /absolute/path/fresh-attempt \
  --timeout 1200
```

Each attempt directory must be new. It contains the frozen request, launch
description, streamed stage log, worker outcome and supervisor receipt. The
separate `output_root` holds the owned scientific archive and public artifacts.
An existing committed scientific result with the same request is reused; the
command never overwrites it with a newly fitted result. A different request for
the same run fails. A committed receipt with a missing or corrupt archive fails
rather than silently starting another fit.

Requests contain these exact version-one fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `execution_policy` | `"validation-all-work"` |
| `identity` | `run_id`, `session_id`, tagged `input_sha256` |
| `native_input` | Absolute `path` and tagged `sha256` of native GLRT JSON |
| `track_config` | Absolute `path` and tagged `sha256` of JSON containing `config` |
| `tle_root` | Absolute causal archive root supplied to the public archive reader |
| `output_root` | Absolute local output root, outside QNAP |
| `search_center` | `[37.906, -122.545]`, the current published 25 × 25 km frame |
| `screen_center` | Explicit two-element latitude/longitude screening center |
| `scan_identities` | Unique identities including `identity.session_id` |
| `title` | Recording title used by the renderer |
| `evaluation_reference` | `null`, or presentation-only `latitude_deg`/`longitude_deg` |
| `runtime` | Exact installed versions of `python`, `numpy`, `scipy`, `sgp4`, `matplotlib`, `pillow` |

`leo.operations.localization_v3_job.runtime_versions()` reports the runtime
pins. Freeze these in the request before comparing runs; do not change them to
make a mismatched runtime pass. Input and configuration bytes are checked before
inference and again before committing evidence. The full configuration, request
digest, runtime versions and loaded owned source hashes are saved in provenance.
The archive reader and preparation retain the causal catalogue evidence.

The current figure contract fixes the regional frame; this command does not
introduce a new location-specific fitting prior. Evaluation coordinates are
passed only to rendering/publication and do not enter fitting or association.

## Recovery without refitting

```sh
PYTHONPATH=src python -B -m leo.cli.algo07v3 resume \
  --request /absolute/path/request.json \
  --work-dir /absolute/path/fresh-resume-attempt \
  --timeout 1200
```

`resume` requires an already committed scientific archive. It verifies the same
identity and request, then publishes its saved PNGs and sidecars through the
existing public port. It needs neither native GLRT bytes nor the TLE archive and
does not rerun rendering or inference. This supports interruption after the
scientific commit, including partial UI publication. It does not restart a
partially completed optimizer. Repeated publication preserves content digests.

## Limits and cancellation

This execution adapter uses Linux/POSIX process groups and signal timers. The
supervisor pins BLAS thread counts to one and enforces `--timeout` over the child
process, including its imports, numerical work and publication. Accepted limits
are positive and at most 7,200 seconds. The default is 1,200 seconds.

The execution adapters use Linux `fork` from a single Python-thread owner. They
share the scan copy-on-write and inherit the worker's CPU affinity; they do not
expand that CPU allowance. Initial search queues all nominated branch/arm fits
on at most three children, collecting results in original branch/c0/fitted-c
order. The caller still owns the scientific branch budget. The paired fallback
and other paired-fit stages use at most two children. Optional initial branch
callbacks retain their values/order but arrive after the complete queue; the
native engine currently supplies no such callback.
Successful fits wait for normal worker exit under the existing job/stage deadline,
without a new short completion cutoff. A child crash, serialization error or
incomplete result aborts the job and cannot become a scientific rejection.
Parent interruption terminates, kills if necessary and reaps all running children;
queued tasks do not start after cancellation or failure.

On timeout the supervisor sends termination to the entire worker process group, waits up to
two seconds, then kills remaining descendants and reaps the direct child. A
timeout returns exit code 124. Parent cancellation cleans up the same group and
returns 130. SIGKILL of the supervisor itself is outside this adapter's cleanup
guarantee; a service manager should own the process group/cgroup in deployment.

Gap stages retain their supplied stage caps. Their Python-level timer raises a
dedicated `BaseException` so a cancellation cannot become an ordinary scientific
rejection/fallback. Native code can defer Python signal handling; the process
supervisor supplies the hard outer limit. An interrupted job is not reported as
complete. If cancellation races a finished commit, the attempt can report
interruption while durable evidence exists; use `resume` to verify and reconcile
that state.

The all-work policy admits the validation discovery work without the older
ALGO03 elapsed-time admission cutoff. It retains the numerical budgets, stopping
rules and existing inner limits. It does **not** establish ordinary production
admission equivalence, nor guarantee all work finishes within the requested
timeout. Changing those scientific admission semantics remains a release gate.

## Timing scopes

The worker records native-to-render, evidence projection/save, publication and
their combined time. Its combined clock starts after loading the result/public
adapters. The supervisor separately records child process elapsed time, including
startup/imports and final outcome writing. Neither clock includes capture,
detector/native GLRT extraction or queue waits. Matched full reference/current
runs are required before claiming an end-to-end speedup.

The external `tools/qualify_algo07v3_cli.sh` harness runs this same command in
private mount/network namespaces, masks older installations/bulk results/reports,
binds the frozen bundle read-only, and can hide it completely for `resume`.
It requires namespace/mount privileges; the CLI itself does not.
