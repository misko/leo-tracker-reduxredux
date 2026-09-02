# Protected corpus and browser qualification

`leo-release-qualify` is the supported nightly/release gate for the protected
real-IQ detector smoke, current native science, the direct-async PostgreSQL
operational graph, and the production-built web and Chromium UI.
Release-qualification V3 runs these five release-blocking lanes:

1. `protected-real-corpus` — the bounded protected science smoke;
2. `current-native-science` — native-rate scientific equivalence, state-reset,
   full-capture GLRT, QAM, and terminal path-report gates;
3. `current-native-postgresql` — the direct-async V6 mixed-rate PostgreSQL
   capture, analysis, PNG, and browser-artifact vertical;
4. `production-web-build` — the production web Vitest suite, TypeScript compile,
   and Vite build through the canonical `qualify:release` script; and
5. `production-chromium-e2e`.

The three pytest commands must each produce a bounded, nonempty JUnit result with
zero failures, errors, or skipped tests. Missing or corrupt required corpus
bytes fail closed. Historical V3/V5 recording checks are excluded from release
authority; `--include-historical` runs them explicitly as a non-blocking lane.

Independent lanes run concurrently within a bounded two-to-four-unit scheduler.
A lane may reuse a sealed passing result from the prior 72 hours only when its
command, bounded input closure, runtime identity, and retained evidence all
match exactly. PostgreSQL lanes remain mutually exclusive, and Chromium waits
for its matching web build.

## Isolation and safety

The default lanes do not import corpus data and never access `/mnt/qnap01`.
Their only persisted scientific input is the protected TEST corpus at
`/srv/bulk/leo/test-corpus`, mounted read-only. PostgreSQL tests create and drop
unique test-owned schemas and write generated recordings and analysis artifacts
beneath private temporary roots. The browser composition independently uses a
unique schema, generated TEST recordings, and the exact compiled scratch build.

The dedicated database must contain only its ordinary `public` schema at the
start and after each database-using gate. Graceful Chromium-server shutdown
drops its unique schema. As a second line of defense, the runner treats any
recognized `leo_e2e_*`, `leo_processing_*`, or `leo_test_*` leak as a failed
qualification, removes only that test-owned schema, and records the failure.
An unrelated schema is never removed automatically.

The database itself must also be separate. Create it once; the command refuses
the production `leo_tracker` database name and accepts only a name containing
`qualification` or ending in `_test`:

```text
sudo -u postgres createdb --owner=leo leo_qualification
sudo install -d -o leo -g leo -m 0750 \
  /srv/bulk/leo/qualification/release
```

Do not set `LEO_QUALIFICATION_DATABASE_URL` to the production catalog. The
runner constructs an allowlisted child environment, a private scratch `HOME`,
and explicit protected/native corpus roots; production database, bulk, and web
paths cannot leak into a command. Database cleanup runs in `finally` for every
database-using command, including failures.

## Manual release run

Run from an immutable staged or selected release with locked Python and npm
dependencies already installed and Chromium provisioned. The Git-free release
marker binds the receipt to one exact revision and source tree.

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  export PATH=/opt/leo-tracker/current/.release-tools:/opt/leo-tracker/current/.venv/bin:/opt/leo-tracker/current/web/node_modules/.bin:/usr/local/bin:/usr/bin; \
  exec /opt/leo-tracker/current/.venv/bin/leo-release-qualify \
    --project-root /opt/leo-tracker/current'
```

The release-local tooling prefix is required even though the runner itself has
an absolute path: its isolated commands invoke the exact `uv` executable sealed
inside that immutable release. A later stage therefore cannot invalidate an
older rollback candidate by replacing shared tooling. The reviewed
environment supplies the same `PLAYWRIGHT_BROWSERS_PATH` used while staging.

For an explicitly named release, add `--run-id release-2026-08-19`. Run IDs are
unique: an existing evidence directory is never resumed or overwritten. The
command exits nonzero after sealing a failure receipt when any gate fails. It
does not proceed to browser build/E2E after a corpus failure.

Each run has this stable layout:

```text
/srv/bulk/leo/qualification/release/RUN_ID/
  definition.json
  logs/01-protected-real-corpus.log
  logs/02-current-native-science.log
  logs/03-current-native-postgresql.log
  logs/04-production-web-build.log
  logs/05-production-chromium-e2e.log
  results/protected-real-corpus.junit.xml
  results/protected-real-corpus.junit.summary.json
  results/current-native-science.junit.xml
  results/current-native-science.junit.summary.json
  results/current-native-postgresql.junit.xml
  results/current-native-postgresql.junit.summary.json
  results/web-build.json             # hashes of the exact compiled assets
  results/browser-e2e.json
  results/playwright/                 # retained traces/screenshots on failure
  receipt.json
```

`definition.json` records the source revision and tree, lockfile and
corpus-declaration digests, redacted qualification database identity, the
read-only corpus root, the exact five commands, lane input closures, and safety
boundaries. `receipt.json` records one
closed, ordered outcome per command, exact timing and exit status, semantic
JUnit/result summaries, and SHA-256 for the complete durable evidence
inventory. The definition, results, and evidence tree must be regular
non-symlink paths; unexpected, missing, duplicate, or modified entries fail
cutover. Files and the completed run directory are made read-only after
sealing. A missing `receipt.json` means interruption and is not a pass. Evidence
should be retained or copied to the release record without altering the
original directory.

Review a run with:

```text
jq . /srv/bulk/leo/qualification/release/RUN_ID/receipt.json
sha256sum /srv/bulk/leo/qualification/release/RUN_ID/logs/*.log
```

## Nightly timer

The timer is independently gated and does not conflict with acquisition, the
soak, workers, or API. Install the templates, validate them, then create the
marker only after one successful manual run:

```text
sudo install -o root -g root -m 0644 \
  /opt/leo-tracker/current/deploy/systemd/leo-release-qualification.service \
  /opt/leo-tracker/current/deploy/systemd/leo-release-qualification.timer \
  /etc/systemd/system/
sudo systemd-analyze verify \
  /etc/systemd/system/leo-release-qualification.service \
  /etc/systemd/system/leo-release-qualification.timer
sudo install -o root -g root -m 0644 /dev/null \
  /etc/leo/release-qualification-enabled
sudo systemctl daemon-reload
sudo systemctl enable --now leo-release-qualification.timer
```

The service sandbox exposes the local corpus read-only, permits writes only to
the qualification evidence root and private temporary space, and makes
`/mnt/qnap01` inaccessible. It runs at idle I/O priority below acquisition and
workers. It never restarts or stops any live service.

Inspect the schedule and most recent run with:

```text
systemctl list-timers leo-release-qualification.timer
systemctl status leo-release-qualification.service
journalctl -u leo-release-qualification.service --since today --no-pager
```

To disable future runs, remove the marker and disable the timer. Do not delete
or reuse completed evidence directories.
