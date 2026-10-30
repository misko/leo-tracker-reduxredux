# ALGO03 production deployment — 2026-10-30

ALGO03 is active in production. The API/UI switched at 14:21:37 PDT on
October 30 (21:21:37 UTC); the numerical watcher started at 14:22:52 PDT
(21:22:52 UTC). Live graph responses and baseline fallback passed verification.

The user authorized deployment of ALGO03 with the instruction “Lets push it!
please deploy to remote main and production”, after the completed evaluation
identified aggregate runtime as the sole failed promotion criterion. The
original gate remains failed; this is an explicit operational exception, not
a revision of the scientific results or thresholds.

## Evaluation supporting the decision

The [full fast-only comparison](../2026_10_30_algo03_fast_full_evaluation/README.md)
contains all 400 DS23/DS24/DS26 acquisitions and both matched c arms. There are
377 qualified paired results and 23 unavailable cases, retained in the report.
No evaluation GPS or future TLE is admitted to inference.

| Dataset | Qualified scans | ALGO02 fitted-c mean error (km) | ALGO03 fitted-c mean error (km) |
| --- | ---: | ---: | ---: |
| DS23 | 204 | 1.240379 | 1.226884 |
| DS24 | 25 | 1.202710 | 1.179030 |
| DS26 | 148 | 1.316670 | 1.307223 |
| Pooled | 377 | 1.267831 | 1.255250 |

Pooled associated GLRT coverage increased from 70.571% to 71.031%, adding
6,854 points. The mean position improvement is modest, about 12.6 metres;
the P95 and worst position errors were unchanged. Frequency fit alone was
not used to claim localization improvement. The paired c=0 results and all
failure denominators remain in the linked evaluation.

Combined runtime P95 was 1,360.918 seconds versus the predeclared 1,045.448
second limit. Recovery P95 was 1,170.144 seconds. The user-authorized exception
accepts the aggregate runtime cost; the 1,200-second per-recovery budget remains.
These results are conditional on the evaluated same-site corpus.

## Exact releases and scope

- Numerical release: `e67f67484c4f54316b33dfd8e12f6e68d09d1e13`, installed at
  `/opt/leo-fast-graph/e67f67484c4f54316b33dfd8e12f6e68d09d1e13`.
- API/UI release: `9b3be7f84fddeb1a1ca4dacb283edb65af24be0d`, installed at
  `/opt/leo-tracker/releases/9b3be7f84fddeb1a1ca4dacb283edb65af24be0d`.
- Model: `algo03-causal-predictive-v1`; separate schema-major-2 namespace.
- All 1,977 evaluated runtime files match the installed numerical release;
  all 29 frozen scientific members remain unchanged.
- A separate watcher processes new completed, provenance-validated fast ALGO02
  baselines after a fixed deployment cutoff. It runs one recovery at a time.
  Adaptive scans and historical automatic backfill are excluded.
- The existing ALGO02 producer remains in service. The graph API/UI exposes
  both the baseline and selected result, and explicitly falls back to ALGO02
  when no valid ALGO03 result is available.

## Installed validation

The numerical canary used DS23-0088, chosen for its short successful evaluated
runtime, without ranking by GPS error. It ran under the production `leo`
account from the immutable installed release. Its source job is
`b903436532b765cf58ff2ed9385a9a02`; its v2 job is
`f272ee7d0017e298c8824be9c54e9f97`.

The canary selected `ALGO03_single`, passed the v2 contract, validated the
unchanged source baseline, and passed all six RF support/ownership checks.
All five launched-process read receipts were accounted for with no denied
paths. Recovery took 57.587 seconds; baseline plus recovery was 136.439 seconds.
Both c arms used matched observations and satellite owners.

The full installed API environment passed 30 focused API, production, storage
and contract tests. The staged web passed 10 component tests and a
TypeScript/Vite production build. Read-only production-root probes returned
HTTP 200 for the web, fast-scan API and graph endpoint, including exact ALGO02
fallback behavior. The numerical runtime is not used as the API environment.

The installed CLI restart probe exited successfully without changing the
completed canary's status hash or rerunning recovery. The numerical watcher is
enabled and active under `leo`, with deployment cutoff
`1793395227961750830` UTC nanoseconds and zero restarts at verification.
The ALGO02 service retains its original process (PID 2557002) and release.

Live HTTP checks on production port 8090 passed for static HTML, its graph
JavaScript bundle, the Fast Scan API, the actual canary graph response and
a missing-v2 fallback. The canary response selected `ALGO03_single`; its
position exactly matched the validated installed v2 terminal, and its embedded
baseline exactly matched the original ALGO02 terminal. The missing-v2 response
selected the exact ALGO02 baseline. The old API overlay cannot shadow the
new release: the override clears inherited `PYTHONPATH` and selects the
immutable API executable, working directory and web distribution.

Evidence: [authorization](authorization.json),
[installed canary](installed-canary-receipt.json),
[restart check](restart-receipt.json),
[numerical activation](numerical-activation-receipt.json),
[API/UI staging](app-staging-receipt.json),
[API/UI activation](app-activation-receipt.json),
[HTTP checks](api-activation-http-receipt.json),
[fixed cutoff](activation-plan.json), and
[installed numerical unit](leo-algo03-graph-position.service).

The explicit installed canary is historical; the enabled watcher does not
backfill the remaining evaluation corpus. At activation verification no new
post-cutoff production result had yet been observed. Catalogue discovery takes
a few minutes at startup; this is separate from the recorded recovery runtime.

## Rollback

1. Stop and disable `leo-algo03-graph-position.service`.
2. Remove only the ALGO03 API override named in the application activation
   receipt, run `systemctl daemon-reload`, then restart `leo-api.service`.
3. Verify the prior API/web release and the unchanged
   `leo-fast-shared-position.service` ALGO02 producer.

Prior API selectors and drop-ins are preserved. Retain v2 outputs and diagnostics;
rollback does not delete observations or rewrite baseline products. No RF
collection, acquisition service, database schema or QNAP mutation is part of
this deployment.
