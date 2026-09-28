# Receiver-geometry confirmation inventory

## Decision

The bounded four-record panel is frozen by metadata only: at each supported sample rate,
select the earliest capture UTC (then session ID) among existing derived caches that are
hash-valid, pose-bound, and disjoint from the ten-record receiver-sequence pilot.

| Rate | Selected session | Capture start UTC ns | Prior use |
|---:|---|---:|---|
| 2.5 Msps | `scan-fw-40ebc07665464c7d` | 1790481640900573984 | Roof geometry confirmation and later static-arm studies |
| 5 Msps | `scan-fw-f147dd8a5bc99346` | 1790480368699207814 | Roof geometry confirmation |
| 7.5 Msps | `scan-fw-b5604c3d838fa7ed` | 1790479945102849516 | Roof geometry confirmation |
| 10 Msps | `scan-fw-339af454a2aab2f4` | 1790482064896844310 | Roof balanced confirmation |

These are reused historical observations. They are not blind, unseen, or independent of
the broader research history merely because the receiver-sequence pilot did not use them.
No reception, association, location, or geometry outcome was used by this selection.

## Integrity and overlap

The four source inventories contain 18 unique sessions. Eight satisfy the objective
eligibility rule; the rule selects one per rate. Every selected cache exists and matches
its recorded SHA-256. No conflicting cache binding was found where a session appears in
more than one source inventory.

All selected sessions are disjoint from the ten pilot sessions and from DS7's 88 admitted
sessions. They predate the DS7 post-DS6 corpus boundary. The inventories and prior manifests
provide exact input-manifest hashes, analysis-manifest hashes, capture bounds, sample rates,
and the same pose authority at 37.849056280893684 N, -122.48575489722863 E.

## Pipeline readiness

The caches identify the public persisted type
`leo.contracts.scanner_tracking.TrackingInput` and carry the input and analysis hashes used
by the current training-bank loader. They therefore have the required public shape for the
existing opportunity, partition, training-bank, and alias-mapping pipeline when run in the
installed analysis interpreter that owns this contract. A generic repository interpreter
without that installed module cannot unpickle them; this is an environment requirement,
not a cache-integrity failure.

[inventory.json](inventory.json) contains the full source accounting. The pipeline input is
`selected-inventory-corrected.json`; every row has `ready: true`, `split: evaluation`, source
hashes, cache binding, and sample rate. `manifest.json` contains the pose-bearing pipeline
rows, and `snapshot-authority.json` is the sanitized bank authority. The initially emitted
versions are preserved as `initial-inventory.json`, `initial-manifest.json`, and
`initial-snapshot-authority.json`; `selected-inventory.json` is also retained unchanged.
The snapshot digest is read separately from a named, hash-bound historical analysis receipt
for each session. The builder verifies each receipt's session, cache, input-manifest, and
analysis-manifest binding, then asserts that all four independently recorded snapshot digests
agree. The receipt paths and SHA-256 values are stored in `inventory.json`; no residual or
score field participates in selection. The next preparation may make temporal 60/20/20 partitions internally,
but the confirmation panel remains a four-record evaluation macro-panel. No numerical
reanalysis, RF collection, or raw-IQ access occurred during this inventory.

## Reproduction

Run `build_inventory.py` from the repository root. It reads only the named JSON inventories,
their pose manifests, the frozen pilot partitions, the DS7 manifest, and the local derived
cache bytes for SHA-256 verification. It does not deserialize candidates or inspect outcomes.
