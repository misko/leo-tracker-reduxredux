# Standard-v2 implementation handoffs

These handoffs cover the work that remains after the bounded foundation,
science, station-authority and presentation-contract slices. They are execution
documents, not a replacement for `standard_pipeline_plan.md`.

## Non-negotiable context

- The target is the only automatic Standard pipeline for eligible ordinary
  recordings. It operates independently on every receiver path, then performs
  product-only radio and paired reduction.
- Evidence is permanently candidate-only: no Starlink attribution, target
  presence, phase coherence, payload decoding or statistical-independence
  claim.
- The protected regression input is
  `/srv/bulk/leo/test-corpus/trial-132-four-path-v1`. Automated tests must not
  depend on QNAP. The archive beneath
  `/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1` is
  read-only reference data; repository code must never create, modify, move,
  rename or delete anything beneath `/mnt/qnap01`.
- Full 40-character Git SHA is the pipeline release authority. Family/semver is
  display metadata only.
- Persisted v1 contracts are immutable. New semantics use additive kinds and
  schema versions.
- Reusable scientific payloads contain stable computation identity only.
  Run/job/product IDs and the consuming release belong in run-owned membership
  lineage.
- Raw-IQ integrity verification is non-cacheable. An exact rerun may perform
  zero scientific analyzer calls, but it must still verify the raw recording.
- Reducers have no IQ authority and consume only the exact persisted dependency
  inventory compiled from the verified manifest.

## Current checkpoint

| Area | Evidence | State |
|---|---|---|
| Frozen architecture | `standard_pipeline_plan.md`, commit `67536ba` | complete |
| Protected corpus | local protected copy plus verification ledger | complete |
| Typed scope/DAG foundation | commits through `5e181a0` | final atomicity correction in flight |
| Pure Standard science | commits through `6c8bdc3` | final source-binding/config correction in flight |
| Station topology contracts | `bf2e651`, `8de6dcf` | independent re-review active |
| Presentation contracts/UI | commits through `161ffd6` | independently passed; production port unbound |
| Durable reuse | schema scaffolding only | not complete |
| Production vertical | no complete typed Standard vertical | not complete |
| Release canary | no Standard-v2 canary/rollback receipt | not complete |

## Recommended agent order

1. [01 — Station/catalog integration](01-station-catalog-and-subject-binding.md)
2. [02 — Atomic PostgreSQL vertical](02-atomic-postgres-vertical.md)
3. [03 — Production analyzers and full science](03-production-analyzers-and-science-vertical.md)
4. [04 — Durable reuse, retention and manifest v2](04-derivation-cache-retention-and-manifest.md)
5. [05 — Production CLI/API/UI binding](05-production-operator-and-browser-binding.md)
6. [06 — Release candidate, canary and rollback](06-release-canary-and-rollback.md)

Do not start a downstream handoff by weakening an upstream gate. If an upstream
contract is insufficient, amend it additively with its own tests and request an
independent review.
