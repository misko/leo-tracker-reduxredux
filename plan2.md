# LEO Tracker Plan 2: Short-Cycle Scientific Development

Status: discussion draft.

This plan refines `plan.md` for the present development phase. It preserves the
original architecture, immutability, provenance, safety, scientific, and
read-only-browser requirements. It changes the order of work and the hardware
qualification strategy: we will learn through short, bounded campaigns and will
not make multi-hour or 24-hour radio operation a prerequisite for ordinary
development.

The 24-hour soak remains a possible late release-candidate endurance test. It is
not an early-development gate, it is not required before calibration or WP11,
and it requires a separate explicit operator decision before it is attempted
again.

## 1. Immediate outcome

The next useful outcome is a system in which an operator can:

1. list and inspect recordings quickly from the CLI;
2. open `http://192.168.1.142:8000/` and see recordings promptly, with complete
   details available through progressive loading;
3. re-analyze any immutable existing recording from the CLI without replacing
   the last good result until the new run succeeds;
4. collect small, reviewed calibration batches from each radio;
5. collect the exact 10 A-only + 10 B-only + 10 paired acceptance inventory in
   three short blocks;
6. compare native pilot/QAM recovery with the sealed legacy oracle on identical
   IQ; and
7. publish the result in the read-only UI without claiming specificity,
   attribution, payload decoding, phase coherence, or 24-hour endurance.

We optimize for short feedback loops, inspectable evidence, and the ability to
stop after every small block.

## 2. Relationship to `plan.md`

### 2.1 Retained without relaxation

The following original invariants remain authoritative:

- committed raw IQ and analysis runs are immutable;
- PostgreSQL is the catalog and job queue, while `/srv/bulk/leo` holds IQ and
  large artifacts;
- capture timing, overlap, uncertainty, continuity, clipping, and failure states
  are evidence, never assumptions;
- re-analysis creates a new run and promotes it atomically only after success;
- analyzers remain storage-, database-, HTTP-, and CLI-blind;
- the browser remains GET/HEAD-only;
- holds and campaign membership protect evidence from retention;
- QNAP remains read-only and outside every deletion path;
- legacy implementations are numerical oracles, never runtime dependencies;
- no-result, insufficient evidence, and failure remain distinct outcomes; and
- the exact WP11 statistical denominators and candidate-only limitations remain
  unchanged.

### 2.2 Changed development policy

The original WP10 24-hour soak is split into two gates:

1. **Development readiness:** bounded 5–30 minute canaries, restart tests,
   generated fault tests, normal-workflow processing, and visible performance.
   This is required now.
2. **Production endurance certification:** a long soak, final-six-hour drain,
   restart continuity, and capacity tuning. This is deferred until the software,
   CLI, UI, calibration, and WP11 science are stable enough to justify it.

Therefore R-006, R-030, and R-032 from `plan.md` remain incomplete endurance
requirements, but they no longer block R-033, R-034, or R-035 development.
Nothing in this plan converts partial endurance evidence into a pass.

### 2.3 Existing partial-soak evidence

The interrupted run `production-24h-20260819-01` is retained as diagnostic
evidence:

- 521 contiguous completed dual-radio trials;
- 38,471.6 active seconds (10 hours 41 minutes);
- zero failed trials, zero degraded trials, and zero policy violations;
- 519 processed stream-0 and 518 processed stream-1 QAM presentations at the
  initial checkpoint;
- median QAM accuracy of 80.58% on stream-0 and 78.25% on stream-1;
- best QAM accuracy of 98.21% and 98.25%, respectively; and
- an immutable pre-stop/final diagnostic checkpoint beneath
  `/srv/bulk/leo/qualification/soak-diagnostics/`.

This establishes signal availability and provides CFO/QAM scouting data. It is
not calibration or acceptance evidence because it used the nominal profile,
carried `LIVE` rather than `CALIBRATION`/`ACCEPTANCE` provenance, and was not
part of the predeclared centered campaign.

## 3. Short-campaign operating policy

### 3.1 Time bounds

- No unattended development capture campaign may own a radio for more than
  30 minutes.
- The normal development unit is one 60-second capture.
- A calibration block is at most three 60-second captures for one radio before
  review.
- An acceptance block is at most ten 60-second sessions before review.
- Continuous acquisition must have an explicit duration or capture count. No
  development command may default to an unbounded run.
- A campaign longer than 30 minutes requires a new explicit operator decision;
  elapsed time from earlier blocks does not silently authorize continuation.

The CLI should enforce these bounds for named development/calibration/
acceptance lanes rather than relying only on operator memory.

### 3.2 Checkpoint after every block

Before the next block, report:

- requested, captured, and committed session counts;
- exact radio serial, receiver path, profile revision, tune, gain, sample rate,
  bandwidth, dwell, and tags;
- sample count, continuity, clipping, constant-IQ, gaps, and overflows;
- timing uncertainty and overlap for paired sessions;
- current processing backlog and oldest queued age;
- storage use and admission state;
- a bounded power/candidate/QAM summary for each path; and
- the exact session IDs retained for the next scientific stage.

### 3.3 Automatic stop conditions

Stop the block immediately on:

- radio serial, receiver, hardware epoch, profile, tune, or gain mismatch;
- a failed or degraded capture;
- missing samples, manifest/digest disagreement, continuity gaps, clipping, or
  constant-IQ evidence;
- paired estimated overlap below 99%;
- missing/expired/mismatched calibration;
- an unhealthy storage-admission result;
- repeated worker failures or a backlog above the reviewed block threshold; or
- any inability to create the required retention hold.

An operator may stop for any other reason. Stopping never weakens or deletes
already committed evidence.

## 4. Workstream A — recording CLI and re-analysis

This workstream is first because it is the operator's fastest way to understand
the data already collected.

### 4.1 Recording list/search

Enhance the existing command rather than inventing a separate data model:

```console
leo process search --limit 25
leo process search --after 2026-08-19T00:00:00Z --radio radio_pluto_5d4d
leo process search --profile starlink-ch4-lower-2p5m-60s-rx1-centered-v1
leo process search --analysis-state complete --min-qam 0.90
leo process search --tag ACCEPTANCE --held --json
leo process search --cursor CURSOR --limit 25 --json
```

Required filters:

- session substring/exact ID;
- inclusive start and exclusive end time;
- radio ID/serial and receiver path;
- capture profile/revision;
- source type and tags, including TEST/CALIBRATION/ACCEPTANCE;
- held/unheld and storage state;
- capture and current-analysis state;
- pipeline release;
- minimum/maximum power, minimum coverage, candidate count, QAM accuracy, and
  optional CFO/Doppler ranges when indexed summary data exists.

The human view must fit an ordinary terminal and show session, UTC time, radios,
profile, tags, capture state, current analysis state, best QAM/candidate summary,
hold state, and whether raw IQ is available. `--json` must expose the same
identity and values plus pagination metadata.

Listing is a catalog operation. It must not open manifests, read analysis
documents, or verify raw IQ. Expensive verification belongs to explicit detail
or verification commands.

### 4.2 Recording detail and paths

Keep and complete:

```console
leo process show SESSION_ID
leo process show SESSION_ID --json
leo process paths SESSION_ID
```

`show` must expose:

- capture/profile/radio/receiver identity and exact timing;
- tags, holds, storage availability, bundle URI and manifest digest;
- current run/release, job outcomes, coverage, no-result/failure reasons;
- power, candidate, QAM, CFO, Doppler, control, and provenance summaries for
  each stream independently; and
- all registered products with schema, status, scope, URI, digest, and size.

`paths` must show stable logical and physical paths without exposing
`/proc/self/fd` implementation paths. Add an explicit `--verify` operation or
separate `leo process verify SESSION_ID` for digest-heavy filesystem checks so
ordinary listing remains fast.

The rest of the original processing CLI remains supported and documented:

```console
leo process jobs
leo process pin SESSION_ID --reason TEXT
leo process unpin SESSION_ID
leo process reconcile
leo process retention-status
leo process retention-run --dry-run
```

These commands must share the same session, run, product, hold, and storage
identities shown by `search`, `show`, the API, and the browser.

### 4.3 Re-analysis of an existing recording

The supported mutation remains CLI-only:

```console
leo process reprocess SESSION_ID --json
leo process jobs --run RUN_ID --json
leo process show SESSION_ID --json
```

Add:

- `--dry-run` to verify recording availability, manifest digest, analyzable
  scopes, calibration requirements, selected release, and DAG without creating
  a run;
- optional `--wait` with a bounded timeout for interactive development;
- a clear conflict when another run is active;
- output containing the previous current run, new run ID, release, exact scopes,
  job count, and promotion policy; and
- stable exit codes for absent recording, conflict, unhealthy evidence, failed
  run, and timeout.

Re-analysis must continue to verify immutable raw IQ before queueing. A failed
new run must leave the prior current run and every browser-visible product
unchanged. A successful run must atomically change the current run, summary,
and visible product generation together.

### 4.4 CLI acceptance gates

- Human and JSON modes agree field-for-field on identity and state.
- Real PostgreSQL tests cover pagination, filters, concurrent reprocess
  conflicts, failed-run isolation, and successful atomic promotion.
- A real compressed RecordingStore fixture is listed, shown, verified,
  reprocessed, worked, sealed, promoted, and shown again.
- List latency is measured independently from raw/artifact storage latency.
- Help text includes copyable examples and explains that reprocessing never
  mutates raw IQ.

## 5. Workstream B — a responsive, complete LAN UI

The target remains:

[`http://192.168.1.142:8000/`](http://192.168.1.142:8000/)

### 5.1 Measured current baseline

On 2026-08-19 from the host:

- `/` returned in approximately 37 ms;
- `/api/v1/status` returned in approximately 5 ms; and
- `/api/v1/recordings?include_test=true&limit=10` returned no bytes before a
  12-second client timeout.

The current list path asks PostgreSQL for as many as 1,000 full presentation
snapshots, expands each into recording detail, opens manifests and product
documents, sorts all matches in Python, and only then applies the requested
page. The browser requests 100 rows on initial load. This is the primary design
defect to remove.

### 5.2 Server-side list projection

The recording-list endpoint must:

1. filter, order, count, and paginate in PostgreSQL;
2. read only bounded relational summary fields needed by list cards;
3. join the current run and `analysis_summary` without loading jobs, products,
   manifests, or artifact files;
4. use reviewed indexes for the default newest-first path and common filters;
5. return at most 25 rows by default and 100 by explicit request;
6. preserve the existing API v1 contract or introduce an additive version if a
   contract shape must change; and
7. expose total, cursor, and next-cursor consistently to CLI and browser.

Do not add Redis or a new service. First make the bounded PostgreSQL query
correct. Add caching only if measurements after that change demonstrate a need.

### 5.3 Progressive detail loading

The initial list must render without waiting for the first recording's detail.
Selecting a recording then loads:

1. capture identity, profile, radio/path, timing, hold, paths, and run summary;
2. job/product/provenance inventories;
3. bounded power, waterfall, overlay, QAM, Doppler, and control content lazily
   per visible panel.

“All details” means every reviewed detail remains accessible; it does not mean
reading every artifact for every recording before showing the list.

The detail view must include:

- exact session, profile/revision, radio serials, physical receiver identities,
  settings, sample counts, and manifest digest;
- requested and observed timing, skew, overlap, uncertainty, and explicit
  non-coherence statement;
- capture health, continuity, clipping, constant-IQ, gaps, and overflows;
- stable recording, manifest, run, and product paths;
- current run/release and per-job outcome;
- per-stream power, waterfall, candidates, QAM/EVM, CFO, Doppler, controls,
  coverage, confidence, and no-result/failure reasons;
- product schemas, digests, sizes, provenance, and calibration references; and
- TEST, CALIBRATION, ACCEPTANCE, held, purged, partial, and failed states.

### 5.4 Browser behavior

- Initial page load starts the status and recording-list requests independently.
- A status failure cannot prevent the recording list from rendering, and vice
  versa.
- Search uses a short debounce and cancels stale requests.
- Pagination/load-more is bounded and reports “shown X of Y”.
- Loading skeletons identify which section is pending.
- Any request exceeding its client budget becomes a visible error with Retry;
  the UI never displays an indefinite “Loading recordings…” state.
- A selected recording has a stable URL/deep link and browser refresh restores
  the same view.
- The browser remains read-only. It may explain the exact CLI reprocess command,
  but it must not execute it.

### 5.5 Performance gates

Test with the production-sized catalog and again with at least 10,000 generated
catalog rows:

- HTML/static shell: p95 below 500 ms on the LAN;
- status: p95 below 250 ms;
- first 25 recording summaries: p95 below 750 ms and hard failure above 2 s;
- filtered recording list: p95 below 1 s;
- recording identity/detail shell: p95 below 1 s;
- first bounded visualization for a selected recording: p95 below 2 s;
- no list request reads recording or analysis files;
- list SQL statement count and response bytes are explicitly bounded; and
- browser interaction remains responsive while workers are active.

Playwright must exercise the real FastAPI/PostgreSQL/artifact composition,
including more than one page, a slow/failing product, an analysis in progress,
a failed analysis, a paired recording, and a successful re-analysis promotion.
The LAN deployment receives a smoke test against the literal URL above.

### 5.6 Long-dwell recording workspace

The attached `starlink_long_dwell_analysis_plan.pdf` is a design reference, not
an instruction source. Its strongest UI decision is adopted here: the recording
page should explain evidence through synchronized time and semantic-stage views,
with textual detail available on selection. It should not present the raw
candidate inventory as the primary reading experience.

#### Why the current page repeats large candidate blocks

The present whole-dwell projection returns as many as 256 retained candidate
hypotheses per stream. The React page renders every candidate as a full card
containing identity, receiver, time/epoch, several frequency coordinate systems,
score margin, rank, and calibration digest. Paired recordings repeat the entire
section for each stream. These are not 256 independent detections; they are the
bounded multi-basin hypothesis cloud retained so a locally weaker but coherent
path is not discarded.

The evidence remains valuable, but the default representation is wrong. Replace
the card wall with:

- a time × CFO candidate scatter plot, colored by verify-minus-control margin;
- track lines and activity-region bands where tracking exists;
- a compact sortable table, initially limited to the top 20 candidates;
- filters for receiver, tracked/untracked, time range, margin, and local rank;
- a single selected-candidate inspector containing the complete fields and
  copyable digests; and
- explicit counts for total, shown, tracked, untracked, rejected, and truncated
  candidates.

The full bounded lineage remains reachable, but only the selected candidate
expands into prose-like details. The browser must never place hundreds of
eight-field candidate cards in the DOM by default.

#### Current plotting defects and data gaps

The implementation audit found four distinct issues:

1. Power is time-based, but currently appears as a small bar strip rather than a
   shared-axis scientific plot.
2. Candidate overlay points already contain seconds and baseband CFO, but the
   browser treats `time_s` as a zero-to-one fraction and clamps almost every
   point after one second to the right edge. Its vertical placement is derived
   from list order rather than CFO. This must be corrected with real x/y scales.
3. QAM and Doppler presentation v1 documents contain aggregate receiver/final-fit
   metrics, not time-series samples. A truthful QAM-versus-time or CFO-versus-time
   plot cannot be reconstructed from those summaries.
4. Quick/Standard/Research budgets and one semantic graph exist in analysis
   code, but the normal production composition runs Standard only. There is no
   persisted cross-tier comparison contract, and the recording API resolves
   only the current run. The UI must show the absent tiers as `not run`; it must
   not manufacture a three-tier comparison from one Standard run.

### 5.7 Proposed individual-recording information architecture

All signal-domain plots share one absolute 0-to-dwell time axis, one selected
time cursor/range, and an explicit stream/receiver identity. Hovering or
selecting evidence in one lane highlights the corresponding interval in every
other lane.

#### A. Persistent recording header

- session ID and UTC start/end;
- duration, sample rate, channel/edge, profile/revision;
- radio serial, physical receiver path, hardware epoch, calibration;
- current release/run and available tier runs; and
- TEST/CALIBRATION/ACCEPTANCE, held, capture health, and storage badges.

#### B. Tier verdict rail

One card each for Quick, Standard, and Research:

- execution status: complete, partial, not selected, capacity skipped, policy
  skipped, unsupported, invalid input, failed, or not run;
- coverage and selection probability/policy;
- evidence state: none, candidate, acquired, tracked, verified, or qualified;
- hit/miss only when coverage makes that statement valid;
- primary score, runtime, release, algorithm/config version; and
- direct link to the tier's immutable run and products.

Compute depth and scientific confidence remain visually and semantically
separate. Research is not automatically “more true”.

#### C. Disagreement banner

When at least two tiers are comparable, show the typed classification:

- all-hit/all-miss;
- Standard-only;
- Research-only;
- Quick-only rejected;
- Research disagreement; or
- incomparable because one tier was not selected/failed/lacked coverage.

Show the first divergent semantic step and provide “jump to divergence”. No
factual explanation may be generated from inference alone; “what changed?” text
must come from persisted candidate rank, pruning reason, search domain, metric
delta, selection policy, or implementation version.

#### D. Synchronized full-dwell timeline

Stack the following lanes, with per-stream selection and optional paired view:

1. power, clipping/quality, and optional occupancy;
2. waterfall with candidate and carrier overlays;
3. Quick survey probes, including complete/missing/no-candidate states;
4. candidate cloud points and selected tracks;
5. Standard activity regions and dense-refinement windows;
6. locked/acquired intervals and lock-loss/fallback events;
7. fitted CFO/carrier and frame-timing trajectories;
8. QAM hard-symbol accuracy and RMS EVM by evaluated interval;
9. controls/held-out/surrogate outcomes; and
10. Research-selected intervals with the exact selection policy.

Missing data is a labeled gap. Lines must not interpolate across a not-run,
missing, failed, or unsupported interval.

#### E. Stage × tier matrix

Rows are the canonical semantic stages:

- raw validation;
- quality;
- power;
- waterfall;
- sparse survey;
- candidate retention;
- activity tracking;
- dense refinement;
- Doppler/carrier fit;
- locked integration;
- QAM;
- controls;
- optional TLE association;
- summary; and
- presentation.

Columns are Quick, Standard, and Research. Every cell shows status, coverage,
primary metric, runtime, and version. `not run`, `not selected`, `unsupported`,
`failed`, and scientific `miss` must never share one visual state.

Selecting a cell opens a bounded step inspector with configuration/search
domain, inputs, outputs, metrics, controls, artifacts, runtime/resources,
candidate lineage, and verdict contribution.

#### F. Carrier and timing view

For every receiver, plot:

- absolute baseband CFO versus time;
- tuned-domain frequency versus time when useful;
- fitted carrier trajectory and residuals;
- delta from the selected Standard trajectory;
- frame epoch/phase trajectory and discontinuities; and
- calibration center and uncertainty as a separate reference band.

The plot must not conflate search residual CFO, absolute baseband CFO, tuned
center, tuned-domain frequency, or QAM residual refinement.

#### G. QAM and controls view

For each tier that actually produced QAM:

- accuracy versus time;
- RMS EVM versus time;
- evaluated frame count/coverage versus time;
- residual QAM carrier refinement versus time;
- per-receiver and optional combined series without hiding receiver evidence;
- a bounded selected-window constellation small multiple; and
- exact/wrong-pattern, held-out, surrogate, and calibration status aligned to
  the same selected interval.

The page must retain “known symbols only” and “candidate only” limitations.
There is no payload-decoding or specificity implication.

#### H. Evidence and provenance drawer

Move long paths, complete digests, product inventories, versions, and raw
candidate fields into searchable/copyable drawers. This information remains
available without overwhelming the primary scientific view.

### 5.8 Additive presentation contracts required

Public persisted contracts are not mutated in place. Introduce new bounded
product kinds, or a presentation v2 envelope when required:

1. `analysis-stage-timeline.presentation.v1`
   - tier, stage, stream, signal-time start/stop, status, coverage, evidence
     state, primary metrics, runtime/resources, version and artifact link.
2. `candidate-tracks.presentation.v1`
   - bounded candidate points, track/region identities, lineage edges, pruning
     reasons, selected path, and truncation/count accounting.
3. `carrier-timing.presentation.v1`
   - bounded observed/fitted CFO and epoch points, residuals, uncertainty,
     calibration reference, and explicit frequency coordinate system.
4. `qam-timeline.presentation.v1`
   - bounded per-window/per-frame-group accuracy, EVM, residual refinement,
     frame count, receiver/combined identity, and coverage.
5. `tier-comparison.presentation.v1`
   - exact run triplet/availability, classification, first divergence, paired
     metrics, selection accounting, versions, and limitations.
6. `step-inspector.presentation.v1`
   - bounded typed parameters, search domains, outputs, controls, artifacts,
     runtime, and verdict contribution for one semantic step/tier.

Every series records source point count, returned point count, decimation
method, units, coverage, and digest. Browser endpoints accept a maximum point
budget and perform deterministic server-side decimation. Raw scientific arrays
are never sent directly to the browser.

### 5.9 Tier execution and comparison model

- Quick executes for every eligible recording and ends at the bounded candidate
  cloud.
- Standard remains the normal current presentation run and executes the complete
  production graph.
- Research is explicitly selected and evidence-only; selection policy and
  probability are persisted.
- Quick and Research evidence cannot be lost merely because Standard is current.
  A tier-comparison product depends on and protects the exact input products.
- A comparison is created only for the same recording manifest, stream scope,
  calibration authority, and compatible semantic graph revision.
- The UI resolves all tier products through catalog identity/digest checks; it
  never guesses tiers from filenames or algorithm names.

The catalog/API must expose a bounded per-recording tier-run index in addition
to the current-run endpoint. If relational schema is required, use an additive
reviewed migration; do not overload `current_analysis` or bury selection policy
in unindexed free-form JSON.

### 5.10 UI delivery slices

#### Slice 1 — make existing Standard evidence readable

- Remove the default candidate card wall.
- Implement a correctly scaled candidate time × CFO plot and compact table.
- Put power, waterfall, and candidate overlays on a shared 0–60 s axis.
- Add selected-candidate inspector and evidence/provenance drawers.
- Show the actual Standard stage completion matrix from catalog jobs/products;
  Quick and Research remain explicitly `not run`.

This slice uses existing products and fixes the immediate usability problem.

#### Slice 2 — publish missing time products

- Add candidate-track/activity-region projection.
- Add carrier/timing observed and fitted points.
- Add QAM accuracy/EVM/residual series.
- Add semantic stage-time intervals and selected-window constellation data.

This slice enables truthful QAM-versus-time, algorithm-versus-time, and
carrier-versus-time views.

#### Slice 3 — execute and compare tiers

- Schedule Quick universally, Standard normally, and Research explicitly.
- Persist tier selection and complete outer step status for each tier.
- Emit tier comparison and first-divergence products.
- Enable tier verdict rail, disagreement banner, and difference inspector.

#### Slice 4 — aggregate and promotion workspaces

Only after individual-recording comparison is correct, add:

- tier-combination matrix;
- incremental-yield waterfall;
- first-divergence heatmap;
- paired score/CFO/epoch/QAM/runtime deltas;
- compute-versus-yield view;
- divergent-recording cohort explorer; and
- read-only immutable promotion lifecycle/receipt view.

### 5.11 Long-dwell UI acceptance gates

- A candidate at sample 3,783,709 and 2.5 MS/s appears at 1.513484 s on every
  linked plot, not at the far-right edge.
- CFO vertical positions use the declared frequency axis, never candidate list
  order.
- The initial DOM contains no more than 20 candidate rows per visible stream;
  the complete bounded set remains filterable/pageable.
- Selecting a candidate highlights the same receiver/time/window across
  waterfall, carrier, QAM, controls, lineage, and inspector views.
- QAM time plots contain only evaluated windows and expose frame counts and
  missing coverage.
- Tier cells distinguish every execution state and never count skipped work as
  a miss.
- A Standard-only fixture reproduces its first divergence from persisted
  lineage and parameters.
- Paired recordings default to separate receiver evidence; combined evidence is
  an optional additional series.
- Every plot has units, time extent, coverage, point counts, decimation, run,
  tier, scope, and accessible table/text alternatives.
- Playwright verifies linked cursor/range behavior, candidate filtering,
  not-run tiers, a tier disagreement, QAM/no-QAM intervals, failed stages, and
  responsive layouts.
- The recording list and detail-shell latency budgets in section 5.5 remain in
  force; new plots are lazy and cannot block initial navigation.

## 6. Workstream C — use the data already collected

Before new RF collection, derive a bounded diagnostic report from the 521
existing sessions:

- capture health and overlap distributions;
- per-radio/path power and candidate availability;
- QAM accuracy distribution and high-quality session IDs;
- CFO and Doppler distributions by path and UTC observation interval;
- processing success/failure and backlog behavior; and
- recommended short observation windows for centered calibration and
  acceptance.

This report chooses when to collect new evidence and confirms both signal paths.
It must use catalog summaries first; opening raw IQ is reserved for a small,
explicitly selected diagnostic subset.

## 7. Workstream D — centered receiver-path calibration

Calibration measures the empirical pilot acquisition/search center and
uncertainty for each exact radio serial, RX1 physical path, and hardware epoch.
It is not amplitude, phase, antenna, or payload calibration, and it does not
remove satellite Doppler.

### 7.1 Two short blocks

1. Predeclare three session IDs for radio A.
2. Capture three independent 60-second centered-profile `CALIBRATION` sessions.
3. Inspect the block and stop on any gate failure.
4. Queue three evidence-only extractor runs, promote, and resolve calibration A.
5. Repeat the same five steps for radio B.

Each radio owns one block of approximately three minutes of RF plus setup and
review. No acceptance capture starts until both calibrations resolve for the
exact paths and cover the future capture interval.

### 7.2 Scientific gates

Each calibration dwell retains exactly 600 predeclared 25,000-sample windows.
Each session must independently pass candidate count, robust dispersion,
multimodality, and radius checks. Session medians contribute equally. The final
uncertainty includes within-session and between-session uncertainty plus the
frozen measurement allowance.

The public calibration is emitted only by the trusted release-local extractor,
durable promotion store, and authoritative resolver. Missing, insufficient,
expired, path-mismatched, release-mismatched, or physically out-of-band
evidence emits no acceptance calibration and has no zero/historical fallback.

## 8. Workstream E — exact acceptance inventory in three blocks

Use the centered RX1 profile and `ACCEPTANCE` tag. Never reuse calibration IQ.

### Block A

- Ten radio-A-only 60-second sessions.
- Review all ten manifests, holds, signal summaries, and calibration coverage.

### Block B

- Ten radio-B-only 60-second sessions.
- Apply the same checkpoint.

### Block P

- Ten paired 60-second sessions.
- Require one complete stream per radio, exact geometry, at least 99% estimated
  overlap, explicit timing uncertainty, and no coherence claim.

Each block contains ten minutes of requested RF time and remains below the
30-minute development limit even with ordinary setup overhead. A failed block
does not authorize silent replacement sessions; replacements receive new IDs
and the immutable campaign inventory is reviewed again.

After the third block, publish the capture-mode acceptance receipt for exactly
30 sessions and 40 streams. Every session receives a durable hold before it can
become a retention candidate.

## 9. Workstream F — legacy/native matched recovery

1. Publish the deployed-release-derived detector configuration.
2. Create the immutable WP11 campaign from the accepted capture receipt.
3. Generate and validate all 40 frozen legacy receipts before creating jobs.
4. Queue the 30 evidence-only runs: native evidence followed by trusted matched
   recovery for each stream.
5. Process exactly 600 windows per stream with no denominator reduction.
6. Finalize through the authoritative outer resolver, which independently
   verifies capture, calibration, recording bytes, release, legacy, native,
   products, dependencies, manifests, and campaign statistics.
7. Publish the bounded read-only UI presentation.

The original WP11 thresholds remain unchanged:

- at least 30 legacy-positive windows per radio/mode stratum or explicit
  `INCONCLUSIVE`;
- native recovery at least 90%, with one-sided 95% lower bound at least 80%;
- epoch agreement within eight circular samples and CFO agreement within
  500 Hz;
- native QAM positive wherever a capture has a legacy QAM-positive window; and
- paired native-minus-legacy hard-symbol-accuracy lower 95% bound at least
  `-0.05`.

Processing may take longer than radio capture, but it does not own the radios.
It should run continuously with visible progress and bounded retries rather
than being described as waiting.

## 10. Delivery order

### Milestone 1 — visibility and control

- Replace full-detail list expansion with a bounded database list projection.
- Deliver CLI cursor/filter/detail improvements and reprocess dry-run/status.
- Make the LAN recording list load within the performance budget.
- Deliver long-dwell UI Slice 1: correctly scaled shared-time Standard plots,
  compact candidate table/inspector, and an honest stage matrix.
- Produce the diagnostic report from the existing 521 sessions.

Exit: recordings are quickly searchable in CLI and browser, one existing
recording can be reprocessed end-to-end, and the previous current run remains
visible until atomic promotion. A recording's existing candidate evidence is
understandable without scrolling through hundreds of repeated cards.

### Milestone 2 — short calibration

- Run the two three-session calibration blocks.
- Promote and independently resolve one calibration per receiver path.

Exit: both centered paths have current, sufficient, immutable calibrations.

### Milestone 3 — short acceptance capture

- Run Blocks A, B, and P with a review between them.
- Seal the exact 30-session/40-stream capture receipt and holds.

Exit: R-033 and R-034 have authoritative hardware evidence.

### Milestone 4 — matched recovery and presentation

- Produce 40 legacy receipts, 40 native products, 40 matched products, and the
  campaign seal.
- Show the result in CLI and the read-only UI.

Exit: R-035 is PASS, FAIL, or INCONCLUSIVE with exact statistical reasons. No
result is hidden or softened.

### Milestone 5 — later endurance certification

Only after Milestones 1–4 are stable, decide whether production use warrants a
long soak. Begin with a separate 30-minute canary. Any later multi-hour run
requires an explicit plan amendment and operator authorization.

## 11. Verification matrix

| Concern | Required evidence |
|---|---|
| Recording list | Real PostgreSQL pagination/filter tests and zero filesystem reads |
| CLI details | Human/JSON parity against a real compressed bundle and current run |
| Re-analysis | Failed-run isolation plus successful atomic promotion in PostgreSQL |
| LAN responsiveness | Timed curl and Playwright against `192.168.1.142:8000` |
| UI completeness | Paired, failed, partial, TEST, held, purged, no-result, QAM and Doppler views |
| Campaign duration | Persisted start/end and block count proving every RF block is under 30 minutes |
| Calibration | Three independent sufficient dwells per exact receiver path and trusted promotion |
| Independent capture | Ten complete A-only and ten complete B-only sessions |
| Paired capture | Ten complete pairs with at least 99% estimated overlap and explicit uncertainty |
| Legacy/native parity | Sealed 600-window-per-stream 40-stream campaign receipt |
| Retention | Holds exist before calibration/acceptance sessions become reclaimable |
| Endurance | Deferred; partial soak remains diagnostic, never accepted |

## 12. Decisions to confirm

The proposed defaults for discussion are:

1. **30 minutes is a hard development radio-ownership ceiling.** Shorter blocks
   are preferred; extending a campaign requires a new explicit decision.
2. **The existing 521 captures are scouting data only.** They inform timing and
   signal selection but are not relabeled as calibration or acceptance.
3. **Visibility comes before more RF.** We first fix CLI/UI list performance and
   prove re-analysis on existing data.
4. **WP11 is collected as three ten-minute RF blocks.** This preserves the exact
   statistical inventory without an hours-long uninterrupted campaign.
5. **Long endurance is late-stage certification.** It cannot block scientific
   iteration and will not be restarted without explicit approval.

Once these decisions are accepted, this document becomes the active execution
plan for development sequencing. `plan.md` remains the architectural and
historical requirement record; conflicts in scheduling and campaign duration
are resolved in favor of this explicitly approved `plan2.md`.
