# Scanner production rollout: qualified 2.5 MS/s adaptive hopping

## Scope and measured basis

Deploy the receive-only host/ARM-userspace scanner and its UI, preserving the
300-second capture, 120 ms valid dwell, 20-minute cadence and 50/50 rate cycle.
The [bounded LNB report](2026_09_10_scanner_lnb_live_checkpoint.md) contains the
figures, exact bundle identities and retained evidence: 94.53% duty at 2.5 MS/s
with all visits screened, versus 94.28% capture duty but only 24.95% screening
coverage and a latched uniform policy at 5 MS/s. No firmware or FPGA update is
part of this deployment.

## Rate-specific promotion

`LEO_SCANNER_HOP_POLICY=adaptive` selects weighted hopping only for rates in
`LEO_SCANNER_ADAPTIVE_SAMPLE_RATES_HZ`. Set the latter to `2500000` for this
rollout. Other scheduled rates retain fixed-order hopping. GLRT remains advisory
and unavailable results never assert that a channel is empty. The default
allowlist is both supported rates, preserving existing opt-in behavior; the
default policy remains fixed. Invalid, empty or duplicate rates fail validation.

This is runtime policy selection, not a change to published intent contracts or
the canonical sample-rate/bandwidth schedule. Existing recordings cannot be
relabelled across hopping kinds on retry. The immutable live-tested ARM bundle
is unchanged. Adaptive 5 MS/s promotion remains deferred pending CPU and
intentional-skip health work; this rollout does not claim that limitation fixed.

## Paused-cadence queue collision

Read-only inspection found the old acquisition service repeatedly restarting
while the web UI's capture authority remained paused. Its scanner enqueue used
`coalesce_pending_kind=False`, unlike ordinary cadence enqueue. A second due
scanner intent violated the catalog's one-pending-cadence-kind unique index.

Scanner enqueue now uses the catalog's existing transactional coalescing port.
Superseded pending intent records remain in history as cancelled; the newest
pending intent is retained, and leased work is not displaced. No database
constraint is weakened and no production row is manually deleted or rewritten.

## Pre-deployment checks

- 199 CLI, radio, scanner, storage and API tests passed, including real fixture
  captures through both rate-specific runtime paths and read-only retry.
- 14 explicitly PostgreSQL-marked acquisition-operation tests passed in unique
  schemas in `leo_qualification`, including concurrent scanner enqueue.
- The supervisor fixture now enforces the same one-pending-kind invariant as
  production, and the paused multi-slot regression preserves cancelled history.
- Ruff and whitespace checks passed.

The dependency's hosted Python 3.11 paired-recorder failures are pre-existing on
its remote main; they are not reported as passing. Production uses Python 3.14
and must additionally pass frozen installed-runtime checks before activation.

## Deployment and verification protocol

Publish the report and source, fast-forward remote default branches, stage the
exact main revision, and validate the sealed non-editable runtime. Keep capture
paused during API/acquisition cutover. Perform one authorized, bounded 300-second
2.5 MS/s LNB verification with the deployed runtime and production stores, inspect
source continuity, valid duty, detector coverage and UI visibility, then resume
scheduled capture as explicitly requested. Record actual outcomes separately;
the plan above is not evidence that deployment or verification has completed.
