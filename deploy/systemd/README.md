# systemd deployment templates

These units run the installed `leo` and `leo-api` entrypoints from
`/opt/leo-tracker/.venv`. Install them in `/etc/systemd/system` and install
[`deploy/etc/leo/leo.env.example`](../etc/leo/leo.env.example) as
`/etc/leo/leo.env` after replacing every placeholder.

The environment file is required. All services fail closed if it is absent.
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

The independent `leo-release-qualification.timer` owns no radio or production
data. It runs the protected detector/processing corpus and compiled Chromium
E2E against a dedicated PostgreSQL database, temporary RecordingStore roots,
and a temporary web build. It is separately disabled unless
`/etc/leo/release-qualification-enabled` exists. Its sandbox makes
`/mnt/qnap01` inaccessible and permits writes only below the release evidence
root. See the runbook before enabling it.

Validate and activate the normal services with:

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
