# Handoff 04 — Derivation cache, retention and run manifest v2

## Goal

Make deterministic scientific computation reusable across reprocess runs while
preserving exact producing/consuming release provenance, raw integrity,
reference-aware retention and immutable run membership.

## Starting point

- Stage derivation and derivation-output schema scaffolding exists.
- Typed derivation keys distinguish stable upstream content identities from
  run-owned product IDs.
- Products associated with derivations are conservatively excluded from legacy
  purge; complete shared-blob reclamation is not implemented.
- No authoritative cache-hit execution path or run-manifest v2 resolver exists.

## Required implementation

1. Freeze a per-stage derivation key over:
   stage/algorithm/schema identity, stage-specific implementation/config and
   environment digests, typed scope, exact selected raw stream/chunk closure,
   stable upstream derivation/output identities, calibration applicability,
   timing/synchronization inputs and external reference snapshots.
2. Keep full pipeline release outside the reusable inner key where equivalence is
   reviewed. Every run-owned membership still records producing release,
   consuming release and `reused_from` lineage.
3. Perform mandatory raw integrity before any cache decision.
4. On hit, safely read and digest-verify the immutable artifact, revalidate exact
   key material and create a new run-owned product membership/dependency closure
   without invoking the analyzer.
5. On concurrent miss, publish one derivation/output. Losers reload and compare
   exact bytes/metadata; conflict on any difference.
6. Seal `AnalysisRunManifestV2` with the exact expanded graph, subject bindings,
   raw attestations, release authority, derivation decisions, direct product
   dependencies and final products.
7. Implement reference-aware shared-blob retention:
   stable-lock every referencing available/held/current/campaign binding, claim
   eligibility, atomically move the blob to trash, then commit all tombstones,
   derivation availability and retention event together. Restore on pre-commit
   crash. Never delete a blob still referenced elsewhere.

## Invalidation matrix

- Exact rerun: zero scientific analyzer calls, but raw integrity still reads IQ.
- Renderer-only change: numerical science reused; presentation recomputed.
- Tracker config/implementation change: validation/quality/power/waterfall/
  schedule/pilot reused; tracker and descendants recomputed.
- Pilot config change: pilot and every descendant recomputed.
- One path chunk change: only that path and aggregate descendants recomputed.
- Timing/synchronization-only change: path science reused where selected IQ and
  path semantics are identical; aggregate timing/presentation recomputed.
- Added/changed calibration: baseband ancestors reused; frequency-binding and
  association descendants recomputed.
- TLE/reference snapshot change: only consumers and descendants recomputed.
- Partial/insufficient becomes complete: affected stage and descendants cannot
  reuse an ineligible terminal.
- Catalog URI relocation with identical immutable content: science may reuse;
  membership/presentation provenance refreshes.

## Required tests

- Spy counters for analyzer calls, IQ bytes and per-stage hit/miss decisions.
- Eight-worker identical miss, crash before/after artifact/row/seal, collision
  and exact retry.
- Artifact tamper/truncate, catalog digest/size drift, copied URI, root/child
  symlink swap and zero QNAP syscalls.
- No run/job/product IDs or consuming-release labels inside reusable bytes.
- Old failed reprocess never displaces the old current run.
- Shared blob remains while any current/held/campaign/available dependency
  closure references it; final eligible reclamation is recoverable.
- Populated migration, downgrade quarantine and immutable SQL fences.

## Completion evidence

- Matrix report showing exact recomputation frontier and IQ/analyzer counts.
- Real-PG concurrency and retention recovery receipts.
- Run-manifest v2 resolver independently reloads and matches catalog/artifacts.
- Independent PASS with no P0/P1.
