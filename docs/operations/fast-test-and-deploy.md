# Fast test and deployment front door

The repository has one operator-facing command:

```bash
./ops test
./ops test --base CURRENT_PRODUCTION_SHA
./ops deploy --plan
sudo ./ops deploy
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

`./ops deploy --plan` is read-only. It requires a clean worktree and an exact local
`origin/main` SHA, compares it with `/opt/leo-tracker/current`, and reports affected components,
service restarts, migration requirements, and worker-fence requirements.

`sudo ./ops deploy` requires a passing exact-revision test receipt covering the complete production
delta. It automatically performs an API-only atomic selector/restart for web/API-only changes and a
full staged, qualified, fenced cutover for every broader change. `--full` forces the latter. Full
startup launches the API, workers, and acquisition directly; reconciliation remains durable and
asynchronous on its timer. A no-migration failure restores the prior environment, selectors,
units, and services. Migration cutovers require a production backup and fail closed rather than
attempting an unsafe schema rollback.

The first rollout containing component selectors must use `sudo ./ops deploy --full`. Subsequent
web/API-only deployments avoid worker fencing, acquisition interruption, database work, and full
reconciliation.

The reviewed ownership manifest is `config/ops-components.json`. Every tracked path must match at
least one component; an unclassified new path fails closed. Test-infrastructure paths form an
exclusive bounded shard so changing the runner does not recursively select the entire suite.
