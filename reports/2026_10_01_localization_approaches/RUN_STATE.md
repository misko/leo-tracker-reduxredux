# Execution state

## Completed benchmark and reporting

The official run is complete: 128 primary attempts and 31 permitted continuations.
A1 accepts 55/64 (eight acquisition errors, one unresolved); B1 accepts 53/64
(eight acquisition errors, three unresolved). No fit or diagnostic processes
remain from this benchmark. No further fitting, retries, or polishing are planned.

The final results and interpretations are in [README.md](README.md), with all
figures and per-scan outputs under `results/`. The complete official audit passes
159/159 attempts, the source audit passes 58 checks, and the combined component
and research suite passes 100 tests. Posthoc association diagnostics are complete
and excluded from benchmark timing. Frozen sources and addenda remain unchanged.

The execution notes below are historical checkpoints, superseded by this completion
record. `METHODS.md` retains its frozen admission-time status intentionally.

Implementation started after user approval of the SOL comparison plan.
Three SOL lanes own A1, B1, C1 pure numerical modules and tests. Coordinator
owns the frozen-evidence adapter, harness, scheduling, and integration. A fresh
independent verifier will audit admitted methods and evaluation.

No new RF, raw-IQ extraction, or orbit propagation. Same 64-source selection,
uniform Sacramento 250 km prior, 30.48 m MSL height, ν=4 fixed-scale likelihood.
Initial phase: synthetic gates and then source-bound three-scan development.
At most two real fits concurrently, single numerical thread, bounded batches.
The historical experiment is immutable. New results live in this directory.

## Current handoff

Implemented A1/B1/C1 modules in src/leo/analysis/localization_*.py and owned
tests. A1 selected-score port restores original score consistency guard and
eligibility checks. Report adapter uses one-satellite prediction for hard fits,
global time support, and full catalogue normalization. Batch physics supplies
compact six-column full-candidate Jacobians for B1. B1 retains all gradients;
no truncated branch cap is admitted. C1 profiles the original MAP quadratic
and uses conditional IRLS drift proposals, not marginalized Student-t evidence.

Completed development:

- pilot-v1/A1: three cached-seed fits, all converge, 6–10 seconds. Original
  endpoints agree within 0.2 mm; same iteration/status per corresponding seed.
- pilot-v1/C1: three cached-seed fits, all converge, 19–31 seconds, effectively
  same answers as A1. No benefit for full-panel admission so far.
- pilot-v1/B1: DS9-F001 unresolved after four iterations / 85 seconds.
- pilot-v2/B1: exact sparse-scatter assembly improved this to 18 iterations /
  85 seconds, still unresolved. Both failed prototypes remain immutable.
- pilot-fresh-v1/oracle and A1: three fresh-acquisition scans each, all winners
  converge. Seeds exactly equal. A1 43–49 seconds; oracle 66–86 seconds. Shared
  acquisition ~37–39 seconds; A1 fit ~5–9 seconds versus oracle ~28–46 seconds.
  Per-fit numerical thread count is one; global concurrency at most two.

Subsequent completed development:

- pilot-v3/B1 compact full gradients: DS9 and DS11 converge in primary;
  DS10 converges in its one continuation (pilot-v3-continuation/B1).
  Errors: 604.29, 1592.92, 1623.23 m; mixed accuracy versus A1, not a clear win.
- stress-fresh-v1/A1: DS9-F080 converges, DS10-F131 converges after its
  continuation, DS11-F087 hit the **40-second acquisition sub-limit** before fit.
  This failure remains preserved.
- Before official freeze, shared acquisition sub-budget explicitly revised to
  **50 seconds**, with unchanged grid/seeds/science and unchanged90/180 overall
  limits; PROTOCOL.md documents the new experiment. CLI --acquisition-budget
  defaults to50. Current source/config differs from old40 parents, so do not
  resume old receipts under new code. Completed old continuations are preserved.
- stress-budget50/A1/DS11-F087 acquired successfully (~44.6 s), then got one
  continuation in stress-budget50-continuation/A1. Check final convergence;
  historical equivalent remained unresolved after48iterations.
- B1 final bug fix: all-background empty candidate vector bypasses bulk
  linearization, returns all_background; tested. No truncation introduced.
- 77 numerical/oracle/adapter/audit/evaluator/independent-gradient tests passed
  before the non-scientific acquisition-CLI extension. Recheck final suite.

Historical active-session notes (all finished):

- exec session6197: pilot-budget50/oracle, F001 eachdataset, workers1, fresh.
  DS9 andDS10 finished (~85.7s); DS11 still running. Matched control under new
  common50 scheduling must be retained separately from older40 controls.
- exec session79660: stress-budget50/B1, DS9-F080,DS10-F131,DS11-F087,
  workers1, fresh, full compact gradients. Await then status-only continuations.

Next free slot: run pilot-budget50/A1 F001three if needed for exactly matched
50s control timing (old40 A1 andoracle seeds already exactly match; avoid claiming
identical protocol across the40→50 change). Then freeze admittedA1 and possiblyB1
sources/config after stressgate. No official64 runs yet. No full-panel C1 orD1.

Independent SOL verifier created audit_receipts.py, test_harness.py,
evaluate_approaches.py and tests. Evaluator API:

    evaluate_approaches.py --run-root FOLDER [--continuation-root FOLDER]
        --output-prefix PREFIX [--plot]

It audits before reading pinned evaluator reference, emits 64 rows per arm
with not_run, JSON/CSV/figures. pilot-v1-results and pilot-fresh-v1-results are
published diagnostics. Source snapshots preserve earlier code despite later
development fixes. Working-source-changed warnings are expected when snapshots
validate. Supervisor preserves partial worker artifacts and seals failures;
both native and launch receipts are sealed. Source bindings include batch.py,
pyproject.toml, uv.lock and loaded numerical modules.

## Official execution, 2026-10-01 03:28 UTC

Final 77-test suite passed. Matched 50-second acquisition smoke controls all
converged: A1 median54.54s versus original solver85.65s. B1 stress scans converged
2/3 after their allowed stages; DS11-F087 remains unresolved. A1 DS11-F087 remains
unresolved after48iterations despite other converged seeds. These outcomes are
preserved, not repaired by an extra stage or reference-driven mode selection.

FREEZE.json admits A1 and B1, stops C1 (same answers, slower), and defers D1.
First official A1 batch-01 launched with workers2, fresh acquisition50s, selected
prediction. All official outputs will live beneath benchmark-v1/primary and
benchmark-v1/continuation. Source code and PROTOCOL are frozen during this panel.
Independent verifier is adding a separate official-only audit of exact freeze
config/source matches; the generic development evaluator alone is not sufficient
to establish official freeze compliance. This adds no fit-side changes.

Remaining: finish eight explicitly reviewed <=8-scan blocks for both arms,
rotate arm order, run at most one continuation only for unresolved primary
winners, then audit/evaluate/plot primary and cumulative outcomes on all64.

Execution ownership: SOL agent /root/sol_benchmark_plan exclusively owns all
remaining official fits. Root must not launch competing fits. Block01 finished:
A1 8/8 converged; B1 6/8 primary, DS10-F001 converged in continuation,
DS11-F005 preserved acquisition TimeoutError. Block02 B1 is running, then A1.
The worker will finish blocks02–08 with explicit per-arm reviews, status-only
continuations and at most2 fits globally. Companion audit initially falsely
required A1-only localization_evaluation.py for B1; only that unbound helper was
corrected and regression-tested. All17 block01 attempts then passed. No frozen
code/config/receipt changed. Final audit requires --require-complete.

New reporting helpers are independently pinned in EVALUATION_ADDENDUM.json
and its detached digest. summarize_benchmark.py requires --official-audit plus
primary and two-stage evaluation files, and compares historical primary and
continuation controls separately. compare_hard_oracle.py performs truth-free
same-seed numerical comparisons. Final helper tests13 plus frozen suite77 pass.
Root handles final audit, summaries, plot inspection, README and user response;
SOL audit agent is available for final independent review.

Latest checkpoint: B1 through block06 (48primaries,17continuations), A1 through
block05 (40primaries,5continuations), then A1block06 and blocks07–08 remain.
Benchmark worker still owns every fit; root must not duplicate launches.
B1 42/48 accepted after stages,4 acquisition failures,2 unresolved; A1 35/40
accepted,5 acquisition failures. Sources/config unchanged. Interim paired
analysis (21 shared accepted scans) showed about2m median B-minus-A improvement,
not a meaningful accuracy win; full-panel results remain pending.

User asked which agents consume CPU. Root traced 17 production systemd
leo-adaptive-analysis-worker@0..16 services running as userleo. A2-second sample
showed ~18cores hop analysis +3cores scanner tracking, ourfits~1core at that
instant (maximum2), otherPython~1core. Inspected service instances have infinite
CPUQuota/MemoryMax. Two tracker roots @1/@6 shared session7fc0bc69dcdb9ec4;
one had33minute elapsed despite560second CLIargument. This is an observation,
not a diagnosed cause. User received detailed commentary; no services changed.
Question did not cancel benchmark. environment-snapshot.json and
process-attribution-snapshot.json preserve observations beneath benchmark-v1.

Additional new reporting code is sealed in TIMING_ADDENDUM.json and
DIAGNOSTIC_ADDENDUM.json (detached .sha256 files). Do not modify pinnedhelpers.
timing_diagnostics.py reads evaluatorJSON and excludes unchanged copiedparent
fit_seconds in continuations. benchmark_diagnostics.py provides resource,
discordantcompletion, practical-win gates and two extrafigures. Its CLI takes
PRIMARY TWO_STAGE --output JSON --figure-prefix PREFIX. association_diagnostics.py
takes finaltwo-stageJSON --output JSON, recomputes one score_all per accepted
track with frozenadapter, nooptimization/Jacobians/truth. Run it ONLY AFTER all
timedfits finish; posthoc runtime is excluded. Background-only conditional
satellite entropy is correctly undefined. All98 targeted tests currently pass
across frozen77 + reporting13 + timing3 + benchmark2 + association3.

Final work once SOL worker returns: run officialaudit --require-complete, verify
all three reporting addenda and FREEZE detached/source hashes, evaluate primary
and cumulative roots, summarize with --official-audit, run timing/benchmark/
association diagnostics, comparehardoracle with continuationroot, run combined
98-test suite, inspectplots, get independentSOLaudit review, writeREADME with
actualerrorsmeters/completion/runtime/limitations and update this state. No new
fits or thirdstagepolish. Finalresponse should also retain the CPU attribution
answer because commentary is collapsed; productionservices are the mainload.

Earlier next-step notes (superseded by official execution above): inspect active pilots; give status-only continuation if needed. Test the
complete owned suite. Freeze admitted methods and exact current source/config
before official 64 evaluation. At minimum A1 appears eligible pending stress
cases; B1 requires pilot results. C1 can be a documented slower control. D1 is
deferred per plan until acquisition/uncertainty gates; do not run a speculative
online filter. Full panel is eight explicit bounded arm-batches using the exact
plan benchmark.json IDs, never an automatic multi-hour campaign. Review each
batch and separately schedule allowed continuations (90+90 sec cumulative).
Keep all unresolved winners; do not adopt a worse converged mode or retroactively
polish the last scan into primary success. Plan maximum24 iterations per seed
per stage still applies.
