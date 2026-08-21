# Scheduled acquisition queue backpressure

Continuous `leo acquire run` checks one authoritative processing backlog snapshot
immediately before each scheduled dwell. One-shot `leo acquire once` is unchanged.

The snapshot contains two independent counts:

- `queued`: jobs in PostgreSQL `pending` state; this is the only admission input.
- `running`: jobs in PostgreSQL `leased` state; this is reported in logs but does
  not contribute to the queued threshold.

The acquisition process enters suppression when `queued > 30`. Once suppressed,
it remains suppressed while `queued >= 20` and resumes only when `queued < 20`.
At process start the controller begins active and applies the entry threshold to
the first snapshot, making restart behavior deterministic. If the catalog cannot
provide a snapshot, scheduled acquisition fails closed and remains suppressed
until a later authoritative snapshot is below the exit threshold.

Admission is deliberately point-in-time. Queue growth after admission never
interrupts an active radio dwell, bundle publication, catalog registration, or
analysis admission. The next scheduled check observes that growth and may
suppress the next dwell. While suppressed, no session identifier is allocated,
no manifest is created, and no spool directory is opened.

Every observation emits a structured `acquisition_backpressure` log containing
`queued`, `running`, `suppressed`, and `transition`. Catalog failures additionally
carry `error_type` and `error`.

## Verification

```bash
uv run pytest -q \
  tests/acquisition/test_backpressure.py \
  tests/cli/test_acquisition_backpressure.py

uv run pytest -q tests/acquisition tests/cli/test_acquire_cli.py
```

The focused tests cover the exact 30/31 and 20/19 boundaries, hysteresis-band
oscillation, restart behavior, catalog failure, running-job exclusion, active
dwell completion, point-in-time admission races, and absence of phantom capture
sessions while suppressed.
