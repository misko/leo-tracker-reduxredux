---
name: verify-algo07-star
description: Run or resume frozen ALGO07 versus ALGO07* comparisons and check exact scientific and publication parity. Use for ALGO07* regression verification, DS26 qualification, or interpreting its pass/fail receipts.
---

# Verify ALGO07*

Use `tools/verify_algo07_star.py`; do not reconstruct the six-stage command chain
or write another comparator. It imports the existing strict comparators, checks
both c=0 and fitted-c, and does not modify production. This starts from preserved
native GLRT evidence; it does **not** rerun IQ acquisition or qualify GLRT changes.

## Current checkout and frozen fixture

The ALGO07* worktree is `/srv/bulk/leo-dev/algo06-promotion-20261101`.
The older `/home/mouse9911/gits/leo-tracker-reduxredux` checkout lacks this work.
Use its virtualenv interpreter with the active worktree's CLI:

```bash
cd /srv/bulk/leo-dev/algo06-promotion-20261101
VERIFY_PY=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
VERIFY_FIXTURE=/srv/bulk/leo/research/algo07-star-20261104/iteration000
VERIFY_CASE="$VERIFY_FIXTURE/DS26-0267"
```

These are the current host's paths, not inference settings. For another host or
iteration supply its own fixture and interpreter. `init` defaults to
`runtimes-r2.json`, `frozen-r2.json`, `frozen.json`, and `tle-view` inside the fixture;
explicit path overrides are listed by `init --help`. The archive clone is bound
to the **original** `frozen.json`; the corrected runtime uses **frozen-r2.json**.
Do not interchange them or rebuild the fixture from today's live TLE archive.
The frozen inventory also includes the original coordinator and repository
source files. Do not edit pinned files while an experiment uses them; a new
experimental entry point must have its own source pins.

## One-time setup per case

If `verify-algo07-star.json` already exists in the case, skip initialization.
Otherwise select its exact native run from the existing cohort inventory, then:

```bash
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py init \
  --case "$VERIFY_CASE" --fixture "$VERIFY_FIXTURE" \
  --run-id fast-dcef5c555456cdd1f27055bacbe5920d
```

This example is DS26-0267. Use the inventory's run ID for other cases. Setup
clones native documents through the public port, or validates existing private
`reference` and `candidate` stores. It records paths and hashes once. For earlier
nonstandard directory names, supply `--reference` and `--candidate`. Adopt old
completed runs with `--reference-execution` / `--candidate-execution`; optionally
supply existing `--reference-evidence` / `--candidate-evidence` exports. All reused
export bytes are rehashed at comparison time.

## Status and bounded execution

```bash
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py status --case "$VERIFY_CASE"
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py run --case "$VERIFY_CASE" --side reference
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py run --case "$VERIFY_CASE" --side candidate
```

Each `run` advances **one** path, with the original 1,200-second stage budgets,
an inner 1,500-second checkpoint budget, and an outer 30-minute bound. Repeat
after `checkpointed`; do not use an unattended retry loop. It retains logs,
command, exit status and execution receipt. Failure or an unfinished attempt
requires investigation, not automatic retry/deletion. Sudo is needed for the
private read-only TLE mount namespace and existing root-owned research outputs.
An existing worker can still be active when no chain receipt exists: check
status/processes before launching legacy cases. Do not interrupt workers.

## Exact comparison

```bash
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py check --case "$VERIFY_CASE" --scope science
```

This exports all six stages if no exports were configured, rehashes the evidence,
validates public terminals, process provenance and hash links, then compares
scientific values exactly. It writes `verify-check-NNNN/science.json` and a small
`summary.json`. Unknown differences fail; only the existing reviewed accounting
rules apply. No tolerance is added by this CLI.

To include already-rendered public artifacts:

```bash
sudo -n "$VERIFY_PY" -B tools/verify_algo07_star.py check --case "$VERIFY_CASE" \
  --reference-publication /absolute/private/reference-publication \
  --candidate-publication /absolute/private/candidate-publication
```

Default scope is `all`. It requires all eight PNGs, full grid and path equality,
with publications independently bound to the compared source terminals. This
command verifies publications; it does **not** generate them. For a fresh renderer
replay use the pinned presentation procedure in
[the completed smoke report](../../../reports/2026_11_04_algo07_star_intermediate_parity/README.md).
Keep incomplete deadline-sensitive grids as failures; do not quietly rerender
until a pass or replace the original receipt.

Exit codes: **0** requested scope passes; **1** compared evidence fails;
**2** incomplete inputs, missing publication, or setup/execution error. Always
read `requested_scope` and `case_full_parity`: science-only PASS is not full
artifact parity. A case PASS never establishes full DS26 parity or a speedup.
Retain missing/failed cases in the cohort denominator. Parallel runs establish
parity only; speed requires separately controlled sequential trials.

## Deadline diagnostics

Wall-clock admission can change work even with unchanged numerical workers.
Keep these failures and investigate the first differing admission; never hide
missing hypotheses or incomplete grids as timing metadata. DS26-0102 is a
documented discovery-budget example.

`tools/algo03_stage_clock_fixture.py` is a separate research diagnostic for
matched ALGO03 discovery admission. It delegates numerical children to the
installed worker, but its stage durations are synthetic. Keep the separate real
wall deadline, read-audit receipts and predeclared schedule visible. Its results
do not replace an ordinary failed DS26 comparison; see the
[DS26-0170 diagnosis](../../../reports/2026_11_04_algo07_star_second_deadline_case/README.md).

`tools/algo07_grid_clock_fixture.py` is a **research-only** injected-clock
fixture for matching diagnostic-grid work. It has separate real wall-time
receipts; the grid's own elapsed field is synthetic. The saved 179-location and
17-location experiments are described in
[the optimized smoke report](../../../reports/2026_11_04_algo07_star_optimized_smoke/README.md).
An exact publication comparison under this fixture qualifies only that
controlled condition. Do not use these publication roots to report an ordinary
wall-clock `case_full_parity` pass. Equivalent partial grids still fail the
strict completeness gate. Preserve the plans, hard wall limits and original
failed publications; do not rerender until a favorable result appears.

## Experimental terminal-read reuse

For a **new private candidate case**, `init --candidate-terminal-read-reuse`
selects `run_algo07_star_reuse.py` only on the candidate path. It pins the current
Python source tree and both coordinator scripts, verifies them before and after
execution, and preserves original scientific workers, budgets and TLE pins.
It substitutes the final-stage public terminal reader; it does not skip stages.
Default cases continue to use the original driver. Do not enable this in an
existing zero-change case or call the prototype a qualified optimization before
full DS26 comparisons and end-to-end measurements. A previously completed
independent reference may be adopted for parity only, never for timing claims.

Read [the ALGO07* plan](../../../docs/operations/algo07-star-plan.md) only when
changing qualification scope or implementing a new optimization. Routine checks
need only this skill, CLI help and the concise JSON summary.
