# LEO Tracker ReduxRedux: Architecture and Execution Plan

Status: authoritative implementation plan; all implementation requirements are initially `PENDING`.

This document records the decisions agreed for the fresh implementation in this repository. It is the contract for architecture, module ownership, delivery order, and acceptance. The older `leo-tracker`, `leo-tracker-redux`, `pluto-plus-utils`, their reports, and the attached long-dwell analysis documents are evidence and scientific references, not implementation instructions and not compatibility requirements.

## 1. Mission and scope

Build a lean platform that can:

- acquire CI16 IQ continuously or at configurable duty cycles from one or two remote Pluto+ radios over Ethernet;
- use one or both receive channels on each Pluto+;
- make an honest best effort to overlap captures from two radios without claiming hardware or phase synchronization;
- durably store self-describing, compressed, immutable raw IQ recordings on the local RAID;
- process new recordings and explicitly reprocess existing recordings with the current analysis pipeline;
- restore the previously demonstrated Starlink/Qin/QAM detection capability before extending it;
- support whole-dwell survey, candidate tracking, Doppler, locked acquisition, QAM evidence, controls, and later research stages;
- expose equivalent search, provenance, paths, power, Starlink, QAM, Doppler, and health information through a CLI and read-only web UI;
- protect selected recordings indefinitely and automatically reclaim unprotected data under storage pressure;
- continuously validate the system against a small protected corpus of real and controlled TEST recordings.

The expected maximum acquisition topology is two Pluto+ radios, with two RX channels per radio. Sample rate and dwell duration are research variables, not hard-coded constants. The initial operating point is expected to be near 2.5 MS/s, with duty cycles ranging from roughly 10% to 100%.

### Explicit non-goals for the initial system

- No phase-coherent or sample-coherent claim between separate Pluto+ radios.
- No acquisition or reprocessing controls in the web UI.
- No authentication, authorization, or TLS; the UI is open HTTP on the trusted LAN.
- No Redis, Celery, Kafka, Kubernetes, network object-store service, or NFS control plane.
- No API, database-schema, or file-layout compatibility with either older tracker repository.
- No automatic historical back-processing caused by a schema or software release.
- No deletion from `/mnt/qnap01`; the new project must contain no QNAP deletion path.
- No attempt to put raw IQ or large numerical artifacts inside PostgreSQL.

## 2. Authoritative system shape

```text
1-2 Ethernet Pluto+ radios
          |
          v
 acquisition coordinator + per-radio workers
          |
          v
 immutable recording bundle on /srv/bulk
          |                         \
          v                          v
 PostgreSQL catalog/jobs       retention controller
          |
          v
 processing workers -> immutable scientific products
          |                         |
          v                         v
 presentation projectors -> stable presentation products
          |
          v
 read-only FastAPI -> React web UI
          ^
          |
 acquisition and processing CLI
```

There are four long-running responsibilities:

1. Acquisition owns radios and publishes recording bundles.
2. Processing workers execute leased, versioned analysis jobs.
3. The read-only API serves current catalog and presentation data.
4. PostgreSQL is the catalog, job control plane, and current-analysis selector.

Retention runs from a systemd timer. Acquisition must not depend on analysis keeping up; a processing backlog is acceptable and visible.

## 3. System invariants

These rules may not be relaxed without an explicit architecture decision record.

1. **Raw IQ is immutable.** A committed recording is never edited in place.
2. **A recording is self-describing.** Its manifest and stream metadata are sufficient to reconstruct the catalog without PostgreSQL.
3. **Partial output is not committed output.** A missing final manifest or incomplete atomic publication cannot appear as a usable recording or analysis run.
4. **One session is the acquisition unit.** A synchronized two-radio attempt is retained or purged as one session, even when one stream fails.
5. **Timing claims are evidence-based.** Store requested and observed times, timing source, skew, overlap, gaps, and uncertainty; never infer coherence from a software barrier.
6. **Database and filesystem have separate roles.** PostgreSQL holds searchable state and pointers; `/srv/bulk` holds IQ and large artifacts.
7. **Analysis runs are immutable.** Reprocessing creates a new run and never modifies the current run in place.
8. **Promotion is atomic.** The UI sees either the previous complete run or the replacement complete run, never a mixture.
9. **Analyzer code is infrastructure-blind.** Analyzers do not construct paths, query PostgreSQL, or serve HTTP.
10. **Scientific and UI schemas are separate.** Frequently changing scientific products are converted by projectors into bounded, versioned presentation contracts.
11. **No silent test skips.** A required fixture that is absent or corrupt fails its declared test lane clearly.
12. **TEST is first-class provenance.** TEST recordings are obvious, permanently held by default, and excluded from normal aggregates unless explicitly included.
13. **Holds beat retention.** A held recording and its required current products are never automatically deleted.
14. **QNAP is read-only evidence.** Copying from QNAP is explicit; source files remain untouched.
15. **Migrations do not imply analysis.** Database evolution never silently queues old recordings.
16. **No-result is a scientific result.** `no_candidate`, `partial_coverage`, and `insufficient_data` are not confused with worker failure.

## 4. Repository and module boundaries

The target implementation is a Python monorepo with a TypeScript browser application compiled to static assets. A concrete module layout is:

```text
src/leo/
  domain/          IDs, value types, state machines, shared contracts
  config/          host config and immutable capture-profile loading
  catalog/         SQLAlchemy models, Alembic integration, repositories
  storage/         recording/artifact stores, manifests, IqReader
  acquisition/     Pluto transport adapters, coordinator, radio workers
  pipeline/        analyzer SDK, DAG, leases, executor, promotion
  analysis/
    quality/
    power/
    waterfall/
    starlink/
    qam/
    doppler/
    controls/
  presentation/    version-specific scientific-to-UI projectors
  api/             read-only HTTP routes and response contracts
  cli/             acquire and process command groups
  operations/      retention, reconciliation, health, maintenance
web/               React + TypeScript + Vite application
tests/
  unit/
  contract/
  integration/
  dsp/
  e2e/
  hardware/
```

### Required interfaces

`CatalogRepository` owns catalog transactions and exposes operations such as:

- create/finalize a capture session;
- create an analysis run and its job DAG;
- claim, heartbeat, complete, fail, and reclaim a job lease;
- register an immutable product idempotently;
- seal and atomically promote an analysis run;
- search sessions and resolve the current run;
- create/remove retention holds and record retention events.

`RecordingStore` owns recording layout, durable publication, validation, and reconstruction.

`ArtifactStore` owns logical artifact URIs, temporary output, hashing, `fsync`, atomic publication, validation, and garbage-collection eligibility.

`IqReader` exposes receiver-aware sample slices and streaming block iteration with exact sample/time mapping across compressed shards.

`Analyzer` receives `AnalysisContext`, `IqReader`, `ProductReader`, and `OutputSink`, and returns a typed `StageResult`.

`PresentationProjector` consumes declared scientific product versions and emits a declared presentation schema version.

`RadioTransport` isolates network/device-specific operations so acquisition coordination can be tested without hardware. Proven serial-attested Ethernet transport, paired-RX capture, continuity metadata, health checks, constant-IQ checks, and exclusive ownership concepts from `pluto-plus-utils` should be adapted behind this boundary.

The initial analyzer registry is explicit and in-repository. Dynamic third-party plugin discovery is deferred until there is a real need.

## 5. Acquisition design

### 5.1 Domain model

The primary entity is `capture_session`.

A session contains one or two `radio_stream` records. A radio stream contains one or two enabled receiver paths. RX0 and RX1 from the same Pluto+ are paired because they are returned by the same device refill. Separate Pluto+ radios are not assumed to share clocks.

A session supports:

- one Pluto+, one enabled RX;
- one Pluto+, paired RX0/RX1;
- two Pluto+ radios, with one or two RX paths each;
- best-effort synchronized mode;
- a partial session in which one radio fails and the surviving radio completes;
- imported legacy and TEST recordings.

### 5.2 Capture profiles

Replace the former “arms” concept with immutable, revisioned `capture_profile` definitions.

Human-edited YAML defines a profile. The first use creates an immutable database revision and digest. Editing a named profile creates a new revision; old sessions continue to cite the exact revision used.

Profile fields include:

- dwell duration;
- sample rate;
- RF bandwidth;
- RF/IF center and Starlink edge/channel intent;
- enabled receivers;
- gain mode and gain values;
- buffer/refill size;
- continuity policy;
- radio settle/prime behavior;
- synchronization mode;
- chunk/compression policy reference;
- campaign name and default tags.

Operators may select a profile or apply recorded one-shot overrides without editing code. All effective values and their digest are captured in the session manifest.

### 5.3 Best-effort two-radio synchronization

Synchronized mode means maximizing actual time overlap. It does not mean hardware triggering, common-clock timing, phase coherence, or exact sample alignment.

The coordinator must:

1. Discover, connect, serial-attest, and exclusively lock both radios concurrently.
2. Apply the same session intent and the correct per-radio settings.
3. Settle and prime both devices.
4. Have each radio worker report ready.
5. Release both workers against one near-future host UTC target.
6. Record independent observed first-sample and end-time evidence from each stream.
7. Calculate start skew, exact overlap interval, overlap duration, overlap fraction, and timing uncertainty.
8. Continue a surviving stream when its peer fails, while marking the session partial.

The manifest records the timing method for every value, for example device/FPGA metadata, host monotonic/UTC bracketing, or inferred sample count. The UI and CLI must display the observed overlap and an honest synchronization grade.

### 5.4 Acquisition reliability

- One bounded capture pipeline per radio separates device refill from compression/disk writing.
- Bounded queues apply an explicit failure/backpressure policy; data loss is never hidden.
- Every refill contributes continuity, sequence, sample-count, and timing evidence.
- Constant-IQ, clipping, gap, late-refill, and device-error evidence is recorded.
- Acquisition runs at normal CPU/I/O priority; analysis runs at lower weights.
- Consecutive dwell operation records the actual inter-session gap and never assumes 100% duty was achieved.
- Losing PostgreSQL after durable bundle publication must not lose the recording; a reconciler registers it later.

## 6. Recording storage

### 6.1 Storage topology

The canonical live root is the local cached RAID:

```text
/srv/bulk/leo/
  spool/
  recordings/YYYY/MM/DD/<session-id>/
  analysis/<session-id>/<analysis-run-id>/
  test-corpus/
  postgres/
  backups/
```

`/mnt/qnap01` is a legacy-import and evidence source only. It is not the live recording store, queue, lock service, or backup target. Local RAID is sufficient for the initial durability requirement.

### 6.2 Bundle layout

```text
recordings/YYYY/MM/DD/<session-id>/
  manifest.json
  radio-<serial>/
    iq-000000.ci16.zst
    iq-000001.ci16.zst
    timeline.jsonl.zst
```

Initial IQ encoding:

- signed little-endian CI16;
- logical layout `(sample, receiver, component)`;
- receiver order declared in the manifest;
- independently compressed Zstandard shards;
- approximately 128 MiB uncompressed per shard, aligned to complete refills;
- sample start/count plus compressed and uncompressed SHA-256 for every shard.

Zstandard level 3 is the initial default, subject to an on-host throughput/ratio qualification. It is configuration, not a scientific profile attribute. Independent shards support bounded-memory reading, random access, corruption isolation, and parallel processing.

### 6.3 Thin and detailed metadata

`manifest.json` is the small reconstruction and discovery record. It includes:

- session ID, source type, tags, and profile revision/digest;
- software release and host identity;
- radio serials, endpoint identity, firmware/hardware epoch, and receiver mapping;
- complete effective RF, sample, bandwidth, gain, buffer, and compression settings;
- requested and observed start/end times and the evidence/uncertainty for each;
- sample counts, encoding/layout, continuity summary, and stream terminal state;
- paired-radio relationship, skew, overlap interval/fraction, and synchronization grade;
- calibration references and digests;
- full chunk inventory, sizes, sample ranges, and hashes.

Detailed refill-level timing and continuity evidence lives in compressed `timeline.jsonl.zst`.

### 6.4 Crash-safe publication

1. Capture into `spool/<session-id>.partial`.
2. Publish each completed shard durably and append durable continuity metadata.
3. Close and verify stream inventories.
4. Write the session manifest last.
5. `fsync` files and directories.
6. Atomically rename the session into its dated recording path.
7. Register/finalize the session in PostgreSQL.

A crash after step 6 but before step 7 is repaired by catalog reconciliation. A partial spool directory is never analyzed as a committed recording. Recovery tooling may validate and explicitly finalize a provably complete partial bundle; ambiguous partial data is quarantined and reported, not silently accepted or deleted.

## 7. PostgreSQL catalog and migrations

Use PostgreSQL 18, SQLAlchemy 2, Psycopg 3, and Alembic. Tests use real PostgreSQL, never SQLite as a behavioral substitute.

### 7.1 Stable relational schema

Initial stable tables:

- `radio`
- `receiver_path`
- `hardware_epoch`
- `frequency_calibration`
- `capture_profile`
- `capture_profile_revision`
- `capture_session`
- `radio_stream`
- `recording_chunk`
- `tag`
- `session_tag`
- `retention_hold`
- `retention_event`
- `pipeline_release`
- `analysis_run`
- `processing_job`
- `processing_job_dependency`
- `processing_job_attempt`
- `analysis_product`
- `product_dependency`
- `current_analysis`
- `analysis_summary`

Large waterfalls, IQ, tracks, and arrays are paths plus hashes in the catalog, not database blobs.

Algorithm-specific detail initially belongs in versioned artifact schemas and bounded JSONB summaries. Only metrics proven useful for cross-recording search are promoted to indexed relational columns through reviewed migrations.

### 7.2 Migration policy

- Maintain one linear Alembic head initially.
- Never edit an applied migration.
- Every migration is reviewed with generated SQL.
- CI runs `alembic check` for ORM/schema drift.
- CI upgrades both an empty database and the previous released schema snapshot.
- Destructive or type-changing migrations use an explicit expand/migrate/contract sequence when needed.
- Product schema evolution is independent from relational migration.
- Old recordings and old product metadata remain readable after migration.
- Migrations never enqueue reprocessing implicitly.

## 8. Processing control plane

PostgreSQL is the only processing queue. A `processing_job` is leased using a short transaction and `FOR UPDATE SKIP LOCKED`.

Job states are `pending`, `leased`, `succeeded`, `failed`, and `cancelled`. Each logical job is unique on `(run_id, stage_key, scope_key)`. Attempts are immutable records. Leases use database time, have an owner and expiry, and are extended by heartbeat. An expired lease is safely reclaimable. Execution is at-least-once, so product publication and completion are idempotent.

The DAG stores explicit dependencies. A job is claimable only when all required dependencies have successful terminal scientific outcomes. Downstream behavior for `no_candidate`, `partial_coverage`, and `insufficient_data` is declared by the graph rather than embedded in worker code.

Start with four lower-priority processing workers and tune using observed CPU, RAM, disk, and backlog measurements. Resource classes prevent too many heavy waterfall or dense-acquisition stages from running together.

## 9. Analysis products and artifact storage

### 9.1 Run layout

```text
/srv/bulk/leo/analysis/<session-id>/<run-id>/
  scientific/
    quality/...
    power/...
    waterfall/...
    starlink-survey/...
    candidate-tracks/...
    qam/...
    doppler/...
    controls/...
  presentation/
    summary/...
    timelines/...
    waterfall/...
    overlays/...
  manifest.json
```

PostgreSQL stores logical URIs such as `bulk://analysis/<session>/<run>/...`; configuration resolves them to `/srv/bulk/leo`. The resolved path is available to CLI/UI users.

### 9.2 Scientific products

Scientific products preserve analysis evidence at useful precision and may evolve frequently. Initial approved encodings are:

- JSON or JSON.zst for small structured evidence;
- Parquet for candidate tables, tracks, and long time series;
- a documented, versioned tiled numeric encoding for large matrices.

Every `analysis_product` and run manifest records:

- product kind, role, semantic schema version, and media type;
- producing stage/algorithm/configuration digest;
- exact recording and input-product digests;
- receiver, segment, time/frequency scope, units, and coverage;
- semantic status such as `complete`, `partial_coverage`, `no_candidate`, or `insufficient_data`;
- logical URI, byte size, and SHA-256.

### 9.3 Presentation products

The UI does not read arbitrary scientific files. Version-specific projectors emit a stable, bounded presentation contract containing:

- recording/run summary;
- downsampled power and quality timelines;
- bounded waterfall tile pyramid and index;
- candidate, CFO, and Doppler overlays;
- QAM/pilot display evidence;
- coverage, units, provenance, and failure/no-result states.

Presentation schema and HTTP API versions evolve deliberately. A scientific product change normally requires a projector update, not a browser rewrite or relational migration.

### 9.4 Product and run publication

Each product is written beneath the analysis spool, hashed, flushed, `fsync`ed, and atomically moved to its final path before idempotent catalog registration. The run manifest is written last after required products reach accepted terminal states. Once sealed, the directory is immutable.

The UI only reads a sealed run selected by `current_analysis`. Failed/incomplete run output remains non-current and is eventually cleaned under an explicit failed-run policy.

## 10. Analyzer contract and pipeline graph

Conceptual analyzer interface:

```python
class Analyzer:
    spec: StageSpec

    def run(
        self,
        context: AnalysisContext,
        iq: IqReader,
        inputs: ProductReader,
        outputs: OutputSink,
    ) -> StageResult: ...
```

`StageSpec` declares:

- stage and algorithm versions;
- accepted input product kinds/schema versions;
- output product kinds/schema versions;
- validated configuration schema;
- CPU, RAM, and I/O resource class;
- deterministic/non-deterministic behavior;
- retry and accepted terminal-outcome policy.

Analyzers are independently unit-testable with fake readers, product inputs, and sinks. `OutputSink` alone owns temporary paths, hashes, publication, and registration.

## 11. Reprocessing semantics

`leo process reprocess SESSION_ID` means “replace the UI/CLI-visible analysis with a newly completed run of the current pipeline,” not “mutate or delete the former run before work begins.”

1. Validate that raw IQ, manifest, and required calibration inputs exist.
2. Create a new `analysis_run` and complete versioned job DAG.
3. Process into a new run directory while the former current run remains readable.
4. Verify accepted terminal state and required scientific/presentation products.
5. Seal the run manifest.
6. In one transaction, mark success, switch `current_analysis`, and update the indexed `analysis_summary`.
7. Make large superseded artifacts eligible for later garbage collection while retaining their small receipts and provenance.

Initially allow only one active run per session. A second request fails clearly rather than creating ambiguous promotion order. Failed reprocessing never changes the current pointer. An API request resolves one current run ID at its start so it cannot mix product generations.

## 12. Scientific recovery and long-dwell analysis

Parity with demonstrated historical results is the first scientific milestone. Do not redesign the detector until the numerical primitives are recovered and protected by tests.

Port and freeze behind analyzer boundaries:

- Qin waveform/template generation;
- historical symbolwise acquisition;
- multiple timing/alias candidate retention;
- receiver-centered calibrated CFO search;
- conditioned fine-CFO refinement;
- pilot constellation and QAM metrics;
- inverse-noise dual-receiver combination.

The frequency contract is:

```text
absolute CFO = immutable receiver calibration center + searched residual CFO
```

Never return to a universal absolute `+/-400 kHz` acquisition box. Calibration and immutable receiver center are explicit inputs and provenance.

The production graph is one semantic graph with different budgets, not unrelated Quick/Standard/Research implementations:

```text
raw validation
  -> clipping, constant-IQ, continuity, and quality
  -> power timeline
  -> bounded waterfall
  -> calibrated sparse whole-dwell survey
  -> multiple acquisition basins
  -> activity-region and continuity tracking
  -> dense epoch/CFO refinement
  -> de-Doppler and locked integration
  -> pilot/QAM evidence
  -> held-out/null/surrogate controls
  -> optional TLE association
  -> scientific summary
  -> presentation projectors
```

- **Quick:** every recording; quality, power, bounded waterfall, sparse whole-dwell survey, bounded candidate cloud.
- **Standard:** normal full processing; tracking, dense acquisition, Doppler, controls, and QAM.
- **Research:** explicit/manual policy; wider searches, alternate models, more surrogates, and long integrations.

Compute tier and scientific confidence are distinct. Research output is not automatically a detection. Candidate lineage, search coverage, calibration, controls, and reasons for rejection/promotion must be retained.

## 13. Retention and deletion

Measure the filesystem containing `/srv/bulk/leo`, not the root filesystem.

- At 70% used, begin automatic reclamation.
- Reclaim until usage falls to 65%.
- At 75%, emit a prominent operational warning.
- At 80%, stop admitting new captures if no eligible data can be removed.

Reclamation order:

1. Expired failed-run spool and unreferenced temporary artifacts.
2. Eligible large superseded analysis artifacts.
3. Oldest eligible unheld capture sessions, deleting raw IQ and replaceable large current scientific artifacts while retaining a small tombstone, searchable summary, manifest identity, hashes, timing, and paths.

A session is eligible only if it is fully committed, unheld, not TEST, has no active processing/reconciliation claim, is not already purging, and satisfies the configured minimum analysis policy. A paired session is purged as a unit.

`retention_hold` is indefinite until explicitly removed. A hold protects raw IQ, manifest, and required current analysis/presentation products. TEST imports receive a hold automatically. Superseded experimental artifacts of a held recording may still be collected once they are not current or explicitly held.

Deletion is serialized and auditable:

1. Select and lock exact catalog targets.
2. Mark the session/artifacts `purging` transactionally.
3. Recheck holds and resolved paths.
4. Delete only under the configured `/srv/bulk/leo` root.
5. Record bytes reclaimed and tombstone state.

No code path may delete from `/mnt/qnap01`. Any future source deletion feature requires a separate design and explicit user authorization.

## 14. CLI and web UI

Use one `leo` executable with two top-level operational areas.

### 14.1 Acquisition CLI

```text
leo acquire radios
leo acquire doctor
leo acquire profiles
leo acquire once --profile NAME
leo acquire run --profile NAME
leo acquire status
```

### 14.2 Processing/data CLI

```text
leo process search [filters]
leo process show SESSION_ID
leo process paths SESSION_ID
leo process reprocess SESSION_ID
leo process jobs
leo process pin SESSION_ID --reason TEXT
leo process unpin SESSION_ID
leo process import-qnap MANIFEST --copy --tag TEST
leo process retention-status
leo process retention-run --dry-run
```

All commands have concise human-readable output and `--json`. Search supports time, radio, receiver, profile, source type, TEST, tag, hold, processing state, pipeline release, power, candidate, QAM, Doppler, coverage, and storage state where meaningful.

### 14.3 Read-only API and browser

FastAPI serves React/Vite static assets and GET/HEAD API routes. Initial route families are:

- health, storage use, and processing backlog;
- recording/session search;
- recording detail and resolved paths;
- current analysis and provenance;
- bounded presentation products and tiles;
- aggregate power, Starlink, QAM, and Doppler statistics.

There are no HTTP mutation routes for acquisition, reprocessing, pinning, retention, or deletion. The LAN service is open HTTP without authentication as explicitly required.

The browser must show:

- clear TEST and held badges;
- recording/profile/radio metadata and exact paths;
- actual cross-radio skew, overlap, uncertainty, and partial-stream state;
- quality and power timelines;
- synchronized receiver waterfalls and detector overlays;
- candidate lineage, CFO/epoch tracks, QAM, Doppler, and optional TLE evidence;
- pipeline/product versions, coverage, controls, no-result/failure states;
- storage pressure, purge state, and job backlog.

## 15. Regression corpus and test lanes

Create a small immutable corpus under `/srv/bulk/leo/test-corpus`. Copying from QNAP is allowed; deleting or moving the QNAP source is not.

Initial fixture categories:

1. RETRO known-pilot candidate and selected short window.
2. Recovered J1 calibrated candidate; absence is explicit and cannot silently skip the parity lane.
3. One small synchronized QNAP pair for layout/import/UI validation, labeled `unlabeled` rather than detector truth.
4. Deterministic injected positive over frozen real noise.
5. Deterministic null and stationary-interferer/confounder controls.

Every fixture records an immutable fixture ID, source/digest/license/provenance, expected role, expected metrics/tolerances, `source_type=TEST`, tag `TEST`, and an automatic indefinite hold. TEST data is visible in UI/CLI but excluded from ordinary aggregates by default.

Test lanes:

- **Every change:** unit, property, schema-contract, migration, small selected real-IQ windows, API contract, and focused browser tests.
- **Main branch:** complete small TEST-corpus ingestion through PostgreSQL, workers, CLI, API, and Chromium.
- **Nightly/release:** full 60-second real-data reprocessing, detector parity, long-dwell controls, resource bounds, and full browser flow.
- **Hardware canary:** scheduled single- and dual-Pluto captures; separate from deterministic CI.

Playwright runs real Chromium and retains traces/screenshots on failure.

## 16. Deployment

Use systemd directly on the dedicated host:

- `leo-acquisition.service`
- `leo-worker@.service`
- `leo-api.service`
- `leo-retention.timer`
- PostgreSQL 18
- nightly corpus/release qualification timer

Acquisition has normal CPU/I/O priority. Analysis workers have lower CPU/I/O weight so a backlog cannot interfere with recording. Services expose structured logs and health state keyed by session, run, job, radio, and worker IDs.

Back up PostgreSQL metadata and configuration locally. Raw data durability is the local RAID plus integrity manifests; no second raw copy is required initially.

## 17. Parallel execution program

Status values are `PENDING`, `IN PROGRESS`, `BLOCKED`, and `DONE`. All work packages begin `PENDING`.

### Dependency graph

```text
WP0 contracts/scaffold
  |--- WP1 catalog/migrations/jobs ---------|
  |--- WP2 storage/readers -----------------|
  |--- WP3 Pluto acquisition ---------------|--> WP8 integrated operations
  |--- WP4 analyzer SDK/executor -----------|
  |--- WP5 corpus + detector parity --------|--> WP9 long-dwell science
  |--- WP6 presentation/API/web ------------|
  `--- WP7 retention/reconciliation --------|

WP8 + WP9 -> WP10 qualification and production gate
```

WP1-WP7 may proceed in parallel after WP0 freezes the shared identifiers, manifests, state machines, and interfaces. Implementations use fakes until their dependencies land. Package ownership must keep work in separate module trees; cross-package changes require contract review.

### WP0 — Contracts and repository scaffold (`DONE`)

Deliver:

- Python/TypeScript project skeleton and developer commands;
- architecture decision records for IDs, state machines, timing, schemas, and logical URIs;
- Pydantic/JSON Schema contracts for recording and run manifests;
- shared enumerations and error semantics;
- fake catalog, radio transport, IQ reader, product reader, and output sink;
- lint, type-check, unit-test, and real-PostgreSQL CI foundations.

Exit gate: contracts round-trip in Python and TypeScript, state transitions reject illegal moves, and downstream packages can build against fakes.

### WP1 — Catalog, migrations, and PostgreSQL jobs (`DONE`)

Deliver:

- stable schema and initial Alembic migration;
- repository layer with explicit transactions;
- job DAG, leases, heartbeats, retries, attempt history, and cancellation;
- run sealing/promotion and current summary transaction;
- search and hold primitives.

Exit gate: migration, concurrency, lease-expiry, idempotency, dependency, and atomic-promotion tests pass against PostgreSQL 18.

### WP2 — Recording/artifact storage and readers (`DONE`)

Deliver:

- recording and artifact stores;
- Zstandard shard writer/reader and receiver-aware `IqReader`;
- durable atomic publication;
- logical URI resolver;
- checksum validation, manifests, reconciliation, and quarantine support;
- generated-data fault-injection harness.

Exit gate: kill-point tests expose no partial committed object, random reads across shard boundaries are exact, corrupt data is detected, and catalog reconstruction works from manifests.

### WP3 — Pluto acquisition (`DONE`)

Deliver:

- adapted Ethernet/serial-attested Pluto transport;
- radio discovery, exclusive ownership, doctor/health, and settings application;
- one-radio paired-RX capture;
- bounded streaming compression/writing;
- two-radio readiness barrier and target release;
- actual timing/overlap/continuity accounting and partial-session behavior;
- profile-driven `once` and continuous operation.

Exit gate: generated transport tests plus hardware canaries prove correct settings/provenance, paired layout, honest overlap, peer-failure survival, and clean recovery from process/device/network failure.

### WP4 — Analyzer SDK and processing executor (`DONE`)

Deliver:

- analyzer/stage/product contracts and explicit registry;
- validated pipeline DAG and release digest;
- worker lease loop and resource-class scheduling;
- product output sink and run sealer;
- reprocess CLI and atomic current-run switch.

Exit gate: fake-analyzer integration proves retry safety, semantic no-result handling, immutable outputs, failed-run isolation, and atomic replacement.

### WP5 — TEST corpus and detector parity (`IN PROGRESS`)

Deliver:

- protected fixture registry/importer;
- RETRO and J1 fixture resolution with immutable hashes;
- deterministic positive/null/confounder fixtures;
- Qin, historical acquisition, calibration, fine-CFO, QAM, and receiver-combination ports;
- numerical oracle tests with documented tolerances.

Exit gate: historical results are reproduced within tolerance, null/control behavior is bounded, and a missing required fixture fails explicitly.

### WP6 — Presentation, read-only API, and web UI (`DONE`)

Deliver:

- presentation schema v1 and projectors;
- read-only FastAPI routes and OpenAPI contract;
- React search, session detail, visualization, provenance, health, and storage views;
- conspicuous TEST/held/partial/no-result/failure states;
- Playwright fixtures, traces, and full browser flows.

Exit gate: synthetic and real TEST presentations pass schema contracts and Chromium E2E without HTTP mutation routes.

### WP7 — Retention, reconciliation, and operations (`DONE`)

Deliver:

- 70%/65% watermark controller, 75% warning, and 80% admission stop;
- hold-aware, session-unit deletion and tombstones;
- failed/superseded artifact GC;
- bundle/run/catalog reconcilers;
- dry-run/status CLI and auditable events;
- systemd definitions and operational health.

Exit gate: destructive tests on generated isolated data prove exact target resolution, pinned/TEST/current immunity, paired-session atomicity, threshold behavior, and no possible QNAP target.

### WP8 — Integrated acquisition-to-UI vertical slice (`DONE`)

Deliver:

- one real/simulated capture through bundle, registration, jobs, baseline analysis, projection, CLI, API, and browser;
- reprocessing current-run replacement;
- service restart and backlog recovery.

Exit gate: a fresh TEST capture is discoverable with correct paths/metrics in CLI and Chromium; successful and failed reprocessing exhibit the required pointer semantics.

### WP9 — Whole-dwell Standard/Research pipeline (`DONE`)

Deliver:

- sparse survey, multi-basin candidate cloud, continuity tracking, dense refinement, de-Doppler, locked integration, controls, QAM, optional TLE association, and presentation overlays;
- Quick/Standard/Research budget configurations for one graph;
- bounded-memory and coverage accounting.

Exit gate: full dwell fixtures preserve the correct basin, reproduce parity evidence, reject/qualify controls honestly, and remain inside measured resource budgets.

### WP10 — Qualification and production gate (`IN PROGRESS`)

Deliver:

- 24-hour acquisition soak;
- storage-pressure and fault-recovery campaign;
- full nightly/release corpus and Chromium run;
- operator runbook and measured capacity/worker tuning;
- final requirement traceability review.

Exit gate: every mandatory requirement below is `DONE`, no critical fault loses a committed held recording, and production acceptance gates pass.

## 18. Exact acceptance gates

### 18.1 Database and migration gate

- One Alembic head and no ORM/schema drift.
- Empty-to-head and previous-release-to-head upgrades pass.
- Eight concurrent test workers never hold the same live job lease.
- Expired leases are reclaimed without duplicate logical products.
- Job attempts and failures remain inspectable.
- Old catalog rows and product metadata remain readable after migration.

### 18.2 Recording and storage gate

- CI16 round-trip is bit-exact for one/two RX and one/two radio sessions.
- Arbitrary reads crossing compressed shard boundaries return exact samples.
- Truncation, digest mismatch, bad layout, and continuity gaps are surfaced.
- Fault injection at every publication step exposes no partial bundle/product as committed.
- A bundle committed before a database outage is registered by reconciliation.
- A reconstructed catalog retains radio, profile, timing, pairing, calibration, and hash provenance.

### 18.3 Synchronization/acquisition gate

- Same-Pluto RX paths have identical declared sample counts/layout and pairing evidence.
- Dual-radio readiness and target release are exercised repeatedly on hardware.
- Requested start, actual start/end, skew, overlap, fraction, timing method, and uncertainty are persisted and displayed.
- Peer connection/device failure leaves a truthful partial session and does not discard the successful stream.
- Device/network/process faults do not create a falsely complete session.
- A 24-hour scheduled acquisition soak has no unexplained sample loss or unbounded memory/disk queue.

### 18.4 Processing/reprocessing gate

- Analyzers pass unit tests without filesystem or PostgreSQL access.
- Worker kill/lease expiry does not create duplicate visible products.
- Memory use is bounded with dwell length through streaming interfaces.
- `no_candidate` and partial coverage follow declared graph policy.
- Failed reprocessing leaves the former current run and UI unchanged.
- Successful reprocessing atomically switches summary and every visible product to one new run ID.
- Concurrent API reads observe only complete generations.

### 18.5 Detector and scientific gate

- Qin/template primitives match frozen numerical oracles.
- RETRO candidate epoch, CFO, pilot/QAM metrics, and candidate rank meet documented tolerances.
- Recovered J1 requires and uses receiver calibration, meeting documented tolerances.
- The whole-dwell search retains multiple basins and finds the known basin even when it is not the first coarse rank.
- Injected positive, null, stationary-interferer, corrupted-input, and held-out control cases produce their documented outcomes.
- Candidate claims include search coverage, calibration, lineage, controls, and confidence distinct from compute tier.

### 18.6 Retention gate

- At 70% synthetic utilization, reclamation starts and stops at or below 65%.
- 75% warning and 80% admission-stop behavior are deterministic.
- Held and TEST sessions survive every automatic retention test.
- Active jobs, current protected products, and paired session members cannot be orphaned.
- Tombstones and searchable summaries survive raw/large-artifact purge.
- All destructive tests operate on generated isolated data and prove path confinement below `/srv/bulk/leo`.
- No QNAP deletion API, command, or resolver exists.

### 18.7 CLI/API/browser gate

- CLI human and `--json` views agree on identity and values.
- CLI and HTTP expose the same current run, paths, profile, power, Starlink, QAM, Doppler, coverage, TEST, and hold state.
- HTTP exposes GET/HEAD only for project routes and cannot acquire, reprocess, pin, purge, or delete.
- Playwright verifies search, TEST filtering/badges, session detail, overlap, paths, power, waterfall, overlays, provenance, partial/failure/no-result states, and post-reprocessing replacement.
- Main-branch E2E ingests through the real catalog/workers; it is not a static mock-only demonstration.

### 18.8 Production gate

- All preceding gates pass.
- A 24-hour acquisition soak and a full 60-second detector corpus run pass on the target host.
- Capture remains healthy with a deliberately induced processing backlog.
- Service restarts recover committed bundles, expired jobs, and current-run state.
- Storage and worker capacity measurements are recorded and operational thresholds are configured from those measurements.

## 19. Requirement checklist

Every row is initially `PENDING`. A row becomes `DONE` only when its referenced acceptance evidence is committed and reproducible.

| ID | Requirement | Acceptance evidence | Status |
|---|---|---|---|
| R-001 | Fresh modular implementation in `leo-tracker-reduxredux` with no legacy compatibility obligation | WP0 architecture/module contract review | DONE |
| R-002 | Support one or two Ethernet Pluto+ radios | WP3 transport and hardware canary | DONE |
| R-003 | Support one or two RX paths per Pluto+ | CI16 paired-layout and hardware tests | DONE |
| R-004 | Best-effort synchronized mode maximizes and measures overlap without coherence claims | Synchronization gate | DONE |
| R-005 | Capture parameters and dwell/sample-rate experiments require no code change | Revisioned profile contract and CLI tests | DONE |
| R-006 | Acquisition can approach 100% duty while processing remains decoupled | 24-hour soak and induced-backlog test | PENDING |
| R-007 | Raw IQ is compressed, immutable, independently chunked, and self-describing | Storage gate and reconstruction test | DONE |
| R-008 | Exact radio/settings/times/pairing/calibration/continuity metadata is retained | Manifest schema and reconstruction assertions | DONE |
| R-009 | Live IQ and analysis reside on `/srv/bulk/leo` | URI/path configuration integration test | DONE |
| R-010 | QNAP is copy-only and never automatically modified or deleted | Static/API review plus retention confinement test | DONE |
| R-011 | PostgreSQL is the robust catalog and processing queue | WP1 integration/concurrency suite | DONE |
| R-012 | Alembic supports frequent reviewed migrations without automatic back-processing | Migration gate | DONE |
| R-013 | Analysis artifacts are immutable, versioned, hashed, and stored on `/srv/bulk` | Product publication/fault tests | DONE |
| R-014 | Scientific artifacts and stable UI presentation products are separate | Presentation contract tests | DONE |
| R-015 | Analyzer modules are independently testable and infrastructure-blind | Analyzer fake-boundary tests | DONE |
| R-016 | Processing handles new captures and explicit existing-data re-ingestion | Vertical-slice and reprocess tests | DONE |
| R-017 | Reprocessing replaces visible analysis atomically and preserves last good output on failure | Reprocessing gate | DONE |
| R-018 | Historical detector/QAM capability is recovered before novel optimization | RETRO and J1 parity gate | PENDING |
| R-019 | Whole-dwell analysis retains multiple basins and includes Doppler, QAM, and controls | WP9 detector/scientific gate | DONE |
| R-020 | UI is read-only open HTTP on the LAN | Route audit and Playwright gate | DONE |
| R-021 | CLI has distinct acquisition and processing areas with human and JSON output | CLI contract/integration tests | DONE |
| R-022 | UI and CLI expose paths, provenance, power, Starlink, QAM, Doppler, coverage, and state | Cross-interface assertion suite | DONE |
| R-023 | Playwright E2E validates a real browser against freshly ingested TEST data | Main/nightly Chromium artifacts | DONE |
| R-024 | Small real/control corpus is copied locally, immutable, tagged TEST, and held | Corpus manifest and retention tests | DONE |
| R-025 | Missing required real-data fixtures never silently skip | Fixture preflight failure test | DONE |
| R-026 | Automatic retention starts at 70%, targets 65%, warns at 75%, and stops admission at 80% when blocked | Retention threshold suite | DONE |
| R-027 | Held recordings are never automatically deleted | Hold concurrency/destructive suite | DONE |
| R-028 | Purged recordings retain searchable tombstones and small summaries | Retention/UI integration test | DONE |
| R-029 | Local RAID is sufficient; no second raw-data copy is required initially | Deployment configuration review | DONE |
| R-030 | Services deploy under systemd with acquisition protected from worker load | Soak, restart, and resource-weight tests | PENDING |
| R-031 | Committed filesystem data survives database/service crashes and is reconciled | Crash/reconciliation campaign | DONE |
| R-032 | Final system passes the complete production gate on the dedicated host | WP10 qualification report | PENDING |

## 20. Change control

Changes to an invariant, destructive behavior, synchronization claim, storage root, raw encoding, promotion semantics, or web mutation boundary require:

1. a written architecture decision record;
2. explicit review of failure and migration behavior;
3. an updated acceptance gate and requirement trace;
4. tests landed before the changed behavior is enabled.

Research analyzers and product schemas may evolve rapidly within these boundaries. The purpose of the platform is to make that evolution safe without repeatedly redesigning acquisition, storage, catalog, retention, or the browser contract.
