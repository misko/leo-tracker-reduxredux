# Fast test and deployment front door

The repository has one operator-facing command:

```bash
./ops test
./ops deploy --plan
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
```

`./ops deploy --plan` is deliberately read-only. It requires a clean worktree and an exact local
`origin/main` SHA, compares it with `/opt/leo-tracker/current`, and reports affected components,
service restarts, migration requirements, and worker-fence requirements. The mutating coordinator
will be enabled only after its state-machine tests, receipt validation, rollback, and service
selectors are complete.

The reviewed ownership manifest is `config/ops-components.json`. Every tracked path must match at
least one component; an unclassified new path fails closed. Test-infrastructure paths form an
exclusive bounded shard so changing the runner does not recursively select the entire suite.
