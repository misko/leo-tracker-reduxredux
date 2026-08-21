# Durable single-owner acquisition queue

## Problem

The capture supervisor previously held dwell and scanner deadlines only in process memory.
Analysis backpressure advanced the dwell deadline without retaining an intent, and process restart
forgot scanner work waiting behind a completed dwell. Host-local locks prevented two users from
opening the same Pluto, but allowed independent operations on different configured radios.

The operational requirement is stricter: retain scheduled acquisition intent and allow exactly one
radio-owning operation across the station at any instant.

## Implemented design

`acquisition_operation` is an independent PostgreSQL queue for radio work. It does not reuse the
analysis queue because acquisition has different ownership, ordering, and backpressure semantics.

Each row records:

- an immutable idempotency key, operation kind, payload, and scheduled time;
- `pending`, `leased`, `succeeded`, `failed`, or `cancelled` state;
- attempt count, bounded retries, lease owner, heartbeat/expiry, outcome, and error;
- enough dwell payload to execute after supervisor restart without reconstructing private state.

Claims serialize on a PostgreSQL transaction advisory lock and a partial unique index independently
proves that at most one row can be leased. `FOR UPDATE SKIP LOCKED` makes concurrent claimers safe.
An expired lease is returned to `pending` until its attempt budget is exhausted. A stale owner cannot
complete a recovered operation.

Cadence keys are aligned to UTC interval slots. Repeated enqueue of one slot returns the original row;
reuse of that key with different intent fails closed. The supervisor persists a due dwell before
checking processing backpressure. Backpressure therefore suppresses execution while leaving the dwell
visible and pending. A committed or degraded dwell persists exactly one scanner operation keyed to its
parent. Queue ordering consequently remains:

```text
dwell(slot N) -> scan(after dwell N) -> dwell(slot N+1) -> scan(after dwell N+1)
```

The existing local capture authority now also takes a station-wide kernel lock before exact-radio
locks. This covers all current authority users—including operator-once, qualification, soak, and radio
probe—even before those less frequent commands gain first-class queue submission UX. PostgreSQL is the
durable scheduling authority; kernel locks are the final hardware fence.

The Queue page now presents acquisition operations separately from analysis jobs, including operation
kind, profile, radios, scheduled time, owner, and attempts. Scanner analysis is completed and its report
published before the scanner operation is marked successful, so a successful queue row never means
only that IQ was captured.

## Safety and failure behavior

| Condition | Behavior |
|---|---|
| Processing backlog above the dwell admission threshold | Dwell remains `pending`; no scheduled intent is dropped |
| Capture paused | No operation is claimed; queued rows remain visible |
| Supervisor crash during radio work | Lease expires and the same operation is reclaimed |
| Two supervisors race | Advisory lock plus unique leased-row index permit one owner |
| Duplicate cadence tick | Existing identical operation is returned |
| Conflicting reuse of an operation key | Fails closed |
| Scanner capture or report publication fails | Operation is retried; success is not published |
| Operator tries a different radio concurrently | Station-wide kernel lock returns busy |

## Verification

Passing locally:

```text
ruff: all changed Python paths pass
mypy: acquisition/catalog/CLI/presentation/API paths pass
pytest: 134 acquisition, supervisor, and API tests pass
vitest: 8 Queue/console tests pass
vite production build: pass
```

The new PostgreSQL tests cover idempotent enqueue, conflicting deduplication, a two-worker claim race,
FIFO dwell/scan ordering, expired-lease recovery, and stale-owner fencing. They require an isolated
schema. On this host, the default `leo_tracker` role cannot create schemas, so they could not be run
locally; CI's `leo_test` database is configured for this suite. The migration has one Alembic head:
`63f8b6c1a902`.

## Deployment sequence

1. Stop the acquisition supervisor so the old in-memory scheduler cannot race deployment.
2. Apply Alembic migration `63f8b6c1a902`.
3. Deploy the matching API, Web UI, and acquisition supervisor from one release.
4. Resume capture and verify the Queue page shows one leased dwell followed by a pending scan.
5. Verify the scanner report timestamp advances after the dwell, then verify a new recording enters
   Standard analysis and reaches complete UI products.

Do not deploy the code before its migration: the supervisor deliberately fails instead of silently
falling back to volatile scheduling when PostgreSQL is configured but the acquisition table is absent.
