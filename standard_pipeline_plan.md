# Standard GLRT64 Pipeline — Modular Implementation Plan

Status: proposed for review and discussion. This document does not authorize a
deployment, database migration, QNAP mutation, or new radio collection.

This plan turns the exploratory workflow recorded in
[`standard_pipeline.md`](standard_pipeline.md) into the only automatic ordinary
analysis applied to eligible recordings. It retains the short-cycle policy in
[`plan2.md`](plan2.md): use existing immutable IQ first, keep radio work lean,
and do not block development on multi-hour campaigns.

The target hierarchy for a normal dual-radio, dual-receiver capture is:

```text
T1 capture
├── Radio0 / RX0 ── complete receiver-path Standard pipeline ──┐
├── Radio0 / RX1 ── complete receiver-path Standard pipeline ──┴─ Radio0 report ─┐
├── Radio1 / RX0 ── complete receiver-path Standard pipeline ──┐                 ├─ paired report
└── Radio1 / RX1 ── complete receiver-path Standard pipeline ──┴─ Radio1 report ─┘
```

The four receiver paths are processed and reported independently. A radio
report consumes the two completed receiver-path products for that radio. A
paired report consumes the two completed radio reports. Reducers reuse
immutable products and do not reread raw IQ.

“Independent” means independently executed and provenance-bound receiver
paths. It does not mean the four paths are statistically independent trials.
They observe the same sky interval and may share clocks, antennas, front-end
effects, or interference.

Delivery in one view:

| Phase | Outcome | Parallel work unlocked |
|---|---|---|
| 0. Freeze | scopes, lineage, status, contracts, release and cache rules | corpus, catalog, reader, science and UI mocks |
| 1. Foundation | typed 2×2 DAG, one-RX readers, exact worker release authority | independent scientific modules and reducers |
| 2. Receiver science | four complete path reports with degree 1/2/3 feedback | radio/paired integration and optimization |
| 3. Reuse and reduction | two radio reports, one paired report, exact cache frontier | full CLI/API/UI vertical |
| 4. Operator surfaces | three-row table, stale/reuse state, synchronized interactive plots | shadow operation |
| 5. Release | corpus, performance, canary and rollback gates pass | sole automatic Standard cutover |

## 1. Decisions and non-negotiable rules

1. The new immutable release family/display version is named
   `standard-glrt64-v2`. The authoritative `pipeline_release_id` is the exact
   staged 40-character Git SHA required by the deployment verifier. Family and
   semantic version are separate display metadata, never authority aliases.
2. This graph is the only automatic ordinary scientific analysis. Raw
   validation, artifact projection, and reporting remain necessary support
   stages. Historical Standard products remain readable but are never mutated.
3. Quick and Research do not run automatically. Research tools may remain as
   explicit evidence-only development commands, but they cannot become current
   recording products without a separately reviewed release.
4. GLRT64 is the primary detection and trajectory-feedback lane. The current
   Anchor-8, differential-16/32, GLRT-32, edge-tracker, symbolwise, and QAM
   methods remain bounded diagnostic contributors and same-IQ controls.
5. Every receiver path runs through waterfall, scheduled pilot search,
   segmentation, linear/quadratic/cubic fitting, correction replay, GLRT64
   redetection, trajectory table, and path report.
6. A paired result is derived evidence, not raw data. The UI may show it beside
   radio rows, but its type must always be explicit.
7. Cross-radio comparison is score/trajectory-level. It must not coherently
   combine complex IQ unless a later reviewed phase authority exists.
8. Candidate consistency, QAM response, and successful correction do not prove
   Starlink specificity, attribution, payload recovery, or production
   acceptance. These limitations are permanent fields, not UI footnotes.
9. No component writes, moves, renames, or deletes anything under
   `/mnt/qnap01`. Required test material is independently materialized into a
   protected local TEST corpus at
   `/srv/bulk/leo/test-corpus/trial-132-four-path-v1` and then opened read-only.
10. A new failed or incomplete reanalysis never displaces the prior current
    sealed run.
11. Automatic eligibility is frozen: only committed, healthy ordinary captures
    are selected. `QUALIFICATION`, `CALIBRATION`, and `ACCEPTANCE` are excluded
    from this graph. Reviewed `TEST` corpus runs are explicit evidence-only runs
    and cannot replace current ordinary analysis.

Eligibility and visibility matrix:

| Source/tags | Automatic Standard | Promotion | CLI/UI visibility |
|---|---|---|---|
| ordinary `LIVE` | yes | current | ordinary/current views |
| committed `IMPORT` or re-ingested ordinary data | yes, unless excluded below | current | ordinary/current views with source label |
| reviewed `TEST` corpus | explicit only | evidence-only, never `CurrentAnalysis` | searchable/viewable through typed non-current evidence projection with prominent TEST label |
| `QUALIFICATION`, `CALIBRATION`, or `ACCEPTANCE` | no | owned by its separate evidence lane | visible only through that lane |

### Section checkpoint

- The owner accepts the seven-subject hierarchy: four receiver paths, two
  radios, one pair.
- The owner accepts GLRT64 as primary while retaining the other methods as
  diagnostics and controls.
- The owner accepts that the paired row is derived rather than raw.
- No implementation begins until these decisions and the candidate-only
  vocabulary are recorded in an ADR.

### Test cases

- Contract vocabulary rejects `confirmed Starlink`, `payload decoded`,
  `phase-coherent`, or `independent trials` in Standard result status fields.
- A paired product cannot validate as a raw recording or receiver-path product.
- Old persisted v1 documents still load byte-for-byte after new v2 contracts
  are introduced.
- Real catalog projections prove LIVE and IMPORT automatic/current behavior,
  TEST evidence-only nonpromotion plus labeled CLI/UI discoverability, and
  qualification-tag suppression.

### Verification procedure

1. Review the ADR and this section together.
2. Run the contract compatibility suite.
3. Confirm no migration or code path rewrites an existing public product.

## 2. Current baseline and prerequisites

The exploratory algorithms are substantially ahead of the production execution
model. This is important: the work is not merely adding two reducers.

Current facts:

- `standard_pipeline.md` documents a successful four-path replay, but it was
  produced by explicit tools, not by the ordinary catalog pipeline.
- Production jobs are cloned once per stream, while a stream can contain RX0
  and RX1.
- `RecordingIqReaderProvider` currently interprets `scope_key` as a stream ID.
- Job dependencies and product reads are restricted to the same scope.
- `TrajectoryFeedbackAnalyzer` requires a single-receiver IQ view and returns
  no result for an ordinary dual-RX stream reader.
- Most nominal Standard stages share `LongDwellCoordinator`; the first adapter
  can compute the whole dwell and later adapters expose cached portions. Some
  declared inputs are therefore not actual runtime inputs.
- The coordinator's cache key is only `(run_id, scope_key)`.
- Workers can claim a job for any queued pipeline release and then execute the
  registry already loaded in that worker. There is no exact release/graph/
  executable match before IQ access.
- `AnalysisProduct` is run-owned. There is no durable content-addressed
  cross-run computation cache.

The implementation must close these gaps before claiming modularity, accurate
lineage, or safe reuse.

### Section checkpoint

- Produce a read-only baseline inventory of the current graph, actual data
  reads, generated products, dependencies, run configuration, and worker
  release identity.
- Freeze the current trial-132 numerical results as candidate-only comparison
  evidence, not calibrated truth.
- Decide whether to split every scientific operation into a durable stage or
  initially publish one honest coarse receiver-path science stage. A coarse
  honest stage is preferable to decorative fine-grained stages.

### Test cases

- Instrument every current analyzer and prove which IQ/product reads it
  performs.
- Demonstrate that a dual-RX stream cannot currently complete trajectory
  feedback through the production DAG.
- Queue an old release against a differently loaded registry in an isolated
  environment and prove the future worker gate rejects before IQ or artifact
  access.
- Change a per-run configuration value and prove the future runtime both uses
  it and includes it in lineage. A catalog/runtime disagreement must reject.

### Verification procedure

```console
uv run pytest -q tests/analysis tests/processing
uv run ruff check src tests tools
uv run mypy src
```

Attach the baseline graph, call counters, and output digests to the first design
review. Do not use the current in-process coordinator cache as evidence that the
new durable cache works.

## 3. Target scientific DAG

### 3.1 Receiver-path stages

Every available `(session, stream, receiver)` path receives this complete
pipeline after one shared non-cacheable integrity gate per raw radio stream:

```text
stream-integrity-verify (per RadioStream; every reprocess)
└── path-input-bind (per receiver)
    ├── path-quality
    │   └── path-power
    │       └── path-waterfall
    └── path-probe-schedule
        └── path-pilot-scan
            └── path-trajectory-bank
                └── path-trajectory-feedback
path-quality + path-power + path-waterfall + path-trajectory-feedback
    └── path-scientific-report
        └── path-presentation
```

The stage responsibilities are deliberately narrow:

| Stage | Reads IQ | Primary output |
|---|---:|---|
| `stream-integrity-verify` | yes | full compressed/uncompressed chunk verification and availability for this run |
| `path-input-bind` | no | exact one-RX selector, geometry, coverage and stable input lineage |
| `path-quality` | yes | clipping, continuity, constant-IQ and coverage evidence |
| `path-power` | yes | bounded per-window power timeline and summary |
| `path-waterfall` | yes | bounded frequency × time tiles and metadata |
| `path-probe-schedule` | no | deterministic 1 s / 50 ms / first-20 ms probe identities |
| `path-pilot-scan` | yes | bounded multi-method probe certificates and controls |
| `path-trajectory-bank` | no | segmented candidates and linear/quadratic/cubic models |
| `path-trajectory-feedback` | yes | model-conditioned correction and redetection results |
| `path-scientific-report` | no | complete trajectory table, status, coverage and lineage |
| `path-presentation` | no | bounded browser products and deterministic export PNGs |

For a 60-second recording, the default schedule is exactly 60 coarse windows,
20 probes per coarse window, and 1,200 probes per receiver path. Geometry stays
configurable and is part of the computation identity.

The scientific report preserves every retained degree-1, degree-2, and degree-3
fit, while separately marking which fits were selected for correction. The
frequency convention remains:

```text
cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)
```

The report includes both initial and corrected GLRT64 responses, support,
residual RMS, BIC, iterations, same-IQ control, fit-quality status, and rejection
reason. PNGs are derived views and never the only copy of numerical results.

The stream integrity gate is intentionally not a reusable science result. Every
reprocess verifies current raw bytes synchronously through a pinned store before
catalog run mutation or cache decisions, sharing the work across sibling RX
paths. It emits a bounded `RawIntegrityAttestationV1` that is bound into the
expanded plan and run manifest as an external prerequisite rather than a
reusable leased scientific product. A failure creates no run. An exact
scientific cache hit therefore performs zero scientific analyzer IQ reads, but
it does not mean zero raw-integrity I/O.

### 3.2 Radio reducers

One radio reducer consumes the exact completed path reports belonging to one
radio stream, normally RX0 and RX1. It receives a product-only input port and no
raw IQ capability.

It must:

- preserve each receiver's evidence separately;
- align candidate intervals using sample/time uncertainty;
- compare physical tuned-domain frequency rather than blindly comparing
  baseband CFO;
- retain unmatched paths and candidates;
- treat a manifest-declared one-RX radio as complete for that topology while
  explicitly stating that no dual-RX agreement was evaluated;
- label a missing or failed declared receiver as partial, never as
  dual-receiver agreement;
- reject duplicate, foreign, ambiguous, cross-radio, or differently calibrated
  inputs; and
- publish a bounded `radio-standard-report` plus presentation.

Child truncation is contagious. If a path omitted candidates or trajectories
because a declared bound was reached, the radio reducer preserves that fact. It
cannot interpret a truncated item as absent or claim complete agreement.

### 3.3 Paired-radio reducer

The paired reducer consumes the exact two radio reports from the same manifest
and its canonical synchronization-inventory digest. It also receives no raw IQ
capability.

It must:

- align reports on the manifest's shared UTC time domain;
- preserve the measured radio start skew and timing uncertainty;
- use the union for visualization and the estimated overlap interval plus its
  uncertainty for candidate-level comparison;
- preserve four distinct receiver lanes;
- match compatible trajectory families without forcing a match;
- reject independent captures, unknown or nonpositive estimated overlap,
  incompatible tune or timing semantics, and ambiguous membership; and
- carry `phase_coherent=false` unless a future typed authority proves otherwise.

A zero guaranteed-overlap lower bound limits the strength of the paired claim
but does not erase a positive estimated overlap. Child truncation is also
contagious at this level; it cannot be interpreted as a miss or complete
cross-radio agreement.

Accepted terminal scientific outcomes such as `no_result` and
`insufficient_data` are persisted products and may be reduced according to the
status algebra. A hard failed, cancelled, or not-run child produces no reducer
artifact: the catalog/UI projects the aggregate as `blocked` with exact child
reasons. Reducers do not fabricate failure receipts.

For the current reference recording, the regression target is a measured skew
of 1.425210 ms and a shared union of 60.001424810 seconds.

### Section checkpoint

- A pure planner expands the reference manifest into four path chains, two
  radio reducers, and one paired reducer with exact edges.
- Reducers cannot obtain an `IqReader` through their type or construction path.
- Each scientific stage either consumes its declared durable inputs or is
  collapsed into a coarser honest stage.
- Stage and aggregate status algebra is frozen before UI implementation.

### Test cases

- Topologies: 1 radio × 1 RX, 1×2, 2×1, mixed 2+1, and 2×2.
- Reordered manifest inputs yield the same canonical plan.
- Repeated `stream-0` in different sessions never collides.
- Missing, duplicate, or extra RX paths fail or produce the explicitly defined
  partial status.
- A reducer cannot start before its exact children complete.
- A reducer cannot read an undeclared product.
- All child outcome combinations exercise `complete`, `partial`,
  `insufficient_data`, `failed`, and `not_run` propagation.
- Paired reduction rejects two unrelated single-radio captures.

### Verification procedure

1. Render the expanded DAG as canonical JSON in unit tests.
2. Assert exact job count, scope identity, and dependency edge count for every
   topology fixture.
3. Run analyzers behind spy ports and assert path stages read only their own RX,
   while reducers perform zero IQ reads.
4. Compare paired timing output to the frozen trial-132 timing values.

## 4. Workstream A — typed scope and capture lineage

Opaque scope strings are not sufficient for safe fan-out and fan-in. Introduce
an immutable `ScopeIdentityV1` with canonical documents for:

- `receiver_path(session_id, stream_id, receiver_id)`;
- `radio(session_id, stream_id, radio_id)`; and
- `paired(session_id, synchronization_inventory_digest)`.

The paired inventory digest is derived from the exact ordered stream/timing
inventory in the verified manifest; it is not a caller-supplied group label.
Each document is deterministic and versioned and has a canonical digest.

Do not force the full reversible document into the existing 256-character
`scope_key`: valid component identifiers can already exceed that combined
limit. Add a normalized typed scope table with a surrogate catalog key, unique
canonical digest, kind, and typed identity columns. New jobs/products reference
that row; legacy `scope_key` values remain explicit legacy stream scopes until
they can be resolved. Scope equality must never be inferred from filenames or
opaque string parsing.

Add capture-time receiver lineage keyed by
`(session_id, stream_id, receiver_id)`, binding the exact radio/serial,
receiver ID, physical receiver path, hardware epoch, manifest identity, applied
settings, and timing basis. New captures reconcile this from typed manifests and
frozen topology evidence. Legacy rows remain explicitly unresolved when the
facts cannot be proved.

Calibration remains an analysis-time resolved input covering the whole capture
interval. It is not silently fabricated during reconciliation.

Historical ordinary IQ may lack an authoritative calibration. Its receiver
pipeline still runs in baseband coordinates with a typed
`frequency_reference=uncalibrated_prior`; this is not a
`ReceiverFrequencyCalibration`, carries no calibration ID/digest, and cannot
support tuned-domain cross-path frequency agreement. Radio/paired reports keep
the path evidence but mark physical-frequency association unavailable or
insufficient. When an authoritative calibration later becomes applicable to
that exact capture/path/epoch, baseband-only science may be reused, while every
calibration-dependent wrapper, association, aggregate and presentation is
recomputed.

### Checkpoint A

- Canonical scope vectors and lineage contracts are frozen.
- A populated previous-to-head migration preserves all existing sessions and
  composite `(session_id, stream_id)` identities.
- New trial-132 lineage resolves exactly four receiver paths.
- Unprovable legacy lineage stays unresolved rather than guessed.

### Test cases A

- Scope document round-trip, digest, ordering, component-bound, Unicode and
  delimiter adversaries; the normalized row must support worst-case valid
  component lengths without truncation.
- Cross-session substitution and repeated stream IDs.
- Radio/serial/receiver/physical-path/hardware-epoch substitution.
- Concurrent identical reconciliation is idempotent.
- Conflicting reconciliation rejects and leaves the original row unchanged.
- Calibration before/after validity boundaries and missing calibration.
- `uncalibrated_prior` cannot validate as a calibration, cannot carry a
  calibration digest, and cannot authorize physical-frequency association;
  later authoritative calibration invalidates only the expected descendants.
- Populated migration, empty migration, downgrade safety, ORM drift and single
  Alembic head.

### Verification procedure A

```console
uv run pytest -q -m postgres tests/catalog tests/integration
uv run alembic heads
uv run alembic check
uv run ruff check src/leo/catalog tests/catalog
uv run mypy src/leo/catalog
```

Use only uniquely named disposable PostgreSQL schemas and drop them after each
test. Do not touch the live catalog.

## 5. Workstream B — frozen scientific contracts

Add new contracts instead of changing published v1 shapes:

1. `ReceiverPathInputV1`
   - complete path identity, manifest/chunk closure, IQ selection, geometry,
     timeline, calibration, stage implementation/environment and configuration
     bindings; the consuming release belongs to the run wrapper.
2. `ProbeScheduleV1`
   - exact coarse/subwindow/analyzed interval geometry and all probe IDs.
3. `PilotProbeCertificateV2`
   - bounded multiple candidates per probe, method scores, CFO coordinates,
     epoch, uncertainty, QAM, control and coverage.
4. `TrajectoryBankV2`
   - observations, segmentation, degree 1/2/3 models, fit metrics, family
     membership, selection and rejection reasons.
5. `TrajectoryFeedbackV2`
   - baseline/corrected results, exact correction model, reread sample identity,
     replay gains and controls.
6. `PathStandardReportV1`
   - terminal path status, product set, trajectory table and candidate-only
     interpretation.
7. `RadioStandardReportV1`
   - exact ordered path inputs, associations, unmatched evidence and coverage.
8. `PairedStandardReportV1`
   - exact radio inputs, shared clock, overlap, cross-radio associations and
     noncoherence statement.
9. Bounded presentation contracts for path, radio, paired, stage matrix and
   provenance.
10. `AnalysisRunManifestV2`
    - exact expanded-plan digest, typed job scopes and dependency edges,
      authoritative release/graph/configuration identities, product membership,
      derivation/reuse lineage and terminal outcomes.

Every scientific contract carries source point counts, returned counts,
truncation, units, coordinate system, coverage, configuration digest, direct
stable upstream derivation/output references, and a canonical content digest.
Run-owned wrappers carry the direct catalog input product IDs, run/job IDs,
current artifact URI and consuming-release lineage; these mutable membership
identities never enter reusable scientific bytes.

### Checkpoint B

- Contract model validation can replay all derived identities and summary
  fields from embedded inputs.
- Maximum counts and byte sizes are explicit.
- Candidate-only language and permitted claims are typed.
- Browser contracts contain no unbounded scientific arrays.

### Test cases B

- Redigesting a changed derived value still fails semantic validation.
- NaN, infinity, duplicate IDs, unsorted inputs and excessive counts reject.
- CFO coordinate confusion—residual, baseband, tuned-domain—is rejected.
- Linear, quadratic and cubic coefficient/reference-time reconstruction matches
  frozen vectors.
- Missing-data states cannot validate as a scientific miss.
- v1 compatibility and v2 incompatibility tests prove no in-place mutation.

### Verification procedure B

```console
uv run pytest -q tests/contracts tests/analysis
uv run ruff check src/leo/contracts tests/contracts
uv run mypy src/leo/contracts
```

Publish canonical JSON/digest vectors in tests. Contract review is a hard merge
gate for every downstream workstream.

## 6. Workstream C — verified receiver-path IQ access

Introduce a `ReceiverPathIqReader` that is constructed only from a verified,
pinned `RecordingStore` bundle and a typed receiver-path identity. It exposes
exactly one receiver column while preserving original sample indices and
timeline.

Construction requires the exact successful run-creation
`stream-integrity-verify` attestation for its stream. That gate performs
complete manifest and compressed/uncompressed chunk verification once per
reprocess; path readers
then remain bound to the same pinned inode/chunk identity while scientific work
runs.

RX0 and RX1 remain logically independent, but their samples are interleaved in
the same compressed radio chunks. A bounded radio fan-out reader may decode and
verify a chunk once, then feed two independent single-RX views. This is an
ephemeral performance optimization, not a scientific cache.

Required properties:

- no caller-provided ndarray or arbitrary reader at the production boundary;
- exact binding to the complete stream integrity receipt and verified chunk
  closure;
- stable one-RX selection with no receiver swap;
- consistent output regardless of source chunk partitioning;
- pinned no-follow root and child directory capabilities;
- bounded blocks, reads, memory and fan-out queue depth; and
- no QNAP path or raw filesystem path passed into analyzers.

### Checkpoint C

- One receiver reader reproduces exact selected CI16 bytes and sample indices.
- Two sibling readers can share bounded decode work without sharing scientific
  state.
- Closing or swapping a caller path cannot redirect either reader.
- Partial/gapped IQ cannot claim full coverage.

### Test cases C

- RX0/RX1 selection and deliberate receiver swap.
- Odd block boundaries and multiple compressed chunk layouts.
- Truncated, corrupt, reordered, duplicate and missing chunks.
- Caller capability close and file-descriptor reuse.
- Root and child rename-to-symlink attacks.
- Exact and descendant `/mnt/qnap01`, `..`, and double-slash spellings cause
  zero target syscalls.
- Concurrent sibling readers respect bounded memory/backpressure.

### Verification procedure C

```console
uv run pytest -q tests/storage tests/processing -k 'reader or pinned or iq'
uv run ruff check src/leo/storage src/leo/processing tests/storage tests/processing
uv run mypy src/leo/storage src/leo/processing
```

Instrument compressed bytes read and decompression count. For a sibling RX0/RX1
run, prove that the optional fan-out optimization reduces duplicate decode work
without changing either path digest or numerical output.

## 7. Workstream D — pure cross-scope planner and executor

Replace implicit same-scope dependencies with an exact expanded plan.

Proposed planning contracts:

```text
JobNodeV1
  node_id
  stage_key
  scope: ScopeIdentityV1
  iq_access: none | receiver_path
  resource_class

JobDependencyRefV1
  job_node_id
  depends_on_job_node_id

ExpandedRunPlanV1
  manifest_digest
  pipeline_release_id
  jobs[]
  edges[]
  plan_digest
```

The planner compiles expected children from verified manifest topology. It does
not discover “whatever products happen to exist.” The repository persists the
exact edges instead of converting a dependency stage name to the dependent's
scope.

The product input port authorizes only the exact producer node/product
requirements declared in the plan. Reducer execution uses a product-only
analyzer interface.

The scheduler must also enforce actual resource limits. Four receiver paths,
worker processes, and inner trajectory pools must not multiply into unbounded
CPU or RAM usage. Heavy-stage tokens, worker concurrency, inner pool size,
maximum RSS/output, timeout and cancellation behavior are part of the release
configuration.

### Checkpoint D

- Dry-run planning validates every edge and cycle before catalog mutation.
- Real PostgreSQL can schedule path fan-out and radio/paired fan-in.
- ProductReader resolves exact declared cross-scope inputs and records every
  consumed product ID.
- Reducers have no IQ reader.
- Resource limits are enforced rather than documented only.

### Test cases D

- Missing, cyclic, cross-session, wrong-scope and undeclared dependency edges.
- Extra/ambiguous producer products.
- Fan-in blocked until all exact required children reach accepted outcomes.
- One failed path prevents false complete aggregate status.
- Eight workers race job claims without duplicate execution/publication.
- Lease loss before output, during publication, before register, after register,
  and before completion.
- Worker cancellation, timeout and retry preserve idempotence.
- 2×2 topology under maximum configured concurrency stays inside memory and
  process limits.

### Verification procedure D

1. Use a disposable real PostgreSQL schema and real artifact store.
2. Create the exact 2×2 graph and inspect all job and dependency rows.
3. Run multiple workers with forced delays/crash points.
4. Assert one sealed run, exact product dependency closure, no duplicate
   publications, and unchanged prior current run on failure.
5. Compare measured peak RSS/process count with the configured hard limits.

## 8. Workstream E — exact worker/release authority

A pipeline release label is not sufficient provenance. Before reading IQ or
creating outputs, a worker must prove that its executable registry matches the
queued run.

Freeze and compare:

- full source revision;
- graph digest and exact selected stage set;
- stage algorithm and configuration schema versions;
- normalized release configuration digest;
- executable/package-tree digest;
- Python and numerical environment digest;
- template/reference digests; and
- renderer environment when deterministic PNG reproduction is claimed.

Claims must be release-compatible before they consume an attempt. Prefer
release-filtered claims. If a post-claim recheck discovers a mismatch, the job
is atomically released/requeued without incrementing its attempt count or
changing scientific run state, and a separate operational incompatibility
event is recorded. In all cases rejection occurs before input/output access.
The authoritative stage configuration has one source; registry construction
defaults cannot silently override catalog release configuration.

### Checkpoint E

- Old worker/new job and new worker/old job both reject before IQ access.
- Exact matching worker executes and binds the same release evidence into every
  product and run manifest.
- One changed configuration parameter changes runtime behavior and derivation
  identity.
- Rolling cutover has a documented drain/requeue procedure.

### Test cases E

- Release ID collision with different graph/configuration.
- Same package version with different Git/source tree.
- Changed installed package after worker startup.
- Catalog configuration versus analyzer-constructor disagreement.
- Template, dependency or numerical ABI drift.
- Pending old jobs during a new worker deployment.

### Verification procedure E

Run an isolated two-release cutover matrix. Use spy IQ/artifact ports to assert
zero calls on every mismatch. Then run the matching release and compare its
receipt, run manifest and catalog release identities byte-for-byte.

## 9. Workstream F — modular scientific implementation

Port the exploratory code into pure analyzers; do not invoke the tools as
subprocesses. Numerical kernels remain in narrow modules, orchestration stays in
processing/application code, and rendering stays separate from scientific
computation.

Recommended module boundaries:

- path validation, continuity and clipping quality;
- bounded per-window power measurement;
- probe scheduling and candidate identities;
- bounded multi-method pilot/QAM scoring;
- GLRT64-primary segmentation;
- general multi-method degree-1/2/3 trajectory fitting;
- trajectory family deduplication and selection;
- polynomial phase integration/dechirp;
- conditioned replay and GLRT64 redetection;
- scientific tables/status; and
- presentation renderers.

Each module has typed input/output and no PostgreSQL, HTTP, CLI, storage-path or
ORM imports. Algorithms may be optimized independently only while their frozen
semantic tests and accuracy gates remain unchanged.

### Checkpoint F1 — path validation, quality, power and waterfall

- One path validates exact full coverage and emits per-RX quality, power and
  bounded waterfall data.
- Power is a real time series with declared aggregation, not one mean point
  presented as a dwell timeline.
- Frequency is horizontal and elapsed time is vertical in exported PNGs.
- Interactive presentation preserves full physical axes.

Tests: tone frequency placement, time-bin placement, chunk invariance, all-zero,
clipping, constant IQ, missing interval, multi-window power, axis/units metadata,
deterministic data output.

Verification: compare the reference path quality/power summaries, waterfall
numerical tiles and PNG metadata to the reviewed exploratory artifact; visual
inspection supplements but does not replace numeric assertions.

### Checkpoint F2 — pilot scan

- The exact default schedule emits 1,200 probes for 60 seconds.
- All methods score the same IQ/probe/epoch/coarse-CFO identity.
- Rolled controls remain distinct and bound to the same IQ.
- Multiple bounded candidates per probe are retained.

Tests: exact and rolled pilots, off-grid CFO, CFO boundary/alias ambiguity,
noise, tones, stationary interference, NaN/Inf, maximum candidate count,
parallel worker ordering and deterministic output.

Verification: numerical parity with frozen synthetic vectors and the protected
RETRO candidate excerpt within preregistered tolerances.

### Checkpoint F3 — segmentation and polynomial tracking

- Each enabled method contributes candidate observations.
- Degree 1, 2 and 3 models are fitted and reported separately.
- Crossing, parallel and intermittent tracks are not silently merged.
- Family deduplication is bounded and deterministic.

Tests: exact synthetic linear/quadratic/cubic tracks, crossing tracks, parallel
tracks, long gaps, branch birth/death, duplicate observations, clutter,
permuted input ordering, BIC/RMS selection and rejected-fit reasons.

Verification: reproduce the 6.20–9.65 s recovered trial-132 tracklet and the
reviewed family counts without upgrading the result beyond candidate evidence.

### Checkpoint F4 — trajectory feedback

- Each selected family is integrated into phase and applied only to bounded IQ
  probes; no full corrected recording is materialized.
- Baseline and corrected detection share exact sample identity.
- GLRT64 is the primary replay score and fit-selection lane.
- All diagnostic methods and QAM are rerun and retained.

Tests: analytical phase for degree 1/2/3, nonzero reference time, block boundary
continuity, wrong-sign correction, unrelated trajectory, zero gain, positive
gain, sample substitution, replay limits and deterministic parallel execution.

Verification: reproduce the reviewed GLRT64 quadratic replay gain for the
reference interval within frozen tolerance and verify the symbolwise-only
comparison remains distinguishable.

### Checkpoint F5 — terminal path report

- Scientific JSON alone reconstructs every plotted trajectory.
- Initial/corrected responses, fits and rejections cover the full dwell.
- Report and presentation are byte-deterministic where declared.
- Every dependency is a real consumed product, not a decorative edge.

Tests: report replay, product substitution, renderer-only change, missing
science product, truncation accounting, deterministic ordering and bounded PNG.

Verification: rebuild the path PNG and trajectory table solely from registered
science products and compare semantic values to the exploratory reference.

## 10. Workstream G — durable computation reuse

Implement reuse only after lineage, cross-scope dependencies and release
authority pass. Until then, cross-run scientific caching remains disabled.

### 10.1 Derivation key

Define `StageDerivationKeyV1` as the canonical digest of:

- stage key, algorithm version, output schema and implementation digest;
- normalized stage configuration;
- typed subject scope and receiver-path identity;
- exact selected stream/chunk/IQ closure and only the timeline/topology fields
  semantically consumed by that stage;
- exact ordered upstream derivation/output identities, including scope, kind,
  schema, role, accepted status and content digest;
- calibration set/member and hardware-epoch identity only for stages that use
  it;
- template/reference/TLE snapshot digests where used; and
- numerical environment compatibility identity.

Run-owned product IDs are recorded in the current run's lineage but are not part
of a cross-run key; otherwise an exact rerun could never hit and a catalog
restore would alter scientific identity. The session-wide manifest digest and
whole pipeline release ID also do not belong in every inner key: doing so would
invalidate an unaffected radio or waterfall after an unrelated stream,
tracker, or renderer change.

Freeze two identities from the first cache implementation:

1. `StageDerivationArtifactV1` is the reusable inner numerical document. It
   contains only stable scope/input/algorithm/configuration/environment/output
   identities. It contains no run ID, job ID, database product ID, current-run
   URI, or whole pipeline release label.
2. `RunProductMembershipV2` is the run-owned wrapper. It binds the full manifest,
   consuming release/run/job/product, producing release/source derivation,
   exact artifact digest, current dependencies and `reused_from` provenance.

A current release may reuse an inner artifact only when its authoritative stage
declaration reconstructs the exact same derivation key. The wrapper never
relabels old bytes as newly computed. This makes selective stage reuse across
immutable pipeline releases both explicit and auditable.

### 10.2 Durable result cache

The cache is immutable persisted scientific output, not an in-memory object.
Separate reusable artifact identity from run membership:

- one atomic derivation record per computation key;
- one immutable output set with product digests and producing lineage;
- a run-owned product membership/reference for every reused output;
- explicit `computed` versus `reused` provenance, producing release/source
  derivation, current consuming release, and `reused_from` identity;
- exact dependencies for the current run; and
- reference-aware retention protection.

Do not point a new run at a purgeable source-run URI without shared artifact
ownership and retention accounting. Only deterministic terminal outcomes are
eligible. Transient execution failures are never cached.

A shared artifact becomes reclaimable only when no available, held, current,
campaign-bound, or dependency-protected binding needs it. Because historical
product rows are tombstoned rather than deleted, mere row existence is not a
permanent hold. Purge must stable-lock/claim every eligible referencing binding,
atomically rename the one shared blob to trash, then commit all binding
tombstones, derivation availability and the retention event together; a crash
before commit restores the blob, and physical deletion is asynchronous. Purging
one run product can never remove a blob still used by another run.

### 10.3 Expected invalidation frontier

| Change | Path work | Radio reducer | Paired reducer |
|---|---|---|---|
| Exact rerun, no change | rerun stream integrity; reuse all scientific outputs | reuse | reuse |
| Selected IQ/chunk/path-local timeline change on R1/RX0 | recompute affected path descendants | recompute R1 | recompute pair |
| Different stream changes in the same manifest | reuse unaffected path science; refresh wrappers | reuse unaffected radio science if topology inputs are identical | recompute pair |
| Path calibration/hardware epoch change | recompute affected calibration-dependent path descendants | recompute owning radio | recompute pair |
| Pilot scan configuration change | reuse validation/waterfall/schedule; recompute scan onward | recompute owning radio | recompute pair |
| Tracker implementation/config change | reuse IQ validation/waterfall/scan; recompute tracking onward | recompute owning radio | recompute pair |
| Radio reducer method change | reuse paths | recompute affected radio | recompute pair |
| Paired reducer method change | reuse paths | reuse radios | recompute pair |
| Timing/synchronization/overlap evidence change | reuse timing-independent path science; recompute affected wrappers | recompute affected timing summary | recompute pair |
| TLE/reference snapshot change | recompute dependent association/summary only | recompute dependent summary | recompute dependent paired summary |
| Deterministic partial/insufficient input becomes complete | recompute affected descendants | recompute owning radio | recompute pair |
| Presentation renderer change | reuse all science | science reused | regenerate presentation only |
| Storage URI relocation with the same verified manifest/bytes | reuse science; refresh run membership/provenance | reuse science | reuse science |
| Catalog hold changes only | reuse | reuse | reuse |
| Catalog source/eligibility tag changes | reuse existing science; reevaluate scheduling/current-promotion eligibility and presentation | reevaluate | reevaluate |
| Manifest source/tag-only change | reuse inner science; refresh wrappers and eligibility | refresh wrapper/status | refresh wrapper/status |

### Checkpoint G

- Exact rerun executes zero eligible scientific analyzers and performs zero
  scientific IQ reads after the mandatory non-cacheable stream integrity gate.
- A one-field mutation recomputes exactly the expected descendants.
- Concurrent identical misses produce one durable derivation and identical
  reused references.
- Cache hits digest-verify artifacts before use.
- Current and historical run manifests remain complete and truthful.

### Test cases G

- Every row in the invalidation table.
- Receiver, radio, session, release, graph, config, calibration and template
  substitution.
- Hash/content mismatch, artifact truncation, copied URI and stale DB metadata.
- Concurrent eight-way miss, crash before/after publication, retry and conflict.
- Cached partial/insufficient result offered to a complete requirement.
- Timing/synchronization-only changes, TLE/reference changes, and a transition
  from partial/insufficient evidence to complete evidence.
- Eviction/retention while referenced by path, radio, paired and historical
  current runs.
- Same verified bytes under a relocated storage URI preserve science but refresh
  run provenance; catalog hold changes preserve science; source/eligibility tag
  changes reevaluate scheduling/current-promotion state and wrappers; different
  bytes under the same claimed identity reject.

### Verification procedure G

Run a spy-backed cache matrix that counts analyzer calls, IQ bytes,
decompressions, artifact reads and output writes. Then repeat against real
PostgreSQL and the protected compressed fixture. Inspect exact derivation,
product membership and retention rows after each mutation.

## 11. Workstream H — radio and paired reports

Reducers are pure computations over immutable child products.

### 11.1 Radio report

For each radio, publish:

- exact RX inventory and child product digests;
- per-RX initial/corrected GLRT64 timelines;
- per-RX trajectory tables and selected fits;
- time/frequency uncertainty-aware associations;
- unmatched and conflicting evidence;
- QAM/control comparisons without hiding receiver results;
- coverage and explicit partial/insufficient reasons; and
- cache/release/provenance summary.

Any child candidate/trajectory truncation is propagated and is never treated
as evidence that an omitted phenomenon was absent.

### 11.2 Paired report

For the paired subject, publish:

- exact two-radio inventory and child report digests;
- union and overlap time domains, skew and uncertainty;
- four synchronized lanes;
- cross-radio compatible trajectory groups;
- unmatched/conflicting candidates;
- no phase-coherence claim; and
- complete lineage to all four path products.

Any path or radio truncation is propagated into the paired status and
presentation.

Coincidence increases candidate consistency only. Four agreeing paths are not
four independent trials and do not create a specificity claim.

### Checkpoint H

- Radio reports preserve both RX results and never reread IQ.
- Paired report preserves all four lanes, exact timing, and never rereads IQ.
- Product dependency closure exactly equals the planned children.
- A missing or failed child yields the frozen explicit status.

### Test cases H

- Symmetric/asymmetric SNR and one-RX dropout.
- Duplicate, foreign, cross-radio and cross-session child products.
- Baseband CFO equality but incompatible tuned-domain frequency.
- Calibration uncertainty just inside/outside association gates.
- Unknown, zero, partial and full time overlap.
- Radio ordering and RX ordering permutation invariance.
- One strong path plus three controls does not become agreement.
- Candidate crossing/parallel branches remain distinct across reducers.

### Verification procedure H

Use synthetic truth first, then the trial-132 four-path products. Assert the
exact child digest inventory, zero IQ reads, timing union/skew, association
counts, unmatched counts and candidate-only status. Independently reconstruct
the aggregate from its child products and compare every derived field.

## 12. Workstream I — pipeline release, current state and staleness

Every displayed subject records:

- authoritative pipeline release ID (exact staged 40-character Git SHA);
- release family and semantic display version;
- source revision;
- graph and normalized configuration digests;
- stage implementation/schema versions;
- environment and template/reference digests;
- input manifest and path identity;
- child/derivation product digests;
- computed/reused state; and
- sealed run/product identity.

The UI may display `standard-glrt64-v2.0.0`, but the underlying authority and
CLI/API value remains the exact full SHA. An existing authoritative release ID
cannot be republished with different contents.

Subject states are:

```text
not_analyzed | queued | running | blocked | partial | current | stale | failed | unavailable
```

`stale` is computed against the configured desired release and exact inputs. It
must carry machine-readable reasons such as:

- desired release changed;
- input manifest changed;
- the authoritative calibration applicable to the capture/path/epoch changed;
- upstream path/radio digest changed;
- stage implementation/configuration changed; or
- paired report predates a child report.

A desired-release change makes the old subject stale until a new run seals.
During that run, Workstream G's release-independent inner artifact may be reused
stage by stage only when the new release reconstructs the exact derivation key;
new run-owned wrappers still bind the new consuming release.

### Checkpoint I

- Immutable release registration rejects ID/content collision.
- Every path/radio/paired subject has a deterministic current/stale evaluation.
- Reanalysis dry-run lists exact reused and recomputed stages before mutation.
- A fully sealed new run atomically promotes all subject views.

### Test cases I

- Desired release changes with all stage implementations identical: the old
  subject becomes stale, dry-run reports reusable inner artifacts plus new
  wrappers, and the new sealed run becomes current without relabeling producer
  provenance.
- One stage implementation/config changes.
- Wall-clock time passes beyond a calibration's `valid_until` but the historical
  capture interval was covered: the result remains current. A changed
  authoritative applicability decision for that capture/path/epoch makes it
  stale.
- One path changes and propagates stale state to its radio and pair only.
- Failed reanalysis leaves old current rows and UI unchanged.
- Concurrent reanalysis conflict and idempotent retry.
- Raw corruption/substitution fails before catalog run creation even when every
  scientific derivation would otherwise be a cache hit.
- Old products are unavailable/corrupt rather than silently displayed as
  current.

### Verification procedure I

Use real PostgreSQL to create two releases and several controlled derivation
changes. Compare CLI/API/UI stale reasons and dry-run recomputation plans
field-for-field. Verify current promotion changes in one transaction only after
all required path, radio, paired and presentation products seal.

## 13. Workstream J — artifacts and presentation

Scientific JSON is authoritative. PNGs are deterministic export artifacts for
reports and review. The browser uses bounded presentation contracts for
interactive plots.

Any PNG registered as a durable retryable job product must be byte-identical
across processes, restarts and retries in the frozen renderer/font environment.
If that guarantee cannot be met, the PNG is rendered on demand from the
authoritative JSON and is not a persisted analysis product. “Non-authoritative”
is not sufficient to bypass immutable publication idempotence.

All signal plots share one time coordinate and cursor:

- receiver-path page: path-local elapsed time plus absolute UTC reference;
- radio page: two RX lanes aligned on the radio timeline;
- paired page: four lanes aligned on the shared union timeline;
- no interpolation through missing/not-run/failed intervals.

Required views:

1. per-RX quality/continuity/clipping state and power versus time;
2. frequency-horizontal/time-vertical waterfall;
3. initial and corrected GLRT64 response versus time;
4. candidate CFO cloud versus time;
5. selected/rejected degree 1/2/3 trajectories;
6. QAM accuracy/EVM and control response versus time where evaluated;
7. compact trajectory table with reconstruction fields;
8. exact stage matrix, runtime, version and cache hit/miss state; and
9. searchable provenance drawer.

Presentation products include full-domain bounds before decimation. Server-side
decimation is deterministic and returns source/returned point counts. Raw
scientific arrays never go directly to the browser.

Pinned artifact reads use no-follow directory capabilities, regular-file and
mode/link/count checks, bounded byte reads, digest verification and stable
pre/post `fstat`.

### Checkpoint J

- Every plot can be reconstructed from registered products with no IQ access.
- Path/radio/paired plots share exact time coordinates.
- Numerical domain extrema survive decimation.
- Presentation never strengthens scientific language.
- Artifact reads are confined and bounded.

### Test cases J

- Known timestamp 1.513484 s and known CFO placement on all linked plots.
- Per-RX power contains multiple correctly timed points and quality/clipping
  state is not hidden by the radio/paired summary.
- Full waterfall x/y orientation and units.
- Missing intervals, truncated points and full-domain extrema.
- Linear/quadratic/cubic labels and table/curve reconstruction.
- Root/child swap, symlink, digest/size mismatch, truncation and oversized
  artifacts.
- Renderer-only changes leave scientific derivations untouched.
- Cross-process/restart PNG byte equality for persisted exports, plus a crash
  after publish but before register; nondeterministic renderers are exercised
  only through the on-demand non-product path.
- Accessible tables and keyboard-linked cursor/range behavior.

### Verification procedure J

```console
uv run pytest -q tests/artifacts tests/presentation tests/api
cd web && npm test
cd web && npm run build
```

Run Playwright against a real local API/catalog fixture and visually inspect the
reference path, radio and paired pages. Compare plotted cursor values against
the numeric presentation document, not screenshots alone.

## 14. Workstream K — catalog/API/CLI/UI surfaces

### 14.1 Three top-level rows

For a complete dual-radio capture, the recording analysis table shows exactly:

| Capture | Subject | Paths | Pipeline | State | Reuse |
|---|---|---:|---|---|---|
| T1 | Paired Radio0 + Radio1 | 4/4 | `standard-glrt64-v2…` / full SHA | current/stale/etc. | summary |
| T1 | Radio0 | RX0, RX1 | `standard-glrt64-v2…` / full SHA | current/stale/etc. | summary |
| T1 | Radio1 | RX0, RX1 | `standard-glrt64-v2…` / full SHA | current/stale/etc. | summary |

The table includes an explicit subject-type column/icon so the pair is never
misrepresented as raw. Expanding a radio row shows its two path pipelines.
Expanding the paired row shows both radio reports and all four synchronized
receiver lanes.

Single-radio and partial topologies render honestly rather than manufacturing a
paired row.

### 14.2 CLI

Extend the existing commands:

```console
leo process search --pipeline-state stale --limit 25
leo process show SESSION_ID --subjects --json
leo process plan SESSION_ID --release FULL_STAGED_GIT_SHA --json
leo process reprocess SESSION_ID --release FULL_STAGED_GIT_SHA --dry-run --json
leo process reprocess SESSION_ID --release FULL_STAGED_GIT_SHA --wait --json
leo process stale --release FULL_STAGED_GIT_SHA --json
```

Dry-run shows:

- four path, two radio and one paired subjects when applicable;
- exact jobs and dependency edges;
- cache hits/misses and recomputation frontier;
- selected release/configuration;
- full pinned raw-integrity attestation, availability and calibration
  requirements;
- estimated resource class, not an invented runtime promise; and
- stable refusal reasons.

Mutating operations stay CLI-only. The browser remains read-only.

### 14.3 API and browser

Add bounded list/detail projections, not raw ORM or scientific documents. List
requests use indexed database state and never open IQ or full artifacts. Detail
loads progressively: shell, subject summaries, then selected plot data.

The browser must display pipeline version, current/stale reason, computed versus
reused products, runtime, coverage, calibration, timing uncertainty and
candidate-only limitations.

### Checkpoint K

- Exact three-row hierarchy renders for T1.
- CLI, API and UI agree on subject identity, release, state and stale reason.
- Initial recording list remains fast and filesystem-independent.
- Reanalysis dry-run is truthful and mutation occurs only after confirmation by
  command invocation.
- Browser uses GET/HEAD only.

### Test cases K

- All topology and status combinations.
- Automatic selection suppresses `QUALIFICATION`, `CALIBRATION` and
  `ACCEPTANCE`; reviewed TEST corpus analysis is explicit evidence-only and
  cannot become current ordinary analysis.
- Real PostgreSQL CLI/API/Playwright coverage proves a sealed TEST evidence-only
  result remains discoverable through `--include-test` and the read-only UI
  with an unmistakable TEST/non-current label, while committed IMPORT data
  follows the ordinary automatic/current path.
- Pagination beyond the first page.
- Current, stale, partial, failed, not-run, purged/unavailable and cached rows.
- Human/JSON parity and stable CLI exit codes.
- A stale child causes only the correct radio and paired badges to become stale.
- Corrupt/missing presentation becomes unavailable; no stale fallback.
- Browser labels the numerical lane as `GLRT64 detector response` or
  `candidate redetection`, never as a claimed target detection, attribution or
  payload result.
- Read-only API returns 405 for mutation methods.
- Initial list does zero raw/artifact filesystem reads.

### Verification procedure K

```console
uv run pytest -q tests/cli tests/api
uv run pytest -q -m postgres tests/integration tests/catalog tests/processing
cd web && npm test
cd web && npm run build
cd web && npm run test:e2e:production
```

Also measure the LAN endpoint with timed `curl` and Playwright navigation. Record
median and p95 shell/list/detail times and payload sizes. Plot requests are lazy
and cannot block the initial table.

## 15. Workstream L — golden corpus and scientific evaluation

### 15.1 Corpus policy

Use three tiers:

1. small deterministic synthetic fixtures committed with the repository;
2. small digest-pinned real-IQ TEST excerpts under the protected local corpus;
3. the full 60-second four-path reference as an explicit `real_corpus` test.

The reference source is currently
`production-24h-20260819-01-trial-00000132`, manifest digest
`sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d`.

The repository must not populate `/mnt/qnap01`. If the owner wants an archival
copy beneath `/mnt/qnap01/mouse9911/leo-store/`, that is a separately reviewed
operator action outside application code. Tests run from a materialized local
read-only corpus at `/srv/bulk/leo/test-corpus`, with source and
selected digests verified before publication and permanent TEST holds.

### 15.2 Fixture matrix

| Fixture | Purpose | Permitted claim |
|---|---|---|
| Synthetic four-path pilot bank | Exact epoch/CFO/path isolation/reducer association | numerical truth |
| Synthetic noise/tones/rolled pilots | controls and false-branch behavior | numerical control |
| Synthetic crossing/parallel/intermittent tracks | segmentation/association | numerical truth |
| Synthetic RX dropout/timing-skew matrix | partial and synchronization states | contract truth |
| `retro-positive-68p7` | per-RX acquisition/QAM parity | real candidate regression |
| synchronized 80 ms two-radio excerpt | four-path ingestion/order/timing | unlabeled ingest regression |
| trial-132 full 60 s four-path session | whole-dwell numerical/performance regression | candidate-only exploratory evidence |
| J1 declaration | missing-evidence behavior | explicitly non-executable |

Golden outputs change only through explicit scientific review. Tests do not
rewrite goldens on failure. Scientific numeric goldens and presentation goldens
are stored separately.

### 15.3 Accuracy metrics

Measure:

- epoch and CFO error;
- candidate recall on synthetic injected truth;
- control activation;
- QAM accuracy and EVM;
- segmentation/association error;
- trajectory coefficient, RMS and support error;
- initial-to-corrected GLRT64 gain;
- unmatched/false merge/split counts; and
- path/radio/paired coverage and status.

Thresholds and tolerances are preregistered from synthetic truth or the frozen
baseline before looking at optimized output.

### Checkpoint L

- Required fixtures have immutable manifests, digests, truth tiers, permitted
  claims, oracle revision and tolerances.
- Missing REQUIRED fixtures fail the marked lane; J1 is explicitly unavailable.
- Trial-132 completes four path pipelines and both reducers reproducibly.
- Controls remain controls and do not become claimed negatives or specificity
  evidence.

### Test cases L

- SNR, on/off-grid CFO, epoch, gain imbalance, calibration uncertainty,
  Doppler slope/curvature and intermittent occupancy sweeps.
- Metamorphic chunk-size, RX/radio permutation, repeated execution, worker
  ordering, amplitude scaling, frequency translation and sample-time shift.
- Four-path expected schedule/counts, candidate intervals, family counts and
  fit/replay metrics within frozen tolerances.
- Missing, wrong-digest and unauthorized corpus material.

### Verification procedure L

```console
uv run pytest -q tests -m real_corpus
```

The lane first validates the corpus manifest and every selected byte digest,
then runs numerical tests. It emits a bounded comparison report but never
updates expected results. Any intended golden change requires a reviewed diff
explaining the algorithm change, expected scientific effect and control impact.

## 16. Workstream M — performance and optimization interface

Runtime work is deliberately modular. Each stage exposes a stable benchmark
port and accuracy oracle so independent optimization cannot silently change
science.

Benchmark datasets:

- tiny deterministic CI16 fixture;
- 25,000-sample RETRO candidate;
- 80 ms real four-path synchronized fixture; and
- full 60-second, 2.5 MS/s, four-path reference.

Measure:

- wall and CPU time;
- real-time factor;
- peak RSS and process count;
- bytes read/decompressed/written;
- artifact count/size;
- PostgreSQL queries;
- cache hits/misses;
- queue wait and reducer wait; and
- per-stage and whole-run timing.

Procedure:

1. Record code, config, input, storage, machine and RAID state.
2. Run one warm-up.
3. Run at least five randomized baseline/candidate repetitions.
4. Test one, two and four path workers while enforcing heavy-stage limits.
5. Report fresh-worker and warm application-cache separately.
6. Do not call a run cold-cache unless filesystem cache was actually controlled.
7. Require numerical parity before accepting a speed improvement.

Optimization work packages can independently target:

- compressed radio fan-out;
- pilot scan vectorization;
- bounded process scheduling;
- GLRT kernels;
- trajectory fitting/assignment;
- correction replay;
- artifact encoding/decimation; and
- database/cache lookup.

### Checkpoint M

- Baseline performance receipt is frozen before optimization.
- Each component has a microbenchmark plus scientific parity suite.
- Full four-path execution respects configured CPU/RSS/output bounds.
- A speed change with any unreviewed accuracy change fails.

### Test cases M

- One/two/four workers and nested-pool oversubscription.
- Warm/cold application cache and exact cache invalidation.
- Large maximum candidate/trajectory bounds.
- Cancellation/timeout and worker restart.
- Slow artifact store/database and reducer backpressure.
- Repeatability/noise bands for benchmark measurements.

### Verification procedure M

Produce a versioned benchmark receipt with distributions, not one timing.
Compare it to the frozen baseline using preregistered accuracy equality and
runtime/resource thresholds. Run the full corpus performance lane only when the
host is not performing a RAID rebuild or another known heavy workload.

## 17. Workstream N — rollout, cutover and rollback

### N1. Shadow release

- Register the immutable new release without making it automatic.
- Run it evidence-only on the protected reference corpus and a bounded set of
  existing recordings.
- Compare numerical results, controls, runtime, failures and product lineage.
- Do not collect new radio IQ for this checkpoint.

### N2. Read-only presentation

- Expose new path/radio/paired products behind an explicit release selector.
- Keep the old current recording view available.
- Verify LAN responsiveness and all unavailable/partial states.

### N3. Default cutover

- Stop automatic creation briefly, drain or explicitly cancel/requeue old
  release jobs, deploy release-matched workers, and verify release health.
- Make the exact staged full-SHA release carrying display family
  `standard-glrt64-v2` the sole default ordinary graph.
- Re-enable automatic creation and process a small canary set.
- Never rewrite historical products or release rows.

### N4. Rollback

- Stop new job creation.
- Preserve every new run and artifact for diagnosis.
- Restore the previous default release and matching worker.
- Failed new runs never replace previous current runs, so browser rollback is
  catalog-safe.

### Checkpoint N

- All gates G0–G6 below pass.
- Independent scientific and provenance reviews report no open P0/P1.
- Canary produces complete four-path/radio/paired products with exact release
  identity and bounded resources.
- Rollback drill succeeds without deleting data.

### Test cases N

- Pending old jobs during deployment.
- Worker/release mismatch in both directions.
- Crash during every publication and promotion fence.
- Failed canary, successful retry and rollback.
- Retention pressure while old/new/reused products are referenced.
- Browser/API behavior during running, failed and rollback states.

### Verification procedure N

Run the isolated full vertical first. Then use a bounded existing-data canary,
record exact run/product/release IDs, verify artifacts and dependencies, inspect
CLI/API/UI parity, exercise rollback, and only then change the default release.

## 18. Parallel delivery plan and merge checkpoints

Parallel work begins only after G0 freezes contracts. Each stream owns narrow
ports and component tests; shared catalog/graph/contracts files merge at named
checkpoints rather than being edited concurrently without coordination.

| Stream | Primary responsibility | Starts after | Can run beside |
|---|---|---|---|
| P0 | ADR, scope/status/lineage/cache contracts | immediately | baseline audit |
| P1 | Golden corpus manifests and evaluation harness | G0 | P2–P7 |
| P2 | Capture receiver lineage and migrations | G0 | P3, P4, P5 |
| P3 | Verified one-RX reader and bounded fan-out | G0 | P2, P4, P5 |
| P4 | Cross-scope planner, executor and product ports | G0 | P2, P3, P5 |
| P5 | Receiver scientific kernels/analyzers | G0 contracts | P2–P4, P6 mocks |
| P6 | Radio/paired pure reducers | G0 contracts | P2–P5 using fixtures |
| P7 | Worker release authority and derivation cache | G0; integrates after P4 | P1, P3, P5 |
| P8 | Catalog/API/CLI projections | stable P2/P4/P7 contracts | P9 |
| P9 | Browser interactive views | presentation contracts | P8 with mocks |
| P10 | Performance harness/optimizations | P1 plus relevant component | all component streams |
| P11 | Integration, adversarial review and rollout | each merge checkpoint | continuous |

### Merge checkpoint C0 — contracts

- ADR accepted.
- Canonical scope, expanded-plan, status, lineage, derivation-key and product
  contracts frozen.
- Digest vectors and compatibility tests pass.

### Merge checkpoint C1 — foundation

- Capture lineage migration passes populated PostgreSQL tests.
- Planner emits exact 2×2 graph.
- One-RX reader is pinned and verified.
- Worker rejects release mismatch before input access.

### Merge checkpoint C2 — minimal vertical

- Real ProcessingService executes one minimal receiver product per path, two
  product-only radio reducers and one paired reducer.
- Exact dependencies, retry/idempotence, seal and current-run isolation pass.
- This checkpoint deliberately precedes expensive detector porting.

### Merge checkpoint C3 — complete receiver science

- Waterfall, probe scan, trajectories, feedback and path report pass synthetic,
  RETRO and deterministic tests.
- Four paths can run independently with bounded resources.

### Merge checkpoint C4 — reuse and aggregate science

- Cache invalidation matrix passes.
- Radio/paired reducers pass synthetic and trial-132 tests.
- Exact rerun repeats the mandatory stream-integrity read but performs zero
  eligible scientific analyzer IQ reads.

### Merge checkpoint C5 — operator and browser surfaces

- Three-row hierarchy, version/stale/reuse state and synchronized plots pass.
- CLI dry-run/reanalysis and API/UI parity pass.
- Initial LAN list/detail remains within measured budgets.

### Merge checkpoint C6 — release candidate

- Full real-PG/compressed-store/artifact/browser vertical passes.
- Full real corpus and performance receipts pass.
- Shadow and rollback drills pass.
- Independent review approves default cutover.

## 19. Global release gates

### G0 — architecture and contracts

Typed scopes, exact cross-scope dependency authority, status algebra, complete
lineage, cache policy, candidate-only vocabulary and schema-version policy are
reviewed and frozen.

### G1 — execution foundation

Populated migration, topology compiler, exact release-matched worker, pinned
readers, actual product consumption and retention fences pass. No science/UI
rollout occurs before G1.

### G2 — component science

Pure receiver analyzers and reducers pass negative, numerical, deterministic,
property and resource-limit tests.

### G3 — isolated complete vertical

Real PostgreSQL, compressed RecordingStore, ProcessingService workers,
ArtifactStore, derivation reuse, reducers, run manifest, atomic promotion and
crash/retry all pass for maximum 2×2 topology.

### G4 — scientific regression

Reviewed local real-IQ corpus, synthetic truth, controls, predefined tolerances
and candidate-only interpretation pass. No silent fixture skips or golden
updates.

### G5 — presentation and operator control

Generated contract parity, bounded API, three-row subject UI, synchronized
plots, Playwright, CLI dry-run/reanalysis and confinement tests pass.

### G6 — operational canary

Exact release/graph/environment validation, old-job drain, max-topology
CPU/RSS/disk/backlog benchmark, restart/retry/retention/rollback drills and
independent reviews pass before the release becomes the sole default.

## 20. Final definition of done

The plan is complete only when all of the following are true:

- Every available receiver path independently completes the full Standard
  GLRT64 pipeline with quality, power, waterfall, degree 1/2/3 trajectory
  products and report.
- Every radio report reuses its exact receiver products and performs zero IQ
  reads.
- Every paired report reuses its exact radio products, preserves shared timing
  uncertainty and performs zero IQ reads.
- Exact reruns reuse eligible immutable outputs; one-field changes invalidate
  only the correct downstream closure.
- Every product and table row exposes the immutable pipeline release and
  trustworthy current/stale reason.
- A dual-radio recording renders exactly the requested paired, Radio0 and
  Radio1 top-level rows, with receiver paths available below them.
- Interactive plots and export PNGs cover the full aligned time domain and
  reconstruct from authoritative numerical products.
- CLI can list, plan, dry-run, reprocess, wait, show and find stale analyses.
- The production worker cannot execute under false release provenance.
- The protected corpus, full four-path regression, accuracy gates, performance
  gates, real-PG vertical, Playwright suite, cutover canary and rollback drill
  all pass.
- No new long radio campaign is required to deliver or validate this software.

The existing `standard_pipeline.md` remains the working scientific record and
command history. This document is the implementation and verification plan.
When implementation begins, completed checkpoints should be marked with commit,
test receipt and reviewer links rather than rewriting their acceptance criteria.
