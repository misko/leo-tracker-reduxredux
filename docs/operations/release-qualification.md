# Protected corpus and browser qualification

`leo-release-qualify` is the supported nightly/release gate for the protected
real-IQ detector smoke, the complete production processing path, and the
production-built Chromium UI. It runs one bounded one-path/one-second protected
science smoke, the isolated PostgreSQL 2-radio x 2-RX Standard operational
vertical, and the Playwright production project. It deliberately does not
repeat the reviewed full four-path-twice scientific regression: the sealed
Standard cutover receipt is the authority for that expensive computation.
Missing or corrupt REQUIRED corpus bytes fail closed; J1 remains explicit,
non-executable `UNAVAILABLE_HISTORICAL_EVIDENCE` and can never count as a
passing lane.

## Isolation and safety

The lane does not import corpus data and never accesses `/mnt/qnap01`. Its only
scientific input is the already materialized, held, local TEST corpus, read-only
at `/srv/bulk/leo/test-corpus`. The operational processing test creates and
drops a unique PostgreSQL schema and writes its generated compressed recording
and analysis artifacts beneath pytest's temporary directory. The browser
composition independently creates and drops another unique schema, publishes
generated TEST recordings beneath a temporary bulk root, and serves a compiled
UI from a temporary build directory.

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
runner removes `LEO_DATABASE_URL`, `LEO_BULK_ROOT`, and `LEO_WEB_DIST` from all
child environments so neither test path can inherit production locations.

## Manual release run

Run from a clean, deployed Git checkout with locked Python and npm dependencies
already installed and Chromium provisioned. A dirty checkout is rejected so a
receipt always identifies one exact revision.

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  export PATH=/opt/leo-tracker/current/.release-tools:/opt/leo-tracker/current/.venv/bin:/opt/leo-tracker/current/web/node_modules/.bin:/usr/local/bin:/usr/bin; \
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/opt/leo-tracker/current; \
  exec /opt/leo-tracker/current/.venv/bin/leo-release-qualify \
    --project-root /opt/leo-tracker/current'
```

The release-local tooling prefix is required even though the runner itself has
an absolute path: its isolated commands invoke the exact `uv` executable sealed
inside that immutable release. A later stage therefore cannot invalidate an
older rollback candidate by replacing shared tooling. The reviewed
environment supplies the same `PLAYWRIGHT_BROWSERS_PATH` used while staging.
The command-scoped Git configuration trusts only the root-owned selected
release; it does not modify global or service-account Git configuration.

For an explicitly named release, add `--run-id release-2026-08-19`. Run IDs are
unique: an existing evidence directory is never resumed or overwritten. The
command exits nonzero after sealing a failure receipt when any gate fails. It
does not proceed to browser build/E2E after a corpus failure.

Each run has this stable layout:

```text
/srv/bulk/leo/qualification/release/RUN_ID/
  definition.json
  logs/01-protected-real-corpus.log
  logs/02-production-web-build.log
  logs/03-production-chromium-e2e.log
  results/real-corpus.junit.xml
  results/web-build.json             # hashes of the exact compiled assets
  results/playwright/                 # retained traces/screenshots on failure
  receipt.json
```

`definition.json` records the Git revision, lockfile and corpus-declaration
digests, redacted qualification database identity, exact commands, and safety
boundaries. `receipt.json` records timing, outcome, exit codes, and SHA-256 for
every durable evidence file. Files and the completed run directory are made
read-only after sealing. A missing `receipt.json` means interruption and is not
a pass. Evidence should be retained or copied to the release record without
altering the original directory.

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
