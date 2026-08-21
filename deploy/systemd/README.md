# systemd deployment templates

These units run the installed `leo` and `leo-api` entrypoints from immutable
releases selected by `/opt/leo-tracker/current-api`, `current-worker`, and
`current-acquisition`. The global `current` selector remains only for
maintenance commands during the rollout window. Install the units in
`/etc/systemd/system` and install
[`deploy/etc/leo/leo.env.example`](../etc/leo/leo.env.example) as
`/etc/leo/leo.env` after replacing every placeholder.

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

Qualification is similarly disabled unless
`/etc/leo/qualification-enabled` exists. It conflicts with continuous
acquisition because both own the radios; use the procedure in the operator
runbook rather than enabling its timer during normal acquisition.

The acquisition service also schedules the configured Starlink scanner when
`LEO_SCANNER_ENABLED=true`. The scanner radio is selected by logical radio ID;
all acquisition entry points share a durable capture authority and kernel-held
per-radio leases, so ordinary, scanner, soak, qualification, probe, and manual
captures cannot overlap on the same physical radio. Each scan captures all
eight low-band channel edges at the configured 80 ms dwell, releases the radio,
then analyzes and retains a timestamped JSON report beneath
`LEO_SCANNER_REPORT_ROOT`. Each dwell and its following scan are durable queue
operations. Backpressure, pause, and restart preserve rather than drop those
intents, while the global radio lease permits only one acquisition operation at
a time.

Full recording reconciliation is recovery and maintenance work, not a readiness
probe. API, workers, and acquisition do not order themselves behind
`leo-reconcile.service`; the persistent timer runs it asynchronously.
Reconciliation must remain idempotent with concurrent committed-session
registration and worker claims.

Use `leo acquire pause --reason ...` to durably fence new radio work and drain
active captures, and `leo acquire resume` to permit it again. Pausing the
acquisition service therefore pauses scanner capture as well; there is no
separate scanner service or timer to coordinate.

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
