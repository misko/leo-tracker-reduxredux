# Immutable production deployment and lean Standard cutover

This is the authoritative transition from the temporary `mouse9911` user
services to canonical system services running as the dedicated `leo` account.
It is deliberately split into gates. Staging a release cannot touch the live
data plane, PostgreSQL, systemd, or `/opt/leo-tracker/current`. The ordinary
Standard path uses the committed, independently reviewed four-path regression
as scientific authority and a bounded post-start live canary for operational
proof.

In short: the reviewed four-path Standard receipt, qualification of the exact
staged SHA, and an `alembic upgrade head` are mandatory gates. A 24-hour soak is
not a prerequisite for Standard capture startup. A separately requested soak
receipt remains an optional alternative qualification authority.

`/mnt/qnap01` is outside the deployment and is inaccessible to every canonical
service. Do not start or wait for a new radio soak during this cutover.

## Topology and invariants

```text
/opt/leo-tracker/releases/FULL_SHA/       immutable checkout, venv, web build
/opt/leo-tracker/current -> releases/...  only mutable application selector
/etc/leo/leo.env                          root:leo 0640 configuration
/etc/systemd/system/leo-*                 root-owned canonical units
/srv/bulk/leo                             existing local data plane; never replaced
PostgreSQL leo_tracker                    existing catalog; migrated forward in place
```

The release tree is root-owned and not writable by `leo`. Runtime writes are
confined to `/srv/bulk/leo`. The API gets read-only access. Acquisition has
CPU/IO weights `1000/1000` and OOM score adjustment `200`; API is
`200/200/400`; workers are `100/100/500`; reconcile and retention are lower.
This preserves acquisition before API, workers, and maintenance under pressure.

The production acquisition service supplies the reviewed dual-RX 2.5 and 5 MS/s
profiles. Its exact eight-dwell policy persists a digest-bound, permuted bag with
two both-2.5 dwells, two both-5 dwells, and one 2.5/high mixed dwell for each of
5, 10, 15, and 20 MS/s. Mixed high-radio order, high-rate RX, tuning, and tandem
HOLD/AUTO mode are deterministic random selections bound before either radio is
opened, so retries cannot redraw them. The reviewed 60-second profiles and
180-second start period begin one dwell every three minutes.

## Stage 0 — freeze the cutover inputs

Choose the exact commit only after all intended code and deployment changes
are committed. Use a full SHA, never a branch, tag, abbreviated SHA, or dirty
worktree:

```text
cd /home/mouse9911/gits/leo-tracker-reduxredux
git status --short
release_revision=$(git rev-parse HEAD)
test ${#release_revision} -eq 40
```

Record the revision in the operator log. Do not proceed if `git status` has
output. The deployment helper clones committed objects; uncommitted files can
never enter a release.

## Stage 1 — release-only stage

First exercise the non-mutating validation form:

```text
deploy/scripts/stage-production-release \
  --source /home/mouse9911/gits/leo-tracker-reduxredux \
  --revision "$release_revision" \
  --python-bin /usr/bin/python3.14
```

After reviewing its exact target, use the deployment front door to stage it on
an existing production installation:

```text
sudo ./ops deploy --stage-only --revision "$release_revision"
```

This phase requires no test or rate-qualification receipt. It may create the
`leo` account and writes only beneath `/opt/leo-tracker` and `/var/lib/leo`; it
cannot touch systemd, `/etc/leo/leo.env`, component selectors, services,
PostgreSQL, `/srv/bulk/leo`, or QNAP. Repeating it for an existing immutable
target revalidates that target and changes no runtime state. It uses the sealed
`uv` from the current immutable release, so an existing global release selector
is required. Initial host bootstrap instead uses the reviewed raw stager with
an explicit tool path:

```text
sudo deploy/scripts/stage-production-release \
  --source /home/mouse9911/gits/leo-tracker-reduxredux \
  --revision "$release_revision" \
  --python-bin /usr/bin/python3.14 \
  --uv-bin /home/mouse9911/.local/bin/uv --execute
```

The staging helper creates `/opt/leo-tracker/releases/$release_revision`,
installs the locked hardware/Python dependencies, runs `npm ci`, provisions
Chromium for the `leo` account, builds the UI, verifies the installed
entrypoints, makes the tree root-owned and non-writable, and seals the
release-local copied `uv`
executable and lockfile hashes in external publication metadata. The helper
seals `uv` at `.release-tools/uv` inside this exact release before running it as
`leo`. Older rollback candidates therefore never depend on mutable shared
tooling. The underlying stager's `--python-bin` is mandatory and accepts only
an explicitly versioned, root-owned, non-writable interpreter under `/usr/bin`
whose observed version is Python 3.12 or newer. The selected path, observed
major/minor version, and executable SHA-256 are sealed in release metadata;
replacing the host interpreter therefore invalidates qualification and rollback
until a matching release is staged. An unversioned or service-account-managed
Python is refused.
This host currently supplies `/usr/bin/python3.14`.

The hardware build also installs the metadata-ABI-1 host runtime matched to the
production `.20`/`.21` firmware. It uses the release-sealed `uv`, verifies the
immutable upstream libiio source commit, installs native libiio and pylibiio
inside the release venv, and writes
`.venv/share/pluto-plus-utils/metadata-runtime.json`. Publication verifies this
runtime in a fresh process with ambient loader variables removed, before any
entrypoint can import pyadi. The external release metadata seals the receipt,
native library, and Python binding hashes. Missing build tools, a wrong
constructor ABI, a non-release native mapping, or any hash mismatch aborts
staging; stock system libiio is never a fallback.

Before any cache write, `prepare-leo-cache` walks `/var`, `/var/lib`,
`/var/lib/leo`, `.cache`, `uv`, and `ms-playwright` one component at a time
with no-follow file-descriptor operations. It requires fixed ownership and
modes and rejects symlinks lexically, before their targets can be accessed.
It uses the stable
`PLAYWRIGHT_BROWSERS_PATH=/var/lib/leo/.cache/ms-playwright` for both staging
and systemd qualification, so a previous failed attempt is safely retryable.
It refuses to overwrite either a staging or release directory. It does not
create or change `current`.

Every checkout is verified by `check-staged-release` before the build and again
as `leo` after the build. Source is renamed to its exact final SHA directory
*before* `uv sync --no-editable`, so console-script shebangs, package metadata,
and imports are created at the path they will use in production; no virtual
environment is relocated. The directory carries a root-owned
`.leo-release-incomplete` marker and is not published while the build runs.
The checker captures the exit status of both Git
commands before interpreting their output, so an ownership/safe-directory or
other Git failure is a hard failure rather than an apparently empty clean
status. A host-wide nonblocking `flock` serializes publishers. The exit trap
removes only invocation-created staging or exact-SHA incomplete paths, and only
while both `current` and external metadata are absent. It never removes a
selected or published release.

After root ownership and permissions are final, `leo`, `leo-api --check`, and
`leo-release-qualify --help` are executed as `leo`; the installed module must
import from that release's noneditable venv, and a binary scan rejects every
staging-path reference. A unique metadata temporary file is hash-validated,
the incomplete marker is removed and fsynced, and the external `0440`
root:`leo` metadata rename is the final publication operation. Cutover and
every canonical-path qualification revalidate metadata, ownership, hashes,
entrypoints, imports, and path confinement.

### Quarantine a release published by the former masked check

Revision `62889572f09930376a61c4a167ee01fa41dac402` completed its build, but its
final Git command failed the dubious-ownership check and the former shell
assertion mistakenly interpreted that failure as clean. It must never become
`current` or count as qualified evidence. Because no `current` symlink or
service refers to it, preserve it recoverably rather than deleting it:

```text
bad_revision=62889572f09930376a61c4a167ee01fa41dac402
sudo test ! -e /opt/leo-tracker/current
sudo test ! -L /opt/leo-tracker/current
sudo install -d -o root -g leo -m 0750 /opt/leo-tracker/quarantine
sudo mv -- /opt/leo-tracker/releases/$bad_revision \
  /opt/leo-tracker/quarantine/$bad_revision.invalid-cleanliness-check
sudo mv -- /opt/leo-tracker/release-metadata/$bad_revision.txt \
  /opt/leo-tracker/quarantine/$bad_revision.invalid-cleanliness-check.metadata
```

Abort if either `current` check fails. Do not remove, overwrite, or restage the
same SHA. Commit the checker fix, stage that new full SHA, and qualify only the
new release. The quarantine operation changes `/opt` only; it does not touch
services, PostgreSQL, `/srv/bulk`, recordings, or QNAP.

Revision `125a8f112fa46715e543f9e935562d85b98d1a3f` was likewise published by
the former relocate-after-build design. Its entrypoint shebangs and editable
package path name the removed `.staging-125a8f1...` directory, so it is invalid
even though its tracked checkout is clean. With `current` absent, quarantine
its release and metadata exactly as above, using suffix
`.invalid-relocated-venv`; never repair or select it in place.

## Stage 2 — frozen Standard evidence, without a new radio campaign

Install a sealed copy of the reviewed four-path regression receipt from the
exact staged release. The cutover verifier checks its complete raw SHA-256,
the staged committed copy, the golden summary SHA-256, all four path identities,
both byte-identical full-run outputs, polynomial coverage, and candidate-only
claim fences.

```text
sudo install -d -o root -g leo -m 0750 /srv/bulk/leo/qualification/standard-cutover
sudo install -o root -g leo -m 0440 \
  /opt/leo-tracker/releases/$release_revision/corpus/goldens/trial-132-standard-v2-full-review-receipt.json \
  /srv/bulk/leo/qualification/standard-cutover/trial-132-standard-v2-full-review-receipt.json
```

This receipt supplies scientific regression authority only. The bounded
post-start canary in stage 7 supplies installed capture, queue, processing, UI,
and restart evidence. Do not acquire extra scientific acceptance data.

If an operator separately chooses the legacy qualification-soak route, complete
[final-soak-audit.md](final-soak-audit.md) and pass its sealed receipt with
`--soak-receipt` instead. That optional route is never required for ordinary
Standard startup.

Run the protected corpus and compiled Chromium lane against the *same staged
SHA*. It may run while ordinary workers/API remain active, but only after the
service account has read ACLs on the local protected corpus and write access to
the release evidence directory (stage 3 below). Its sealed receipt must say
`passed=true` and `git_revision=$release_revision`.

## Stage 3 — maintenance window and service-account access

Announce the maintenance window. Review the exact temporary user services, then
stop and disable only these known LEO units; do not use a broad process kill:

```text
systemctl --user list-units 'leo-*' --all --no-pager
systemctl --user stop leo-reconcile.timer leo-retention.timer
systemctl --user stop leo-soak-worker-{01..08}.service leo-api-production.service
systemctl --user disable leo-reconcile.timer leo-retention.timer \
  leo-soak-worker-{01..08}.service leo-api-production.service
systemctl --user list-units 'leo-*' --state=active,activating,reloading --no-legend
```

The final command must produce no output. Disable any legacy soak unit if it was
enabled; do not wait for or restart it. Do not delete the old user unit files
yet; they are the bounded initial rollback.

Create only the canonical local directories. Confirm all public stores share
one filesystem before changing access:

```text
sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/{recordings,analysis,spool,control,trash,presentation-cache,scanner-recordings,scanner-reports}
sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/spool/analysis
sudo install -d -o root -g leo -m 0750 /srv/bulk/leo/{test-corpus,qualification,backups}
sudo install -d -o root -g leo -m 2770 \
  /srv/bulk/leo/qualification/{release,capture,legacy,frequency-calibration-plans,frequency-calibration-promotions,wp11-configs,wp11-plans,trusted-campaigns}
sudo install -d -o root -g leo -m 2770 /srv/bulk/leo/qualification/wp11-plan-runs
stat -c '%d %n' /srv/bulk/leo/{recordings,analysis,spool,trash}
findmnt -T /srv/bulk/leo
```

All four `stat` device numbers must match. Never recursively `chown` the data
plane: immutable evidence retains its original ownership. Grant `leo` read and
traverse access to existing immutable stores and read/write access to recovery
state, then set inheritable ACLs for new objects:

```text
sudo setfacl -R -m u:leo:rX /srv/bulk/leo/recordings /srv/bulk/leo/analysis \
  /srv/bulk/leo/test-corpus /srv/bulk/leo/qualification
sudo setfacl -R -m u:leo:rwX /srv/bulk/leo/spool /srv/bulk/leo/control \
  /srv/bulk/leo/trash /srv/bulk/leo/presentation-cache \
  /srv/bulk/leo/scanner-recordings /srv/bulk/leo/scanner-reports
sudo find /srv/bulk/leo/recordings /srv/bulk/leo/analysis -xdev -type d \
  -exec setfacl -m u:leo:rwx {} +
sudo setfacl -m u:leo:rwx,d:u:leo:rwx /srv/bulk/leo/{recordings,analysis,spool,control,trash,presentation-cache,scanner-recordings,scanner-reports}
sudo setfacl -m u:leo:rwx,d:u:leo:rwx \
  /srv/bulk/leo/qualification/{release,capture,legacy,frequency-calibration-plans,frequency-calibration-promotions,wp11-configs,wp11-plans,trusted-campaigns}
sudo setfacl -m u:leo:rwx,d:u:leo:rwx /srv/bulk/leo/qualification/wp11-plan-runs
sudo -u leo test -r /srv/bulk/leo/test-corpus/manifest.json
sudo -u leo test -w /srv/bulk/leo/recordings
sudo -u leo test -w /srv/bulk/leo/analysis
sudo -u leo test -w /srv/bulk/leo/spool
sudo -u leo test -w /srv/bulk/leo/scanner-recordings
sudo -u leo test -w /srv/bulk/leo/scanner-reports
for path in release capture legacy frequency-calibration-plans \
  frequency-calibration-promotions wp11-configs wp11-plans trusted-campaigns; do
  sudo -u leo test -w "/srv/bulk/leo/qualification/$path"
done
sudo -u leo test -w /srv/bulk/leo/qualification/wp11-plan-runs
```

The qualification-only legacy oracle remains pinned to its reviewed historical
checkout and managed interpreter. Grant `leo` traversal/read access to only
those immutable trees; ACLs do not change their reviewed mode bits or content:

```text
legacy_checkout=/home/mouse9911/gits/leo-tracker-oracle-0bb80d1
legacy_python=/home/mouse9911/.local/share/uv/python/cpython-3.12.14-linux-x86_64-gnu
sudo setfacl -m u:leo:--x /home/mouse9911
sudo setfacl -m u:leo:--x /home/mouse9911/.local /home/mouse9911/.local/share \
  /home/mouse9911/.local/share/uv /home/mouse9911/.local/share/uv/python
sudo setfacl -R -m u:leo:rX "$legacy_checkout" "$legacy_python"
sudo -u leo test -x "$legacy_checkout/.venv/bin/python"
sudo -u leo "$legacy_checkout/.venv/bin/python" -I -S -c \
  'import sys; assert sys.version_info[:2] == (3, 12)'
sudo -u leo /usr/bin/git -c "safe.directory=$legacy_checkout" \
  -C "$legacy_checkout" rev-parse --verify HEAD
```

Do not grant general `leo` read access to the home directory. If either exact
runtime path or any frozen identity changes, stop and perform a new legacy
environment review rather than widening the ACL or bypassing preflight.
The launcher repeats the exact command-local `safe.directory` setting for every
Git query and never writes global or per-user Git configuration.

The directory-only ACL pass is required because a new recording may share an
existing date hierarchy and a new run may share an existing session hierarchy.
It grants entry creation/removal on those directories but does not make any
immutable IQ or artifact file writable. `-xdev` prevents crossing a nested
mount. These operations change metadata only on the local RAID and can take
time. They must never name `/mnt/qnap01`.

## Stage 4 — configuration, database backup, and exact release qualification

### Preferred guarded cutover for an existing production installation

Once `/etc/leo/leo.env`, the production database, and component selectors
already exist, do **not** execute the manual selector/start sequence in the
remainder of Stages 4–6. Use the audited deployment transaction. It snapshots
the original environment bytes and all four selectors, qualifies the target,
quiesces every shipped LEO service/timer and worker, applies the exact reviewed
continuity environment, fences old-release work, switches the four component
selectors, installs units, starts the runtime, and verifies health. Automatic
rollback performs those operations in reverse before it starts the prior code.

From a clean target worktree:

```text
git fetch origin main
release_revision=$(git rev-parse HEAD)
test "$release_revision" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain)"
LEO_TEST_DATABASE_URL=postgresql+psycopg:///leo_qualification ./ops test --release
sudo ./ops deploy --stage-only --revision "$release_revision"

required_keys=(
  LEO_DATABASE_URL LEO_PIPELINE_RELEASE_ID LEO_CAPTURE_PROFILE
  LEO_CAPTURE_PROFILE_5M LEO_MIXED_RATE_POLICY
  LEO_CAPTURE_INTERVAL_SECONDS LEO_QUALIFICATION_PROFILE LEO_SOAK_PROFILE
  LEO_SCANNER_ENABLED LEO_SCANNER_RADIO_ID LEO_SCANNER_INTERVAL_SECONDS
  LEO_SCANNER_MAXIMUM_LATENESS_SECONDS LEO_SCANNER_DWELL_MS
  LEO_SCANNER_GAIN_DB LEO_SCANNER_MARGIN_GATE LEO_SCANNER_REPORT_ROOT
)
for key in "${required_keys[@]}"; do
  count=$(sudo awk -F= -v expected="$key" '$1 == expected { count += 1 } END { print count + 0 }' \
    /etc/leo/leo.env)
  test "$count" -eq 1 || { echo "invalid environment binding count: $key=$count" >&2; exit 1; }
done

environment_snapshot=/etc/leo/leo.env.pre-$release_revision
sudo test ! -e "$environment_snapshot"
sudo install -o root -g leo -m 0440 /etc/leo/leo.env "$environment_snapshot"
sudo sha256sum "$environment_snapshot"

./ops deploy --plan --revision "$release_revision"
sudo ./ops deploy --full --revision "$release_revision"
```

The full-cutover transaction runs any required `alembic upgrade head` while
every LEO unit is quiescent. Before starting any worker, its cutover preflight reads
`public.processing_resource_capacity` as `leo` with `psql --no-psqlrc` and
requires the complete ordered inventory to be exactly `streaming=16`, `cpu=8`,
`memory=4`, and `heavy=3`. A missing, duplicate, extra, malformed, or drifted
row blocks startup.

The historical target-bound 3 MS/s qualification receipt is not a cutover gate:
3 MS/s is absent from `production-native-rates-8-v2`. The transaction instead
checks the exact staged profile bytes and service command, the exact-revision
release qualification, the reviewed Standard regression authority, and both
live radios through the ABI-3 counter-authoritative adapter before starting any
runtime unit. A bounded post-start cycle verifies policy behavior. Failures of
experimental 10/15/20 MS/s legs are recorded as firmware evidence and do not
renormalize or silently replace the scheduled dwell.

The current Standard-native scientific product family is reviewed through
10 MS/s. A successful 15 or 20 MS/s capture remains durably cataloged, but
automatic Standard analysis refuses it with the explicit unreviewed-rate error
until an additive path/source product major is qualified; published contracts
are not widened in place. The 10 MS/s single-RX branch is covered by the
radio-report V5 and paired-report V6 three-path operational vertical.

Legacy V6 3 MS/s and native-bandwidth receipts remain immutable historical
evidence, but the current deployment path neither regenerates nor consumes
them. Do not run those retired RF campaigns as part of this cutover.

Do not pre-edit the production environment to the reviewed target values: doing so
would make a naive rollback snapshot the new configuration rather than the
true pre-cutover bytes. The deployment transaction applies only the exact
reviewed key map after preserving the original. Before invoking it, separately
confirm capture control is paused/drained and that no processing job or radio
lease is active. After it returns, verify all 20 workers—not just workers 1 and
20—and confirm `NRestarts=0`, all four selectors, the API, and the unchanged
capture-control generation.

The remainder of Stages 4–6 documents first-time host bootstrap and the
underlying checks. It is not the normal upgrade procedure for an active
component-selected installation.

Install the example once; never overwrite an existing reviewed file:

```text
sudo install -d -o root -g leo -m 0750 /etc/leo
sudo test -e /etc/leo/leo.env || sudo install -o root -g leo -m 0640 \
  /opt/leo-tracker/releases/$release_revision/deploy/etc/leo/leo.env.example \
  /etc/leo/leo.env
sudoedit /etc/leo/leo.env
sudo stat -c '%U:%G %a %n' /etc/leo/leo.env
```

Install the reviewed four-path station authority as a root-owned, read-only
document and verify the exact file identity configured in `leo.env`:

```text
sudo install -d -o root -g leo -m 0750 /etc/leo/station-authority
sudo install -o root -g leo -m 0440 \
  /opt/leo-tracker/releases/$release_revision/deploy/station/gauss-four-path-postreboot-20260816-v1.json \
  /etc/leo/station-authority/gauss-four-path-postreboot-20260816-v1.json
echo '5ec14f15bfe2a6abc52024f41db29b4ab6123209e6c4779a47644b1e70c477ae  /etc/leo/station-authority/gauss-four-path-postreboot-20260816-v1.json' \
  | sha256sum --check --strict
```

Verify the frozen station radio IDs, addresses, and serials against the two
committed station-topology documents. Set `LEO_PIPELINE_RELEASE_ID` to the exact
40-character `$release_revision`; never reuse
`standard-v1` or another existing catalog ID for a changed graph. Keep the paths
on `/srv/bulk/leo` and `/opt/leo-tracker/current`. Do not create retention,
qualification, soak, or release-qualification marker files yet.

Back up the production catalog before ownership or migration changes. Never
put the backup on QNAP:

```text
sudo install -d -o root -g leo -m 0750 /srv/bulk/leo/backups/postgresql
backup_file=/srv/bulk/leo/backups/postgresql/pre-cutover-$release_revision.dump
test ! -e "$backup_file"
set -o pipefail
sudo -u postgres pg_dump --format=custom leo_tracker | sudo tee "$backup_file" >/dev/null
sudo chown root:leo "$backup_file"
sudo chmod 0440 "$backup_file"
sudo pg_restore --list "$backup_file" >/dev/null
sudo sha256sum "$backup_file"
```

Peer authentication means runtime connections originate as `leo`. Inspect
owners before changing anything. On this host the expected former owner is
`mouse9911`; abort if another owner appears, then transfer only that role's
objects in the production database:

```text
sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='leo'" | grep -qx 1 || \
  sudo -u postgres createuser --login leo
sudo -u postgres psql -tAc "select 1 from pg_roles where rolname='leo'" | grep -qx 1
sudo -u postgres psql -d leo_tracker -c \
  "select distinct tableowner from pg_tables where schemaname='public'"
sudo -u postgres psql -d leo_tracker -v ON_ERROR_STOP=1 -c \
  'REASSIGN OWNED BY mouse9911 TO leo'
sudo -u postgres psql -v ON_ERROR_STOP=1 -c 'ALTER DATABASE leo_tracker OWNER TO leo'
sudo -u postgres psql -d leo_tracker -v ON_ERROR_STOP=1 -c 'ALTER SCHEMA public OWNER TO leo'
```

Create the separately isolated qualification database if absent. Select the
release temporarily by an atomic link only after all user services are down:

```text
sudo -u postgres psql -tAc "select 1 from pg_database where datname='leo_qualification'" | grep -qx 1 || \
  sudo -u postgres createdb --owner=leo leo_qualification
sudo ln -s releases/$release_revision /opt/leo-tracker/current.next
sudo mv -Tf /opt/leo-tracker/current.next /opt/leo-tracker/current
sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
  /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini upgrade head
sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
  /opt/leo-tracker/current/.venv/bin/alembic -c /opt/leo-tracker/current/alembic.ini current
```

Now run `leo-release-qualify --project-root /opt/leo-tracker/current` with the
reviewed environment, as described in [release-qualification.md](release-qualification.md).
Do not continue until its sealed receipt passes and names the exact SHA.

## Stage 5 — fail-closed cutover preflight

Run the repository verifier as root. It is read-only: it validates immutable
release identity/build output, exact-revision release qualification, frozen
four-path Standard evidence, station-authority inode/digest, environment
permissions/placeholders, both systemd scopes, unit syntax, and QNAP denial.

```text
sudo /opt/leo-tracker/current/deploy/scripts/verify-production-cutover \
  --revision "$release_revision" --legacy-user mouse9911 \
  --release-receipt /srv/bulk/leo/qualification/release/RUN_ID/receipt.json \
  --standard-regression-receipt \
    /srv/bulk/leo/qualification/standard-cutover/trial-132-standard-v2-full-review-receipt.json
```

`CUTOVER PREFLIGHT PASSED` is mandatory. Any warning or failure is a stop
condition, not permission to bypass the check.

## Stage 6 — install units and controlled startup

Install from the selected immutable release and validate before daemon reload:

```text
sudo install -o root -g root -m 0644 /opt/leo-tracker/current/deploy/systemd/leo-* \
  /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/leo-*.service \
  /etc/systemd/system/leo-*.timer
sudo systemctl daemon-reload
```

Run doctor before starting any continuous service:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire profiles validate'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire doctor --probe-radios'
sudo systemctl start leo-reconcile.service
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo process retention-run --dry-run --json'
```

Start in dependency order. Twenty worker processes remain the global process
bound on the 24-logical-CPU production host. Catalog admission is intentionally
stricter by resource class: `streaming=16`, `cpu=8`, `memory=4`, and `heavy=3`.
Each worker forces OpenBLAS, OpenMP, and MKL to at most eight threads at the
exec boundary, after environment-file composition. The three-lease HEAVY cap
therefore admits at most three independent native path jobs and 24 nominal
numerical-library threads at once. Acquisition remains protected by its higher
CPU and I/O weights and lower nice value. This reviewed 3-by-8 profile replaces
the 2-by-10 profile after host telemetry showed sustained idle E-core capacity,
negligible CPU pressure and I/O wait, no swap, and a heavy-analysis queue whose
peak arrival rate exceeded the prior two-lease service rate. Revisit the profile
only with measured CPU pressure, memory, I/O, capture-continuity, RAID, OOM,
swap, thermal, and kernel-storage evidence:

```text
sudo systemctl enable --now leo-reconcile.timer
sudo systemctl enable --now leo-worker@{1..20}.service
sudo systemctl enable --now leo-api.service
sudo systemctl enable --now leo-acquisition.service
sudo systemctl enable --now leo-retention.timer
```

The retention timer is harmless without `/etc/leo/retention-enabled`. Create
that marker only after a reviewed dry run, hold inventory, backup verification,
and recovery drill. Never enable the radio qualification timer or soak unit
during continuous acquisition.

## Stage 7 — runtime proof before removing the rollback

Capture these exact properties for acquisition, API, and every worker:

```text
sudo systemctl show leo-acquisition.service leo-api.service leo-worker@{1..20}.service \
  -p Id -p ActiveState -p SubState -p MainPID -p NRestarts \
  -p CPUWeight -p IOWeight -p Nice -p OOMScoreAdjust
sudo systemctl status leo-acquisition.service leo-api.service 'leo-worker@*.service' --no-pager
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire status --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo process jobs --json'
curl --fail http://127.0.0.1:8090/api/v1/status
```

The durable authority is still paused after qualification and deployment. Keep
it paused during ordinary service startup. For each of the two direct canaries,
stop the acquisition scheduler first, explicitly resume, run exactly one
dual-radio one-shot, and immediately re-pause and drain before restarting the
scheduler. This prevents the scheduler from racing the direct command. Run the
pause command even if its preceding one-shot fails; do not restart the service
until status again reports paused and drained.

Run the exact 2.5 MS/s canary first:

```text
sudo systemctl stop leo-acquisition.service
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire resume --operator production-cutover \
  --reason "bounded direct 2.5 MS/s post-cutover canary" --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire once --profile "$LEO_CAPTURE_PROFILE" --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire pause --operator production-cutover \
  --reason "direct 2.5 MS/s post-cutover canary complete" \
  --wait --timeout-seconds 90 --json'
sudo systemctl start leo-acquisition.service
```

Save its session ID, then verify registration, the exact Standard subject
hierarchy, queue creation, worker completion, and API/UI visibility:

```text
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo process search --limit 5 --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo process show SESSION_ID --subjects --json'
curl --fail --max-time 10 'http://127.0.0.1:8090/api/v1/recordings?limit=5'
curl --fail --max-time 10 'http://127.0.0.1:8090/api/v2/recordings/SESSION_ID/standard-subjects'
```

Confirm the live session exposes the paired radio0+radio1 subject, both radio
subjects, all four RX subjects, pipeline release `$release_revision`, and a
current completed analysis after workers drain. Confirm `NRestarts=0` and the
expected weights/OOM adjustments.

Then stop acquisition, start one reconcile pass, and restart acquisition while
the durable authority remains paused. Verify the service reports active but
capture remains paused. Stop acquisition again and run the exact 5 MS/s canary
under the same explicit resume/re-pause boundary:

```text
sudo systemctl stop leo-acquisition.service
sudo systemctl start leo-reconcile.service
sudo systemctl start leo-acquisition.service
sudo systemctl show leo-acquisition.service -p ActiveState -p SubState -p MainPID -p NRestarts
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; leo acquire status --json'
sudo systemctl stop leo-acquisition.service
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire resume --operator production-cutover \
  --reason "bounded direct 5 MS/s post-cutover canary" --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire once --profile "$LEO_CAPTURE_PROFILE_5M" --json'
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  leo acquire pause --operator production-cutover \
  --reason "direct 5 MS/s post-cutover canary complete" \
  --wait --timeout-seconds 90 --json'
sudo systemctl start leo-acquisition.service
```

Verify the 5 MS/s session reaches the same Current Standard/UI state and that
final capture status remains paused. Stop and investigate if either bounded
dwell fails; do not continue collecting to compensate. These two short observations,
each 60 seconds, supply the installed capture and restart evidence required by
R-030 without enabling continuous acquisition. Retain the old user units until
both observations pass. Continuous acquisition requires a later, separate
operator resume.

Retain the two session IDs, CLI/API responses, `systemctl show` output, and UTC
observation bounds beneath `/srv/bulk/leo/qualification/standard-cutover`, then
seal those files read-only. They are operational evidence, not additional
scientific acceptance data.

## Fast API-only restart during development

When `/opt/leo-tracker/current` already names a staged, qualified immutable
release and neither its release identity nor the database schema is changing,
restart only the API:

```text
sudo /opt/leo-tracker/current/deploy/scripts/restart-current-api
```

This command verifies the exact relative 40-character release selector, sealed
metadata ownership, and installed API entrypoint; restarts only
`leo-api.service`; and waits at most 30 seconds for `/api/v1/status`. It does
not stage or qualify a release, run cutover preflight, migrate PostgreSQL,
drain or restart workers, reconcile recordings, or touch acquisition.

Do not use this fast path after a code revision, environment authority, unit,
dependency, or schema change. Those changes still require the guarded release
cutover above.

## Fast worker stop-and-fence during development cutovers

Do not wait for worker leases to expire when replacing one exact release.
Before changing `current`, record the old 40-character selector. Stop new
acquisition, kill the old worker cgroups, and stop their units. After selecting
the new release and applying its migration, use the new release's CLI to fence
every still-active run owned by the exact old release:

```text
old_release=OLD_40_CHARACTER_SHA
new_release=NEW_40_CHARACTER_SHA
operation_id=deploy-YYYYMMDDTHHMMSSZ-$old_release

sudo systemctl stop leo-acquisition.service
sudo systemctl kill --kill-who=all --signal=SIGKILL 'leo-worker@*.service'
sudo systemctl stop 'leo-worker@*.service'

sudo -u leo env LEO_DATABASE_URL=postgresql+psycopg:///leo_tracker \
  /opt/leo-tracker/releases/$new_release/.venv/bin/alembic \
  -c /opt/leo-tracker/releases/$new_release/alembic.ini upgrade head
sudo -u leo /bin/bash -c 'set -a; source /etc/leo/leo.env; set +a; \
  exec /opt/leo-tracker/releases/'"$new_release"'/.venv/bin/leo \
  process stop-and-fence --release '"$old_release"' \
  --operation-id '"$operation_id"' --operator deployment \
  --reason "development cutover to '"$new_release"'" \
  --all-active-for-release --yes --json'
```

The catalog operation is one PostgreSQL transaction. It serializes against
claims for that release, expires leased attempts, cancels leased and pending
jobs, cancels their active runs, and writes immutable operator evidence. Late
heartbeats, publications, and completions fail because their job leases have
been revoked. Succeeded jobs, products, artifacts, recordings, and immutable
release directories are preserved. Replaying the same `operation_id` and exact
arguments is harmless; reusing it for different arguments is refused.

For narrower maintenance, replace `--all-active-for-release` with one
`--expect-run RUN_ID` per active run. The operation rolls back if the exact
active inventory differs. The CLI refuses a malformed release and refuses the
configured current release unless the operator supplies the separate
`--allow-current-release` safeguard. Start only the new release's workers and
acquisition after the fence receipt is successful. Old immutable release
directories remain intentionally available for audit and rollback; they have
no execution authority after their processes are killed and active runs fenced.

## Rollback without data loss

The guarded `./ops deploy --full` path automatically rolls back a failed
no-migration cutover. It quiesces the target runtime **before** restoring the
original environment bytes, all four selector snapshots (`current`,
`current-api`, `current-worker`, and `current-acquisition`), and prior units. It
then fences active target-release work, starts and verifies the prior runtime,
and quiesces again if that verification fails. A schema-changing failure stays
stopped; never run `alembic downgrade` against the application database.

For an operator-initiated rollback after a nominally successful deployment:

1. Pause and drain capture; record the exact failed and previous release SHAs,
   capture-control document, environment snapshot digest, selector targets, and
   active job/lease inventory.
2. Stop all timers and services listed in `tools/ops.py`, kill/stop every
   `leo-worker@*.service`, and require no LEO unit in `active`, `activating`,
   `reloading`, or `deactivating` state.
3. Require the previous release's Alembic head to equal the production database
   head. If it differs, remain stopped and fix forward.
4. Atomically restore the root-owned pre-cutover environment snapshot and all
   four selector snapshots. Reinstall units from the previous immutable global
   release and run `systemctl daemon-reload`.
5. With the restored environment but the failed release's CLI, fence every
   still-active job/run owned by the failed release. Preserve the receipt.
6. Start the previous API, all 20 workers, acquisition, and the normal timers;
   verify every selector, unit, restart count, API, and unchanged paused capture
   state. If any prior-health check fails, quiesce the entire runtime again.

Rollback never deletes or rewrites recordings, artifacts, database rows,
receipts, scanner reports, gap maps, or either immutable release. Never touch
QNAP, never overwrite/drop `leo_tracker`, and never relabel a legacy
continuity-unobservable recording as safe. Preserve the pre-cutover database
dump and environment snapshot until operator review closes the rollback window.

## Deferred post-resync tuning

The RAID is currently rebuilding at about 50 MB/s. That degraded measurement
does not establish final writer capacity. After resync completes, rerun the
128-MiB-shard sustained writer benchmark and induced-backlog worker benchmark,
then record the chosen worker count and acquisition reserve in qualification
evidence. Keep the catalog HEAVY capacity at two until that evidence proves
memory and I/O headroom; four is the maximum reviewed next step, not an
automatic post-resync setting.
