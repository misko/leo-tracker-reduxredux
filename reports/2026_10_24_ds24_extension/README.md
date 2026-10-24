# DS24 revision 2: all 10 MS/s scans through October 24

DS24 now contains **103 complete acquisitions: 34 fast and 69 adaptive**. This adds **84 acquisitions** to the original 19: 15 newer fast scans and 69 adaptive scans. The user's updated scope is all 10 MS/s scans; adaptive acquisitions are therefore included, including eligible ones within the original time window.

The acquisition-start window is **[2026-10-21 23:42:37 UTC, 2026-10-24 14:38:14 UTC)**. In Pacific time, the endpoint is **October 24, 2026, 7:38:14 a.m. PDT**. The original lower boundary is retained rather than rolling the dataset forward to a new 48-hour window. Whole acquisitions are included by their start, without selecting on signal quality, analysis readiness or localization outcome.

## Membership and continuity

| Item | Count |
|---|---:|
| Original members retained with identical IDs | 19 |
| Newly admitted fast acquisitions | 15 |
| Newly admitted adaptive acquisitions | 69 |
| Total acquisitions | 103 |
| Complete / incomplete acquisitions | 103 / 0 |
| Recorded windows or retained adaptive visits | 379,526 |
| Referenced compressed IQ bytes | 1,366,219,031,599 |
| Integrity errors detected | 0 |

DS24-0001 through DS24-0019 preserve their original labels, content identities and acquisition times. Newly admitted acquisitions receive DS24-0020 through DS24-0103 in acquisition order. Because adaptive acquisitions were previously outside DS24's fast-only scope, label order across the entire revised dataset is not chronological. Use each member's `captured_utc_ns` for time ordering.

The latest included fast acquisition starts at 2026-10-24 14:31:54 UTC; the latest adaptive acquisition starts at 14:06:45 UTC. Discovery checks the existing fast roots and the adaptive/legacy roots listed in the manifest. Storage copies are deduplicated by recorded content hashes. Fifty-six in-window fast roots and 19 adaptive manifests have 2.5 MS/s capture metadata and are excluded. Device restoration settings are not used as capture sample rates.

The original [DS24 report and manifest](../2026_10_23_ds24_fast10m/README.md) remain unchanged. This is a separately sealed membership revision. [parent-manifest.json](parent-manifest.json) preserves the exact original manifest and its hash is bound into the revised authority. Existing numerical results remain results for the original eight evaluated scans; this update does not recalculate position errors.

## Authorities and verification

The complete authority is [manifest.json.gz](manifest.json.gz), a lossless gzip of the local `manifest.json`. Compression is needed because the full authority, including per-chunk IQ provenance, exceeds GitHub's individual-file limit. The SHA-256 in [manifest.sha256](manifest.sha256) applies to the **decompressed bytes**. [membership-summary.json](membership-summary.json) is a convenient compact scan listing, not a replacement for the full authority. [evaluation-units.json](evaluation-units.json) binds all 103 case IDs to that authority.

The local full snapshot is `/srv/bulk/leo/research/ds24-20261024-extension/manifest.json`. [seal.json](seal.json) binds the inventory, parent authority, verification and source files. To verify the published capsule, decompress `manifest.json.gz` to `manifest.json` before checking the seal. [publication.json](publication.json) separately pins the compressed file and its decompressed hash.

The inventory checks source manifest hashes, fast index hashes, payload sizes and recording completion metadata. Selected manifests and analysis-input hashes are rechecked after enumeration. IQ payloads are referenced in place and are not fully rehashed or copied. The filesystem census is not atomic. This revision is frozen at the stated cutoff and does not automatically ingest later captures.

Twenty-four fast scans have discoverable published tracking-input contracts at this snapshot. Adaptive analysis readiness is **not inventoried** by this metadata extension, so the remaining 79 must not be described as 79 failed or unavailable analyses. No upstream GLRT processing or localization rerun was launched for this membership update.

Three owned tests cover stable labels when an earlier adaptive scan is admitted, rejection of missing or changed original identities, and capture-rate extraction that ignores restored radio settings and detects conflicting capture rates. All pass. The final audit verifies unique identities, the frozen time interval, all 103 rates, original labels and identity retention, source hashes, summary counts, and lossless publication compression.

## Reproduction

`extend.py` uses the pinned inventory helpers in `support/`. It refuses to overwrite a completed revision. In a fresh output directory containing those sources and `parent-manifest.json`, run `python -B extend.py --cutoff-ns 1792852694000000000` with read access to the corpus. It performs metadata reads only. Run `python -B -m pytest -q -p no:cacheprovider test_extend.py` for the owned tests.

Rerunning at a later time may discover migrated or newly published inputs; the sealed artifacts here, rather than a later enumeration, define revision 2.
