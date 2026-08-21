# Fast test and deployment: measured audit and proposed design

Date: 2026-08-21 UTC  
Audited revision: `baeffb940cfe2957fd6cfb5fb70192762b67ccd8` (`origin/main` at audit start)  
Scope: developer tests, immutable staging, release qualification, Alembic migration,
cutover preflight, worker fencing, systemd startup, reconciliation, and live verification.

## Implementation receipt

Implemented and deployed on 2026-08-21 at exact main revision
`9254a9b523603f8938990b57aea7b69a427bbb51`.

| Workflow | Prior observation | Implemented result |
| --- | ---: | ---: |
| Changed test/deploy implementation slice | accidental broad run exceeded 5 min | 1.89 s |
| Exact production delta after rebase | not available | 39.54 s, all gates passed |
| Small coordinator-only follow-up | not available | 0.70 s, all gates passed |
| Complete portable repository tier | 191.83 s with failures | 110.31 s, all gates passed |
| Full exact release deployment | manual multi-command coordination | 237.36 s total |
| Protected qualification within full deploy | median 168.9 s historically | 188.52 s |
| API unavailability during full cutover | 112 s observed previously | about 19 s |

The ordinary front doors are now `./ops test` and `sudo ./ops deploy`. Tests use reviewed
ownership, separate parallel CPU and bounded PostgreSQL pools, per-file slow shards, external
per-user caches, automatic locked web dependency setup, and production-database refusal. Deploys
use exact-main receipts, immutable staging, component selectors, atomic stop-and-fence, migration
detection and backup, bounded health retries, no-migration rollback, and durable receipts. API,
workers, and acquisition start independently; reconciliation is asynchronous and no longer extends
the service-start critical path.

The full scientific tier intentionally remains minutes rather than seconds: protected real-IQ and
production Chromium proofs run while the prior release stays live. Subsequent API/web-only changes
use the minimal component selector and API restart path without worker fencing, acquisition
interruption, migration, or full reconciliation.

## Executive recommendation

The system should have one operator front door with two ordinary commands:

```text
./ops test
sudo ./ops deploy
```

`./ops test` should be a safe, change-aware developer gate. It should normally finish in
10--25 seconds on a warm checkout by running independent gates concurrently. It must never
inherit or default to the production database.

`sudo ./ops deploy` should deploy the exact clean `origin/main` commit, derive an impact plan,
reuse only content-addressed qualification receipts whose complete inputs are unchanged, stop
and fence only affected services, and return only after bounded health checks pass. UI/API-only
deployments should take 10--30 seconds including immutable publication and about 3 seconds of API
downtime. A no-op should take less than 5 seconds.

The explicit exhaustive commands remain available:

```text
./ops test --release
sudo ./ops deploy --full
```

These are not shortcuts. The release form retains the protected real-IQ smoke, the full Standard
operational vertical, scientific goldens, isolated PostgreSQL migration checks, compiled browser
tests, immutable publication checks, and cutover verification. The speedup comes from putting each
gate at the correct tier, running independent work in parallel, and reusing evidence only when the
gate's content-addressed input closure is identical.

## What the system does today

The current workflow is not one deployment operation. An operator manually composes at least six:

1. stage an exact Git SHA under `/opt/leo-tracker/releases/SHA`;
2. install a complete Python environment, npm tree, Chromium, and compiled web application;
3. run the protected-corpus, four-path operational, web-build, and Chromium qualification lane;
4. repoint the global `current` symlink and run Alembic;
5. run the initial-cutover verifier and install/verify all systemd units;
6. stop acquisition/workers/API, fence old work, reconcile, start everything, and manually inspect
   a live recording.

The individual mechanisms are generally careful. The problem is composition: the initial-host
cutover runbook is being used as the routine development deploy procedure, and one global release
identity makes every change look like a scientific worker change.

### Existing safety boundaries that must remain

- deploy only a clean, full 40-character committed revision;
- immutable, root-owned release trees with sealed external metadata;
- no runtime or deploy writes beneath `/mnt/qnap01`;
- frozen scientific goldens change only through explicit review;
- qualification uses the dedicated `leo_qualification` database and temporary schemas/data roots;
- production migrations are forward-only, with exact head checks;
- old worker leases are revoked transactionally before a new incompatible worker generation starts;
- late old-generation heartbeat/publication/completion is rejected;
- capture authority remains exclusive and acquisition state survives deployment;
- rollback never deletes recordings, products, catalog rows, or evidence.

## Measurements

All measurements below were read-only except for ordinary test caches and the isolated worktree
virtual environment. No live service, production database, recording, or QNAP path was mutated.

### Developer and release gates

| Item | Observed time | Finding |
| --- | ---: | --- |
| Ruff check | 1.60 s | Fast, but audited `origin/main` failed one line-length error. |
| Ruff format check | 0.16 s | Fast, but audited `origin/main` had 10 unformatted files. |
| mypy, cold cache | 17.95 s | Largest ordinary static gate. |
| mypy, warm cache | 0.16 s | Persistent cache makes it effectively free. |
| Existing immutable release revalidation | 5.17 s | Metadata, Git, entrypoints, imports, and binary path scan are not the bottleneck. |
| Broad local pytest attempt | 238.69 s before interruption | 1,032 passed, but it was not a valid run: 139 PostgreSQL setup errors and 3 failures. |
| Recent 10 successful release qualifications | 139--239 s; median 168.9 s | This is the dominant pre-cutover duration. |
| Protected corpus + operational vertical | 112--185 s; median 127.3 s | Dominates release qualification. |
| Production web build in qualification | 2.8--6.6 s; median 3.9 s | Already small. |
| Production Chromium E2E | 23.3--46.4 s; median 31.7 s | Material but bounded. |

The qualification values come from the ten most recent passing sealed receipts under
`/srv/bulk/leo/qualification/release`. Across all 38 passing receipts present during the audit,
qualification had a 64.4-second median, but that historical number is misleading after the
operational vertical grew. The recent median is the appropriate planning number.

### Live restart and orchestration

| Item | Observed time | Finding |
| --- | ---: | --- |
| Direct API stop/start to application-ready | about 3 s | The API itself restarts quickly. |
| Recent full cutover API outage | about 114 s | API stopped at 14:59:30 and was application-ready at 15:01:24. |
| Same cutover acquisition outage | about 182 s | Acquisition did not start until 15:02:32. |
| Reconcile examples | 69--115 s wall time | Reconcile, not systemd startup, is the major live delay. |

The service graph explains the acquisition delay. `leo-reconcile.service` is a long-running
one-shot and is ordered before acquisition and workers. Starting or finding that service active
makes normal producers wait. Reconciliation is valuable recovery work, but a complete store scan
is not a suitable readiness probe.

The journal also showed every worker independently creating a temporary Matplotlib cache at
startup because workers do not receive the persistent `MPLCONFIGDIR` already configured for the
API. That is avoidable startup CPU/I/O and warning noise, although it is not the principal delay.

## Correctness gaps discovered by the audit

### The local test command can point at production

Several PostgreSQL fixtures default to:

```text
postgresql+psycopg:///leo_tracker
```

Many of those tests are not marked `postgres`, so `-m "not postgres"` does not exclude them. The
audit's broad test attempt inherited/defaulted to `leo_tracker` and attempted to create test
schemas there; host permissions prevented it. A developer front door must not rely on permissions
as its production-data safety boundary.

Required fix:

- centralize database fixture creation in one root `tests/conftest.py` helper;
- remove every production database default from tests;
- require `LEO_TEST_DATABASE_URL` for database tests;
- parse the URL and reject database `leo_tracker` unconditionally;
- accept only a name containing `qualification` or ending `_test`;
- automatically apply the `postgres` marker to every test that requests the shared fixture;
- verify pre/post schema inventory and remove only uniquely named test-owned schemas.

### Passing release qualification does not imply the repository gates pass

Revision `baeffb9` has a passing exact-SHA release receipt even though the audited checkout fails
Ruff check, Ruff format, and at least one ordinary deployment-template test. The qualification
command intentionally runs a narrow scientific/operational lane and Chromium; it assumes ordinary
CI has passed, but cutover does not consume a sealed CI/test receipt.

Required fix: staging or deployment must require a test receipt for the exact Git tree and lockfile
digests. Release qualification complements that receipt; it does not replace it.

### Initial installation checks are repeated during development

The production deployment document mixes one-time host ownership/ACL/database-role conversion and
legacy user-service shutdown with repeatable application cutover. Those checks should remain in a
separate `./ops bootstrap` operation and an independently runnable `./ops audit-host`. Routine
deploy must not recursively change ACLs, transfer database ownership, create accounts/databases,
or inspect obsolete user units.

### Application release and scientific pipeline release are conflated

`LEO_PIPELINE_RELEASE_ID` is forced to equal the exact repository SHA. That gives excellent
provenance but makes a CSS, UI, report, or API-only change appear incompatible with all processing
workers. The resulting global symlink and fence are much broader than the actual change.

Keep both identities:

- `application_release_id`: the exact immutable Git SHA that built the running component;
- `pipeline_release_id`: a content digest over the scientific graph, analyzers, contracts,
  numerical dependencies, configuration schema, and reviewed scientific fixtures.

Persist both. A UI-only commit changes the application identity without changing scientific
product identity. This preserves stronger provenance while allowing a narrow restart.

## Proposed test command

### Interface

```text
./ops test                         # changed-component developer gate
./ops test --all                   # complete portable Python + web + isolated PostgreSQL suite
./ops test --release               # --all plus protected corpus, goldens, and production Chromium
./ops test --explain               # print selection and input digests without executing
./ops test --json PATH             # also write a machine-readable receipt
```

With no option, compare the worktree to the merge base with `origin/main`; if running on main,
compare the last commit. Untracked files are included. A generated ownership manifest maps every
tracked path to one or more components and test sets. An unclassified changed path is a hard error,
never permission to run no tests.

### Always-run fast gates

Run these concurrently:

1. `ruff check` and `ruff format --check` on the changed Python files;
2. cached mypy on `src` (incremental cache kept outside disposable worktrees or keyed by Python,
   lockfile, and mypy version);
3. contract/import-boundary tests;
4. the component-owned tests selected by the change manifest;
5. Vitest and TypeScript for a web change;
6. migration-head/static SQL checks for a migration or model change.

Do not add a test-discovery service. A small reviewed TOML/JSON ownership manifest and a Python
runner using `subprocess` is enough. Parallelize coarse independent processes first; consider
`pytest-xdist` only after measuring the remaining serial shard.

### Receipts and caching

Write `.leo/test-receipts/GIT_TREE_DIGEST.json` with:

- Git tree and dirty-overlay digest;
- Python, Node, lockfile, test-runner, and manifest digests;
- selected component closures and exact commands;
- per-gate duration, exit code, and output digest;
- sanitized database identity and pre/post schema inventory.

A cache hit is allowed only when the gate command and every declared input digest match. Never
cache a failure. The release form writes a sealed receipt outside the mutable checkout.

### Target times

| Change | Warm target |
| --- | ---: |
| Documentation only | 1--3 s |
| Small Python component | 5--15 s |
| API/presentation | 10--20 s |
| Web UI | 10--25 s |
| Migration/catalog | 20--45 s |
| `--all` portable | under 90 s with coarse parallel shards |
| `--release` | 2.5--4 min with current science runtime |

The release target is intentionally not promised as a 10-second operation. It is expensive
scientific evidence. The ordinary development loop should not rerun it when its input closure is
unchanged.

## Proposed deployment command

### Interface

```text
sudo ./ops deploy                  # exact clean origin/main; automatic minimal impact
sudo ./ops deploy --plan           # read-only plan, receipts, services, migration, rollback
sudo ./ops deploy --full           # force full component cutover and live canary
sudo ./ops deploy --revision SHA   # explicit full SHA; still must be reachable from origin/main
```

Do not infer a revision from an arbitrary root working directory. Before privilege escalation,
resolve and record the source repository, exact `origin/main` SHA, clean status, and remote
ancestry. After escalation, revalidate those values and pass only explicit absolute paths and the
full SHA to lower-level helpers.

### Deployment state machine

The command should hold one host deployment `flock` and emit one durable deployment receipt.

1. **Resolve:** validate exact committed revision and classify impact.
2. **Evidence:** require the exact ordinary test receipt; compose/reuse release-gate receipts by
   content closure. A scientific input change requires a new scientific receipt. A web/API
   contract change requires a new Chromium receipt.
3. **Stage:** clone the exact SHA and publish an immutable release. Reuse the uv download cache,
   shared Playwright browser cache, and a root-owned content-addressed npm package cache. Continue
   to create a release-local noneditable venv and compiled web output.
4. **Preflight:** validate metadata, receipts, current/target Alembic heads, disk capacity, service
   impact, capture desired state, and rollback eligibility before stopping anything.
5. **Quiesce:** stop only affected services. If workers are incompatible, kill their cgroups and
   run the existing transactional stop-and-fence operation. Preserve successful work.
6. **Migrate:** run Alembic only when target head differs. Migration changes force full mode and a
   pre-migration production backup/verification. No migration means no routine backup delay.
7. **Select:** atomically select component release paths.
8. **Start:** start affected services concurrently. Do not run full reconciliation as a dependency.
9. **Verify:** bounded API status, exact component identities, schema head, worker heartbeat/claim,
   acquisition desired/observed state, queue invariant, and scanner/report endpoints.
10. **Seal:** write the timings, decisions, fence receipt, migration state, health observations,
    and final component identities. On failure, execute the precomputed rollback only when schema
    compatibility permits; otherwise stop producers and report fix-forward.

### Component selectors

After one full migration, replace the single operational selector with:

```text
/opt/leo-tracker/current-api
/opt/leo-tracker/current-worker
/opt/leo-tracker/current-acquisition
```

Each remains an exact relative link to one immutable full-SHA release. Systemd units use their
component selector explicitly. This permits an API/web deployment without disturbing capture or
workers. It is simpler than introducing containers, a reverse proxy, or an orchestrator.

Impact rules are fail closed:

| Changed closure | Restart/cutover |
| --- | --- |
| `web/**`, static presentation only | API only |
| API/application presentation code or API contracts | API only, plus browser contract gate |
| analyzer/DSP/pipeline graph/scientific contracts | workers + API; stop and fence old workers |
| acquisition/scanner/radio authority | acquisition only, after current radio operation commits |
| catalog models or migrations | full cutover + migration + backup |
| systemd, environment schema, dependencies, deploy code | full cutover |
| unknown/unclassified | full cutover |

### Reconciliation and readiness

Create a fast `leo startup-check` that checks only:

- database connectivity and exact compatible Alembic head;
- canonical local roots and write/read authority for the component;
- current immutable release metadata;
- station/capture authority document identity where relevant;
- no QNAP runtime path;
- acquisition single-owner invariant.

Target: under 2 seconds. API, workers, and acquisition may start after this check. Run full
`process reconcile` asynchronously and keep its timer; remove its `Before=` relationship to normal
producers. Add concurrency tests proving reconciliation is idempotent while new captures register
and workers claim jobs. If that proof cannot be made, split reconciliation into a sub-second
recovery-journal pass (startup gate) and a full historical scan (asynchronous).

Set a persistent `MPLCONFIGDIR` for workers immediately. Longer term, keep Matplotlib and plotting
imports out of API/worker startup paths unless that component actually renders a plot.

### Target times

| Deployment | End-to-end target | Service interruption target |
| --- | ---: | ---: |
| No-op exact release | <5 s | 0 s |
| API/web only, dependencies cached | 10--30 s | 2--5 s API only |
| Worker/science, already qualified | 20--45 s | 5--15 s workers; acquisition stays up |
| Acquisition-only | 10--30 s after current radio op | no interrupted radio op |
| Schema/systemd/full | 1--3 min excluding new qualification | <30 s after preflight |
| New release qualification | 2.5--4 min, before downtime | 0 s |

## Redundant or misplaced work

| Current work | Decision |
| --- | --- |
| Full scientific qualification for every Git SHA | Key it to scientific input closure; retain the exact receipt binding in the composed release receipt. |
| Web build during staging and again in qualification | Build once in immutable staging; E2E the exact built bytes and seal their digest. |
| `npm ci` for unchanged lockfile in every release | Materialize from a content-addressed cache, while retaining release-local read-only runtime assets. |
| Chromium install for every stage | Validate/reuse the already shared browser digest. |
| Repeated metadata/runtime validation | Keep cheap boundary checks; 5.17 s is acceptable. Consolidate their output in one deploy receipt. |
| Full reconciliation before service start | Replace with fast startup check; reconcile asynchronously. |
| Stop API/acquisition for worker-only change | Stop only impacted components. |
| Stop/fence workers for UI-only change | Separate component selectors and pipeline identity; do not fence. |
| Run Alembic on unchanged head | Compare heads first and record no-op. |
| Initial account/ACL/ownership conversion in every deploy | Move to `ops bootstrap`/`ops audit-host`. |
| Two live 60-second canaries for ordinary UI changes | Keep for full release/acquisition changes; API-only deploy uses generated fixture/API/browser smoke. |

## Acceptance tests for the implementation

### Test front door

1. A production `LEO_DATABASE_URL` or `LEO_TEST_DATABASE_URL` is removed and cannot reach any child.
2. An explicit test URL naming `leo_tracker` is refused before connection.
3. Missing qualification DB is a clear failure for a selected PostgreSQL test, never a skip.
4. Every shared PostgreSQL fixture automatically marks its consumer `postgres`.
5. Pre/post database schema inventory is exactly `public`; only recognized unique test schemas may
   be cleaned after failure.
6. Every tracked repository path is classified; adding an unclassified file fails the manifest test.
7. Analyzer changes select scientific contract/unit/golden tests; web changes select TypeScript,
   Vitest, API fixture, and Chromium contracts; migration changes select migration/catalog tests.
8. Independent gates execute concurrently and the receipt contains accurate monotonic durations.
9. Warm cache hits require identical command, tool, lockfile, fixture, and source closure digests.
10. A failed/incomplete receipt is never reusable.

### Deployment front door

1. `--plan` makes no filesystem, DB, or service changes.
2. Dirty, abbreviated, unpushed, non-main, or changed-after-validation revisions are refused.
3. A UI-only plan cannot stop/fence workers or acquisition and cannot run Alembic.
4. A scientific change cannot reuse a receipt after any analyzer, graph, numerical dependency,
   contract, configuration, test, fixture, or golden input changes.
5. A migration or unit change always selects full mode.
6. Stop-and-fence is run once and only for an incompatible old worker generation; its receipt is
   bound into the deployment receipt.
7. Late old-worker publication remains rejected after the new workers start.
8. Exactly one acquisition operation can be leased across every deployment boundary.
9. Paused capture stays paused; running capture resumes only if it was running before deployment.
10. API health reports the exact API release; worker heartbeat reports the exact application and
    pipeline identities; database head matches target.
11. Full reconcile can overlap a new capture registration without loss, duplication, or deadlock.
12. A startup failure rolls component selectors back when schema-compatible and leaves producers
    stopped with an explicit fix-forward receipt otherwise.
13. No code path writes, renames, moves, or deletes beneath `/mnt/qnap01`.
14. Timing tests on the production host enforce the no-op, API restart, startup-check, and common
    deployment budgets without making scientific runtime a flaky unit-test threshold.

## Migration plan

### Phase 1: safe test front door (highest priority)

- centralize and harden PostgreSQL test fixtures;
- classify all tests and paths;
- implement `./ops test`, JSON receipts, parallel coarse gates, and warm caches;
- make CI invoke the same command rather than duplicating its inventory;
- require its exact clean-tree receipt before staging/deploying.

This phase should also fix the existing Ruff/format/template failures. Do not bless or reformat
scientific goldens as part of the infrastructure work.

### Phase 2: one full deployment coordinator

- implement `./ops deploy --plan` and `--full` around the existing stage, qualification,
  metadata, Alembic, fence, and systemd helpers;
- add a durable deployment receipt and one host lock;
- move one-time bootstrap steps out of routine deployment;
- run all expensive qualification before service downtime;
- replace full reconcile startup ordering with the tested fast startup check;
- add persistent worker Matplotlib cache configuration.

At the end of this phase, the operator has one safe command even before component-specific cutover
is enabled. Full deploy downtime should fall below 30 seconds in the no-migration case.

### Phase 3: component identities and minimal restart

- persist separate application and scientific pipeline identities;
- introduce the three component selectors and update systemd templates;
- implement fail-closed impact classification;
- allow API-only, worker-only, and acquisition-only cutovers;
- compose content-addressed gate receipts into one exact-SHA release receipt.

Roll this out through one normal full cutover. Keep the previous global selector during the first
rollback window, then remove it after component rollback and mixed-generation tests pass.

### Phase 4: optimize only measured residuals

- if immutable staging remains material, cache npm/uv materialization by lock digest;
- if portable pytest remains above 90 seconds, split high-cost scientific tests from portable
  component tests and evaluate limited `pytest-xdist` concurrency;
- if API downtime above 5 seconds matters after minimal restart, measure socket activation before
  considering a reverse proxy. Do not add containers or an orchestrator for a single host.

## Recommended decision

Refactor the workflow, not the scientific pipeline or storage architecture. PostgreSQL, local
immutable artifacts, systemd, Alembic, and the existing transactional fence are sufficient. The
right simplification is a small tested coordinator, safe test-database boundary, content-addressed
evidence, component-specific release selectors, and asynchronous reconciliation.

The first implementation slice should be Phase 1 plus the Phase 2 coordinator in read-only
`--plan` mode. It gives immediate feedback and exposes every deploy decision before any live
behavior changes. Then land the fast startup check and component selectors behind full end-to-end
tests before enabling minimal production cutovers.
