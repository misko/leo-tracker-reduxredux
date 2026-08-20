# CFO De-aliasing and Final-Trajectory Plan

## Decision

Add a shared, explicit **CFO de-aliasing and merge boundary** between the raw
GLRT64 trajectory bank and any final CFO trajectory used for corrected replay.

This is required for both analysis lanes:

- **Standard:** automatic, `2 × 20 ms` probes in each 50 ms subwindow.
- **Research:** manual, `3 × 20 ms` probes in each 50 ms subwindow.

The two lanes share pure numerical code but never share runs, products,
promotion state, or cache identities.

The system must preserve raw independent-search evidence. De-aliasing is an
additional interpretation and fit stage; it must never overwrite a raw CFO,
the raw trajectory bank, or the unmerged PNGs.

## Non-negotiable invariants

1. **Raw evidence is authoritative and immutable.** Every canonical or final
   row points back to exact raw observation IDs and input product digests.
2. **Canonical CFO is not correction CFO.** It groups ambiguity-equivalent
   hypotheses; only an explicitly replayed absolute lift may dechirp IQ.
3. **Merging hypotheses must not erase targets.** If two absolute lifts both
   pass independent replay, both remain final candidates until a later
   multi-target discriminator can separate them.
4. **No extrapolation-only merges.** A pair without measured temporal overlap
   is recorded as `not_compared_no_overlap` and remains separate.
5. **One receiver path at a time.** Alias grouping never combines radios or RX
   paths. Radio/paired products compare final path results later.
6. **GLRT64 proposes; other methods confirm.** Symbolwise, Anchor-8, QAM, and
   controls cannot create a trajectory component.
7. **Determinism is part of correctness.** Input order, worker count, retry,
   and process boundary cannot alter product bytes or IDs.
8. **All claims remain candidate-only.** A merged track is not satellite
   identity, attribution, payload evidence, or an independent trial.

## Why this stage is needed

Each probe independently searches the full configured CFO interval. A pilot
candidate can therefore appear at CFO coordinates separated by the symbol-rate
ambiguity spacing:

\[
\Delta f_{alias}=1/T_{symbol}=1/4.4\,\mu s=227,272.727\ \text{Hz}.
\]

The historical re-analysis found overlapping raw tracks that differed from
exactly one alias spacing by only 52--1,008 Hz RMS. Other apparent near-pairs
missed the nearest alias by 15.7--92.6 kHz RMS and must remain separate.

Represent the spacing internally as the exact rational

\[
\Delta f_{alias}=2{,}500{,}000/11\ \text{Hz},
\]

derived from 4.4 microseconds. Contracts store the numerator and denominator;
the repeating decimal is display metadata only. Centered modulo uses the
half-open interval `[-Δ/2, +Δ/2)`, including an explicit upper-bound wrap rule.
This prevents platform-dependent boundary rounding from changing component
membership.

Canonical CFO is useful for grouping duplicate hypotheses. It cannot select the
absolute CFO lift that is needed to dechirp IQ. The selected absolute lift must
continue to come from same-IQ replay against the GLRT64/control evidence.

## Current state and cut line

Already available and reviewed:

- Standard uses two independently searched 20 ms probes at offsets 0 and 25 ms
  in every 50 ms subwindow, with a full -400 to +400 kHz CFO search per probe.
- The production receiver-path work is fused into one `path-standard` job and
  publishes the raw pilot scan, raw trajectory bank, raw feedback/table, and
  persisted PNGs atomically.
- `leo.analysis.starlink.cfo_aliases` and the historical comparison tools prove
  the modulo/overlap idea offline and preserve the recent reports/figures.

The frozen planning evidence is:

- `reports/2026_08_26_20ms_window_comparison.md` for independent-search probe
  geometry and the original raw plots;
- `reports/2026_08_26_cfo_alias_canonicalization.md` for trial-132 modulo and
  same-IQ lift replay; and
- `reports/2026_08_20_recent_cfo_alias_history.md` for cross-capture accepted
  and rejected alias-pair distributions.

Not yet available in production:

- no persisted alias map or canonical branch bank;
- no explicit multi-target assignment between alias grouping and final fit;
- no observed-lift replay selected from a canonical branch bank;
- no final-bank-backed Standard reducers/UI; and
- no executable Research registry—the Research lane remains a parked design.

Implementation should extract and harden the reviewed offline arithmetic rather
than create a second formula. Offline reports remain numerical oracles, not
runtime dependencies.

## Target graph

```text
raw independent ±400 kHz pilot scan
  │
  ├── raw trajectory bank ────────────────> unmerged PNG
  │
  └── alias-map / overlap graph
         │
         ├── canonical merged trajectory bank ─> de-aliased PNG
         │
         └── observed absolute-lift replay
                │
                ├── zero, one, or several replay-supported lifts
                │
                └── final absolute-CFO trajectory bank ─> final PNG/table/report
```

The **canonical bank** feeds absolute-lift replay. The resulting **final
absolute-CFO bank** feeds the final trajectory table, radio reduction, paired
reduction, and the normal final UI view. A separately labeled validation replay
may consume the final bank, but it is not the selection replay that produced
the bank. Raw and canonical products remain independently visible.

## Product contracts

Do not mutate an existing product kind/schema pair. The current raw products
remain the source of truth and the new products are additive.

| Kind | Schema | Producer input | Required content |
|---|---:|---|---|
| `standard.trajectory-bank` | 2, existing | raw GLRT64 pilot scan | Immutable raw segmented fits and representatives. |
| `standard.cfo-trajectories-png` | 1, existing | raw bank + raw scan | The original unmerged figure. Its meaning and bytes are not repurposed. |
| `standard.cfo-alias-map` | 1, new | raw pilot scan + raw trajectory bank | Per observation: raw CFO, centered modulo residue, component-relative CFO, integer alias index, residual, raw trajectory ID, component ID; all accepted/rejected/not-compared pair decisions and exact input digests. |
| `standard.dealiased-trajectory-bank` | 1, new | alias map + raw bank | Canonical degree 1/2/3 fits, component membership, support IDs, branch intervals, diagnostics, truncation and no-merge reasons. |
| `standard.cfo-lift-replay` | 1, new | canonical bank + raw scan + exact raw IQ | Every observed absolute lift tried for every canonical component, GLRT64/control/QAM results, pass/fail status, and deterministic ordering evidence. |
| `standard.final-trajectory-bank` | 1, new | canonical bank + lift replay | Zero, one, or several replay-supported absolute-CFO linear/quadratic/cubic models per component, selected integer lifts, canonical/absolute coefficients, support, and replay receipts. |
| `standard.glrt64-final-trajectory-table` | 1, new | final bank + lift replay | Bounded machine-readable final equations and replay metrics for reducers, CLI and UI. |
| `standard.cfo-trajectories-dealiased-png` | 1, new | alias map + canonical bank | Before/after alias grouping on a shared fixed CFO axis. |
| `standard.cfo-trajectories-final-png` | 1, new | final bank + lift replay | Final replay-selected trajectories with baseline/corrected GLRT64 response. |

The changed terminal documents are also additive: `standard.path-report` v2,
`standard.path-presentation` v3, `standard.radio-report` v2, and
`standard.paired-report` v2. Their predecessors include the new final table and
final-bank digest. Existing report versions remain readable but are never mixed
into a new final reducer.

All scientific documents, and the registered metadata for PNG products, carry
`candidate_only=true`, `specificity_claimed=false`, and
`payload_decoded=false`.

Research uses the same contract shapes but exact `research.*` product kinds,
its own stage configuration digest, and its own run/promotion policy. A
Research product can never satisfy a Standard `ProductRequirement`, even when
the numerical payloads happen to be identical.

The direct scientific dependency closure is exact:

```text
pilot scan + raw bank
  └─> alias map
pilot scan + raw bank + alias map
  └─> de-aliased branch bank
path input binding + raw integrity + pilot scan + de-aliased bank + IQ
  └─> lift replay
de-aliased bank + lift replay
  └─> final bank
final bank + lift replay
  └─> final trajectory table
all declared raw/canonical/final products
  └─> path report v2 ─> radio report v2 ─> paired report v2
path report v2 + declared bounded plotting products
  └─> path presentation v3 ─> persisted PNG renderers
```

No later product recomputes an earlier stage and calls that recomputation a
dependency. PNG renderers are pure projections of registered JSON products and
never reopen IQ. The lift replay binds the exact V3 path input, raw-integrity
attestation, channel, edge, sample geometry, calibration state, and IQ closure.

### Contract bounds

Freeze bounds before implementation so malformed products cannot create an
unbounded graph or replay explosion:

| Inventory | Initial bound |
|---|---:|
| Raw representatives per path | 64 |
| Pair comparisons per path | 2,016 |
| Alias components per path | 64 |
| Raw observations referenced per component | 9,600 |
| Distinct observed lifts per component | 5 |
| Canonical polynomial models per component | 3 |
| Final replay-supported lifts per component | 3 |
| Published final trajectories per path | 64 |

Hitting a bound is `partial_coverage` with exact source/retained/truncated
counts. Truncation can never be reported as `complete` or `no_result`.

### Configuration authority

Define one strict `CfoDealiasConfigV1` and bind its canonical digest into every
new product. No call site supplies silent defaults. The pipeline definition
must explicitly set:

| Field | Initial reviewed value/policy |
|---|---|
| `symbol_duration_s` | `4.4e-6`; alias spacing is derived, never separately rounded. |
| `minimum_overlap_s` | `0.250` |
| `comparison_point_count` | `128`, including overlap endpoints |
| `maximum_alias_residual_hz` | `2_500.0` at every comparison point |
| `maximum_raw_representatives` | `64` |
| `maximum_alias_components` | `64` |
| `maximum_observed_lifts_per_component` | `5` |
| `maximum_final_lifts_per_component` | `3` |
| `polynomial_degrees` | exact ordered tuple `(1, 2, 3)` |
| `continuity_gap_s` | copied explicitly from the reviewed trajectory merge-gap authority |
| `association_gate` | reviewed frequency/slope/acceleration uncertainty gate ID |
| `association_penalties` | reviewed birth/death/missed-probe penalty document |
| `maximum_branches_per_component` | frozen from synthetic crossing and trial-132 review |
| `maximum_assignment_iterations` | finite reviewed bound; non-convergence is explicit |
| `replay_gate_version` | reviewed immutable gate ID, not an inline threshold |

The Standard and Research definitions may differ in probe geometry, but their
de-alias configuration is equal unless a separately reviewed Research release
intentionally changes it. Alias spacing is derived from the selected Qin pilot
symbol duration and is independent of sample rate, channel, and upper/lower
edge. Channel and edge remain mandatory source-binding inputs to scan and
replay; they are never inferred from CFO.

### Pure component interfaces

Keep numerical code below `leo.analysis.starlink` free of catalog, HTTP, CLI,
artifact, and scheduler imports. Freeze four narrow entry points:

```python
build_cfo_alias_map(raw_scan, raw_bank, *, config) -> CfoAliasMapV1
fit_dealiased_trajectories(raw_scan, raw_bank, alias_map, *, config) -> DealiasedTrajectoryBankV1
replay_observed_cfo_lifts(iq, raw_scan, canonical_bank, *, edge, config) -> CfoLiftReplayV1
select_final_trajectories(canonical_bank, replay, *, config) -> FinalTrajectoryBankV1
```

Every function validates exact predecessor digests, finite values, ordering,
and bounds at entry. It returns a typed document plus status; it never reads a
file or publishes an artifact. Renderers and the fused analyzer are adapters on
top of these functions.

## Numerical algorithm

### A. Raw trajectory bank

Run the existing GLRT64-only segmentation on raw independent-search
observations. It produces the immutable raw bank and raw candidates. Other
methods remain confirmers and are not trajectory proposers.

### B. Alias-equivalence graph

For each pair of raw representatives on the same receiver path:

1. Require a real measured overlap of at least 250 ms.
2. Sample the common interval on an exact deterministic grid containing both
   endpoints and 126 equally spaced interior points.
3. Compute the integer spacing (n=round(median(f_b-f_a)/\Delta f_{alias})).
4. Compute residuals: \(r(t)=f_b(t)-f_a(t)-n\Delta f_{alias}\).
5. Add an alias edge only if **every** sampled residual is within 2.5 kHz.
6. Record rejected comparisons, including the nearest alias index and RMS/max
   residual, so absence of a merge is auditable.

Connected components are canonical groups. A component can contain multiple
raw trajectory segments and several integer lifts. Tracks that do not overlap
are not merged merely by extrapolation.

Pair ordering is canonical `(start_s, end_s, trajectory_id)`. Component IDs are
digests of the ordered raw member IDs and accepted edge documents, not array
positions or display colors. Integer shifts are solved with a potential-aware
union/find or equivalent deterministic graph traversal. A contradictory alias
cycle makes only that component `insufficient_data`; the implementation must
not silently drop the least convenient edge. Other valid components may still
complete, while the path becomes `partial_coverage` because a declared
component was unresolved.

Persist two distinct canonical coordinates:

- `residue_cfo_hz`, centered into `[-Δf_alias/2, +Δf_alias/2)`, for a stable
  modulo display and cross-component diagnostics; and
- `component_cfo_hz`, unwrapped relative to the earliest-starting, then
  lowest-ID member, for continuous polynomial fitting.

This avoids wrap discontinuities while keeping the modulo position globally
interpretable.

For a model around declared epoch `t0`,

\[
f(t)=a_0+a_1(t-t_0)+a_2(t-t_0)^2+a_3(t-t_0)^3,
\]

an alias shift changes only `a0`. Slope `a1`, acceleration `2*a2`, and jerk
`6*a3` are invariant. Persist both coefficients and derived physical units so
radio comparison never accidentally compares absolute intercepts.

### C. Canonical observations and multi-target association

Alias components are ambiguity groups, not target identities. A single
component may still contain two simultaneous physical branches. Resolve that
before fitting one final curve:

1. Apply each member's integer alias shift to every supported GLRT64
   observation and retain the raw absolute lift as metadata.
2. Deduplicate only the exact same observation ID. If one observation maps to
   two canonical CFO values outside numerical tolerance, mark the component
   insufficient rather than choosing one.
3. Group observations by exact probe time. Alias-equivalent alternatives from
   one probe form one hypothesis set; distinct measured peaks remain separate
   nodes even when their canonical CFOs are close.
4. Build a directed acyclic association graph in time. Permit an edge only
   within the explicit gap bound and only when frequency, slope, acceleration,
   and uncertainty gates pass. Edge cost is a frozen weighted tuple, not an
   opaque learned score.
5. Solve deterministic minimum-cost path cover with explicit birth, death, and
   missed-probe penalties. This gives global one-to-one assignments and avoids
   a greedy nearest-neighbour swap when two branches cross.
6. Iteratively fit and reassign until assignments are unchanged or the bounded
   iteration limit is reached. Non-convergence is `insufficient_data`, never a
   last-iteration result presented as stable.
7. Collapse duplicate branches only when they have equivalent fitted values
   throughout real temporal overlap **and** their supporting observation-ID
   sets are identical or one is a strict alias-hypothesis duplicate of the
   other. Two different simultaneous peaks are never collapsed merely because
   their fitted curves are close.

The association configuration freezes maximum time gap, frequency/slope/
acceleration gates, birth/death/gap penalties, maximum branches, and maximum
iterations. Each accepted/rejected association edge and each duplicate collapse
is persisted with its reason. This is the layer that handles branch birth,
death, crossings, and the suspected two-target interval near 0--10 seconds.

### D. Canonical branch refit

For every resolved branch:

1. Split support at gaps larger than the explicit continuity bound.
2. Fit degrees 1, 2, and 3 using the existing deterministic robust fitter.
3. Persist coefficients in ascending powers of elapsed seconds from a declared
   branch epoch, residual RMS/max, support interval/count, and observation IDs.
4. Run family/representative selection only among models of the same resolved
   branch. A representative cannot consume observations assigned to another
   simultaneous branch.
5. Retain rejected model orders and their reasons; do not silently replace a
   failed cubic with a linear fit under the cubic identity.

### E. Absolute-lift replay

For each canonical branch representative, enumerate the bounded, finite set of
integer lifts actually observed on that branch. Do not synthesize every
mathematically possible lift in the search span. For every observed lift:

1. Convert canonical coefficients to absolute CFO coefficients.
2. Dechirp the exact raw IQ at that lift.
3. Rerun GLRT64 with its rolled same-IQ control; retain existing QAM and pilot
   confirmation outputs.
4. Classify the lift with a frozen replay gate and order passing lifts by:
   GLRT64 margin gain, control separation, support count, absolute alias index,
   then signed alias index.

If no lift satisfies the replay criterion, retain an explicit `no_result` or
`partial` receipt. If one lift passes, publish it as the final correction. If
multiple lifts pass on distinguishable simultaneous support, publish each as a
separate final candidate with one shared component ID and distinct branch/lift
IDs. Do not force a winner merely to simplify the table. Do not promote a
component just because it grouped cleanly.

The exact numerical replay gate must be frozen from the existing reviewed
GLRT64/control behavior during D0. Until then, tests use explicit injected gate
fixtures rather than embedding an unreviewed threshold in production code.

### F. Radio and paired comparison

Cross-path association happens only after each receiver path has a final bank.
Absolute CFO intercept is deliberately excluded because tuner/calibration
offsets and alias lift can differ between paths. For every overlapping pair,
evaluate on one exact common time grid:

\[
v(t)=df/dt,\qquad a(t)=d^2f/dt^2,\qquad j(t)=d^3f/dt^3.
\]

Compare RMS/max differences in slope, acceleration, and jerk with propagated
fit/timing uncertainty. Rebase polynomial epochs before evaluation; comparing
stored coefficients directly is invalid when `t0` differs. Use deterministic
one-to-one assignment so one path track cannot agree with two tracks on the
other radio. Persist unmatched tracks and rejection reasons. The result is
multi-path candidate agreement only—never phase coherence, statistical
independence, satellite attribution, or a replacement for per-path replay.

## Status algebra

Apply one status vocabulary to products, jobs, reducers, API, and UI:

| Condition | Component outcome | Path implication |
|---|---|---|
| No raw trajectory representatives after a complete scan | `no_result` | Complete search with no retained trajectory. |
| Valid alias graph, canonical fits, and at least one replay-supported lift | `complete` | Candidate final trajectories available. |
| Valid graph and fits, but no lift passes replay | `no_result` | Complete tested search; preserve all losing receipts. |
| Missing/gapped required IQ or too little support to fit/replay | `insufficient_data` | Path cannot claim a complete final search. A singleton with enough support is valid and is not penalized merely for lacking an alias pair. |
| Contradictory finite alias cycle or bounded assignment non-convergence | `insufficient_data` | Preserve the unresolved component; other components may publish, but the path is partial. |
| Any source/representative/lift truncation | `partial_coverage` | Propagates through radio/paired presentation. |
| Non-finite/tampered upstream value, digest mismatch, undeclared input, or contract violation | `failed` | Fail closed; publish no atomic path result. |

Mixed `complete + no_result` children reduce to `complete`, not partial.
Missing, failed, insufficient, or truncated declared children remain visible and
cannot be interpreted as a miss.

## Execution boundaries

### Standard lane

Add the pure stages inside the fused receiver-path analyzer after raw bank
fitting. Preserve the existing raw feedback/table/PNG as explicitly unmerged
inspection evidence. In parallel, run alias map → multi-target association →
canonical refit → observed-lift replay → final bank/table. The v2 path report,
v3 path presentation, v2 radio reducer, v2 paired reducer, API final table, and
default final PNG consume only the new final bank/table.

The first implementation remains one atomic `path-standard` job because the
current production graph is deliberately fused. Internally split the pure
functions and product construction; do not re-expand the database DAG unless
profiling later shows a measured need. Atomic publication must include the
complete declared inventory (preserved raw products plus the new terminal
versions) or publish nothing. A new run need not republish superseded v1/v2
report documents merely to preserve their historical readability.

For a 2×2 capture, topology remains exactly 8 jobs and 10 job edges: four path
jobs, two radio reducers, one paired reducer, and one paired presentation job.
With the contracts above, the registry output-spec inventory is expected to
move from 21 to 32:

- path job: 20 outputs (existing raw science and three PNGs, five new science
  products, v2 report, v3 presentation, and two new PNGs);
- radio reducer: 6 outputs (v2 report plus five PNG views);
- paired reducer: 1 v2 report;
- paired presentation: 5 PNG views.

D0 must freeze this inventory in a registry test. Any later count change needs
an explicit contract review rather than editing the assertion to match.

### Research lane

Use the identical pure algorithm with the Research probe pattern and its own
pipeline-definition/configuration digest. Research remains manual. Its
de-aliasing products must use lane-specific product/run identities and cannot
satisfy Standard dependencies.

Research may use the same fused four-analyzer topology, but it has a distinct
registry factory, stage keys or pipeline-lane discriminator, `research.*`
products, queue capacity, current pointer, and UI route. It cannot update the
ordinary Standard current analysis. The initial Research policy is one active
run per recording and lower scheduling priority than Standard.

### Resource bounds

- Alias comparison is CPU-only and bounded by `maximum_replayed_families` and
  maximum raw representatives.
- Never materialize an entire dwell or a corrected dwell per lift.
- Replay bounded probe batches only; reuse the existing one-second task model.
- Cap observed lifts per component and publish truncation if the cap is hit.
- Treat alias map and canonical fit as cheap CPU stages; preserve existing heavy
  tokens for raw scan and IQ replay.
- Initial performance target: alias graph + canonical refit below 5% of path
  science wall time and below 128 MiB incremental RSS on a 60-second path.
- Lift replay wall time scales with the number of observed lifts; record
  component/lift counts and measured replay time separately from orchestration.

## UI behavior

The recording detail page exposes three clearly named artifacts per path/radio/
paired subject:

1. **Unmerged CFO observations** — original raw CFO and raw fits.
2. **De-aliased components** — raw versus canonical grouping, fixed shared
   CFO axis, rejected-pair diagnostics, and alias spacing.
3. **Final replay-selected trajectories** — only the absolute trajectories
   actually used for correction.

The trajectory table gains columns for canonical component ID, selected integer
lift, raw/absolute equation, canonical equation, merge/support count, replay
gain, and status. Cross-radio comparison continues to compare slope,
acceleration, and jerk—not absolute CFO offset.

Default UI ordering is final → de-aliased → unmerged, while all three remain
one click away. The default final view must never hide a multi-lift component.
Plots use one fixed declared CFO y-domain per recording and show the domain in
artifact metadata. Colors are display-only and never identifiers.

## Test plan

### Unit and property tests

- Exact aliases at `±2,500,000/11 Hz` merge; modulo boundary vectors use the
  exact rational and the declared half-open interval.
- Adding any integer alias spacing changes only the fitted intercept and leaves
  slope, acceleration, jerk, association, and canonical residue invariant.
- Shuffled input, reversed pair iteration, 1/2/4 workers, and retry produce the
  same component/branch IDs and canonical JSON bytes.
- The historical 52 Hz RMS CH4 pair merges.
- Historical 15.7 kHz, 16.4 kHz, and 92.6 kHz near-pairs reject.
- Non-overlapping tracks remain separate without being mislabeled failures.
- Two parallel simultaneous peaks remain two branches, even if separated by
  almost one alias spacing.
- A synthetic crossing keeps pre/post identity under global assignment; the
  greedy nearest-neighbour counterexample must fail the oracle.
- Birth/death, an allowed missed-probe gap, and an over-limit gap produce the
  exact expected branch inventory.
- Duplicate families with the same observation IDs collapse; close fits with
  disjoint simultaneous IDs do not.
- Inconsistent alias cycles become an explicit insufficient component and a
  partial path; malformed/digest-inconsistent cycles fail the atomic job.
- Canonical refit retains degree 1/2/3, finite coefficients, and exact support
  closure.
- A shared raw observation cannot receive conflicting canonical values.
- Wrong absolute lift loses to the known correct lift under same-IQ replay.
- Two independently supported lifts both survive; a deterministic-order test
  proves the implementation does not discard the runner-up merely because it
  is second.
- No winning lift produces an explicit `no_result`; truncation cannot do so.
- Association non-convergence, maximum-branch truncation, and lift truncation
  exercise the frozen status table.
- Radio comparison accepts equal derivative functions with different epochs
  and CFO intercepts, rejects equal intercepts with incompatible derivatives,
  and enforces one-to-one matching through crossing/missing-path cases.

### Contract and lineage tests

- Every new product records exact predecessor digests and source-binding
  digests.
- `path-report` v2 consumes the exact final table; radio v2 consumes only exact
  path-report v2 children; paired v2 consumes only exact radio v2 children.
- The registry remains 8 jobs/10 edges for a 2×2 capture and has exactly 32
  output specs. A reducer cannot read an undeclared raw/canonical product.
- Changing raw IQ, edge, probe geometry, alias spacing, residual gate, replay
  gate, association configuration, or upstream bank invalidates exactly the
  affected descendants.
- Existing raw bank and unmerged PNG bytes remain unchanged.
- Retry/concurrent execution yields byte-identical JSON/PNG artifacts.
- Standard and Research dependencies, current promotion, and cache entries do
  not cross lanes.
- A forged Research product with identical bytes cannot satisfy a Standard
  requirement, and vice versa.
- Missing old-schema products render unavailable/legacy explicitly; no adapter
  relabels v1 raw output as v2 final output.

### Real-data regression tests

- Trial-132 reproduces its reviewed raw products byte-for-byte, reviewed alias
  components, branch inventory, and observed-lift replay outcome.
- The four August 20 historical captures reproduce the frozen alias map within
  tolerance.
- The 0--10 second region is evaluated without presupposing "two satellites."
  The reviewed golden classifies each apparent second branch as one of:
  `alias_duplicate`, `distinct_replay_supported_branch`, `control_like`, or
  `insufficient`. Only the second class supports the multi-target hypothesis,
  and even then remains candidate-only rather than satellite attribution.
- Noise, rolled IQ, wrong edge, gaps, truncation, and no-result controls remain
  candidate-only and do not create final trajectories.
- A deliberately alias-shifted copy of same IQ collapses to one canonical
  branch; a synthetic two-emitter IQ fixture yields two supported branches.

### End-to-end tests

- One compressed local 2×2 fixture executes raw → alias → canonical → replay →
  final products, seals once, and renders all three PNG variants.
- API/UI tests show all three views, distinct labels, fixed axes, bounded
  responses, missing-artifact failure state, and no raw-array leakage.
- Standard remains automatic; Research is manually queued and cannot starve
  Standard under capacity limits.
- Reanalysis failure leaves the prior current Standard run selected; a fully
  sealed new run promotes once. Research completion never changes that pointer.
- Kill/retry at each output publication boundary leaves either zero new
  products or the complete 32-spec run inventory, never a mixed raw/final run.

### Performance and implementation-parity tests

Benchmark the same fixed 60-second path with five warmups/measurements and
report raw scan, alias graph, assignment/refit, lift replay, rendering,
publication, wall time, CPU time, peak RSS, bytes read, and product bytes. The
acceptance gates are:

- raw scan numerical output and timing remain unchanged within noise;
- alias graph + association/refit stay below 5% of path science wall time and
  128 MiB incremental RSS;
- each replayed lift has an explicit count and time, so replay growth cannot be
  misreported as orchestration overhead;
- no unbounded nested worker pool is introduced.

Start with one clear Python reference implementation. Add a C/C++/Rust kernel
only if profiling identifies a measured hot loop. If acceleration is added,
retain the Python reference and run differential tests over exact boundaries,
randomized finite cases, crossings, and all frozen real summaries. Production
may select the native kernel only when its typed output matches the reference
within the frozen coefficient/residual tolerances; identifiers and serialized
documents must remain byte-identical.

## D0 review packet: decisions that must not be invented in code

Before implementation, produce one small, reviewable fixture packet containing:

1. exact rational alias/modulo boundary vectors;
2. accepted historical residual pairs (52--1,008 Hz RMS) and rejected holdout
   near-pairs (15.7--92.6 kHz RMS);
3. synthetic one-target aliases, two-target parallel/crossing, birth/death,
   gaps, duplicate families, noise, and corrupted-lineage cases;
4. distributions of association residuals and same-IQ replay gain/control
   separation from trial-132 plus held-out recent captures;
5. proposed association gates/penalties, iteration/branch bounds, and replay
   gate, with sensitivity plots around each threshold;
6. exact product/schema/dependency/output inventory; and
7. expected status for every fixture.

Choose thresholds from the reviewed positive/control separation, then freeze a
holdout set before looking at its outcome. Do not tune a threshold until the
0--10 s example looks like two targets. If positives and controls overlap, the
correct result is `insufficient_data` and an unresolved next step—not a weaker
gate.

## Implementation work packages

The work is modular, but not all packages can start at once. Freeze D0 first;
then the numerical, adapter, and UI-contract preparation can proceed in
parallel.

| Package | Scope | Depends on | Can run with | Required receipt |
|---|---|---|---|---|
| W0 — contracts/oracles | Typed documents, bounds, config, status table, exact rational vectors, reviewed replay gate | none | none; this freezes the interfaces | Contract round trips, invalid document matrix, approved golden manifest |
| W1 — alias graph | Pair comparison, potential union/find, canonical coordinates | W0 | W2 synthetic fixtures, W6 UI mocks | Unit/property/determinism matrix |
| W2 — multi-target association/refit | Probe nodes, path cover, birth/death/crossing, duplicate collapse, degree 1/2/3 fits | W0 | W1, W3 test harness | Synthetic crossing/two-target oracle and resource receipt |
| W3 — lift replay/final selection | Exact observed lifts, IQ correction, GLRT64/control gate, final bank/table | W0; W1/W2 typed fixtures | W6 UI mocks | Correct/wrong/multiple/no-lift controls and bounded replay benchmark |
| W4 — Standard adapter | Product specs/codecs, fused runner, source bindings, report/reducer versions, PNGs | W1–W3 | W5 after pure API freezes | 32-output atomic 2×2 vertical, lineage and crash/retry tests |
| W5 — Research lane | Manual independent registry/config/queue/current semantics | W1–W3 | W4, W6 | Lane isolation and 3×20 ms numerical parity tests |
| W6 — API/UI | Final/de-aliased/unmerged views, tables, fixed axes, failure states | W0 mocks; authoritative adapter after W4/W5 | W1–W5 | API budgets, Playwright, accessibility and corrupt-artifact tests |
| W7 — qualification | Trial-132/four-history replay, 0–10 s classification, benchmarks, rollout canary | W4; W5 for Research approval | none during final evidence review | Signed immutable receipts and reviewer-approved goldens |

Use an explicit red→green sequence:

- W1 starts with aliases remaining separate and near-aliases incorrectly
  merging; green is the frozen pair matrix.
- W2 starts with the current overlapping/merged branch behavior and a greedy
  crossing swap; green is exact branch birth/death/crossing assignment.
- W3 starts with the known failure of canonical-residue correction and the
  success of the observed upper lift; green is correct/wrong/multiple/no-lift
  replay classification.
- W4 starts with absent new products and a registry count of 21; green is the
  atomic 32-output registry and exact reducer closure.
- W5 starts with no executable Research lane; green is a separately queued,
  nonpromoting `research.*` run.
- W6 starts with only the raw trajectory view; green is truthful final,
  de-aliased, and unmerged rendering from persisted products.

Suggested ownership boundaries avoid shared-file collisions:

- pure science: `leo.analysis.starlink` plus component-owned tests;
- Standard contracts/codecs/products/runner/analyzer: `leo.analysis.standard`;
- Research registry/service: a separate `leo.analysis.research` package;
- presentation adapters and web components: `leo.presentation`, `leo.api`, and
  `web` only after generated/typed contracts exist;
- golden/report work: `tests/fixtures`, `reports`, and immutable receipts only.

No package updates a golden merely because a test changed. Goldens move only
after a field-level numerical review that explains every semantic difference.

## Checkpoints

| Checkpoint | Deliverable | Exit criteria |
|---|---|---|
| D0 | Frozen contracts, configuration and test vectors | Product/schema inventory, exact 32-output registry target, status algebra, association costs/gates, replay gate/order, and historical pair expectations independently reviewed. |
| D1 | Pure alias graph | Exact-rational/property matrix green; historical merge/reject pairs match; no IQ, catalog or presentation imports. |
| D2 | Multi-target association and canonical refit | Crossing/birth/death/duplicate/two-emitter matrix green; deterministic degree 1/2/3 branch bank; bounded convergence receipt. |
| D3 | Absolute-lift replay and final selection | Correct/wrong/multiple/no-lift same-IQ controls green; bounded resource receipt recorded. |
| D4 | Standard integration | 8-job/10-edge topology unchanged; 32 output specs publish atomically; raw/canonical/final products and PNGs have complete lineage. |
| D5 | Research integration | Independent manual lane, exact 3×20 ms schedule, no cross-lane reuse/promotion, capacity policy green. |
| D6 | Local real-data vertical | Trial-132 plus four historical captures match reviewed outcomes; 0–10 s branches classified without attribution. |
| D7 | UI and operational release | Three views/tables work, current-run semantics are truthful, performance budgets pass, Standard queue drain/reprocess/rollback checks pass. |

## Definition of done

This work is complete only when all of the following are true:

1. Every new Standard recording runs the independent ±400 kHz, 2×20 ms scan,
   preserves the raw bank/PNG, and publishes a final bank only after de-alias,
   multi-target association, canonical refit, and observed-lift replay.
2. Research runs the same boundary with 3×20 ms probes under a different run,
   product namespace, cache identity, queue policy, and UI tab.
3. The default trajectory table and cross-radio comparison consume final
   trajectories. They compare slope, acceleration, and jerk, never intercept.
4. A same-signal alias duplicate collapses, while two simultaneous supported
   branches survive. The 0–10 s historical evidence is reported as a tested
   hypothesis, not assumed to be two satellites.
5. Raw, de-aliased, and final artifacts are all available with a common full-
   recording time axis and fixed CFO y-domain.
6. Truncation, insufficient evidence, corruption, and no-result are distinct
   end to end; mixed complete/no-result radios do not become partial.
7. The local compressed 2×2 vertical, frozen real-data regressions, API/UI
   tests, deterministic retry test, and performance budget all pass from a
   clean checkout without QNAP or radio access.
8. A failed new Standard run never replaces the last sealed current run, and a
   Research run never promotes as Standard.

## Rollout

1. Implement and approve D0--D2 using the local reviewed corpus only.
2. Implement D3 and freeze the replay resource/correctness receipt before
   production wiring.
3. Ship Standard integration behind a new immutable pipeline definition; do
   not reinterpret already sealed runs.
4. Reprocess a bounded set of existing captures and compare raw, de-aliased,
   and final outputs against the current Standard output.
5. Promote the new Standard definition only after D6/D7 pass; retain the prior
   sealed current run until promotion succeeds.
6. Keep Research manual until its separate capacity qualification passes.

No new radio collection is required for this work.
