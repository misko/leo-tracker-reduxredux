# Handoff 01 — Station catalog and run-subject binding

## Goal

Turn the pinned station authority into immutable capture-time lineage for LIVE
and IMPORT recordings, while retaining an explicitly weaker TEST-only authority
for trial-132. Produce exact run-bound `StandardPathInputBindV2` and
`StandardPairInputBindV2` documents without fabricating calibration.

## Starting point

- `src/leo/station/authority.py` defines topology, verified-manifest snapshot,
  capture hardware binding and TEST fixture authority.
- `src/leo/station/pinned_loader.py` supplies retained-dirfd, no-follow,
  digest-pinned reads.
- `src/leo/pipeline/subjects.py` is the narrow subject-binding port.
- Catalog capture lineage and normalized scopes exist, but ordinary acquisition
  does not yet ingest station topology independently of calibration publication.
- The execution-foundation correction is adding immutable run-bound subject
  snapshots. Build on that API; do not reintroduce live profile/timing reads.

## Required implementation

1. Add an immutable catalog representation of one approved topology document
   and its exact radio/RX/physical-path/hardware-epoch interval assignments.
2. Register or resolve station topology before capture reconciliation. This is
   hardware identity only; do not require or create frequency calibration.
3. Reconcile every verified manifest stream against the exact station snapshot:
   session, manifest digest, interval, radio ID, serial, transport/endpoint and
   applied receiver inventory.
4. Persist every capture path atomically using the existing composite
   `(session_id, stream_id, receiver_id)` identity. Never rewrite the
   `RadioStream` composite primary key.
5. Resolve calibration separately for the complete capture interval. When none
   exists, emit the typed `uncalibrated_prior`; never synthesize a calibration
   digest or physical-frequency association.
6. For reviewed TEST fixtures, accept only an exact digest-pinned
   `FixturePathAuthorityV1`. It must remain evidence-only, non-current,
   nonpromotable, and unable to claim physical/calibration association.
7. At typed run creation, freeze the complete subject documents into immutable
   run-bound rows. All worker reads use `(run_id, scope)` and the frozen digest.

## Required tests

- Topologies: 1 radio × 1 RX capture, 1×2, 2×1, mixed 2+1 and 2×2.
- Repeated local stream IDs in different sessions remain isolated.
- Reject missing/extra/duplicate receiver, omitted stream, invented stream,
  radio/serial/endpoint substitution, requested-vs-applied substitution,
  reordered/retargeted manifest, partial hardware epoch and epoch-boundary
  crossing.
- Resolve a historical capture inside an old epoch even after wall-clock expiry;
  reject only if the capture interval itself is outside the epoch.
- Missing calibration produces `uncalibrated_prior` and disables tuned-frequency
  association while preserving baseband candidate analysis.
- Later-added calibration invalidates only frequency-binding descendants, not
  raw/baseband ancestors.
- TEST authority remains visible as evidence, never current/promotable, and
  cannot acquire physical/calibration fields through JSON or SQL mutation.
- Populated previous-to-head migration leaves unprovable legacy paths explicitly
  unresolved; no fabricated backfill.
- Eight concurrent identical reconciliations are idempotent; conflicting
  topology/path data fails closed.
- Direct SQL UPDATE/DELETE/late INSERT tests prove immutable topology, assignments
  and run snapshots.

## Verification

Run focused station, recording, catalog, migration and processing suites against
disposable PostgreSQL. Confirm one Alembic head, Ruff and mypy clean. Obtain an
independent review specifically reproducing RX omission, invented stream,
epoch-boundary, TEST promotion and post-run live-state drift attacks.

## Completion evidence

- Commit SHA and migration head.
- Exact test counts/commands.
- One real-PostgreSQL 2×2 capture reconciliation receipt.
- Independent PASS with no P0/P1.
