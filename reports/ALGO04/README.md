# ALGO04 — bounded numerical recovery over published ALGO03

ALGO04 promotes the tested phase-reference and centered-derivative fixes, with an explicit ALGO03 fallback. The user authorized publication and production deployment on 2026-10-31 after reviewing the complete [DS26 comparison](../2026_10_31_ds26_numerical_fix_evaluation/README.md). This is a numerical reliability and evidence recovery release. It does not claim a substantial improvement in position accuracy or achievement of the 500 m goal.

The comparison covered 159 fast acquisitions: 148 usable paired results and 11 pre-existing unavailable cases. Association increased by 299 observations, from 70.9879% to 71.0338%. Fitted-c mean error changed from 1.307223 to 1.306536 km; its median, P95 and worst error were unchanged. The c=0 mean changed from 1.324560 to 1.323061 km. Both arms still have 24/148 scans within 500 m. Some recovered tracks worsen the individual position estimate. The report includes those regressions and the exact conditional replay scope.

## Scientific policy

ALGO04 consumes a completed, validated ALGO03 analysis. Acquisition, GLRT, graph construction, native observation IDs, causal orbit bank, candidate nominations, alias branches, random whole-group partitions and priors are inherited. The regional search remains the original 25 × 25 km box centered at latitude 37.906, longitude −122.545; numerical refits use the original regional starts. Evaluation truth is never an inference input.

The changes are:

1. A bank-checked ±30 s calibration phase-reference domain replaces the ±15 s numerical reference. The uncalibrated target physical phase-mixture support stays ±15 s.
2. Position L-BFGS-B uses centered one-metre derivatives and maxls=40. It retains five phase rounds, 48 iterations, and 240 actual objective calls per round, including derivative evaluations. There is no additional warm continuation.

The frozen ALGO03 implementation remains unchanged. New child-process bootstrap tools apply the evaluated numerical configuration. Existing phase convergence, residual/noise, exact orbit, continuous-phase countercheck, ownership, support and quadrature gates remain in force. Failure of any required check is not waived because a curve looks plausible or a frequency score improves.

## Replay and acceptance

The public ALGO03 export port supplies private byte copies with source hashes. Inside the guarded inference process, local path references and their verified digest edges are relocated into the current recovery directory. Original bytes and original proof hashes are verified before rebinding; scientific values are unchanged. Input paths escaping the export, missing proof members, symbolic links, changing sources and cyclic hash edges fail closed.

The replay uses the original completed annotation schedule, preserving target ranking. It reuses the unchanged inventory and unclipped annotations. Clipped annotations are reevaluated against the saved candidates, aliases and group partitions. Shared-family fits and exact audits are reused only when no changed numerical dependency exists. New-family and joint position fits use the numerical bootstrap. Original bounded Powell retries remain available under the same rules. No new catalogue nomination or historically unexecuted target search is introduced.

Reused stages retain their original budget charges. Newly valid work may consume the budget before later targets. Seven stage timeouts and 25 discovery-budget-limited targets occurred in the DS26 replay and are retained in its accounting. ALGO04 is not an exhaustive recovery search.

A newly accepted result must pass the existing scientific proof reconstruction and a fresh complete process read audit. It must also preserve every observation and satellite owner already published by ALGO03 in both c arms. A historically unverified ALGO03 read audit prevents adoption. Otherwise the exact published ALGO03 position is retained, including its original ALGO02 fallback when applicable. Acceptance never uses position error.

## Production composition

The separate model identity is `algo04-causal-numerical-v1`, with schema major 3 in `fast-scan-graph-position-v3`. Published v1 and v2 contracts and outputs remain immutable. The v3 envelope embeds its validated ALGO03 incumbent and, when available, a candidate using the existing v2 scientific proof envelope. That nested proof is not published into the ALGO03 namespace. The v3 position is exactly the accepted candidate's fitted-c endpoint or the incumbent position.

The existing ALGO02 producer and ALGO03 recovery service continue unchanged. A separate single-worker ALGO04 service watches newly completed ALGO03 results after a fixed activation cutoff. It performs no automatic historical backfill. One explicit historical installed canary is permitted for release verification. The numerical add-on is bounded to 1,200 seconds including preparation; its reported total includes the incumbent's processing time, up to 3,600 seconds. This sequential add-on therefore has a real runtime cost; cached replay timing is not a fresh-pipeline speed benchmark.

The API selects ALGO04 explicitly and shows the actual published result. Missing, pending, failed or invalid ALGO04 outputs fall back to the available ALGO03 result; missing ALGO03 falls back to ALGO02. The UI labels each model and displays the separate incumbent and numerical-add-on times. The API application release and numerical release are installed independently with their existing locked dependencies.

## Qualification, activation and rollback

The release stager packages an exact Git revision, checks the frozen ALGO03 inventory and the new ALGO04 manifest, and installs a root-owned immutable numerical release. A bounded installed canary must exercise the watcher, worker, fresh read guard, v3 contract and unchanged incumbent. A restart probe must retain the completed terminal without rerunning inference. API smoke checks verify both the ALGO04 result and missing-result fallback. Detailed installed evidence and exact revisions are recorded in the [deployment report](../2026_10_31_algo04_production_deployment/README.md).

Rollback stops/disables only `leo-algo04-graph-position.service` and removes only the new ALGO04 API drop-in, then reloads systemd and restarts `leo-api.service`. Existing ALGO03 selectors and services remain available. Retain all v3 outputs and diagnostics; rollback never deletes recordings or rewrites historical positions. No RF collection, acquisition-service change, database migration or QNAP mutation is part of this deployment.
