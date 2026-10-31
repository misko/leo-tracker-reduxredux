# ALGO04 production deployment — 2026-10-31

**ALGO04 is active in production.** The numerical watcher and API/UI switched at **03:20:17 UTC on 2026-10-31**. Live endpoints select `algo04-causal-numerical-v1`, return the installed ALGO04 canary, and correctly return the exact baseline when no recovery result exists. Both new processes were healthy with zero restarts at verification; the ALGO02 and ALGO03 services retained their original processes and releases.

The user explicitly authorized this release after reviewing the DS26 results: “Great work! Can you please push this to remote and production as ALGO04”. The [ALGO04 specification](../ALGO04/README.md) documents the algorithm, bounds and acceptance behavior. The [DS26 evaluation](../2026_10_31_ds26_numerical_fix_evaluation/README.md) remains unchanged: 299 added observations across six scans, 70.9879% → 71.0338% pooled association, and fitted-c mean error 1.307223 → 1.306536 km. The median, P95, worst fitted-c error and 500 m success count did not improve. This promotion is a numerical-reliability and evidence-recovery update, not a claim of materially better dataset-wide accuracy.

## Exact released artifacts

| Component | Release / identity |
|---|---|
| Source commit, pushed to remote main | `f9e262f96b6e2e75b397f69d50a0ea9104e293ef` |
| Numerical release | `/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef` |
| API/UI release | `/opt/leo-tracker/releases/f9e262f96b6e2e75b397f69d50a0ea9104e293ef` |
| Model | `algo04-causal-numerical-v1` |
| Persisted namespace | `fast-scan-graph-position-v3` |
| Scientific manifest | `23a7947a27d7d3c0f13ec70c6fb8155dbff4d842290c991eedb02538381b88a6` |
| Fixed new-completion cutoff | `1793416793495348877` UTC nanoseconds |

The source manifest pins 1,994 members; the numerical stager additionally binds that manifest and retains every frozen ALGO03 scientific member. Both releases are root-owned, immutable installations. The numerical runtime uses the existing locked scientific dependencies and copied CPython 3.12 runtime. The full API application was independently staged and validated using the reviewed root-owned `/usr/bin/python3.14`, its locked dependencies and an npm production build. Neither service runs from the mutable development checkout.

## Behavior and scope

The separate ALGO04 watcher consumes completed ALGO03 analyses through verified public storage ports. It replays the tested wider numerical phase reference and centered position derivatives, retaining the frozen candidate competition and existing physical gates. It adopts an update only after fresh audited execution, scientific proof reconstruction and preservation of every published ALGO03 owner in both c arms. Otherwise it retains the exact ALGO03 result. ALGO03's own ALGO02 fallback remains visible when applicable.

New completions after the fixed cutoff are eligible. There is **no automatic historical backfill** and no adaptive-scan admission. The installed canary was an explicitly chosen historical case. One ALGO04 worker runs at a time, with a 1,200-second numerical budget including preparation. Runtime is reported separately from the ALGO03 incumbent, rather than hiding the additional pass. The API shows the selected model and separate ALGO03-incumbent/ALGO04-add-on times.

No RF was collected, no acquisition service was changed, and no database schema or QNAP path was modified. This release does not automatically rewrite the previously evaluated DS26 positions. At activation verification, the explicit installed canary was complete; no new post-cutoff recording was awaited or claimed as additional scientific validation.

## Verification

**136 Python tests and five UI tests pass**, covering numerical parity, phase/alias/partition preservation, cache corruption and source immutability, proof reconstruction, additive ownership, v3 storage, restart behavior, API selection and existing v2 compatibility. The UI production build and immutable application publication checks pass. Numerical and API tests run in their respective dependency environments; the API development environment does not contain SciPy.

A byte-copy integration probe used the existing production ALGO03 canary without GPS ranking. It qualified in 36.3 seconds. A separate full saved DS26-0044 relocation check verified 201 files, 23 snapshot file digests and six local proof edges, without changing original source bytes or performing new fits.

The **installed** canary ran under service account `leo` from the exact immutable numerical release, through the new v3 CLI/store/worker chain:

- Original ALGO03 source job: `f272ee7d0017e298c8824be9c54e9f97`.
- New ALGO04 job: `30b0cd29dfd9ef81357bfc4654c6e79b`.
- Recording view: `fast-7e8ca5148a366c63d4a17fcf8bca228a`.
- Decision: `ALGO04_additive`; 2,139 associated observations in each c arm.
- Numerical add-on: **42.861 s**; original baseline, ALGO03 and ALGO04 combined: **179.301 s**.
- All six scientific qualification checks pass; all **3/3 launched processes** have clean read receipts and no denied paths.
- Source ALGO03 terminal remains exact and unchanged. This canary exercises integration and numerical replay; it does not demonstrate an additional track-recovery gain.

The CLI restart probe did not change the completed status or terminal hashes and did not rerun inference. After activation, HTTP checks returned 200 for the web, Fast Scan listing, served JavaScript containing ALGO04, the actual canary graph result, and the missing-result fallback. The live canary position exactly equals the validated installed v3 terminal. The fallback position exactly equals its qualified ALGO02 baseline. The preceding ALGO03 API override remains on disk for rollback, while the later ALGO04 override explicitly selects the new executable, working directory, web bundle, empty inherited `PYTHONPATH`, and model.

Evidence: [installed canary](installed-canary.json), [restart](restart-receipt.json), [live activation and HTTP checks](activation-receipt.json), [qualification](qualification.json), [API/UI predeployment review](api-ui-predeployment-review.json), [prior service state](before-activation.json), [activation plan](activation-plan.json), [installed numerical unit](leo-algo04-graph-position.service), and [API override](leo-api-algo04.conf).

## Rollback

Stop and disable `leo-algo04-graph-position.service`. Remove only the new ALGO04 API drop-in at the exact path recorded in [activation-plan.json](activation-plan.json), then run `systemctl daemon-reload` and restart `leo-api.service`. This restores the existing ALGO03 API/UI override targeting `9b3be7f84fddeb1a1ca4dacb283edb65af24be0d`; its numerical service remains on `e67f67484c4f54316b33dfd8e12f6e68d09d1e13` throughout. Verify both graph selection and service health. Preserve all v3 outputs and diagnostic receipts; rollback does not delete recordings or rewrite v1/v2 results.
