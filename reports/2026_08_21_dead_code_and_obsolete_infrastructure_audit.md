# Dead code and obsolete-infrastructure audit

Date: 2026-08-21 UTC  
Audited revision: `f4f7b05e875f1589d321270c9366f1582371d041`  
Scope: the tracked `leo-tracker-reduxredux` repository at that revision. No live
service, PostgreSQL database, radio, recording store, or QNAP path was inspected
or changed.

## Executive summary

The repository does **not** have many convincingly dead files. Most apparent
orphans are externally invoked CLI modules, FastAPI/Typer callbacks, systemd
entry points, immutable contract decoders, test fixtures, or reproducibility
tools. Deleting files from a simple import-count report would break real
surfaces.

There are, however, three meaningful cleanup opportunities:

1. **High-confidence unreachable implementation:** a private pre-EM branch
   association call tree, one unused report helper, one unused browser shim,
   and ten superseded Standard stage classes have no route from production
   composition. The ten stage classes alone occupy 501 class-body lines.
2. **Superseded but contract-sensitive producers:** V1/V2/V3 de-alias/replay
   algorithms and V1 reducers are exercised only by tests while production runs
   the seeded-EM/V4/V3 path. Their old *decoders and contracts* remain necessary
   for persisted artifacts; their old *producer implementations* can be retired
   only after an explicit read-compatibility decision.
3. **Repository organization, not dead runtime code:** one-off scientific tools
   and completed plans are mixed with ordinary runtime sources. They should be
   indexed and moved to a clearly labelled `tools/research/` or documentation
   archive, not casually deleted. Several are the only way to reproduce figures
   in committed reports.

The best first cleanup is small and safe: remove the private unreachable call
tree, `_power_points`, `web/playwright.ts`, and two unused browser request
helpers, with focused tests and a production-registry assertion. Then remove
the superseded per-stage Standard analyzer classes in a separate change. Do not
start by deleting contracts, migrations, systemd units, or report tools.

## Audit method and limitations

The audit combined static evidence rather than treating any one tool as proof:

```text
git ls-files; find src tests tools web/src deploy
rg for every candidate identifier, route, script, unit, and entry point
uvx vulture src tools --min-confidence 60
uvx vulture src tools --min-confidence 90
uv run ruff check src tools tests
uv run mypy src
cd web && npm ci && npm run build
cd web && npx --yes knip --no-progress
AST import graph: source-module importers versus tests/tools
AST definition/load inventory: top-level definitions with no source load
git blame and git log -S for supersession chronology
```

Results relevant to interpretation:

- 693 tracked files, 212 Python source modules, about 84,822 Python source
  lines, 49,673 Python test lines, 12,092 tool lines, and 6,355 TypeScript/TSX
  source lines were in scope.
- Ruff and mypy passed. Vulture reported no findings at 90% confidence. Its 60%
  results were dominated by Pydantic fields/validators and decorated callbacks,
  demonstrating why its raw output is not deletion evidence.
- The web application built successfully. Knip found one unused file, four
  unused exports, and exported contract types. Exported contract types were not
  classified as dead merely because this browser does not import them.
- Static analysis cannot prove absence of imports by downstream Python users or
  shell invocations outside this repository. “No internal reference” is stated
  explicitly where that is the strongest available claim.

## Production reachability baseline

The ordinary processing composition in
`src/leo/cli/processing.py:872-889` constructs
`production_standard_v2_registry()` and `production_research_v1_registry()`.
The Standard registry in `src/leo/analysis/standard/analyzers.py:1056-1070`
contains exactly these five classes:

```text
PathStandardAnalyzer
PathAlternateTracksAnalyzer
RadioScientificReportAnalyzer
PairedScientificReportAnalyzer
PairedPresentationAnalyzer
```

The active receiver runner imports the seeded/V4 path at
`src/leo/analysis/standard/runner.py:27-36`:

```text
fit_seed_preserving_dealiased_trajectories
replay_observed_cfo_lifts_v4
select_final_trajectories_v3
build_final_trajectory_table_v3
default_replay_gate_v4
```

These two closed inventories are the key evidence for distinguishing current
Standard code from predecessor implementations.

## High-confidence cleanup candidates

Confidence below means confidence that there is no in-repository runtime path,
not automatic permission to remove a public API.

| Candidate | Evidence | Confidence | Removal risk | Recommendation |
| --- | --- | --- | --- | --- |
| `_associate_component`, `_minimum_cost_assignment`, `_choice_key`, `_association_cost` in `src/leo/analysis/starlink/cfo_dealias.py:2398-2498` | `rg` finds the root `_associate_component` only at its definition. The other three private functions form a call tree reachable only from that root. Current fitting consumes seeded-EM association output at lines 417-424. | High | Low; private implementation, but numerical tests should prove no output changes. | Remove together in one patch; run all CFO de-alias, seeded-EM, Standard science, and real-corpus gates. |
| `_power_points` in `src/leo/analysis/standard/reports.py:1226-1229` | Only occurrence in the repository is its definition. | High | Very low. | Remove with the Standard report tests. |
| `web/playwright.ts` | Knip reports the file unused. `playwright.config.ts` imports `@playwright/test` directly, and no test imports this shim. It is only listed in `tsconfig.node.json`. | High | Low. | Delete the shim and remove it from `tsconfig.node.json`; run TypeScript build and both Playwright projects. |
| `getLatestScannerReport` in `web/src/api.ts:111-116` | Knip and `rg` find no caller; the Scanner UI uses paged `getScannerReports`. | High for browser code | Low for helper; **do not infer that `/api/v1/scanner/latest` is dead** because it is documented and API-tested. | Remove only the browser helper and let the API route remain until an API-contract decision. |
| `getStandardView` in `web/src/standard-api.ts:94-110` | Knip and `rg` find no caller; the browser uses persisted PNG URLs. JSON view routes are directly covered by API/application tests. | High for browser code | Low for helper; medium if anyone mistakes it as authority to remove JSON routes. | Remove only the TypeScript helper after confirming no downstream web package imports it. |

### Superseded Standard analyzer classes

The following classes are absent from `STANDARD_V2_ANALYZERS`, and no production
source loads their class names:

| Class | Lines | Other internal use |
| --- | ---: | --- |
| `PathInputBindAnalyzer` | 159-170 | none |
| `PathQualityAnalyzer` | 173-210 | none |
| `PathPowerAnalyzer` | 213-256 | none |
| `PathWaterfallAnalyzer` | 259-300 | none |
| `PathProbeScheduleAnalyzer` | 303-345 | none |
| `PathPilotScanAnalyzer` | 348-410 | direct unit tests only |
| `PathTrajectoryBankAnalyzer` | 413-465 | direct unit tests only |
| `PathTrajectoryFeedbackAnalyzer` | 468-558 | direct unit tests only |
| `PathScientificReportAnalyzer` | 561-635 | none |
| `PathPresentationAnalyzer` | 735-774 | none |

They were introduced in commit `5b0b31c` as the expanded Standard DAG. Commit
`15d9c51` later introduced the fused `PathStandardAnalyzer`, which is now the
only ordinary path-science class registered in production. This is strong
supersession evidence, not merely a missing textual reference.

The class bodies total 501 lines. Helpers and imported scientific functions in
the same file must not be removed en bloc: some are shared by the live fused
analyzer, radio/paired reducers, and presentation code. The cleanup should:

1. add a test asserting the exact five-class production registry inventory;
2. delete the ten class definitions;
3. remove only imports/helpers that become unused under Ruff;
4. replace direct tests of the old three classes with receiver-runner or fused
   analyzer tests if they cover behavior not already present there;
5. run the Standard PostgreSQL vertical and protected corpus before merging.

Confidence is **high** that the classes are unreachable in repository-owned
production composition, but removal risk is **medium** because their product
contracts remain live and tests may encode useful scientific invariants.

## Superseded compatibility code: evaluate, do not bulk-delete

### Older CFO replay and final-selection producers

Production uses V4 replay and V3 final selection/table generation. The following
producer functions have no source caller and are test-only or entirely
unreferenced:

| Producer | Internal evidence | Disposition |
| --- | --- | --- |
| `default_replay_gate_v2` | no reference anywhere besides its definition; its docstring incorrectly says it is used by Standard and Research | Remove or move to a historical test fixture first. High-confidence stale producer. |
| `default_replay_gate_v3` | called only by de-alias tests | Inline an explicit historical fixture into those tests, then remove if V3 production replay is intentionally unsupported. |
| `fit_dealiased_trajectories` | V1 path, tests only | Retire producer after keeping V1 decoder/contract coverage. |
| `select_final_trajectories`, `build_final_trajectory_table` | V1 path, tests only | Same. |
| `select_final_trajectories_v2`, `build_final_trajectory_table_v2` | tests only | Same. |
| `replay_observed_cfo_lifts`, `_v2`, `_v3` | tests only | Same; preserve historical document decoding. |

Old contracts are not dead. `src/leo/analysis/standard/codecs.py:91-99` still
decodes V1/V2/V3 replay and V1/V2 final trajectory artifacts, and final-report
contracts embed `FinalTrajectoryV1`. Repository policy also says published
persisted contracts are immutable within a major version. A safe split is:

- keep contract models, schema identifiers, decoders, and read/presentation
  projectors for artifacts already on disk;
- stop exporting old producer functions from convenience modules;
- convert old producer tests to frozen JSON/contract-decoding fixtures;
- remove the old producers only after an inventory proves no queued/current run
  is configured to execute them.

### V1 Standard reducers

`src/leo/analysis/standard/reducers.py` (`reduce_radio` and
`reduce_paired_radios`) is loaded only by tests and re-exported as a Python API.
Production analyzers use V2 reducers from
`src/leo/analysis/standard/final_reports.py`. This is a medium-confidence
superseded implementation. Keep it until the public-export and historical-test
decision is explicit; then retain V1 document decoding but remove V1 production.

### Original long-dwell graph/adapters

`production_long_dwell_registry`, `production_long_dwell_configuration`, and
`long_dwell_graph` are called only by tests. They are not the ordinary worker
registry. This does **not** make `src/leo/analysis/graphs.py` or
`src/leo/analysis/adapters.py` wholly dead:

- `soak_acceptance.py` consumes the old graph's exact Standard stage-key list;
- presentation and qualification code consume `ComputeTier`;
- adapter types and numerical helpers are used elsewhere;
- tests use the original registry as an integration harness.

Recommendation: rename this area to `legacy_long_dwell` or isolate it beneath
qualification/test-support first. If no new soak receipt relies on its stage
inventory, replace the qualification dependency with a frozen receipt schema
and then remove the legacy graph. This could eliminate a large parallel
architecture, but it needs a contract migration rather than a dead-code patch.

## Medium-confidence unused ports and helpers

These have no in-repository call site but could be intentionally exposed ports.

| Candidate | Evidence | Risk / recommendation |
| --- | --- | --- |
| `CatalogRepository.heartbeat_acquisition_operation` at `repository.py:395` | only definition; supervisor leases and completes/fails operations but never heartbeats them | This may indicate a missing lease-renewal behavior rather than dead code. Decide operational semantics first. If acquisition can exceed its lease, wire it in; otherwise remove it and document why the lease is safely longer than every bounded operation. |
| `CatalogRepository.presentation_snapshots` at `repository.py:3578` | only definition; UI uses paged recording queries and individual snapshots | Likely predecessor bulk-read API. Remove after one downstream-import check or mark explicitly as a supported library API. |
| `default_replay_gate_v2` public export status | only definition, but public functions can be imported downstream | Remove from public API in a deliberate breaking release or first deprecate. |
| `tools/render_scanner_report_samples.py` | no code, test, documentation, report, or entry-point reference | It is a valid directly executable operator tool and therefore cannot be proven dead by imports. Either document it with a reproducible output location and add a smoke test, or archive/delete it as an unowned experiment. |

Repository methods such as `create_capture_session`, `job_state`,
`attempt_states`, derivation builders, corpus preflight helpers, fixture builders,
and acceptance helpers were **not** placed in this table merely because only
tests call them. Many are intentional test/contract construction APIs, and some
are re-exported public Python surfaces.

## Research tools and completed documents

Most files under `tools/` are not runtime dependencies. That is expected for
command-line research utilities. At least 20 are named in a committed report or
have a component-owned test. In particular, CFO alias, line-finder, pilot-method,
waterfall, and track-loss tools are reproducibility assets, not dead code.

The current layout still obscures ownership. Recommended organization:

```text
tools/ops.py                         # supported operator front door
tools/workers/                       # subprocess entry points used by qualification
tools/research/<topic>/              # report reproduction, explicit owner/report
tools/archive/<date-or-report>/      # frozen, unsupported experiments
```

Add `tools/research/README.md` with, for every tool, its report, input contract,
expected corpus, output files, and smoke-test status. A tool lacking all five
after one review cycle is a deletion candidate. Do not move tools until report
links and tests are updated atomically.

Root planning documents also mix current and historical truth. `plan.md` still
says the UI has no acquisition/reprocessing controls and is read-only, while the
current UI intentionally has operator actions. `standard_pipeline_plan.md` is
labelled proposed even though much of it is implemented. These are stale
documentation states, not dead code. Add `Status`, `Superseded-by`, and
`Implemented-at` headers and move completed plans to `docs/archive/plans/`.

## Deployment and test infrastructure review

No deploy script or systemd unit was proven dead.

- Every `deploy/scripts/*` helper is called by `tools/ops.py`, another deploy
  helper, systemd, or deployment tests.
- `setup.py` is required to build
  `leo.analysis.starlink._native_acquisition`; it is not redundant packaging
  boilerplate.
- `leo.operations.tle_collector` has no Python importer because
  `leo-tle-collection.service` invokes it with `python -m`.
- `leo-acquisition-soak.service`, qualification services/timers, retention,
  reconciliation, TLE collection, API, acquisition, and worker units are all
  documented or selected/tested. Gated/rare is not dead.
- Alembic migrations are historical database state and must never be pruned as
  ordinary unused Python modules.
- `./ops test` and `./ops deploy` are the current front doors. The lower-level
  deploy scripts remain narrow mechanisms behind them, not competing operator
  workflows.

There is still simplification value: describe lower-level deploy scripts as
private implementation in their README, ensure docs present only `./ops test`
and `sudo ./ops deploy` as routine commands, and reserve direct script examples
for bootstrap/recovery sections. This reduces conceptual surface without
deleting working safety checks.

## False positives that must be protected

| Apparent orphan | Actual reachability |
| --- | --- |
| FastAPI route functions in `src/leo/api/app.py` | Registered by decorators; static callers are not expected. JSON routes may also serve external scripts even when the browser uses PNGs. |
| Typer callbacks in `src/leo/cli/app.py`, `cli/sky.py`, and `cli/standard_pipeline.py` | Registered command callbacks. |
| `src/leo/cli/__main__.py` | External `python -m leo.cli` entry point. |
| `src/leo/operations/tle_collector.py` | systemd `ExecStart` module entry point. |
| `src/leo/presentation/standard_fixtures.py` | test-only fixture factory by design. |
| `src/leo/analysis/research/cfo_lines.py` and `starlink/cfo_aliases.py` | imported by research/report tools and scientific tests. |
| generated/exported TypeScript contract types | public contract vocabulary; unused in this bundle is not proof they can be removed. |
| Pydantic fields and validators | discovered dynamically by Pydantic; Vulture's 60% list is mostly false positive. |
| migrations and old schema decoders | necessary for durable historical data even when no new producer emits that version. |

## Ordered cleanup plan

### Phase 1: zero-semantic-change pruning

1. Add a production-reachability test asserting the exact Standard analyzer
   classes and active runner functions.
2. Remove `_associate_component` and its private-only call tree.
3. Remove `_power_points`.
4. Remove `web/playwright.ts` and its TypeScript include.
5. Remove only the two unused browser helpers, not their API endpoints.
6. Run Ruff, mypy, all CFO/Standard tests, TypeScript/Vitest, production
   Playwright, PostgreSQL operational vertical, and protected real-corpus lane.

Expected reduction: roughly 110 Python lines plus a small amount of browser
surface. Risk: low.

### Phase 2: fused-Standard cleanup

1. Map every test of the ten predecessor classes to equivalent
   `run_receiver_standard` or `PathStandardAnalyzer` coverage.
2. Delete the ten predecessor classes and newly unused glue.
3. Confirm the graph and pipeline-release digests intentionally remain stable,
   or perform an explicit reviewed release update if implementation digests are
   source-derived.
4. Replay the protected Standard corpus and compare all scientific and PNG
   digests expected to remain stable.

Expected reduction: at least 501 class-body lines and simpler registry
reasoning. Risk: medium because science tests must be preserved.

### Phase 3: historical producer retirement

1. Inventory persisted/current product schema versions in the catalog and disk
   manifests using read-only queries.
2. Freeze representative V1/V2/V3 artifacts as decoder fixtures.
3. Remove old producer APIs and tests that recompute obsolete outputs; retain
   decoders/contracts/projectors.
4. Apply the same decision to V1 Standard reducers and the original long-dwell
   registry.

Risk: medium/high. This is a compatibility and evidence-policy change, not
ordinary dead-code removal.

### Phase 4: archive and ownership

1. Reorganize research/report tools with manifests and owners.
2. Archive completed plans and mark supersession explicitly.
3. Document rare qualification/systemd units as gated workflows.
4. Add automated checks: Knip for browser files/exports, an allowlisted Vulture
   report for Python, and a test that every deploy unit/script has an entry-point
   owner.

## Proposed acceptance tests for cleanup work

| Cleanup | Required proof |
| --- | --- |
| Private function removal | Ruff/mypy; `test_cfo_dealias_pipeline.py`; `test_seeded_alias_em.py`; no output digest changes on protected corpus |
| Old stage-class removal | exact registry inventory; fused analyzer unit tests; PostgreSQL operational vertical; protected Standard real-corpus E2E |
| Browser helper/shim removal | `npm run build`, Vitest, `test:e2e:production`; scanner history and PNG gallery still load |
| Old producer retirement | frozen old-version decoder fixtures; current V4/V3 artifacts unchanged; read-only catalog inventory attached to review |
| Tool archival | each affected report still links to an executable reproduction command or explicitly states that code is frozen/unavailable |
| Deploy-doc simplification | `tests/deploy`; `./ops test --explain`; no service, selector, staging, rollback, or fencing path loses an owner |

## Bottom line

There is enough confirmed dead/superseded code to justify a cleanup, but not a
repo-wide deletion campaign. Start with the private unreachable functions and
browser shims, then remove the predecessor Standard analyzer classes. Treat old
scientific producer versions, contracts, migrations, CLI/API callbacks,
systemd units, and report tools as separate compatibility or archival decisions.
That sequence reduces complexity without sacrificing replayability, persisted
evidence, or operational entry points.
