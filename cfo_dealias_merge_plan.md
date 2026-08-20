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

Canonical CFO is useful for grouping duplicate hypotheses. It cannot select the
absolute CFO lift that is needed to dechirp IQ. The selected absolute lift must
continue to come from same-IQ replay against the GLRT64/control evidence.

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
                └── final absolute-CFO trajectory bank ─> final PNG/table/report
```

Only the **final absolute-CFO bank** feeds corrected replay, the final
trajectory table, radio reduction, paired reduction, and the normal final UI
view. Raw and canonical products remain independently visible.

## Product contracts

Do not mutate existing persisted Standard products. Introduce additive, bounded
v1 products and wire their exact digests into all descendants.

| Product | Producer input | Required content |
|---|---|---|
| `standard.cfo-alias-map.v1` | raw pilot scan + raw trajectory bank | Per observation: raw CFO, canonical CFO, integer alias index, residual, raw trajectory ID, component ID; pair decisions and exact input digests. |
| `standard.dealiased-trajectory-bank.v1` | alias map + raw bank | Canonical degree 1/2/3 fits, component membership, support IDs, fit diagnostics, truncation and no-merge reasons. |
| `standard.cfo-lift-replay.v1` | canonical bank + raw scan + raw IQ | Every observed absolute lift tried for every canonical component, GLRT64/control/QAM results, and selected-lift reason. |
| `standard.final-trajectory-bank.v1` | canonical bank + lift replay | Final absolute-CFO linear/quadratic/cubic models, selected integer lift, canonical coefficients, absolute coefficients, support, and replay receipt. |
| `standard.cfo-trajectories-unmerged-png.v1` | raw bank + raw scan | Raw independent-search CFO observations and raw fits. |
| `standard.cfo-trajectories-dealiased-png.v1` | alias map + canonical bank | Before/after alias grouping on a shared fixed CFO axis. |
| `standard.cfo-trajectories-final-png.v1` | final bank + lift replay | Final replay-selected trajectories with the baseline/corrected GLRT64 response. |

All documents must carry `candidate_only=true`,
`specificity_claimed=false`, and `payload_decoded=false`.

The existing `standard.cfo-trajectories-png.v1` remains readable as legacy raw
evidence. New UI code must use the explicit new names rather than changing its
meaning in place.

## Numerical algorithm

### A. Raw trajectory bank

Run the existing GLRT64-only segmentation on raw independent-search
observations. It produces the immutable raw bank and raw candidates. Other
methods remain confirmers and are not trajectory proposers.

### B. Alias-equivalence graph

For each pair of raw representatives on the same receiver path:

1. Require a real measured overlap of at least 250 ms.
2. Sample the common interval deterministically.
3. Compute the integer spacing (n=round(median(f_b-f_a)/\Delta f_{alias})).
4. Compute residuals: \(r(t)=f_b(t)-f_a(t)-n\Delta f_{alias}\).
5. Add an alias edge only if **every** sampled residual is within 2.5 kHz.
6. Record rejected comparisons, including the nearest alias index and RMS/max
   residual, so absence of a merge is auditable.

Connected components are canonical groups. A component can contain multiple
raw trajectory segments and several integer lifts. Tracks that do not overlap
are not merged merely by extrapolation.

### C. Canonical refit

For every component:

1. Apply each member's integer alias shift to its supported GLRT64
   observations.
2. Deduplicate identical observation IDs; disagreement on a canonical CFO is a
   hard failure.
3. Refit linear, quadratic, and cubic canonical models with the existing
   deterministic fitter and its residual/EM gates.
4. Preserve branch birth/death intervals. Do not force components with a gap
   into one continuous polynomial.
5. Produce a family/representative selection within the component only.

### D. Absolute-lift replay

For each canonical representative, enumerate the finite set of observed
integer lifts from its raw component. For every lift:

1. Convert canonical coefficients to absolute CFO coefficients.
2. Dechirp the exact raw IQ at that lift.
3. Rerun GLRT64 with its rolled same-IQ control; retain existing QAM and pilot
   confirmation outputs.
4. Select one lift only by the frozen replay ordering: GLRT64 margin gain,
   then control separation, then deterministic lift/order tie-break.

If no lift satisfies the replay criterion, retain an explicit `no_result` or
`partial` receipt. Do not promote a canonical component to a final correction
just because it grouped cleanly.

## Execution boundaries

### Standard lane

Add the stage inside the fused receiver-path analyzer after raw bank fitting
and before trajectory feedback. Preserve the raw bank and raw PNG first. The
final path report, radio reducer, paired reducer, API trajectory table, and
default final PNG consume only the final bank.

### Research lane

Use the identical pure algorithm with the Research probe pattern and its own
pipeline-definition/configuration digest. Research remains manual. Its
de-aliasing products must use lane-specific product/run identities and cannot
satisfy Standard dependencies.

### Resource bounds

- Alias comparison is CPU-only and bounded by `maximum_replayed_families` and
  maximum raw representatives.
- Never materialize an entire dwell or a corrected dwell per lift.
- Replay bounded probe batches only; reuse the existing one-second task model.
- Cap observed lifts per component and publish truncation if the cap is hit.
- Treat alias map and canonical fit as cheap CPU stages; preserve existing heavy
  tokens for raw scan and IQ replay.

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

## Test plan

### Unit and property tests

- Exact aliases at `±227,272.727 Hz` merge; shuffled input order is identical.
- The historical 52 Hz RMS CH4 pair merges.
- Historical 15.7 kHz, 16.4 kHz, and 92.6 kHz near-pairs reject.
- Non-overlapping, crossing, and parallel distinct tracks reject.
- Inconsistent alias cycles fail closed.
- Canonical refit retains degree 1/2/3, finite coefficients, and exact support
  closure.
- A shared raw observation cannot receive conflicting canonical values.
- Wrong absolute lift loses to the known correct lift under same-IQ replay.
- No winning lift produces an explicit non-final outcome.

### Contract and lineage tests

- Every new product records exact predecessor digests and source-binding
  digests.
- Changing raw IQ, edge, probe geometry, alias spacing, residual gate, replay
  configuration, or upstream bank invalidates descendants only.
- Existing raw bank and unmerged PNG bytes remain unchanged.
- Retry/concurrent execution yields byte-identical JSON/PNG artifacts.
- Standard and Research dependencies, current promotion, and cache entries do
  not cross lanes.

### Real-data regression tests

- Trial-132 reproduces its reviewed alias components and observed-lift replay
  outcome.
- The four August 20 historical captures reproduce the frozen alias map within
  tolerance.
- Noise, rolled IQ, wrong edge, gaps, truncation, and no-result controls remain
  candidate-only and do not create final trajectories.

### End-to-end tests

- One compressed local 2×2 fixture executes raw → alias → canonical → replay →
  final products, seals once, and renders all three PNG variants.
- API/UI tests show all three views, distinct labels, fixed axes, bounded
  responses, missing-artifact failure state, and no raw-array leakage.
- Standard remains automatic; Research is manually queued and cannot starve
  Standard under capacity limits.

## Checkpoints

| Checkpoint | Deliverable | Exit criteria |
|---|---|---|
| D0 | Frozen contracts and test vectors | Product names, status algebra, replay ordering, and historical pair expectations reviewed. |
| D1 | Pure alias graph and canonical refit | Unit/property matrix green; no IQ or catalog imports. |
| D2 | Absolute-lift replay | Correct-lift/wrong-lift controls green; bounded resource receipt recorded. |
| D3 | Standard integration | Raw, canonical, and final products/PNGs published with complete lineage. |
| D4 | Research integration | Independent manual lane, parity on shared probe offsets, no cross-lane reuse. |
| D5 | Local real-data vertical | Trial-132 plus four historical captures match reviewed outcomes. |
| D6 | UI and operational release | Three views/tables work; Standard queue drain and rollback checks pass. |

## Rollout

1. Implement and approve D0--D2 using the local reviewed corpus only.
2. Ship Standard integration behind a new immutable pipeline definition.
3. Reprocess a bounded set of existing captures; retain old raw/final evidence.
4. Compare final replay-selected results against the current Standard output.
5. Promote the new Standard definition only after D5/D6 pass.
6. Keep Research manual until its separate capacity qualification passes.

No new radio collection is required for this work.
