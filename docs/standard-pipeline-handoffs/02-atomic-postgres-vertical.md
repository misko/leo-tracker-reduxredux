# Handoff 02 — Atomic PostgreSQL Standard vertical

## Goal

Prove the typed execution machinery independently of expensive science by
running a manifest-authoritative multi-scope DAG through real PostgreSQL,
compressed `RecordingStore`, pinned artifacts and product-only reducers.

## Starting point

- `compile_standard_run_plan()` produces 43 jobs and 94 direct edges for 2×2.
- Claims carry exact scope, product dependency node IDs, resource class and IQ
  access.
- Verified receiver-path IQ access, full raw attestation, release authority,
  timeouts and resource limits exist.
- The in-flight foundation correction adds `commit_stage_result`: one transaction
  for lease validation, complete declared outputs, consumed IDs, product rows,
  dependency rows, lineage sealing and job completion.
- A complete typed Standard production vertical does not yet exist.

## Required implementation

1. Finish and use the atomic typed stage-result API. No typed analyzer may call
   per-product registration followed by a separate completion transaction.
2. Validate exact worker authority immediately after input construction and
   immediately before the atomic commit. Catalog validation must bind the lease,
   attempt, run release, node, scope, declared output inventory and exact
   predecessor inventory.
3. Implement the concrete run-bound `SubjectBindingReader` adapter.
4. Build a minimal test registry:
   - four path input-binding nodes;
   - two product-only radio inventory reducers;
   - one product-only paired inventory reducer.
   It must exercise heterogeneous scopes without duplicating the expensive
   detector.
5. Publish immutable artifacts through the pinned store. Artifact publication
   may precede the DB transaction; on failed commit it is an unreferenced,
   recoverable orphan, never an authoritative catalog product.
6. Seal a run manifest v2 containing the exact expanded nodes, direct edges,
   subject snapshots, raw attestation, worker authority and products.

## Required tests

- Exact 7-node minimal vertical and exact full 43-job/94-edge plan inventory.
- Fan-in cannot claim until every exact child succeeds.
- Reducer cannot open IQ or read undeclared, foreign-run, foreign-release,
  foreign-scope or extra products.
- Multi-output stage is all-or-nothing under lease loss, crash before/after each
  artifact, authority change and duplicate retry.
- Mutation inside IQ-provider construction is detected before analyzer access.
- Mutation at pre-commit injection leaves no catalog products and does not
  consume an attempt.
- Eight identical workers publish one exact result; retries return identical
  product IDs/digests and seal once.
- Worker crash, timeout, SIGTERM/SIGKILL, heartbeat loss and expired lease leave
  no partial authoritative state.
- Root/recordings/artifact child rename-to-symlink and caller-FD close remain on
  retained inodes. Lexical QNAP variants make zero target syscalls.
- Output count/bytes, IQ block size, stage wall time and heavy semaphore are
  enforced, including max 2×2 concurrency.
- Current analysis is unchanged when the new run fails.

## Verification

Use a disposable real PostgreSQL schema at the sole Alembic head and a small
compressed local RecordingStore fixture. Assert exact jobs, direct edges,
products, dependencies, attempts, run manifest and current-promotion state by
database query. Run every injected failure fence at least once and the key race
tests repeatedly.

## Completion evidence

- One committed vertical test with exact counts.
- Atomicity/concurrency/failure-fence receipts.
- Ruff, mypy, migration upgrade/downgrade and focused suites green.
- Independent PASS with no P0/P1.
