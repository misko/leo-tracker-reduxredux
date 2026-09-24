# DS2 bounded preprocessing and analysis backfill

This path consumes exactly the 20 raw-capture-eligible session IDs frozen by
[`../2026_09_24_ds2_inventory/manifest.json`](../2026_09_24_ds2_inventory/manifest.json).
It does not start a radio capture, modify source IQ, or access QNAP.  The plan
opens immutable local capture manifests as the `leo` service account, records
only explicit capture-time receiver geometry, and creates at most one derived
analysis or tracking queue record per frozen session.

The production queue worker owns the expensive processing.  Each lease is
bounded to 2 analysis workers, 2 host workers, 2,500 visits, and 560 seconds;
it resumes unfinished work and queues tracking only after sealed metrics and
relative phase are complete.  The enqueue operation is idempotent on session,
input-manifest digest, and configuration digest.

Run a non-mutating inspection as the service account:

```bash
sudo -n -u leo sh -c 'set -a; . /etc/leo/leo.env; exec /opt/leo-tracker/releases/51701a6ba364bd20170cbc167c1ee0db8c640483/.venv/bin/python \
  /home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_24_ds2_backfill/enqueue_frozen.py \
  --output /tmp/ds2-backfill-plan.json'
```

After reviewing the plan, append `--enqueue` to create only the planned
derived-product jobs.  Copy the resulting JSON into this directory as the
machine-readable execution record; no credentials appear in the artifact.

`receiver_geometry` is reported only if present in each sealed capture
manifest.  In particular, `LT3D-001A` is not inferred from a radio ID.  The
binding records fixture digest, receiver-slot mapping and its verification
status so downstream phase/position work can reject provisional geometry when
needed.

## 2026-09-24 bounded execution

The service-account dry run read and digest-checked all 20 frozen capture
manifests.  At the first observation, the older analysis-status presentation
showed no sealed metrics/relative-phase products, so the idempotent enqueue
attempted the analysis route and found all 20 jobs already in the production
queue; it created zero additional jobs.  The authoritative tracking endpoint
is the readiness authority: [`tracking-readiness.json`](tracking-readiness.json)
records the sealed V14 product identity, input/analysis/configuration digests,
tracklet count, TLE-candidate count, review count, and artifact count for every
complete session.  `plan.json` is refreshed from current V14 product state and
does not requeue completed tracking merely because the older endpoint omits it.

Three early captures contain explicit `LT3D-001A` capture-time bindings:
`scan-fw-f3ce5fe73aa40506`, `scan-fw-9f3d5067d149118e`, and
`scan-fw-cfcf667726e80735`.  They all bind RX0 to `negative-x` and RX1 to
`positive-x`, but mark both mappings **provisional**.  The remaining 17 are
schema-13 capture manifests without a `receiver_geometry` field.  They are
eligible for ordinary analysis/tracking, but must not be treated as
geometry-aware phase inputs until an explicit binding is available.

The registry resolution is deliberately separate from the capture binding.
For the three `radio_pluto_19f2` captures, it validates matching sealed radio
ID and serial plus capture time against
[`src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json`](../../src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json).
The plan records its path, content hash, validity interval, fixture digest and
provisional RX-slot mapping.  No such valid registry entry exists for
`radio_pluto_5d4d`, so its 17 captures remain geometry-unavailable.

Reproduce the readiness snapshot without touching source IQ:

```bash
.venv/bin/python reports/2026_09_24_ds2_backfill/status_snapshot.py \
  --output reports/2026_09_24_ds2_backfill/tracking-readiness.json
```
