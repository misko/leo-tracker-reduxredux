# Algo07v4 native solver release

Algo07v4 publishes the full-budget native solver under `algo07v4-native-v1`.
Algo07v3 keeps its original default solver and persisted contract. V4 selects
its solver through the scan likelihood, rather than changing module globals.
V4 requests, scientific storage and publication provenance identify the native
backend separately. A saved v3 result cannot satisfy a v4 resume request.

The C source is byte-identical to the measured research candidate. Precision
budgets, convergence rules, priors and the `1e-12` conditioning guard are
unchanged. Unsupported numerical layouts use the original solver. Source,
wrapper, binary and provider bindings are checked before activation. Each
process reports its own calls, activations and fallbacks.

## Verification

The release passes 1,536 tests across 92 localization, application, CLI,
contract, storage, execution and evaluator modules. Ruff passes for all 30
changed or added Python files. Whitespace checks pass.

A built wheel contains the current Python runtime, packaged C and CLI entry
point. An extracted wheel builds its native backend and activates it on a
synthetic problem independently of the source checkout.

The complete DS26-0002 run through the new evaluation CLI reproduces the saved
research-native result exactly in both arm summaries, observation ownership
and all eight PNG bytes. Its 56 process receipts record 6,702 native calls
and zero fallbacks. Saved receipts match final process receipts, including
the evidence-projection calculations. The bound source and evaluator hashes
remain stable through completion. This is a packaging regression check, not
a new speed ratio or an independent accuracy evaluation.

The full plan binds all 159 expected DS26 members. It has 158 planned jobs and
one missing member, DS26-0172. No complete DS26 campaign was started for release.

The first CLI smoke attempt stopped before inference because the evaluator
expected TLE files directly beneath the archive root. The frozen snapshot uses
nested archive folders. The fix validates recursive membership, unique names
and content hashes. Tests reject missing, changed and duplicated snapshots.
The initial broad test run also identified a default-call compatibility issue
and missing local test build inputs. The compatibility fix preserves the old
call shape when no bound is supplied. Existing extensions and the tracked
oracle were prepared before the final 1,536-test pass. Golden fixtures were
not changed to make tests pass.

Local verification and raw attempts are retained under
`/home/mouse9911/.cache/algo07v4-release-20261112/`.
`release-verification.json` binds the final `smoke-0002-003` result to its saved
reference. `smoke-0002-001` retains the failed input preflight. The earlier
successful `smoke-0002-002` also matches the saved native result.

The earlier observed 1.56x and 1.64x complete-worker ratios remain single-pair
development evidence. The hard case changes six internal audit flags. V4 is
available for explicit validation; it does not assert DS26-wide accuracy,
repeatability or the 2x goal. No service deployment is part of this release.

Use the [evaluation commands](../how-to/evaluate-algo07.md) for quick or full
comparisons. The [algo07v5 goal and phase review](algo07v4-v5-goal.md) define the
next experiments and the speed versus accuracy reporting requirements.
