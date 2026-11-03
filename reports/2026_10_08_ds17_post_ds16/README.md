# DS17: post-DS16 adaptive recordings through the request cutoff

**Minted: 51 recordings, 112,543 retained visits, and 13,505.16 seconds
(3.7514 hours) of valid IQ per receiver.** Referenced compressed IQ totals
559,300,718,799 bytes (559.30 GB). Both receivers remain together.

| Property | Frozen value |
|---|---|
| Start, inclusive | October 7, 2026, 6:33:48 p.m. PDT |
| Request cutoff, exclusive for capture starts | October 8, 2026, 7:36:56 a.m. PDT |
| Exact UTC window | 2026-10-08 01:33:48 through 14:36:56 UTC |
| Boundary authority | DS16's frozen window endpoint |
| Recordings | 51 |
| Sample rates | 21 at 2.5 MS/s; 30 at 10 MS/s |
| Retained visits | 112,543 |
| Source at completed inventory | 51 published recordings |
| Analysis-readiness admission gate | None |
| In-window exclusions / unsealed partials found | 0 / 0 |
| Overlap with DS16 by session or uncompressed IQ digest | None |

The authority is [local/manifest.json](local/manifest.json), protected by
[local/seal.json](local/seal.json). Manifest SHA-256:
`39dd3ddd65468718615cc1680365b67a892f46ae6fc8ab660fe9114565f0db27`.
The snapshot includes DS16's exact parent manifest and seal, candidate index,
full source metadata, producer completion evidence where needed, and
[evaluation units](local/evaluation-units.json). Whole recordings are ordered
chronologically and labelled DS17-001–DS17-051. No training split is implied.

## Membership and publication timing

Membership covers whole adaptive recordings starting within the frozen window
and sealed by its end. Published metadata is read through `AdaptiveHopIqStore`
with `read_only=True`; firmware archive manifests are inventoried across the
configured NVMe spool. Analysis completion, signal strength, sample rate, and
localization outcomes do not select membership. Capture-quality flags are
preserved rather than used to remove recordings.

`scan-fw-da79d96a4515ec30` finished before cutoff, but publication completed
after cutoff and its archive left the spool during inventory. Its producer
summary records archive completion at **7:36:03 a.m. PDT**, before the
**7:36:56 a.m.** cutoff. That summary is copied, hash sealed, and bound by
session, radio serial, rate, and the published terminal timestamp. It is included.
`published_finalized_utc_ns` preserves publication time; `finalized_utc_ns`
uses the pre-cutoff completion receipt for this row. Its original archive
manifest was not recovered after transfer; evidence is the producer summary
plus published source metadata.

The initial 50-recording provisional output remains in ignored `provisional-50/`
for traceability and is superseded by `local/`. An earlier unsealed collection
attempt is in ignored `incomplete-attempt/`. Neither is the DS17 authority.
The final mint refuses to overwrite its output directory.

The start boundary applies to recording starts, not individual IQ samples.
`scan-fw-9f3c31087f533011` started at October 7, 6:30:21 p.m. PDT and ended at
6:35:22 p.m.; it straddles the boundary and is outside DS17. This dataset does
not claim uninterrupted sample-level coverage across the DS16 boundary.

## Verification and limits

Fourteen offline tests and Ruff pass. Verification checks artifact hashes,
parent seals, membership, source bindings, late-publication evidence, counts,
and evaluation units. An independent source-snapshot audit reconciled all 51
candidates, chunk visit/byte totals, and parent disjointness. All admitted
receipts report zero transport-missing, unclassified, and unreceived tail
samples. These are receipt assertions, not a fresh IQ payload audit.

```bash
.venv/bin/pytest -q reports/2026_10_08_ds17_post_ds16/test_mint.py
.venv/bin/python reports/2026_10_08_ds17_post_ds16/mint.py verify
```

The live inventory is not atomic. IQ remains in its existing store and was not
copied, decompressed, or rehashed; no retention hold was created. No new RF,
analysis, publication, or service change was initiated. Membership and source
snapshots are local and Git-ignored. No remote push was performed for this mint.
