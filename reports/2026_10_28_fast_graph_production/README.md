# Production deployment of the validated fast-scan baseline

The production localization worker now uses **ALGO02-v1 + qualified causal
signed phase prior + equal-prior satellite-family comparison**, under deployment
identifier **`algo02-causal-family-v1`**. This is the existing validated research
reference, not a new scientific ALGO release. It replaces the older shared-q
worker command in `leo-fast-shared-position.service`.

The exact installed source revision is
`1b63f5908785fc940446086aa4ef5de1a1539003`, staged at
`/opt/leo-fast-graph/1b63f5908785fc940446086aa4ef5de1a1539003`.
Cutover occurred October 28, 2026 at **7:36:39 p.m. PDT**
(October 29 at 02:36:39 UTC). Acquisition, GLRT processing, the API and earlier
scientific products retain their existing services and namespaces.

The user explicitly authorized production deployment and publication to remote
main. SOL high supplied a read-only source and lifecycle audit. The implementation,
release configuration, numerical dependencies and this evidence are committed.

## What is running

The new watcher consumes existing public fast GLRT exports through
`FastScanStore`. A fresh process builds alias-aware polynomial graph tracks,
estimates radio noise and generates the causal regional satellite catalogue
and historical TLE prior. It then executes the original phase-refreshed
discovery, ALGO02 paired inference, qualified signed means and family comparison.
The numerical signed/family adapter reproduces the original DS24 engine; its
only interface change is requiring an explicit output root.

Every successful output retains **both c=0 and fitted-c** results. Observations,
identities, aliases, other priors and numerical budgets are matched between
arms. Selection uses the existing corrected normalized c=0 loss; the published
position is the corresponding fitted-c result. Linear tracks provide predictive
position evidence without calibrating receiver offsets/drifts. Existing
residual gates and the original predictive phase-stability gate remain in
force. Curved-only fallback retains its original acceptance policy and reports
the last phase-refresh change separately.

The fixed deployment search remains the original **25×25 km regional box**,
centered at **37.906°, −122.545°**, with east/north start `(0,0)`. It is not a
global localization policy. There is no evaluation GPS seed, post-scan TLE,
satellite whitelist, stationary cross-scan position pooling, new RF collection,
or incorporation of the rejected ALGO04/CH5–8 recovery candidates.

One job runs at a time, newest public export first, with one BLAS thread and a
1,200-second whole-job cap. Outputs use the separate versioned namespace
`/srv/bulk/leo/fast-scan-graph-position-v1/algo02-causal-family-v1/jobs/`.
Input/model digests identify jobs. Failed/interrupted attempts are retained and
not automatically refitted. Watcher restart can recover an already complete
terminal. The supervisor and systemd terminate the entire process group.

The new terminal has its own public contract, `fast-scan.graph-position` v1.
It explicitly describes residual-policy qualification; it does not reuse or
fabricate the older shared-q optimizer-stationarity contract. The existing
shared-q web views remain views of their older model. This deployment switches
the background localization worker; it does not silently relabel those views
or overwrite older positions.

## Qualification

**146 focused tests pass:** 123 numerical/boundary/component tests and 23
additional ALGO02, signed-prior and family-policy tests. A clean environment
installs exact numerical dependency versions from a hash-locked file. The
release includes an independent CPython 3.12 runtime; all runtime symlinks remain
inside the release. All **1,774 source/configuration hashes** verify.

Two complete original-GLRT replays ran as the `leo` account under the production
filesystem sandbox, including `ProtectHome`, `ProtectSystem`, read-only TLE
access, no QNAP access and the inherited matplotlib-cache environment. Each job
redirects its own plotting cache into its fresh output directory. No hardware
recording or dataset-wide scientific rerun was launched.

| Existing recording | Installed replay time | Research family replacement | Paired position/RMS/loss parity |
|---|---:|---|---|
| DS24-0095 | 161.34 s | Retain incumbent; curved fallback | Exact in both c arms |
| DS24-0077 | 185.50 s | Accept replacement; predictive evidence retained | Exact in both c arms |

Fresh terminal endpoints, frequency RMS, saved frequency-model loss and retained
curved point owners/identities exactly match the saved research results. The
comparison reads those research results only after each fresh terminal seals.
Both runs have four clean per-process read receipts, accounting for every
launched numerical process and its Python descendants. Read guards permit this
job's data, its explicit public input, the causal archive, release code/config
and installed/system dependencies; unrelated data/report reads fail.

These replays establish installed implementation parity and operational
qualification. They do not establish new-site accuracy, a new dataset-wide
performance result or attainment of the 500 m goal. The existing fast-scan
accuracy results remain in the [DS24 channel comparison](../2026_10_24_ds24_channel_halves/README.md),
and the later [recovery promotion assessment](../2026_10_26_ds24_missed_visit_promotion/README.md)
remains a negative promotion result.

Earlier packaging attempts are retained in the local qualification directory.
They exposed missing numerical/import dependencies, historical curved-only
phase metadata and a read-audit bug with descriptor-relative archive opens.
These issues were corrected before service cutover. Their failed terminals are
preserved; they are not counted as successful qualification or scientific
accuracy measurements.

## Operational evidence and rollback

The [canary comparison](evidence/canary-comparison.json), test logs and installed
terminal/read receipts bind the checks above. The [production drop-in](evidence/production-release.conf)
selects the exact release. The [previous drop-in](evidence/previous-release.conf)
is preserved for rollback. The local operational evidence root is
`/srv/bulk/leo/qualification/fast-graph-position-20261029`.

Rollback restores that previous drop-in to
`/etc/systemd/system/leo-fast-shared-position.service.d/release.conf`, runs
`systemctl daemon-reload`, then restarts only `leo-fast-shared-position.service`.
No recording or result is deleted. The earlier shared-q release remains
available.

The first ordinary queued production job, `e707e17dfce3af8c0ea055293c349d0e`,
completed successfully in **142.42 seconds**, with four clean read receipts and
both qualified c arms. Its position likelihood uses **2,508 of 3,283 GLRT
points (76.39%)**: 2,068 curved calibration points and 440 predictive points.
This count excludes postfit-only association extensions. The watcher then
started the next pending export. The
[deployment receipt](evidence/deployment-receipt.json) records the actual service
command, model/source revision, completed input identity, point counts and
terminal hash; the compressed first-production terminal is included. Both the
GLRT analysis service and API remained active. This operational check does not
assign a position-error label to the current recording.

See [the production runbook](../../docs/operations/fast-graph-position-production.md)
for the input/output contract, preparation, budgets and deployment procedure.
