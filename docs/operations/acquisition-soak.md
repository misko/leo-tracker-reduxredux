# Acquisition soak evidence

The acquisition soak exercises the ordinary `AcquisitionApplication` and
`RecordingStore`; it is not a synthetic writer test and it has no private
recording path. Every successful capture is therefore an ordinary compressed
recording subject to normal catalog reconciliation, processing, and retention.
The soak does **not** add a hold or pin. Profile tags are preserved unchanged,
but a profile carrying `QUALIFICATION` is rejected: that tag is reserved for
the bounded acquisition-only harness and intentionally suppresses automatic
analysis. Soak recordings must enter the ordinary processing queue. TEST
profiles retain `TEST` and its normal durable hold; LIVE profiles remain LIVE.

The production gate is 86,400 active seconds with no trial limit. A short run
or a run completed by `maximum_trials` is useful for validating the harness,
but it is not evidence that the 24-hour gate passed. Do not mark that gate
complete until the real-radio run has actually finished and its summary says
`status=complete`, `completion_reason=duration`, and `passed=true`.

## Durable layout and recovery

For soak ID `production-24h-YYYYMMDD`, evidence is written beneath the chosen
local output root as:

```text
production-24h-YYYYMMDD/
  definition.json
  summary.json
  trials/
    trial-00000000.json
    trial-00000001.json
    ...
```

`definition.json` is immutable and binds the profile revision, compiled capture
plan, radios, schedule, and acceptance-policy version. Each trial file is
published once with an atomic create and never rewritten. `summary.json` is a
bounded aggregate atomically replaced after every durable trial; it never
contains the trial list. This avoids repeatedly rewriting one ever-growing JSON
document during a long run.

Session IDs are deterministic (`<soak-id>-trial-NNNNNNNN`). On restart, the
harness reads the contiguous trial files. If the process died after normal
recording publication but before trial evidence publication, it verifies and
records the existing bundle instead of capturing the same session again. An
incomplete spool is recorded as failed evidence and is never treated as a
committed capture. Resume refuses a changed profile, plan, schedule, or policy.

SIGINT and SIGTERM set the normal acquisition cancellation event. Scheduling
waits wake immediately, the current acquisition follows its normal cancellation
path, and the bounded summary is left as `interrupted`. Resume with the same
soak ID and arguments; completed session IDs are not duplicated.

## Recorded evidence and policy

Every trial records capture state, bundle URI and manifest digest verification,
requested/captured samples, gaps, overflows, sample-derived recorded span,
inter-capture gap, wall acquisition time, synchronization skew/uncertainty and
overlap, process peak RSS, `statvfs` storage utilization, admission decision,
and injected processing-backlog observations. The aggregate records extrema,
counts, elapsed active time, and sample-derived duty cycle.

After each bundle commits, production composition runs normal reconciliation,
catalog registration, and new-capture analysis queue creation. Only then does
the harness take the trial's `processing_backlog_after` observation. Each trial
records the callback result, registered/existing session IDs, and queued run
IDs, so queue growth is measured rather than inferred. The callback runs for a
bundle recovered after process interruption too.

A PostgreSQL outage cannot invalidate or delete the committed recording. Its
trial remains `committed` with independent digest evidence while the callback
failure is recorded separately. Acquisition continues, allowing a later
per-trial reconciliation to discover both the missed bundle and the new bundle.
Production policy permits zero callback failures, so such a run does not pass
the full-system qualification even if all IQ is durable; repair PostgreSQL,
reconcile, and begin a new qualification after preserving the failed evidence.

`SoakAcceptancePolicyV1` is an explicit versioned contract. The default policy
fails early on any false-complete claim, invalid digest, gap, overflow, storage
admission rejection, less than 100% committed trials, storage above 80%, peak
RSS growth above 512 MiB, more than 10,000 queued jobs, queue growth above 1,000
jobs, or paired-radio overlap below 99%. Operators may set a justified policy
for a particular qualification, but the immutable definition makes that change
visible. An unavailable backlog observer is recorded as unavailable; production
composition injects both the PostgreSQL backlog observer and the per-trial
registration callback. Missing or failed integration evidence cannot satisfy
the production full-system gate.

Both the recording root and evidence output root hard-reject `/mnt/qnap01` and
its descendants. QNAP remains read-only source material: never delete, move,
rename, purge, or use it as a soak destination.

The initial `SoakAcceptancePolicyV1` does not contain minimum-duty or
maximum-inter-capture-gap fields, and its backlog baseline can include jobs from
before the soak. The production gate therefore adds three predeclared external
checks: sample-derived duty must be at least 50%, no inter-capture gap may exceed
30 seconds, and soak-origin pending/leased jobs must remain below 1,000 after
the inherited queue drains. Over the final six active hours, worker completions
for soak-origin runs must meet or exceed newly created soak jobs. Query by the
recorded soak session/run IDs; a falling aggregate queue is not sufficient.

## Production invocation

The systemd service is deliberately gated by `/etc/leo/soak-enabled` and must
not be enabled as an unattended timer. During a planned maintenance window,
stop ordinary continuous acquisition, probe radios, create the marker, start the
service, and follow its journal. Remove the marker after the service starts so a
later manual restart cannot accidentally begin another soak.

Because this is a 24-hour `Type=oneshot` unit, start it with `systemctl start
--no-block`. Confirm `ActiveState=activating` before removing the marker; that
proves systemd already evaluated the start condition without making the terminal
wait for the whole soak.

The stable command is documented in the main runbook alongside the service
environment. Use a new descriptive soak ID for a new qualification. `--resume`
is safe for recovering and inspecting an interrupted matching run without
duplicating session IDs, but a pre-terminal process/service restart means that
run cannot prove the uninterrupted production gate. Preserve it as diagnostic
evidence and start the authoritative 24-hour qualification again under a new
soak ID. Post-terminal restart/resume testing is a separate recovery gate.

After the terminal summary and processing-cohort drain, run the independent
[final soak acceptance audit](final-soak-audit.md). It freshly verifies every
recording digest and calculates the external duty, gap, outstanding-work, and
final-six-active-hour gates from immutable evidence and a read-only PostgreSQL
snapshot. Do not run that I/O-heavy audit while the soak is still active.
