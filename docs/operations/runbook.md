# LEO Tracker operator runbook

This runbook operates the dedicated local host: PostgreSQL is the control
plane, `/srv/bulk/leo` is the local RAID data plane, and up to two Ethernet
Pluto+ radios provide at most two RX channels each. Commands shown as `leo`
must run with the production environment from `/etc/leo/leo.env`.

Initial installation, immutable release staging, and the transition from
temporary user services are governed by
[production-deployment.md](production-deployment.md). Its terminal-soak and
exact-revision cutover preflight are mandatory; this general runbook does not
override them.

## Non-negotiable safety rules

- `/mnt/qnap01` is a read-only legacy evidence source. Never configure it as
  `LEO_BULK_ROOT`, `LEO_CORPUS_ROOT`, a trash directory, a PostgreSQL backup
  destination, or a qualification output. Never delete, move, rename, or
  modify anything below it.
- A QNAP TEST import requires explicit `--copy --tag TEST`. It copies verified
  slices into the local corpus; it never manages the source.
- A recording session is the purge unit. Paired-radio streams are never split.
- A pin/hold protects raw data and current results. TEST data is automatically
  held. Only an explicit `unpin` releases an operator hold.
- The web/API service is read-only. Acquisition, reprocessing, imports, holds,
  and retention are CLI-only operations.
- Do not manually remove public recording or analysis paths. Use retention so
  filesystem staging, catalog tombstones, and recovery journals stay coherent.

## Initial installation

Prerequisites are Python 3.12+, `uv`, PostgreSQL 18, Node/npm for the web build,
the local RAID mounted at `/srv/bulk`, and working LAN routes to the radios.

1. Create the service account and production directories. The staging helper
   normally creates the account first; if creating it manually, use the same
   stable identity:

   ```text
   sudo useradd --system --home /var/lib/leo --create-home --shell /usr/sbin/nologin leo
   sudo install -d -o root -g leo -m 0755 /opt/leo-tracker
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/recordings
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/analysis
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/spool
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/spool/analysis
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/control
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/trash
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/scanner-recordings
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/scanner-reports
   sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/scanner-runs
   sudo install -d -o root -g leo -m 0750 /srv/bulk/leo/test-corpus
   sudo install -d -o root -g leo -m 0750 /srv/bulk/leo/qualification/acquisition
   sudo install -d -o root -g leo -m 0750 /etc/leo
   ```

   Keep `recordings/`, `analysis/`, `spool/`, and `trash/` on the same local
   filesystem so publication and purge staging use atomic renames. The 8 TB
   NVMe tier should be configured as cache beneath that filesystem, not mounted
   as a separate spool path. Confirm the resolved mount/device layout with
   `findmnt -T /srv/bulk/leo` and `stat -c %d` on those four directories.

2. Stage one exact committed SHA from the development checkout. Never run
   production from `/home` or mutate a deployed release in place:

   ```text
   sudo deploy/scripts/stage-production-release \
     --source /home/mouse9911/gits/leo-tracker-reduxredux \
     --revision FULL_40_HEX_SHA \
     --python-bin /usr/bin/python3.14 \
     --uv-bin /home/mouse9911/.local/bin/uv --execute
   ```

3. Copy `deploy/etc/leo/leo.env.example` to `/etc/leo/leo.env`. Replace both
   documentation IP addresses, both serial placeholders, and the capture
   profile. Keep the file non-secret by using local PostgreSQL peer
   authentication; if credentials are unavoidable, provision them through the
   host credential manager rather than committing them.

   ```text
   sudo install -o root -g leo -m 0640 \
     /opt/leo-tracker/current/deploy/etc/leo/leo.env.example /etc/leo/leo.env
   sudoedit /etc/leo/leo.env
   ```

   The unit sandbox and mount requirements intentionally hard-code the
   production root `/srv/bulk/leo`. If that root is ever changed, update
   `RequiresMountsFor`, `ReadWritePaths`, and `ReadOnlyPaths` in every affected
   unit in the same maintenance change, then rerun `systemd-analyze verify`.

4. Create the PostgreSQL role/database, verify connectivity, and apply the one
   Alembic history to head:

   ```text
   sudo -u postgres createuser leo
   sudo -u postgres createdb --owner=leo leo_tracker
   sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
     /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini upgrade head
   sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
     /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini current
   ```

5. Install and verify the units:

   ```text
   sudo install -o root -g root -m 0644 /opt/leo-tracker/current/deploy/systemd/leo-* \
     /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/leo-*.service \
     /etc/systemd/system/leo-*.timer
   sudo systemctl daemon-reload
   ```

Do not create either enable-marker file yet.

## Preflight and radio doctor

Load the exact service environment for interactive commands without echoing it
into logs, then validate profiles, storage, database configuration, and radio
identity:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire profiles validate'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire doctor --probe-radios'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire radios --probe'
```

Treat a serial mismatch, inaccessible radio, unwritable local bulk directory,
invalid profile, or unhealthy database as a stop condition. The Pluto timing
is best-effort overlap with measured uncertainty; it is not hardware trigger
or cross-radio phase coherence.

## Bounded two-rate scanner canary

Do not collect scanner RF without explicit operator authorization for that
specific run. Keep `LEO_SCANNER_ENABLED=false` in `/etc/leo/leo.env` while
qualifying the scanner. A canary consists of two adjacent UTC scanner slots:
one 300-second 2.5 MS/s run and one 300-second 5 MS/s run. Start within the
configured 120-second lateness allowance after a 20-minute UTC boundary; the
second run then finishes about 25 minutes after that boundary.

First pause and drain the shared capture authority, then stop the normal
supervisor. Verify that no acquisition operation remains leased:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire pause --reason "bounded two-rate scanner canary" \
    --operator operator --wait --json'
sudo systemctl stop leo-acquisition.service
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire status --json'
```

Immediately after an eligible boundary, resume the durable authority and run
the scanner-only supervisor with both an operation-count bound and a 29-minute
wall-clock backstop. The environment override applies only to this foreground
process; it does not enable scanning for the normal service. Scanner-only queue
claims skip all pending ordinary dwells while retaining the global radio mutex.

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; \
  export LEO_SCANNER_ENABLED=true; set +a; \
  leo acquire resume --operator operator --json; \
  timeout --signal=TERM --kill-after=30s 29m \
    leo acquire run --profile "$LEO_CAPTURE_PROFILE" \
      --scanner-only --max-scanner-runs 2 --json'
```

Whether the canary succeeds or fails, pause before restarting the normal
service. The checked-in environment keeps its scanner disabled:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire pause --reason "scanner canary complete" \
    --operator operator --wait --json'
sudo systemctl start leo-acquisition.service
```

Accept the canary only when exactly two new run manifests are `complete`, their
sample-rate set is `{2500000, 5000000}`, each RF bandwidth equals its sample
rate, each dwell is 120 ms, every run lasts approximately 300 seconds, and the
target order is CH1L, CH2L, CH3L, CH4L, CH1U, CH2U, CH3U, CH4U. Also verify
every referenced sweep bundle opens with its recorded manifest digest and that
standard analysis completes. Leave recurring scanning disabled until scanner
IQ has a reviewed, tested local-retention path; at the configured cadence its
conservative raw growth is 649,036,800,000 bytes/day.

## First capture and normal services

Each canonical profile records 60 seconds and
`LEO_CAPTURE_INTERVAL_SECONDS=180` defines the start-to-start period. The
service selects uniformly from the exact 2.5, 3, and 5 MS/s profile bindings
for each dwell, persists the selection, and applies it to both radios. The
runner subtracts capture, durable publication, and reconciliation time from
the following wait, so normal service starts one dwell every 180 seconds
without accumulating post-commit drift. The 5 MS/s profile remains segmented
and capture-only; its presence is not a continuity claim.

Run one bounded production-path capture before enabling continuous acquisition:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire once --profile "$LEO_CAPTURE_PROFILE" --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire status --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo process reconcile --json'
```

For a single-radio experiment, append one `--radio RADIO_ID`. For synchronized
best-effort dual capture, omit `--radio` to use both configured radios or repeat
it for the selected pair.

Enable services in dependency order:

```text
sudo systemctl enable --now leo-reconcile.timer
sudo systemctl start leo-reconcile.service
sudo systemctl enable --now leo-worker@1.service leo-worker@2.service
sudo systemctl enable --now leo-api.service
sudo systemctl enable --now leo-acquisition.service
sudo systemctl enable --now leo-retention.timer
```

The API serves open, unauthenticated HTTP on `0.0.0.0:$LEO_API_PORT`. Confirm
that firewall/routing exposes it only on the intended trusted LAN. HTTP has no
mutation routes.

Acquisition has deliberately higher CPU/I/O weight and lower nice/OOM scores
than workers. Start with two workers, observe acquisition continuity and queue
growth, and tune worker count only from soak evidence.

## Reconciliation and processing

Reconciliation validates manifest-last bundles, restores or completes any
fenced purge recovery, and idempotently registers committed recordings missed
during a database outage. It never treats `spool/` as committed:

```text
leo process reconcile --json
leo process jobs --json
leo process search --limit 20 --json
```

The periodic reconcile timer is the catalog-ingest boundary for newly committed
captures as well as an outage safety net; with the supplied timer, registration
and run creation may lag filesystem commit by up to five minutes. Any reported
corruption or identity conflict requires investigation; do not delete the path
to silence it.

Workers claim short PostgreSQL leases and renew them while processing. A worker
restart may repeat an attempt, but product registration and current-run
promotion are idempotent. Inspect worker health with:

```text
systemctl status 'leo-worker@*.service'
journalctl -u 'leo-worker@*.service' --since today
leo process jobs --json
```

To reprocess one locally available raw recording with the current pipeline:

```text
leo process show SESSION_ID --json
leo process paths SESSION_ID --json
leo process reprocess SESSION_ID --json
leo process jobs --json
```

The queue rejects scientifically identical work when an equivalent run is
pending, running, or has already succeeded. Identity includes the recording
and input manifest, pipeline lane and exact release, promotion policy, expanded
job graph, and stable subject/calibration bindings. Run UUIDs, trigger labels,
queue priority, and a fresh raw-integrity verification timestamp do not make a
new run. Failed and cancelled runs remain retryable; changing a scientific
input or pipeline definition creates distinct work.

The old current run remains visible until every new job succeeds, the run
manifest seals, and promotion commits atomically. A failed run does not replace
the old current result. Purged raw recordings cannot be reprocessed.

### Cancel a queued analysis run

Stop the source that is creating unwanted runs before cancelling a campaign.
Use the run ID returned by `reprocess`, import, reconciliation, or service logs,
then request cancellation with an explicit reason and confirmation:

```text
leo process cancel-run RUN_ID \
  --reason 'operator cancelled obsolete campaign' --yes --json
leo process jobs --json
```

Cancellation is a catalog transaction, not a file deletion. It changes pending
dependency jobs to `cancelled`, expires already-expired attempts, seals the run
as `cancelled`, and leaves completed attempts and immutable products available
for inspection. It never changes the session's current-analysis pointer. The
command refuses to cancel the current run or a run with a live worker lease;
allow the active worker to finish or its lease to expire, then retry. Repeating
the same cancellation is idempotent and reports `changed=false`.

Do not cancel runs by updating PostgreSQL rows or deleting analysis paths. For
a large campaign, first derive and review the exact run-ID set with a read-only
catalog query, save that evidence, and invoke the supported command once per
run. An example production cleanup and its measured result are recorded in
[`2026-08-19-qualification-backlog-cancellation.md`](2026-08-19-qualification-backlog-cancellation.md).

## TEST corpus import

Review the manifest and source paths first. Every source artifact must resolve
beneath `/mnt/qnap01`; the destination is `LEO_CORPUS_ROOT` on the local RAID.

```text
leo process import-qnap /mnt/qnap01/path/to/corpus-manifest.yaml \
  --copy --tag TEST --json
leo process reconcile --json
leo process search --test --held --json
```

The importer verifies the declared slice hashes, writes local immutable fixture
manifests/hold receipts, converts each REQUIRED fixture into an ordinary
compressed RecordingStore bundle, verifies it, registers it as TEST, and queues
the baseline analysis idempotently. PLANNED and
UNAVAILABLE_HISTORICAL_EVIDENCE declarations are not touched. The
command refuses operation without the explicit copy and TEST flags. Never
grant it a QNAP destination.

### Protected real-IQ CI lane

The small real-IQ fixtures currently have `license=NOASSERTION` and
`redistribution=not-assessed`, so do not copy them into Git or upload them as
public workflow artifacts. Register this dedicated machine as a GitHub Actions
self-hosted runner with the labels `linux`, `x64`, and `leo-corpus`. Keep the
materialized, held corpus at `/srv/bulk/leo/test-corpus` and local PostgreSQL
available through peer authentication.

Hosted runners execute the portable suite with `-m "not real_corpus"`. The
separate scheduled and per-change `real-corpus` job executes
`pytest -m real_corpus` on the dedicated host. Missing or corrupt REQUIRED
fixtures fail that job during preflight; no test uses a conditional skip. Treat
a queued real-corpus job as missing qualification evidence, not as a pass.

## Pinning and unpinning

Pin important data before experiments, schema changes, or retention pressure:

```text
leo process pin SESSION_ID --reason 'campaign baseline; retain permanently' --json
leo process show SESSION_ID --json
```

Pin creation writes the durable filesystem receipt before activating the
catalog hold, so a crash fails safe. Release only after a second operator-level
review:

```text
leo process unpin SESSION_ID --json
leo process show SESSION_ID --json
```

Release deactivates the database hold before removing its receipt. If either
operation is interrupted, reconciliation or a repeated command leaves the data
protected rather than prematurely deletable.

## Retention and admission

Policy is fixed at these initial thresholds:

| Used capacity | Behavior |
| --- | --- |
| Below 70% | No automatic purge selection |
| 70% or above | Select oldest eligible units until projected use is 65% |
| 75% or above | Operator warning |
| 80% or above | Stop new-capture admission if eligible deletion cannot reach 65% |

Eligible raw sessions must be committed, reconciled, successfully analyzed,
unheld, non-TEST, and free of active analysis/purge claims. Superseded artifacts
can be reclaimed independently; current UI products remain protected.

Always inspect status and a dry run first:

```text
leo process retention-status --json
leo process retention-run --dry-run --json
```

A manual destructive pass requires explicit confirmation:

```text
leo process retention-run --execute --yes --json
```

The timer invokes the separate systemd-only `--execute --automatic` path, but
the unit is skipped until the enable marker exists. Enable unattended behavior
only after backups, dry-run review, pin review, and a successful recovery drill:

```text
sudo install -o root -g root -m 0644 /dev/null /etc/leo/retention-enabled
sudo systemctl start leo-retention.service
sudo journalctl -u leo-retention.service -n 100 --no-pager
```

To disable it immediately, remove the marker and stop the timer/service. This
does not undo an already committed tombstone:

```text
sudo rm /etc/leo/retention-enabled
sudo systemctl stop leo-retention.timer leo-retention.service
```

Never create or remove this marker from the web UI.

## PostgreSQL backup and restore

PostgreSQL contains lifecycle state, jobs, holds, current-run pointers, and
search summaries. Back it up even though raw IQ is retained on the local RAID.
Store backups locally, never on QNAP:

```text
sudo install -d -o leo -g leo -m 0750 /srv/bulk/leo/backups/postgresql
sudo -u leo pg_dump --format=custom --file=/srv/bulk/leo/backups/postgresql/leo_tracker.dump \
  leo_tracker
sudo -u leo pg_restore --list /srv/bulk/leo/backups/postgresql/leo_tracker.dump >/dev/null
```

For the cleanest control-plane snapshot, briefly stop acquisition, workers,
reconcile, and retention before `pg_dump`; the API may remain read-only. Restart
in the order below.

Restore is destructive to the target database. Confirm the database name and
backup path, stop all LEO services, preserve the failed database for diagnosis,
then restore and reconcile:

```text
sudo systemctl stop leo-acquisition.service 'leo-worker@*.service' \
  leo-reconcile.timer leo-retention.timer leo-api.service
sudo -u postgres createdb --owner=leo leo_tracker_restore
sudo -u leo pg_restore --dbname=leo_tracker_restore \
  /srv/bulk/leo/backups/postgresql/leo_tracker.dump
sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker_restore \
  /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini upgrade head
```

Validate the restored database separately before switching
`LEO_DATABASE_URL`. Do not use `--clean` against the production database unless
the exact destructive target has been independently verified.

## Outage and crash recovery

Filesystem outage:

1. Stop acquisition, workers, reconciliation, and retention immediately.
2. Restore the local RAID mount at `/srv/bulk`; do not redirect production
   writes to QNAP.
3. Check RAID/filesystem health and free space.
4. Start PostgreSQL, run migrations, then run `leo process reconcile --json`.
5. Review reconciliation issues and `retention-run --dry-run`.
6. Start workers, API, and one bounded capture before continuous acquisition.

Database outage:

1. Stop retention and workers. Stop acquisition unless the current release has
   explicitly passed the database-outage capture qualification.
2. Recover PostgreSQL and run `alembic upgrade head`.
3. Run reconciliation; committed local bundles absent from PostgreSQL will be
   registered idempotently and spool directories remain ignored.
4. Inspect jobs/current pointers, then restart workers and acquisition.

Process death during retention:

1. Keep acquisition stopped if capacity is critical.
2. Run reconciliation before another retention pass. Fenced purge journals
   restore uncommitted staging or finish removal for committed tombstones.
3. Confirm holds, recording paths, and retention status before re-enabling the
   timer.

Never repair an outage by editing catalog rows or moving trash paths manually.

## Restart order and logs

After upgrade or outage:

```text
sudo systemctl start postgresql.service
sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
  /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini upgrade head
sudo systemctl start leo-reconcile.service
sudo systemctl start leo-worker@1.service leo-worker@2.service
sudo systemctl start leo-api.service
sudo systemctl start leo-acquisition.service
sudo systemctl start leo-reconcile.timer leo-retention.timer
```

Useful inspection commands:

```text
systemctl status leo-acquisition.service leo-api.service leo-reconcile.service
systemctl list-timers 'leo-*'
journalctl -u leo-acquisition.service -f
journalctl -u leo-reconcile.service -u leo-retention.service --since today
journalctl -u 'leo-worker@*.service' --since today
leo acquire status --json
leo process jobs --json
leo process retention-status --json
```

## Qualification and soak gate

Before declaring production readiness:

1. Stop continuous acquisition and leave the qualification timer disabled.
2. Run `doctor --probe-radios`.
3. Run the sustained writer benchmark with production 128 MiB shards:

   ```text
   leo acquire benchmark-writer --duration-seconds 60 --block-bytes 134217728 \
     --minimum-mb-s 60 --receivers 2 \
     --receipt /srv/bulk/leo/qualification/writer-60s.json --json
   ```

4. Run at least 100 real dual-radio capture trials with an immutable receipt:

   ```text
   leo acquire qualify --profile "$LEO_QUALIFICATION_PROFILE" --trials 100 \
     --receipt /srv/bulk/leo/qualification/acquisition/dual-100.json --resume --json
   ```

5. Run the full 60-second detector corpus, induced worker backlog, service
   restart/reconciliation, storage-pressure, and pin-versus-purge gates.
6. Complete the real 24-hour acquisition soak with the ordinary acquisition
   and recording pipeline. The harness writes one immutable file per trial and
   a bounded atomic aggregate; it records capture/digest state, samples,
   gaps/overflows, duty cycle and inter-capture gaps, synchronization timing,
   peak RSS, storage/admission state, and PostgreSQL backlog. It does not pin
   its recordings. See [acquisition-soak.md](acquisition-soak.md) for the
   evidence and recovery contract.

   Each committed trial is reconciled and queued before its backlog-after
   sample. Check `post_commit_failure_count=0` as well as the completion fields.
   A database failure is recorded without invalidating IQ, and a later callback
   can reconcile missed bundles, but that soak remains failed full-system
   evidence and must not be accepted as the production gate.

   The service is separately gated and has no timer. Set a new ID for each new
   qualification in `/etc/leo/leo.env`, then run it only in a planned window:

   ```text
   sudo systemctl stop leo-acquisition.service
   sudo install -o root -g root -m 0644 /dev/null /etc/leo/soak-enabled
   sudo systemctl start --no-block leo-acquisition-soak.service
   sudo systemctl show -p ActiveState -p SubState leo-acquisition-soak.service
   # Remove only after ActiveState=activating confirms the condition was evaluated.
   sudo rm /etc/leo/soak-enabled
   sudo journalctl -u leo-acquisition-soak.service -f
   ```

   `LEO_SOAK_DURATION_SECONDS` must remain `86400` for this gate. A short test
   or a trial-limited harness result is not the 24-hour gate. Do not mark the
   gate passed until the target-host run actually finishes with
   `completion_reason=duration` and `passed=true`. Resume an interrupted run
   with the same ID and configuration by recreating the marker and starting
   the service again.

The current writer-capacity evidence was collected while the RAID was rebuilding
at roughly 50 MB/s. It is intentionally conservative evidence of a
degraded state, not final tuning data. Rerun the sustained capacity benchmark
after the RAID rebuild completes before fixing worker count, admission reserve,
or expected duty-cycle limits.

Only enable the qualification unit/timer during a planned radio maintenance
window:

```text
sudo systemctl stop leo-acquisition.service
sudo install -o root -g root -m 0644 /dev/null /etc/leo/qualification-enabled
sudo systemctl start leo-qualification.service
sudo journalctl -u leo-qualification.service -f
sudo rm /etc/leo/qualification-enabled
sudo systemctl start leo-acquisition.service
```

Do not leave the qualification marker enabled during unattended production.
