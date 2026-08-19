# Handoff 05 — Production CLI, API and browser binding

## Goal

Bind the independently passed Standard-v2 operator/presentation contracts to the
authoritative catalog, run-manifest and artifact resolvers. Preserve the existing
recordings UI while making per-path/radio/paired analysis discoverable,
reprocessable and visibly versioned.

## Starting point

- Typed hierarchy/detail/view, eligibility, state, stale reason, axis proof and
  bounded presentation contracts exist.
- Fixture-backed contract/UI tests independently passed.
- Production intentionally leaves the Standard-v2 read port unbound and returns
  typed 503; there is no fixture fallback.
- CLI dry-run/search/reprocess models exist but need an authoritative backend.

## Required implementation

1. Implement one production read repository over exact current sealed run or an
   explicitly selected TEST evidence run. Resolve and verify run manifest,
   products, dependencies and pinned artifacts before projection.
2. Return exactly three top-level rows for a dual-radio recording:
   `Paired Radio0 + Radio1`, `Radio0`, `Radio1`, with exact RX expansion IDs.
3. Expose six bounded aligned-time views: quality, power, waterfall, pilot metric,
   CFO/trajectories and stage matrix. Preserve authoritative full-source extrema
   through decimation and at least one point per source-backed lane.
4. Never read raw IQ in API/UI. Do not return unbounded candidate arrays or
   per-probe raw products.
5. Implement CLI:
   - search/list by state, source, tag and pipeline version;
   - show hierarchy, release, cache lineage and product availability;
   - dry-run reprocess showing exact stale frontier with zero mutation;
   - queue/wait explicit reprocess under the exact selected release.
6. Eligibility matrix:
   LIVE and IMPORT ordinary captures are automatic/current eligible when healthy;
   TEST is explicit evidence-only but searchable/viewable with an unmistakable
   label and never current; QUALIFICATION/CALIBRATION/ACCEPTANCE are suppressed.
7. Promote only after the complete sealed run, aggregate reducers and presentation
   products validate. Failed reprocess leaves prior current views unchanged.

## Required tests

- Real-PG/API/Playwright 1×1, 1×2, 2×1, mixed 2+1 and 2×2 hierarchies.
- Current, stale, partial, failed, not-run, purged/unavailable and cache-hit rows.
- TEST visibility/nonpromotion and IMPORT automatic/current behavior.
- Four visibly/accessibly named RX lanes at minimum point budget; exact shared
  time domain and honest frequency/time orientation.
- Candidate-only vocabulary rejects attribution, target presence, detection,
  phase coherence, payload and independent-trial synonyms.
- Artifact missing/tamper/catalog drift becomes unavailable/503, never stale
  fallback or fabricated empty results.
- GET/HEAD only, mutation methods 405, bounded pagination/count/byte budgets.
- `reprocess --dry-run` proves zero backend mutation; concurrent queue is
  idempotent and typed conflicts have stable exits in human/JSON modes.
- Existing recordings production Playwright tests remain green and LAN page load
  meets a measured reasonable response budget.

## Completion evidence

- Production port is bound; typed 503 remains only for genuine configuration or
  authority failure.
- CLI human/JSON receipts and API contract snapshots.
- Production-like Playwright run showing all plots and hierarchy.
- Independent security/scientific-language review PASS.
