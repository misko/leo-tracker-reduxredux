# ALGO03 qualification and reversible production promotion

ALGO03 remains conditional on the frozen DS23, DS24 and DS26 fast-only comparison.
DS26 is the user's name for the new dataset; historical DS25 overlaps DS24 and
is not a separate primary denominator. No RF collection is part of this plan.

The predeclared scientific and operational rules are in
`reports/ALGO03/promotion-criteria-2026-10-30.json`; the executable decision is
`leo.qualification.algo03_promotion.qualify`. Retain every frozen acquisition,
both c arms, failures, unavailable inputs and ALGO02 fallbacks. The primary
criterion is strictly lower fitted-c mean position error overall **and within
each dataset**. Both c arms, acquisition modes, datasets and nonempty dataset/mode
strata receive the same mean/median/P95/worst non-regression guard: no increase
greater than the larger of 50 metres and 5% of the corresponding ALGO02 value.
This margin is an operational materiality choice, not statistical confidence.
The evidence is conditional on this frozen same-site corpus; it cannot establish
accuracy at another observing location. Report frequency-fit scores separately
from position accuracy. Do not compare raw objectives with different data sets.

Candidate total runtime includes the original ALGO02 processing, including for
cached ALGO02 analyses: use the saved terminal's `elapsed_seconds`, not the time
to export it. Recovery P95 must be at most 1,200 seconds, combined P95 at most
twice baseline P95 plus 60 seconds, and each whole job at most 2,400 seconds.
The bounded adapter may attempt eight targets and retain at most two distinct
new families jointly. Individual alternatives cannot be added together; this
release does not claim arbitrary multi-family recovery.

The explicit later user scope change is preserved separately in
`reports/ALGO03/promotion-scope-amendment-2026-10-30.json`. The active denominator
is exactly DS23=207, DS24=34 and DS26=159 fast acquisitions, including all 13
missing public GLRT inputs. Adaptive results are preserved outside this primary
comparison. The original criteria artifact remains unchanged.

## Separate published contract

`leo.contracts.fast_graph_position_v2` publishes schema major 2, model identity
`algo03-causal-predictive-v1`, in `fast-scan-graph-position-v2`. Never write its
outputs into the published v1 namespace or change the v1 model identity. A v2
complete result contains the validated original v1 terminal for the same public
input digest and recording. The selected fitted-c endpoint must exactly match
the published position; fallback must exactly match the baseline position.

A candidate includes its original source-support owner maps, explicitly scored
target IDs/NORAD owners, both selected c arms, and the complete clean process
read-audit receipt. Source owner maps must exactly match baseline terminal gates.
Both c arms must have exactly the same final observation IDs and satellite owners;
their support must equal incumbent union scored targets, with no overlap or
incidental unscored additions. The trusted runner supplies all `RF_CHECKS` only
after replaying matched controls, exact orbit/ownership audits, and source
receipts. Store detailed source audits with the result; scalar booleans alone
are not an instruction to skip the audits. A failed recovery audit may still
publish a valid baseline fallback and must retain its failure receipt.

The envelope records `baseline_seconds`, `recovery_seconds`, and `total_seconds`;
the last must equal their sum. Its bounds are 1,200/1,200/2,400 seconds. No GPS or
future TLE may enter inference or target ranking. Evaluation truth is read only
by the separate report generator after inference is sealed.

## Stage the exact qualified revision

Commit the intended source and tests, then use the complete 40-character SHA.
The separate `tools/stage_algo03_release.py` checks the committed frozen r1
manifest SHA-256
`6dd58bbbe5e7d1f881c820edf0bee0345952a365553afaf37f457dfcec189545`
and every pinned scientific member. It packages their reports and tests as well
as `src`, `tools` and `deploy`; the ALGO02 stager's three source directories alone
are insufficient for the ALGO03 launch-time release verification.

Run its validation form, then the same invocation with `--execute` as root:

```text
/opt/leo-fast-graph/1b63f5908785fc940446086aa4ef5de1a1539003/venv/bin/python \
  tools/stage_algo03_release.py \
  --source /srv/bulk/leo-dev/fast-algo02-production-v1 \
  --revision FULL_QUALIFIED_SHA \
  --python-root /opt/leo-fast-graph/1b63f5908785fc940446086aa4ef5de1a1539003/runtime \
  --uv /opt/leo-fast-graph/1b63f5908785fc940446086aa4ef5de1a1539003/uv
```

This creates a new root-owned immutable `/opt/leo-fast-graph/FULL_QUALIFIED_SHA`,
installs the existing hash-locked dependency set, checks imports, seals hashes,
and removes `.incomplete` only when complete. It cannot modify systemd, recording
data, PostgreSQL or a live selector. Preserve failed incomplete staging for
diagnosis; do not select or repair an incomplete release in place.

Before cutover, execute the component tests and one bounded installed canary as
`leo` from that exact release and verify its v2 result with the contract. The
canary must demonstrate the new watcher/worker integration, clean audited reads,
unchanged source input, durable terminal/restart recovery, and a valid selected
result or exact baseline fallback. A successful scientific receipt alone does
not establish installed service readiness.

## Activate and roll back

Only after all gates pass, save the current complete `systemctl cat
leo-fast-shared-position.service`, its release drop-in, exact unit properties,
and the current release SHA in a deployment receipt. The present rollback
release is `/opt/leo-fast-graph/1b63f5908785fc940446086aa4ef5de1a1539003`.

Keep `leo-fast-shared-position.service` running the existing ALGO02 baseline
producer. Render the separate `deploy/systemd/leo-algo03-graph-position.service`
with the qualified immutable release and a fixed deployment-time UTC nanosecond
cutoff, then install it as `leo-algo03-graph-position.service`. The v2 watcher
consumes only completed validated v1 baselines newer than that cutoff, never
refits the baseline, and never performs an automatic historical backfill.
Fast admission resolves the tracking source's ingest digest through the public
`FastScanStore.source` port to a verified `fast-scan-source` inventory; the
compatibility `capture_mode=adaptive` label is not acquisition authority.
Prepare only its new local v2 namespace as `leo`; preserve v1 outputs.
Keep the existing service account, resource limits, control-group termination,
read-only causal TLE access and QNAP inaccessibility. Reload systemd and start
the separate recovery service only. Record the selected ExecStart, effective source
revision, process account, activation time and first validated terminal receipt.
Acquisition services, radio state and database schema are outside
this cutover.

The normal Fast Scan detail has a separate clearly labeled graph panel, backed
by the narrow `GraphPositions` reader and
`GET /api/v2/fast-scans/{run_id}/graph-position`. Activate it only in a separately
qualified immutable application/API release with
`LEO_GRAPH_POSITION_MODEL=algo03-causal-predictive-v1`. The response includes
both the original ALGO02 and published selected endpoints/model identities. A
missing or invalid v2 result explicitly returns the qualified ALGO02 fallback.
The numerical stager does not install the full API dependency set or build the
web bundle, so selecting it as an API release is invalid. Use the ordinary full
application staging/qualification workflow for the UI change; never run the API
from this mutable source checkout.

The 2026-10-30 source qualification review passed 26 focused API, production
composition, v2 recovery/restart and staging tests using the full application
environment. The graph panel and Fast Scan view passed all 10 focused browser
component tests and a TypeScript/Vite production build in an isolated copy with
the existing frontend dependencies. Read-only production inspection confirmed
that Fast Scan report `run_id` values match exported tracking-input filename
stems, the identifiers consumed by the graph reader. Discovery now logs and
rejects each invalid or non-fast baseline independently, so an ineligible input
cannot prevent later valid fast work; adaptive, missing-input and corrupt-status
regressions cover that behavior. All 29 frozen r1 scientific members and the
manifest remain unchanged. This review did not activate a service or API model;
the exact committed release, installed canary and full scientific gate remain
required before activation.

For a failed installed canary, repeated worker crashes, invalid contract or
unexpected coverage loss, stop/disable the separate ALGO03 recovery service and
restore the prior API model selection or application release. The ALGO02
baseline producer keeps its old immutable ExecStart and ordinary processing.
Preserve v2 results and diagnostics
for analysis; rollback never deletes observations or rewrites v1 products.
