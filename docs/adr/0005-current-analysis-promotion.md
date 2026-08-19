# ADR 0005: Atomic current-analysis promotion

Status: accepted

## Decision

Reprocessing creates an immutable candidate analysis run. Only a sealed run with
all required accepted products may become current. PostgreSQL changes the run
state, current pointer, and current searchable summary in one transaction.

Failed work cannot modify the existing pointer. Readers resolve one current run
identifier at request start so one response cannot mix generations.

Superseded large artifacts may later be garbage-collected, while their compact
run receipts, lineage, configuration, and digests remain searchable.

