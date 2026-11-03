# Native pipeline replay and module boundaries

## Current qualification status

The first mixed-recording test exposes remaining limits: queue capacity 32
rejects three dwells in the denser second capture, and the overlapping downstream
job takes 303.446 seconds. The completed queue-48 retry processes all 6,649
dwells without loss, but maximum latency is 5.479 seconds and loaded downstream
times are 304.410 and 310.180 seconds. These results prevent a
general real-time qualification from the repeated-baseline result below. An
independent host full-chain control also identifies fit-summary-sensitive
partition identities; see the [three-scan report](../reports/2026_10_01_arm_three_scan_sequence/README.md).

The full recorded local-IQ → observations/support → tracks → orbit propagation
→ regional search → association chain now executes on PLUTO+. The latest
four-scan repeated-recording replay reproduces 64,764 observations without
dropped dwells and matches its pinned downstream controls. The bounded queue-32
configuration passes three loaded downstream intervals at 297.086, 297.852 and
297.688 seconds against a fixed 300-second cadence. Maximum dwell latency is
2.913 seconds, peak queue usage 21/32, and the minimum downstream margin only
2.148 seconds. Three distinct recordings have now been tested as described above.
Native/server track memberships still differ, and replay does not qualify live
RF acquisition. See the [current qualification report](../reports/2026_10_01_native_replay_qualification/README.md)
for stage timings, independent comparisons and source/build receipts.

The first-increment description below records the initial development runner.
Later native integration and paced-replay evidence is documented under
“Next integration gates”; those later results supersede its original delivery
limitations. Current optimization candidates must pass full ARM and cadence
qualification before replacing the pinned replay configuration.

## Delivered first increment (historical scope)

`leo.native_pipeline` is a host-side experiment runner for existing native
executables. It introduces no Python requirement on PLUTO+, changes no numerical
algorithm, and does not replace the local scanner or its execution owner.

Implemented: hash-pinned checkpoints, sequential bounded subprocess execution,
typed output validation, immutable run directories, failure receipts, tracker
recipes for all five frozen algorithms, GLRT and LOC1 location CLI recipes, and
an independent membership evaluator. No module imports a report or reference
repository. The membership evaluator was promoted verbatim from the frozen
curvature comparison; the archived original remains unchanged.

The pure integer-epoch projector in `projection.py` now converts explicit window
authority and detector candidates into immutable observations, source identities,
and support moments. The saved-native-result archive adapter verifies capture
identity and receiver/probe completeness. It reproduces all 16,191 DS9
observations and source-map bytes exactly; see `projection-qualified/` in the
replay qualification report. It is not yet a fractional-epoch projector.
`projection-chain-qualified/` additionally verifies the multi-output stage and
its connection to coarse seed generation and tracking, all against frozen hashes.

The supplied-track location adapter now binds projection support and a
capture-specific orbit authority, verifies hashes and capture/epoch coverage,
and delegates identity/partition/LOC1 construction to the native component.
It preserves all hypotheses and emits an explicit duplicate-membership audit;
the raw-hypothesis aggregate is diagnostic, not independent evidence.

Not yet delivered: a new in-process ARM plugin registry,
overlap resolution for positioning, incremental
track revisions, paced multi-stage replay, automatic caching, or production
continuous IQ-to-position qualification. Existing native source/runtime/location
interfaces remain authoritative for live execution. The generic process wrapper
is a development port, not the intended per-dwell device hot path.

## Run and compare

From the repository root, with the scientific environment:

```sh
PYTHONPATH=src python -m leo.native_pipeline run experiment.json /tmp/new-run
PYTHONPATH=src python tools/qualify_native_replay_ds9.py /tmp/new-ds9-qualification
PYTHONPATH=src python -m pytest -q tests/native_adaptive/replay
```

The DS9 command runs all five trackers three times, validates every output,
requires exact agreement with frozen output hashes (including coarse seeds),
and compares recovery, duration buckets, one-to-one matching and unsupported
outputs against the previous report. Required archived binaries/exports must
exist; absence is an error, never a silent skip. No raw IQ or radio is accessed.

A plan declares `schema: leo-native-replay/v1`, `execution: {mode: serial,
workers: 1}`, named `inputs`, and ordered `stages`. Each input has an explicit
path, SHA-256 and format. Paths are relative to the plan file. An argument such
as `@observations` resolves a named input or earlier stage; no shell is involved.
See the generated `*.plan.json` qualification artifacts for complete examples.

Each stage declares ID, kind, pinned executable, argument list, output format,
timeout, and optionally an expected output hash. Track and source-map artifacts
declare which observation checkpoint supplies their identities. Recipes in
`recipes.py` isolate CLI-specific options from orchestration. Adding an algorithm
that uses the existing track format needs a recipe, not changes to the runner.

Stages may additionally declare an ordered `artifacts` list with `id`, relative
`path`, format, and optional expected hash. `@output-dir` supplies an exclusive
stage-owned output directory for the command to create. Each output is validated
before downstream `@id` references become available. Missing outputs, escaped
paths, or changed intermediate bytes invalidate the run. Observation output must
precede its source-map/track output. Saved GLRT archives use the explicit
`native-glrt-archive-v1` format and a deterministic filename/content tree digest.
The runner preserves executable symlink paths so virtualenv interpreters retain
their environment; executable content is still hash-checked.

The native pipeline CLI now supports `--tracks TRACKS.tsv` after its existing
four positional arguments. This bypasses its default Hough reconstruction and
accepts measured memberships from any compatible tracker. The parser validates
counts, lane/source authority, raw CFO, alias conversion, and exact support bounds.
`--validate-tracks OBSERVATIONS.tsv TRACKS.tsv` exposes the same validation alone.
Research track identities are converted to deterministic native adapter identities;
no saved reference memberships are read. A complete positioning adapter still
needs a correctly timed orbit authority and explicit hypothesis-conflict policy.

The runner checks input hashes before execution and again after all stages,
checks intermediate hashes, records actual argv and platform, and hashes output,
stderr and package code. Failed, invalid or timed-out stages never yield a
complete receipt. Child process groups are killed on timeout. Logs and partial
outputs remain for debugging in the failed run directory. Inputs are trusted
local executables; hashing is provenance validation, not a security sandbox.

Process wall time and reported algorithm time are separate. Hashing, parsing and
evaluation are outside per-process wall time. These host measurements are not
new ARM timing measurements. Dynamic-library environments are not hermetically
captured; retain compiler/library build receipts as explicit input artifacts when
qualifying a build. The runner does not yet measure peak memory or queue latency.

## Scientific contracts

| Checkpoint | Required meaning |
|---|---|
| IQ | Sample/receiver/IQ layout, endianness, count/rate, actual RF, half-open device-counter range, first-sample UTC mapping, timing authority and uncertainty |
| Detector output | Raw candidate CFO, exact/control/margin scores, support/probe information; rejected/incomplete work must remain distinguishable from no detection |
| Observations | Immutable raw CFO, actual RF and lane, source group, support start/center/end UTC and scores; sidecar binds original visit/RX/probe identity |
| Tracks | Explicit observation membership, per-point normalized raw CFO and alias choice, lane and support; fitted fields are compatibility summaries, not replacement measurements |
| Location input | Measured track samples, independent-support accounting and masks, orbit generation, receiver/search authority and calibration |
| Location result | Candidate associations/positions, residuals, nuisance parameters, completeness and ambiguity; incomplete search is not convergence |

Existing TSV and LOC1 artifacts are research-private adapters. Do not reinterpret
their fields or mutate published server contracts. A new format gets a new
format identifier and validator. In particular, the current TSV validator freezes
11.2 GHz normalization and 4.4 us alias spacing; a different signal family needs
an explicit new contract rather than a hidden parameter change.

System clock correctness does not establish sample acquisition time. A USB source
must preserve its timing uncertainty and gaps. Local PLUTO acquisition remains
local; experiment transport is not an IQ runtime dependency.

## Execution and future ports

The current replay executor is serial and rejects other executor configurations.
The native location CLI can explicitly request one or two workers internally;
that argument is captured in the receipt. Future shared CPU budgets must include
such module workers, rather than assuming serial stages mean one CPU thread.

Live adapters should retain caller-owned execution and bounded contexts. Expose
capabilities (batch/incremental, history/lookahead, reentrancy, memory capacities,
parallel partitions), never implicit worker pools. IQ borrows expire at the
callback boundary; asynchronous work requires an owned buffer/lease. Stateless
work can partition by window, tracker lane or satellite range only where the
implementation supports it. Stateful tracker updates need ordered input, visible
gaps and watermarks; revisions/merges/splits must supersede earlier hypotheses.

An opt-in location research adapter now binds CLI-owned orbit arrays for an
explicit immutable scoring session. That owner keeps the arrays alive and
unchanged until unbind/rebind or destruction; ending the lifetime invalidates
caches. The ordinary scoring API retains its mutation checks. This ownership
guarantee permits reuse of orbit validation and avoids copying the same orbit
bank for each site. It does not make mutable external buffers safe to borrow
or change any published persisted contract.

Association is not frozen by tracking. Orbit propagation, measurement prediction,
association scoring and position search are separate ports; association and
location may iterate jointly. Competing track hypotheses must not duplicate
independent evidence. Known-position comparison truth is supplied to the
evaluator, never silently to unknown-position search.

## Next integration gates

1. Native recorded IQ now feeds GLRT and integer observation projection in one
   ARM process; fresh native tracking consumes its local checkpoint. Native
   support graphs now connect those tracks to qualified fixed-site association
   scoring on ARM. The complete 400-point regional search and full association
   scoring at its ARM-selected position have now run on ARM; qualify their
   shared scan budget next. The first complete run took 580.59 seconds for
   search alone. Later optimizations improve this, but have not established
   sustained throughput with concurrent GLRT.
   Bounded IQ-buffer reuse now preserves every candidate and all 16,191
   observations/support records on a full original-cadence ARM replay, reducing
   detector/projection whole-process CPU from 306.135 to 288.356 seconds with
   no drops. Together with the 160.055-second regional search, separately
   measured stage CPU still totals about 610 seconds per 300-second scan.
   See `../reports/2026_10_01_native_replay_qualification/recorded-reuse-v1/`;
   these separate measurements do not qualify concurrent execution.
   The subsequent support-geometry replay preserved those exact outputs and
   measured 283.618 CPU seconds for detector/projection, bringing the separate
   stage sum to about 605 seconds. Projection's own thread CPU fell from 8.902
   to 6.554 seconds; other timing variation contributes to the process saving.
   Evidence is in `recorded-support-hoist-v1/` under the same report directory.
   A subsequent per-dwell `ProjectionBatch` cache reduced projection thread
   CPU further to 2.437 seconds and whole-process replay CPU to 279.316 seconds,
   preserving every candidate and all observation/support bytes. Its 16-entry
   cache holds only geometry and never bypasses source or score validation.
   The current separate-stage sum is about 601 seconds; combined execution,
   contention and backlog must now be measured directly. Evidence is in
   `recorded-batch-support-v1/`.
   The subsequently qualified prevalidated-stencil location build takes
   298.280 CPU seconds for all 400 search points and 3.279 CPU seconds for full
   final associations, with identical ARM outputs and passing independent
   host comparison. The separate-stage sum is now about 597 CPU seconds;
   earlier overlap failures are not cleared by this small nominal reserve.
   See `regional-arm-prevalidated-v1/` and `prevalidated-stencil-v1/`.
   The updated nice-10 overlap (`overlap-prevalidated-v1/`) still rejects
   46/2,215 dwells and requires 312.57 seconds for search. All processed
   science remains exact, but lossless cadence is still an open gate.
   Lowering search further to nice 19 (`overlap-nice19-v1/`) reduces losses
   to 4/2,215 dwells but search takes 314.505 seconds; every processed result
   remains exact. Scheduling changes have not yet demonstrated enough capacity.
   Pinning detection to CPU 0 (`overlap-affinity-v2/`) instead loses 47 dwells
   and takes 312.688 seconds for search. Reject this setting. The firmware
   lacks `taskset`; the harness now uses a pinned, preflighted native launcher.
   Reduce compute cost before repeating full concurrent qualification.
   Prepared conservative pair bounds now preserve both complete host traces,
   all 400 ARM search results and full selected-site associations. Fresh PGO
   yields 297.359 search CPU seconds and 3.265 association CPU seconds, bringing
   the separate-stage sum to about 596 seconds. The sub-second search saving
   is too small to infer lossless concurrency; that gate remains open.
   See `regional-arm-pair-prepared-v1/` and `pair-prepared-pgo-v1/`.
   Optional NEON vector pair bounds subsequently reduce full search to
   142.217 wall / 270.442 CPU seconds, preserving all 400 ARM scores and final
   associations exactly. Independent host comparison passes. Peak search RSS
   increases to 120,772 KiB; full associations take 3.595 CPU seconds. The
   separate-stage CPU sum is now about 569.5 seconds. Scalar remains default;
   concurrent lossless qualification is still required. See
   `regional-arm-vector-pair-v1/` and `vector-pair-pgo-v1/`.
   The vector nice-19 overlap then takes 301.591 seconds for search and rejects
   14/2,215 dwells, retaining exact processed science. Auxiliary stages remain
   excluded. See `overlap-vector-pair-v1/`; the sustained lossless gate is open.
   One vector search worker reduces rejects to 5 but takes 317.171 wall seconds
   (`overlap-vector-single-v1/`). It is not a throughput solution. Isolate cache
   capacity next: one worker also has fewer total cached endpoint blocks.
   A matched ordinary 64/128 MiB single-worker cache test saves 8.647% CPU on
   16 sites. The larger bank with fresh PGO completes concurrent search in
   283.411 seconds, but the eight-entry detector queue still rejects 3 dwells
   (`overlap-vector-bank128-v1/`). All processed science remains exact. Test
   bounded burst buffering next, then auxiliary stages and successive scans;
   this partial overlap does not close the sustained full-chain gate.
   With queue capacity 16, `overlap-vector-queue16-v1/` then reproduces all
   16,191 observations without drops, queue peak 9 and maximum latency 1.353 s.
   Search finishes in 283.611 s with exact ARM results and passing host
   comparison. Add auxiliary stages and successive scans next; this is only
   single-scan detector/search overlap.
   The subsequent `search-associate-v1/` preserves all search/association results
   on ARM while reusing the scorer: 245.042 s isolated combined wall time,
   including 1.367 s final associations. `direct-orbit-authority-v1/` also
   connects TLE propagation directly to LOC1 authority and measured-track
   conversion on ARM, removing host packaging. Include these integrations in
   the next full-chain overlap; neither isolated test establishes that gate.
   `fullchain-overlap-v1/` now runs all downstream stages concurrently with
   recorded GLRT. Numerical checkpoints match, but the chain takes 304.103 s
   and GLRT rejects 13 dwells. Early queue buildup appears before the regional
   search. Replace intermediate orbit/LOC1 files with native memory ports and
   remeasure; the first file-based full-chain overlap fails the sustained gate.
   GLRT sampling (`glrt-sampling-v1/`) preserves all 256 profiled recorded
   outputs and identifies repeated received-energy accumulation in conditioned
   scoring. Input-prefix arithmetic and measured FFT-plan experiments were
   rejected after physical ARM timing. Investigate exact reuse of existing
   CI16 energy prefixes with explicit source provenance next; no saving is
   established yet. The qualified detector remains unchanged.
   Exact CI16 conditioned-energy prefix reuse was subsequently tested in two
   variants (`ci16-window-energy-v1/`, `ci16-window-energy-v2/`). Both reproduce
   the saved scientific rows, but neither supplies a useful detector saving.
   Both were reverted. Prioritize the repeated regional Doppler bounds next;
   the full cadence and independent-comparison requirements are unchanged.
   Extend fractional support only with independent geometry fixtures; preserve
   the qualified integer output.
2. Resolve competing memberships before claiming an independent aggregate
   positioning score. The supplied-track adapter is qualified on host and ARM,
   and native orbit generation now matches the capture-specific server state
   bank on physical ARM. The optional exclusive-candidate selector prevents exact
   candidate reuse, but does not establish physical independence. Regional
   selection and final associations are connected end to end; native tracking
   still differs from server memberships, and regional throughput remains an
   open gate.
   Do not reuse reference memberships or leak known-position truth.
   Opt-in held-out residual bounds and recomputed prior-site seeds preserve
   tested host search traces and reduce fixed-site ARM scoring time; these are
   research flags, not qualified real-time regional positioning defaults.
3. Add process-free adapters behind existing native scanner/executor ports.
   Qualify deterministic serial/parallel results before enabling concurrency.
   `memory-session-v2/` now provides the typed borrowed orbit/track search port
   (`native/adaptive/location/session.hpp`). Both complete host traces and final
   associations remain exact; serial/parallel component and ARM unit checks pass.
   Wire native orbit generation and track conversion directly to it next, then
   requalify the full ARM workload without intermediate orbit/LOC1 files.
   `in-memory-position-v1/` connects those ports, and
   `fullchain-memory-overlap-v1/` verifies exact full-chain outputs with no GLRT
   drops. The downstream job takes 302.385 s, so fixed 300-second sustained
   cadence remains unqualified. Reduce the remaining compute/scheduling cost
   before successive-scan testing; do not redefine the interval to fit this run.
   The subsequent `fullchain-index-pgo-overlap-v1/` trial combines an optional
   immutable satellite-ID lookup with the previously trained GLRT PGO archive.
   Downstream work finishes in 297.978 s, all 16,191 observations are exact with
   zero drops, and all downstream controls match. Queue peak is 11/16. This
   closes the single-interval downstream timing gate with only 2.022 s margin;
   successive fixed-origin arrivals, scan-boundary drain/publication and bounded
   downstream backlog are still required before claiming sustained cadence.
   `fixed-clock-v1/` qualifies the recorded detector's explicit Linux monotonic
   origin on 16 physical ARM dwells, with exact candidates and checkpoint rows.
   `--start-monotonic-ns` rejects missed initialization deadlines instead of
   rebasing the arrival schedule; `--clock-now` exposes the shared clock to a
   controller. Successive-scan orchestration and bounded downstream backlog
   measurement remain to be implemented and exercised.
   The subsequent `cadence-three-v1/` experiment adds a native process controller
   with fixed 300-second origins, at most two overlapping detector lifecycles,
   one downstream worker and one pending completed scan. Each downstream job
   consumes its own freshly produced checkpoints. The first three-repeat physical
   test failed: scan 0 is lossless, but scan 1 rejects 13 dwells and the controller
   cancels remaining work. All processed science remains exact; scan 0's search
   stops after 396 exact points. Sustained cadence is still unqualified. A
   follow-up measured about 3.3 CPU seconds per scan of memory-sampling overhead
   at the original one-second interval; reduce measured observer overhead and
   repeat without changing scientific work or scan cadence.
   `cadence-three-observer-v2/` then completes all three scans at fixed 300-second
   origins: 48,573 exact positive observations, no drops, and exact downstream
   controls (independent host search tolerance also passes). Loaded downstream
   durations are 302.261 and 300.643 s, with completed-scan wait increasing from
   2.364 to 2.777 s. The final 257.454 s downstream drain is unloaded. This
   qualifies the finite replay and accounting, but does not establish stationary
   backlog; reduce measured downstream overhead before further loaded testing.
4. Extend the lossless single-scan detector/projection replay to successive scans
   with tracking and positioning sharing the ARM CPU budget. Measure queue
   growth, drops, end-to-end latency and memory. Then qualify continuous local
   acquisition separately. The prior 234.91 s compute sum is not that test.
   The first equal-priority detector/search overlap rejected 430/2,215 dwells
   despite preserving all processed numerical results. Evidence is in
   `../reports/2026_10_01_native_replay_qualification/overlap-fair-v1/`.
   It excludes auxiliary stages and already fails lossless pacing. Qualify
   detector-priority scheduling next and measure search backlog explicitly.
   The subsequent nice-10 search trial (`overlap-priority-v1/`) reduced drops
   to 44/2,215 but took 313.77 seconds for search, so priority alone is
   insufficient. The next compute experiment is PGO of the qualified ungated
   GLRT source: its current build receipt has no profile-use flags. Retain
   complete candidate comparisons and separate training from timing evaluation.

Evaluation remains independent: source coverage, source purity, one-to-one
agreement, splits/merges and extras are separate measures. Server agreement and
physical plausibility are never collapsed into one real-track percentage.

For the regional-search control, `tools/qualify_native_regional_search.py` uses
the original prior center and radius, records binary/input/reference digests,
and runs the full 400-point native search with a 300-second host timeout. Its
`--published-memberships` mode verifies the exact server checkpoint and isolates
search/scoring differences. Without that mode, tracker differences remain part
of the comparison. A completed replay receipt does not imply search convergence:
the separate `search_complete` and `stop_reason` fields retain that distinction.
