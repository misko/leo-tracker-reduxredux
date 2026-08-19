# Qualification backlog cancellation — 2026-08-19

This report records the supported cleanup of analysis work that was queued for
qualification captures before the `QUALIFICATION` automatic-analysis exclusion
policy landed. It is operational evidence for cancellation invariants, not a
scientific qualification result.

## Incident and scope

Reconciliation had created one Standard analysis run for each of 100 sessions
tagged `QUALIFICATION`. Each run contained the 30 jobs produced by the 15-stage,
two-stream graph, for 3,000 pending jobs in total. Processing those captures was
not intended; qualification validates acquisition and storage, and analysis
must be requested separately.

The affected set was selected with a read-only PostgreSQL query joining
`analysis_run` to `session_tag`, restricted to the `QUALIFICATION` tag and
`pending` or `running` run states. No catalog rows were edited directly.

## Supported operation

Each selected run was cancelled through the production CLI with the same
auditable reason:

```text
leo process cancel-run RUN_ID \
  --reason 'Cancel unintended automatic analysis queued before QUALIFICATION skip policy' \
  --yes --json
```

The repository operation locks the run and its jobs in one transaction. It
refuses current runs and live leases, changes pending jobs to `cancelled`,
expires attempts whose leases have already elapsed, records the reason on the
cancelled run, and leaves completed attempts/products inspectable. The prior
current analysis is unchanged. Repeating the operation is idempotent.

## Evidence

- selected active QUALIFICATION runs: 100
- cancelled through the supported CLI: 100
- already cancelled on this pass: 0
- failed cancellations: 0
- pending jobs for QUALIFICATION-tagged sessions after the pass: 0
- total queued jobs for all other work after the pass: 218

No raw recording, immutable analysis product, or QNAP source was removed or
modified. The automatic queue policy now skips `QUALIFICATION` captures, so a
reconciliation pass does not recreate this campaign merely because the
pipeline release changes.
