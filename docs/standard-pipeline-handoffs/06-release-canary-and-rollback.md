# Handoff 06 — Release candidate, canary and rollback

## Goal

Qualify Standard-v2 as the only automatic ordinary-capture pipeline without a
new long radio campaign. Use existing recordings and a short bounded operational
canary only if needed for service behavior, not scientific acceptance.

## Prerequisites

- G0–G5 of `standard_pipeline_plan.md` pass.
- Full 40-character staged Git SHA, graph/config/environment/executable digests
  are installed and validated.
- Complete real-PostgreSQL vertical, reviewed trial-132 regression, durable cache,
  retention recovery and production presentation adapter are independently
  passed.

## Required procedure

1. Register a new immutable release row with exact full SHA and graph authority.
   Never reuse `standard-v1` or a human semver as authority.
2. Drain or defer incompatible queued releases without consuming attempts.
3. Shadow-run existing reviewed recordings; do not acquire a 24-hour corpus.
4. Compare old current and Standard-v2 candidate-only results without promoting.
5. Run bounded max-topology load using existing local IQ. Record CPU, RSS, disk
   read/write, artifact bytes, database time, cache hits/misses and backlog.
6. Exercise worker restart, timeout, lease expiry, artifact orphan reconciliation,
   retention claim/restore and failed reprocess.
7. Promote one sealed canary run atomically and verify CLI/API/UI exact release,
   hierarchy, plots and lineage.
8. Roll back current promotion to the prior sealed run without rewriting or
   deleting either run, products or shared derivations.
9. Make Standard-v2 the default only after the rollback drill passes.

## Required gates

- Fresh-worker and warm-application timing reported separately; no false
  filesystem-cold-cache claim.
- At least five bounded repetitions for runtime distribution after correctness
  is frozen.
- Enforced CPU/RSS/output/wall limits for max 2×2 topology under the configured
  worker pool.
- Zero accepted output from an incompatible or changed release.
- Restart cannot change numerical bytes or product closure.
- Retention never removes current/held/campaign/dependency-protected data.
- Old/missing v1 products remain readable and render unavailable/not-run honestly.
- No production labels claim Starlink detection, attribution, payload,
  phase-coherent combination or independent trials.
- Cutover verifier checks exact Alembic head, authority triggers enabled with the
  expected definitions, pinned roots and current deployed release.

## Completion evidence

- Immutable release and canary run IDs.
- Performance/resource receipt using existing IQ.
- Restart, retention and rollback receipts.
- Production CLI/API/Playwright evidence over the LAN endpoint.
- Independent final completion audit mapping every G0–G6 and definition-of-done
  item to authoritative evidence.
