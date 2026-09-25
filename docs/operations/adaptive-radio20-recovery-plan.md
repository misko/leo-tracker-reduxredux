# Restore adaptive scanning and full analysis on radio .20

Prepared 2026-09-24 from read-only inspection of the running host, effective
systemd units, deployed source, and recent journals. This is a recovery plan;
no services, radio settings, or production data were changed to prepare it.

## Outcome

One traceable path from `ip:192.168.1.20` to a complete, visible analysis:

```text
dual-RX adaptive capture → sealed NVMe spool → verified RAID publication
    → metrics + overview + relative phase
    → tracking + candidate association + position methods → API/UI
```

Use the existing PostgreSQL queue, local stores, and service boundaries. Keep
the last working capture profile while repairing its consumers. A running
process, a successful capture exit, or a rendered overview alone is not proof
that this path works.

## What is established

The snapshot was taken around 14:50 UTC on September 24. Recheck these facts
before execution; other work on this host may change the deployment.

| Observation | Consequence |
| --- | --- |
| `leo-v052-adaptive.timer` is active, scheduled every ten minutes. Its effective service is v0.56, dual RX, 2.5 MS/s, `.20`, serial `1040005e0b100007100010000bf33a5d4d`. | Acquisition is already scheduled; an inactive oneshot between runs is normal. |
| Captures started at 14:20, 14:30, and 14:40 and exited successfully in approximately 5–6 minutes. | Verify their receipts and IQ before treating acquisition as broken or healthy. |
| Transfer reports imported sessions; its deferred count fell from 52 to 49 between 14:20 and 14:48. One earlier capture was explicitly unsupported because a visit was not centred on a canonical pilot. | Publication is progressing, but a backlog and an unsupported-input case exist. |
| The enqueuer logged event schema `3` rejected by a schema `1` reader, including `valid_end_counter_exclusive`; later passes succeeded and took 9m43s and 12m19s. | Investigate compatibility and enumeration cost independently. These logs do not prove every current capture fails. |
| The deployed enqueuer explicitly skips `AdaptiveHopReceiptV6` variable-dwell captures. | Visible recordings may intentionally receive no analysis. Full recovery must address or explicitly bound this gap. |
| Seventeen adaptive workers and twenty ordinary workers were active. | Activity is not completion evidence; measure jobs, memory, and storage pressure before adding workers. |
| RAID was 37% used, NVMe 24%, root 89%, and `/tmp` 95%. | Temporary space is an immediate resource concern; investigate owners before any cleanup. |

Effective release identities matter more than the global `current` link:

| Role | Observed source/release |
| --- | --- |
| Capture | `/opt/leo-v056-adaptive/f758b3af36604843299858c7e17c9050f9d1b5c1`, with a Python runtime in `pluto-plus-utils-feature-103` |
| Spool transfer and enqueue | `c528e9a2d01e0cc9329c479a6f7f5667920b4ec2` |
| Adaptive workers and API | `51701a6ba364bd20170cbc167c1ee0db8c640483` |
| `current-acquisition` and `current-worker` links | `02ae16e8233b6de9b01aacb6b21709840e58536b` |

Different releases are not inherently invalid, but compatibility needs an
explicit test. This workspace is an older, heavily modified checkout and lacks
the deployed adaptive queue implementation. Do not deploy it over production
or import unrelated working changes into this recovery.

## 1. Establish a small recovery inventory

Record effective units and drop-ins, process executable paths, release hashes,
timer state, firmware identity, radio serial, and the actual applied capture
settings. Inspect the latest successful `.20` receipt and verify dual-RX layout,
sample rate, visit boundaries, timestamps/counters, tuning, and payload digest.
Do not infer a recording's duration from the runner's filename or service time.

Use existing store/catalog interfaces to inventory sealed-but-unpublished
spools and published sessions missing each downstream product. Include queue
state, attempts, leases, input/configuration digests, and concise error reasons.
Separate recent `.20` sessions, older backlog, and unsupported contracts.

Select three saved cases: one known supported `.20` capture, one current
dual-RX capture, and one variable-dwell or schema-error case. Start with
`scan-fw-51dadc5c6aa0e74b` and `scan-fw-8634c361a1e38331` as recent candidates,
but verify their receipt identities before selection. Pin their digests.

**Exit:** a session-by-stage table shows precisely where progress stops, with
one reproducible failing input. Record actual firmware reachability/identity
read-only if needed; no new capture is necessary.

## 2. Repair compatibility at the existing boundaries

Create an isolated checkout from the appropriate deployed source revision.
Compare producer, transfer, enqueue, worker, and API contract support, including
the nested event versions and variable dwell timing. Build a small compatibility
matrix before choosing the release to stage.

Preserve published contracts. Add explicit readers/adapters for supported
versions; never strip unknown fields, relabel schema versions, or fabricate
fixed-dwell timing. Variable-dwell analysis must derive slices and timestamps
from the receipt's real boundaries. If its scientific treatment needs more
work, expose an explicit unsupported status and first restore the proven
fixed-dwell path. Do not call that partial milestone full recovery.

Ensure one malformed/unsupported session cannot abort enumeration of healthy
sessions. Preserve its evidence and report a bounded diagnostic. Make repeated
enqueue/reconciliation idempotent and validate producer/consumer configuration
digests and completion predicates together.

**Tests:** component-owned contract fixtures for old and current receipts,
schema-3 events, variable dwell, two receiver columns, invalid boundaries,
and mixed valid/invalid inventories. Test duplicate enqueue, interrupted
publication, retry, and stale lease behavior. Keep scientific goldens unchanged.
PostgreSQL/hardware-dependent tests require explicit markers.

**Exit:** each selected recording either reaches its expected stage or has an
explicit actionable reason; unsupported data cannot starve valid data.

## 3. Prove full analysis using saved IQ

Run one saved `.20` session end to end through the actual queue and candidate
release. Use bounded, resumable analysis slices; the observed worker uses a
560-second slice and a 20-minute lease. Check cancellation, partial progress,
and lease ownership rather than allowing an unbounded subprocess.

Require all of the following for the same input manifest and intended analysis
configuration:

- Metrics, QAM/known-pilot evidence, overview figures, and relative-phase output.
- Doppler/tracking and Starlink candidate association with support and controls.
- The deployed completion contract's shared tracking, additional position
  methods, blind regional analysis, and adaptive TLE position v2 products.
- API/UI visibility with the correct radio, both receivers, release identity,
  stage state, and artifact links.

The inspected worker requires `metrics_complete`, `overview_state=ready`, and
`relative_phase_state=complete` for analysis; tracking additionally checks
position products and store completion. Preserve these checks. A scientifically
valid no-support result is acceptable when explicit and complete. Candidate
association, broadband coherence, local pilot coherence, and validated position
are distinct claims; do not promote one into another.

Measure how much IQ each stage actually examines. Current limits include
120-ms probe stride, 2,500 visits, four tracking groups, and 64 reviewed tracks.
Expose coverage and truncation; “full” means every required stage completes,
not an unsupported claim that every sample and every candidate was analyzed.

**Exit:** a single saved-session receipt links all required products and records
runtime, coverage, resource peak, and any scientific limitations. Then repeat
on the other supported saved cases without changing their source evidence.

## 4. Restore timely scheduling and drain the backlog

Profile the measured 10–12-minute enqueue passes. Prefer cheap indexed
publication/status checks and bounded batches; avoid reading all IQ or
reconstructing completed products just to decide whether work is pending.
Use existing catalog/store ports. Add only the smallest cursor/index change
that measurements justify, retaining periodic bounded reconciliation.

Prioritize recent `.20` captures while guaranteeing bounded progress for older
work. Explicitly backfill sessions outside the automatic two-hour tracking
window, including already-rendered sessions missing phase or tracking. Verify
that delayed metrics completion still queues tracking after that window.

Inspect `/tmp` and root usage, active file owners, and worker memory before
choosing concurrency. Move task-owned scratch/cache to an approved local path
where needed; do not indiscriminately delete temporary files. Set a writable
Matplotlib cache for enqueue. Preserve acquisition CPU/I/O priority.

**Exit:** enqueue finishes comfortably within the ten-minute arrival cadence;
new sessions are not hidden behind the backlog; oldest pending age decreases;
and every incomplete session has a visible state. Measure end-to-end capacity
before claiming the ten-minute capture cadence is sustainable.

## 5. Deploy the tested combination and verify .20

Stage the exact committed recovery revision through the immutable release
workflow. Record the tested producer/consumer matrix and effective unit targets.
Prefer one consumer release where practical; do not blindly point all services
at a global selector. Review changed migrations and back up the catalog if a
migration is needed. Preserve existing working changes and previous releases.

Cut over the affected adaptive consumers with proper lease drain/fencing, then
reconcile saved publications and verify the saved-session proof through the
installed API/UI. Keep unrelated ordinary processing outside the change scope.

Only after explicit authorization for new RF collection, use one bounded `.20`
canary, initially 60–120 seconds if supported by the verified runner. Verify
serial, exclusive radio ownership, dual RX, 2.5 MS/s, and the reviewed tuning
profile. Account for existing timer work so it cannot overlap the canary.
Set an external wall-clock stop, including retries, below the repository's
30-minute collection limit. Do not reflash firmware as a speculative fix.

Trace that canary through spool, publication, queue, all analysis stages, and
UI. Exercise one bounded interruption/recovery check using saved work. Restore
the reviewed scheduled operating state only within the user's authorization;
do not use a multi-hour campaign as an acceptance test.

**Exit:** one live session has complete evidence, reconciliation is idempotent,
restart does not duplicate publication or lose work, and effective service
targets match the tested release matrix.

## Rollback and final handoff

On contract errors, missing IQ, repeated worker failure, or resource exhaustion,
stop the affected new work and preserve its spools, receipts, and artifacts.
Restore the prior compatible consumer units/release after handling active
leases. Never downgrade the database as an application rollback. If its schema
changed incompatibly, fix forward or validate a backup in a separate database.
Leave `/mnt/qnap01` untouched.

Deliver the before/after stage inventory, exact release/configuration identities,
saved and live canary IDs, component-test results, completion/coverage receipt,
queue latency and backlog measurements, and the rollback target. Mark any
remaining unsupported capture type as unfinished work, not silent success.
