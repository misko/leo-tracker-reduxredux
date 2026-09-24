# DS2 inventory: 2026-09-24 adaptive captures

## Frozen inventory

The inventory cutoff is **2026-09-24T15:43:30Z**, exclusive.  It queried the
newest public adaptive-history pages through the prior UTC-date boundary,
then read only existing analysis-status metadata for each in-window session.
No IQ, QNAP path, queue, analyzer, or model was opened or changed.

| Inventory result | Count |
| --- | ---: |
| In-window sessions before cutoff | 22 |
| Raw-capture eligible | 20 |
| Existing analysis-ready sessions with an explicit track count | 0 |
| Geometry-aware model eligible | 0 |
| Analysis status unavailable | 2 |

The earliest included capture began at 00:00:02Z and the latest at
15:30:02Z.  Five sessions came from `radio_pluto_19f2` and 17 from
`radio_pluto_5d4d`.  All 20 metadata-available scans declared RX0/RX1, but
the first radio includes one 15 MS/s capture; downstream DS2 model selection
should separate it from the 2.5 MS/s cohort rather than silently resample it.

## Authoritative tracking readiness

The analysis-status endpoint is not the authority for completed tracking
products: its null track-count field means only that this presentation omits
the count.  The companion
[`../2026_09_24_ds2_backfill/tracking-readiness.json`](../2026_09_24_ds2_backfill/tracking-readiness.json)
queries `/api/v1/scanner/tracking/{session_id}` for this same frozen member
set.  It records the V14 tracking state plus sealed product version,
input/analysis/configuration digests, and tracklet/TLE-candidate/review/artifact
counts.  Use that companion for DS2 readiness; it does not alter the frozen
cutoff or capture membership.

## Signal, tracks, and geometry

All 20 available analysis-status records were `not_started`; none provided an
existing track or signal count.  The frozen manifest therefore records these
counts as null instead of inferring them from retained visits or duty.  This is
an API-field limitation, not evidence that tracking is absent.  The remaining
two sessions returned HTTP 404 for their analysis status endpoint and remain
excluded from raw-capture eligibility until their receiver metadata is
recoverable.

The public API exposes dual-receiver analyzer configuration, but not the
capture-time receiver-geometry binding.  A direct read-only attempt to inspect
the protected `scanner-adaptive-recordings` namespace was denied.  No scan is
described as having LT3D-001A, any other fixture, or a verified/provisional
RX-to-slot mapping on the basis of this inventory.  This is intentional:
radio identity and a dual-RX configuration are insufficient geometry evidence.

## DS2 inclusion rules

The source rules are in [PROTOCOL.md](PROTOCOL.md).  In brief, the manifest
keeps every capture on the date before the frozen cutoff and marks a raw source
eligible only when UTC timing, completion, source-span attestation, nominal
300-second duration, retained visits, and public dual-RX declaration all pass.
Analysis-ready use additionally requires an existing completed status with an
explicit track count.  Geometry-aware positioning requires a capture binding;
none is inferred here.

The proposed next DS2 input set is the 20 raw-eligible sessions, stratified by
radio and sample rate.  Do not schedule an expensive position model until an
authorized analysis backfill publishes track evidence and a geometry authority
is available through a supported read-only interface.

## Reproduction

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds2_inventory/test_build_manifest.py
.venv/bin/python reports/2026_09_24_ds2_inventory/build_manifest.py \
  --cutoff-utc 2026-09-24T15:43:30Z \
  --output reports/2026_09_24_ds2_inventory/manifest.json
```

The machine-readable [manifest.json](manifest.json) and its SHA-256 sidecar
bind the cutoff, source API, eligibility outcomes, signal/track availability,
and builder source.
