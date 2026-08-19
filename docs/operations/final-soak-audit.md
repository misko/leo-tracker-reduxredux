# Final soak acceptance audit

`leo acquire audit-soak` is the read-only, fail-closed WP10 acceptance check for
an already terminal production acquisition soak. It is separate from the soak
harness: the harness gathers durable evidence while acquisition is active; the
auditor later re-reads that evidence, re-verifies every recording bundle,
and measures the exact soak processing cohort in PostgreSQL.

Do not run this command against a running soak. A running summary cannot pass,
and rehashing active long-dwell bundles creates unnecessary I/O. Wait until
acquisition has reached its 86,400-active-second terminal summary and the soak
processing cohort has drained.

## Invocation

The evidence argument is either an existing local evidence directory or a safe
soak ID resolved beneath `$LEO_BULK_ROOT/qualification/soak`. Acceptance also
requires a captured systemd runtime-evidence JSON file. The PostgreSQL URL may
be explicit or supplied by `LEO_DATABASE_URL`:

```text
leo acquire audit-soak production-24h-20260819-01 \
  --runtime-evidence /srv/bulk/leo/qualification/soak-audits/runtime-production-24h-20260819-01.json \
  --database-url "$LEO_DATABASE_URL" --json
```

The command is read-only by default and writes no receipt. To seal the result,
provide one explicit path whose parent already exists:

```text
leo acquire audit-soak production-24h-20260819-01 \
  --runtime-evidence /srv/bulk/leo/qualification/soak-audits/runtime-production-24h-20260819-01.json \
  --database-url "$LEO_DATABASE_URL" \
  --receipt /srv/bulk/leo/qualification/soak-audits/production-24h-20260819-01.json \
  --json
```

Receipt publication is create-only, atomic, fsynced, and mode `0440`. Existing
receipts are never replaced. Symlinked parent directories are refused. The
auditor lexically rejects `/mnt/qnap01` before any lookup or resolution: QNAP is
neither an evidence source nor a receipt destination for this operation.

Human and JSON modes contain the same typed receipt and return a nonzero
unhealthy exit when any acceptance check fails. The receipt has no wall-clock
"audited at" field; its identity is the definition, summary, ordered trial-file
digests, immutable bundle digests, and the measured database snapshot. Repeating
the audit over unchanged evidence and catalog state therefore produces the same
payload.

## Runtime continuity evidence

The v1 trial files do not contain enough information to distinguish short
service downtime from host timestamp jitter. Timing agreement alone therefore
never proves that the soak process was uninterrupted. Immediately after the
terminal summary is durable, capture these properties for the same unit used to
start the soak:

```text
unit=leo-soak-production-24h-20260819-01.service
systemctl --user show "$unit" --no-pager \
  --property=InvocationID,ExecMainPID,MainPID,NRestarts,InactiveExitTimestamp,ExecMainStartTimestamp
date --utc +%s%N
```

Convert the two systemd timestamps with `date --date='<timestamp>' +%s%N` and
write the following bounded JSON document. `observed_utc_ns` is the integer from
the final `date` command:

```json
{
  "kind": "systemd_runtime_continuity",
  "schema_version": 1,
  "soak_id": "production-24h-20260819-01",
  "unit_name": "leo-soak-production-24h-20260819-01.service",
  "invocation_id": "<InvocationID>",
  "exec_main_pid": 1234,
  "main_pid_at_observation": 0,
  "n_restarts": 0,
  "unit_invocation_start_utc_ns": 1787140800000000000,
  "exec_main_start_utc_ns": 1787140801000000000,
  "observed_utc_ns": 1787227202000000000
}
```

Do not reuse evidence from another invocation. Acceptance requires the exact
unit name, a nonempty invocation ID, `NRestarts=0`, an invocation start no later
than its execution start, an execution start no later than the immutable soak
definition, and an observation no earlier than the terminal summary. A running
`MainPID` must equal `ExecMainPID`; a stopped terminal oneshot may legitimately
report `MainPID=0`, while `ExecMainPID` remains the process identity. The auditor
hashes the canonical validated evidence object and embeds it in its receipt;
callers cannot supply an unrelated digest. Missing or inconsistent evidence is
non-acceptance.

## What is proved

The auditor validates all of the following independently of the mutable summary:

- the definition and summary schemas and matching soak identity;
- terminal `complete`/`duration`/`passed` state, exactly 86,400 configured active
  seconds, no trial limit, and at least 86,400 observed active seconds;
- an exact contiguous `trial-NNNNNNNN.json` inventory with no unexpected entries;
- a fresh aggregate recalculation from the immutable trial files;
- every committed bundle URI and manifest digest, plus every compressed and
  uncompressed IQ shard and timeline through `RecordingStore.verify`;
- equality between trial metrics and their immutable recording manifests;
- successful post-commit catalog/queue observations and ownership of every
  recorded run ID by its expected soak session;
- a terminal, sealed `standard-v1` analysis run with the exact 30-job Standard
  stage/scope inventory for every recorded session;
- sample-derived duty of at least 50% and maximum inter-capture gap of 30 seconds;
- zero still-outstanding pre-soak jobs, soak pending plus leased below 1,000, and
  a stricter terminal soak-cohort drain to zero;
- successful worker completions at least equal to job arrivals during the final
  six active hours, with no failed or cancelled soak jobs.

The PostgreSQL measurement is one `REPEATABLE READ` transaction followed
immediately by `SET TRANSACTION READ ONLY`. It executes only `SELECT` statements.
The cohort is the set of run IDs recorded in immutable per-trial post-commit
evidence; unrelated queue decline cannot hide cohort growth. "Inherited drained"
means no currently pending or leased job whose `created_at` predates the soak
definition remains.

## Final-six-active-hour calculation

The active window is `[summary.active_elapsed_seconds - 21,600,
summary.active_elapsed_seconds]`. For an invocation proven uninterrupted by the
separate runtime evidence, it is represented as one UTC interval ending at the
terminal summary timestamp. Consecutive trial-finish anchors compare wall-time
delta with active-time delta. A difference above the predeclared 10-second
host-timing tolerance, including the final trial-to-summary tail, makes the
mapping ambiguous and fails closed.

The same-invocation evidence with `NRestarts=0` proves that systemd did not
restart or replace the service. It does not rule out `SIGSTOP`, host suspend, or
scheduler delay. The 10-second wall/active tolerance bounds that remaining
uncertainty; sub-tolerance stopped time may be included in the UTC window. The
receipt therefore permanently records
`restart_absence_proven_by_timing=false`, and a larger discrepancy fails closed.

Within that mapped interval:

- arrivals are soak-cohort jobs whose `processing_job.created_at` is in the
  interval;
- completions are currently successful soak-cohort jobs whose terminal
  `processing_job.updated_at` is in the interval;
- rates divide those counts by the represented active hours.

Completions may include cohort jobs created before the window and completed
inside it, which is intentional: this gate compares worker service throughput
against new soak job creation during the same active interval. At least one
arrival is required, so an empty cohort cannot pass vacuously.

## Continuity and synchronization honesty

The receipt reports stream counts separately for
`sample_loss_observable=true` and `false`. Zero reported host gaps is permanently
recorded as **not** proving zero device-side loss. For the current Pluto adapter,
device sample loss is not observable; this is an honest limitation, not a failed
digest check.

Guaranteed overlap is copied from the immutable synchronization manifest and
never inferred from estimated overlap. A zero guaranteed overlap remains zero in
the receipt. The audit makes no phase-coherence claim.

## Failure and rerun behavior

A well-formed running, incomplete, threshold-failing, undrained, or
database-unavailable audit returns a typed non-acceptance result. Malformed or
unsafe paths and invalid schemas are input errors. Because a sealed receipt is
immutable, correct an operational condition and rerun without `--receipt` first;
then choose a new explicit receipt path for the final passing state. Never erase
or overwrite an earlier failure receipt.
