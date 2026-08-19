# ADR 0002: Immutable manifest-last publication

Status: accepted

## Decision

Raw recording bundles and analysis runs are immutable after commit. Writers use
a configured local spool, hash their output, flush it durably, write the final
manifest last, and atomically rename the completed directory into its canonical
location. A final manifest is the commit marker.

PostgreSQL registration follows filesystem publication. Reconciliation repairs
a crash between those operations from the sealed manifest.

## Consequences

- Partial output is never presented as complete.
- PostgreSQL loss does not make committed IQ unrecoverable.
- Reprocessing publishes a new run instead of mutating existing artifacts.

