# systemd deployment templates

These units run the installed `leo` and `leo-api` entrypoints from immutable
releases selected by `/opt/leo-tracker/current-api`, `current-worker`, and
`current-acquisition`. The global `current` selector remains only for
maintenance commands during the rollout window. Install the units in
`/etc/systemd/system` and install
[`deploy/etc/leo/leo.env.example`](../etc/leo/leo.env.example) as
`/etc/leo/leo.env` after replacing every placeholder.
Workers additionally load `/etc/leo/worker.env`, which binds their exact
`LEO_PIPELINE_RELEASE_ID` independently of the API and acquisition selectors.

The environment file is required. All services fail closed if it is absent.
Every service also makes `/mnt/qnap01` inaccessible, including read-only API
and maintenance processes. The release link is changed only while all LEO
services are stopped; a build never replaces files beneath a running process.
Acquisition receives the highest CPU/I/O weights and a favorable nice value;
workers and maintenance jobs are deliberately subordinate. The API runs the
read-only production composition and listens on open LAN HTTP (`0.0.0.0`).

Retention is deliberately double-gated. The CLI invocation is explicitly
unattended (`--execute --automatic`), but systemd skips the unit until an
operator creates `/etc/leo/retention-enabled` after reviewing a dry run. It
then applies the catalog policy: start at 70%, select oldest eligible data down
to 65%, warn at 75%, and stop acquisition admission at 80% when retention
cannot make enough room. Holds and TEST sessions remain protected.

Immutable runtime release retention is a separate operator workflow. Deployment
never silently removes rollback releases. Use `sudo ./ops releases --plan`
followed by an exact-digest `--apply` as documented in the production deployment
runbook; the command shares the deployment lock and preserves sealed metadata
and receipts for every retired runtime.

Qualification is similarly disabled unless
`/etc/leo/qualification-enabled` exists. It conflicts with continuous
acquisition because both own the radios; use the procedure in the operator
runbook rather than enabling its timer during normal acquisition.

The acquisition service also schedules the configured Starlink scanner when
`LEO_SCANNER_ENABLED=true`. The scanner radio is selected by logical radio ID;
all acquisition entry points share a durable capture authority and kernel-held
per-radio leases, so ordinary, scanner, soak, qualification, probe, and manual
captures cannot overlap on the same physical radio. Scanner slots are anchored
to UTC every 20 minutes and alternate deterministically between 2.5 MS/s with a
2.5 MHz RF bandwidth and 5 MS/s with a 5 MHz RF bandwidth. Each slot opens and
configures the radio once, then captures complete eight-target sweeps for 300
seconds at 120 ms per target in CH1L, CH2L, CH3L, CH4L, CH1U, CH2U, CH3U, CH4U
order. Every target uses the maximum-coverage IF for that slot's admitted
bandwidth.

Each completed sweep is independently committed as a framed, digest-verified
CI16 bundle beneath `$LEO_BULK_ROOT/scanner-recordings/YYYY/MM/DD/<scan-id>/`;
one terminal run manifest is committed beneath `$LEO_BULK_ROOT/scanner-runs/`.
The bundle manifest preserves every retune's sample boundary and
requested/applied IF/RF, so the concatenated payload must not be interpreted as
one fixed tuning. Standard analysis runs after RF release and startup
reconciliation repairs any missing analysis without recapturing. Ordinary
dwells and scanner slots are independent durable queue operations. Pause and
restart retain their intents, slots over the configured lateness bound are
explicitly skipped, and the global radio lease permits only one acquisition
operation at a time.

Admission rounds the 300-second window up to 313 complete sweeps. Before opening
the radio it therefore requires, in addition to the configured safety reserve,
6,009,600,000 raw bytes for a 2.5 MS/s slot or 12,019,200,000 raw bytes for a
5 MS/s slot. At 72 slots per UTC day this is a conservative 649,036,800,000 raw
bytes/day before compression; operational capacity and retention must be sized
from that upper bound rather than an assumed compression ratio.

Full recording reconciliation is recovery and maintenance work, not a readiness
probe. API, workers, and acquisition do not order themselves behind
`leo-reconcile.service`; the persistent timer runs it asynchronously.
Reconciliation must remain idempotent with concurrent committed-session
registration and worker claims.

Use `leo acquire pause --reason ...` to durably fence new radio work and drain
active captures, and `leo acquire resume` to permit it again. Pausing the
acquisition service therefore pauses scanner capture as well; there is no
separate scanner service or timer to coordinate.

For the initial two-rate canary, keep the service environment disabled and use
the runbook's `leo acquire run --scanner-only --max-scanner-runs 2` procedure.
This bounded mode never enqueues or claims ordinary dwells, but it still honors
the durable pause state and global radio-owner lease. It defers Standard
analysis until the normal, still-paused acquisition service performs startup
reconciliation, keeping the 29-minute canary guard focused on RF capture and
durable run publication.

Scanner IQ participates in the same 70%-to-65% local watermarked retention
plan as ordinary recordings. A scanner bundle is eligible only when an exact
IQ URI/digest reference belongs to a terminal `complete` scanner run and an
allowed Standard analysis manifest names that same input. Execution verifies
the complete analysis products again, stages the exact dated IQ bundle in
local trash, and commits an append-only tombstone containing its immutable IQ
manifest before deletion. Recovery restores a pre-tombstone stage and discards
a post-tombstone stage. Run manifests, reports, analysis products, and their UI
capture-time history remain available; QNAP is never a retention target.

Do not enable unattended scanner slots until the bounded RF canary and the
scanner-retention dry-run/recovery checks in the runbook have both passed.

The independent `leo-release-qualification.timer` owns no radio or production
data. It runs the protected detector/processing corpus and compiled Chromium
E2E against a dedicated PostgreSQL database, temporary RecordingStore roots,
and a temporary web build. It is separately disabled unless
`/etc/leo/release-qualification-enabled` exists. Its sandbox makes
`/mnt/qnap01` inaccessible and permits writes only below the release evidence
root. See the runbook before enabling it.

Do not copy a mutable home-directory checkout into `/opt`. Use
`deploy/scripts/stage-production-release` with one full commit SHA, qualify
that exact staged revision, and follow the guarded cutover in
[`docs/operations/production-deployment.md`](../../docs/operations/production-deployment.md).
Only after its preflight passes should the normal services be activated:

```text
systemd-analyze verify /etc/systemd/system/leo-*.service /etc/systemd/system/leo-*.timer
systemctl daemon-reload
systemctl enable --now leo-reconcile.timer
systemctl enable --now leo-worker@1.service leo-worker@2.service
systemctl enable --now leo-api.service leo-acquisition.service
systemctl enable --now leo-retention.timer
```

Do not enable `leo-qualification.timer` until the acquisition maintenance
window and marker file have been arranged. See
[`docs/operations/runbook.md`](../../docs/operations/runbook.md) for install,
recovery, backup, retention, and qualification procedures.
