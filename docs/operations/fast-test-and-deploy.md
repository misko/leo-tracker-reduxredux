# Fast test and deployment front door

The repository has one operator-facing command:

```bash
./ops test
./ops test --base CURRENT_PRODUCTION_SHA
release_revision=$(git rev-parse origin/main)
sudo ./ops deploy --stage-only --revision "$release_revision"
# Run the authorized hardware qualification with
# /opt/leo-tracker/releases/$release_revision/.venv/bin/python.
rate_receipt="/srv/bulk/leo/qualification/sample-rate-3m/accepted/$release_revision/contiguous-rate-qualification-receipt-v6.json"
./ops deploy --plan --revision "$release_revision" --rate-qualification-receipt "$rate_receipt"
sudo ./ops deploy --revision "$release_revision" --rate-qualification-receipt "$rate_receipt"
sudo ./ops releases --plan --keep 10
# Review plan_sha256, every protected reason, and every retirement candidate.
sudo ./ops releases --apply --keep 10 --expect-plan PLAN_SHA256
```

`./ops test` classifies the dirty overlay (or the current commit when clean), runs independent
component gates concurrently, and writes a JSON receipt under `.leo/test-receipts/`. Use
`./ops test --explain` to inspect the selection without executing it.

PostgreSQL gates have no default database. They require an explicit, test-owned database:

```bash
LEO_TEST_DATABASE_URL=postgresql+psycopg:///leo_qualification ./ops test
```

The command removes `LEO_DATABASE_URL` from every child. It rejects `leo_tracker`, PostgreSQL
maintenance databases, non-PostgreSQL URLs, and ambiguous database names before opening a
connection. A permitted database name must contain `qualification` or end in `_test`.

The available test tiers are:

```bash
./ops test                 # changed components
./ops test --all           # all portable components and explicit PostgreSQL tests
./ops test --release       # release-instruction tests in addition to --all
./ops test --base SHA      # exact clean committed delta intended for deployment
```

`./ops deploy --plan` is read-only. A full-cutover plan also requires the sealed,
exact-revision V6 combined-pool receipt via `--rate-qualification-receipt`. V6 binds the exact
deployed 3 MS/s and 5 MS/s device-axis profiles and fixed two-radio plans, production-radio safety
evidence, native-IP canaries, a measured incompressible writer benchmark of at least 100 MB/s, and
ten strict lossless 3 MS/s Recording V3 trials. It also binds the exact passing V2 pre/post
host-health evidence described below into the target digest.
The same bounded campaign must also seal one full-span 5 MS/s Recording V3 characterization: each
radio has 300,000,000 logical samples, observed plus physical zero fill closes that span, the gap
map and validity inventory agree, and overflow, enqueue failure, and terminal rejection remain
zero. Each 5 MS/s stream must also bind the exact 32-refill queue and a measured high-water no
greater than 24 refills. The accepted receipt is published only after radio restoration and
maintenance-lease release. It has no non-production USB control arm. The plan requires a clean
worktree and an exact local `origin/main` SHA, compares it with `/opt/leo-tracker/current`, and
reports affected components, service restarts, migration requirements, and worker-fence
requirements.

The initial production catalog admits at most two concurrent `heavy` leases. Worker process count
does not override this safety cap. Raising HEAVY capacity to four requires a separately reviewed,
sealed headroom result with healthy non-resyncing RAID, no new kernel I/O or OOM events, no swap
activity, and sufficient free memory and disk before and after the bounded qualification run.
`capture_qualification_host_health_snapshot_v2` is read-only and bounded; capture one snapshot
before the first writer benchmark or RF action, then capture the second only after exact radio
restoration and maintenance-lease release. Seal them with
`evaluate_qualification_host_health_v2`. V6 requires this evidence to pass under the reviewed
`md127`, `/srv/bulk`, `/dev/mapper/vg_bulk-bulk`, 32 GiB available-memory, and 1 TiB free-disk
policy. It rejects production-storage and unclassified I/O errors, and permits prior removable
device errors only when the full classified journal inventory is unchanged. The evidence is a
required V6 prerequisite and therefore part of the rate target digest. V1–V5 rate receipts remain
unchanged.

`sudo ./ops deploy --stage-only --revision FULL_SHA` is the pre-qualification half of a full
deployment. It requires a clean worktree and an explicit SHA equal to the locally fetched
`origin/main`, then creates or revalidates that immutable release, including its release-local
native libiio/Python metadata runtime. It does not require a rate receipt or test receipt and does
not change `/etc/leo/leo.env`, systemd, component selectors, services, or PostgreSQL. Run the
hardware qualification with the staged release's `.venv/bin/python`; the resulting receipt is
therefore evidence for the same native runtime that the later cutover revalidates.

`sudo ./ops deploy` requires a passing exact-revision test receipt covering the complete production
delta. Full cutovers additionally hash and reverify the supplied 3 MS/s rate receipt. It
automatically performs an API-only atomic selector/restart for web/API-only changes and a
full staged, qualified, fenced cutover for every broader change. `--full` forces the latter. Full
startup launches the API, workers, and acquisition directly; reconciliation remains durable and
asynchronous on its timer. A no-migration failure restores the prior environment, selectors,
units, and services. Migration cutovers require a production backup and fail closed rather than
attempting an unsafe schema rollback.

After any required Alembic upgrade and before worker startup, cutover reads the complete production
resource-capacity inventory and requires exactly `streaming=16,cpu=8,memory=4,heavy=2`; any row
drift, omission, duplication, or addition blocks startup. Deployment does not resume the durable
capture authority. For post-cutover 3 MS/s and 5 MS/s direct canaries, stop the acquisition service,
explicitly resume for one `leo acquire once`, immediately re-pause and drain, and only then restart
the still-paused service. Continuous acquisition requires a later, separate operator resume.

The first rollout containing component selectors must use `sudo ./ops deploy --full`. Subsequent
web/API-only deployments avoid worker fencing, acquisition interruption, database work, and full
reconciliation.

`sudo ./ops releases --plan --keep 10` is the read-only immutable-release retention front door.
It needs root only so it can inspect sealed `root:leo` metadata and every `/proc` reference. The
plan always protects all four selectors, runtime-referenced releases, the previous healthy
deployment, the ten newest published metadata records, and each explicit `--protect FULL_SHA`.
It reports exact allocated candidate bytes and a deterministic `plan_sha256`. Missing deployment
history, malformed inventory, symlinks, separate mounts, unexpected ownership, or any QNAP path
fails closed.

Applying retention is a separate audited operation. Pass the exact reviewed digest back through
`sudo ./ops releases --apply --keep 10 --expect-plan SHA256`, repeating every `--protect` argument
from planning. The command takes the same host lock as deployment, rebuilds the complete plan, and
refuses any drift before mutation. Each retired runtime's immutable metadata is retained beneath
`/opt/leo-tracker/retired-release-metadata`; sealed plan and completion receipts live with the
deployment evidence. An interrupted removal is resumable by reviewing a fresh plan. Deployment
only emits an advisory when more than ten releases exist; it never silently prunes as part of a
successful cutover.

The reviewed ownership manifest is `config/ops-components.json`. Every tracked path must match at
least one component; an unclassified new path fails closed. Test-infrastructure paths form an
exclusive bounded shard so changing the runner does not recursively select the entire suite.
