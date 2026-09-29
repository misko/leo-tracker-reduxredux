# Hard-cone scoring: initial execution aborted before data loading

The first process, DS7_early_4, exited 1 before loading observations or candidate
banks and produced no model scores. Importing hard_gate modified the research
module search path before run.py imported study, so Python loaded the existing
cone/trend report's study module instead of this directory's module. The wrong
plan has no per-unit group field, producing KeyError: 'group'.

All frozen sources, the original plan, input seal, failed command, terminal
traceback, exit code and resource receipt are preserved unchanged. The other
seventeen jobs were never launched. This is an execution failure, not evidence
for or against a hard-cone model, and no score or geometric result is reported.

The [corrected execution](../2026_09_29_hard_cone_scoring_v2/README.md) loads the
local study module before the dependency bootstrap. It adds a fresh-process
entry-point test and requires an identical scientific plan. It must use new
output directories and retain this failed attempt. No completed dataset scores
exist here to retry, replace or select around.

The [nine model tests](tests-fixed-imports.log) passed before launch. Their
earlier import-order failure remains in [tests.log](tests.log); the original
published synthetic fixture was never modified. The additional entry-point
test belongs to the corrected execution.

[Frozen protocol](PROTOCOL.md), [plan](plan.json), [source/input seal](input-seal.json),
[failed process](runs/DS7_early_4/terminal.log), [exit code](runs/DS7_early_4/exit-code.txt).
