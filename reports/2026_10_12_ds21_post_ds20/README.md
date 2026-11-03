# DS21: all recordings after DS20

Minted **108 whole recordings: 54 fast and 54 adaptive**, with both receivers
preserved. All 108 are complete in the observed metadata snapshot. They contain
**484,405 retained windows/visits** and reference **585,316,039,024 bytes
(585.32 GB)** of compressed IQ in place.

| Property | Frozen value |
|---|---|
| Parent boundary, exclusive | October 11, 2026, 5:39:36.533236621 p.m. PDT |
| Capture-start cutoff, inclusive | October 12, 2026, 9:15:15.466427639 p.m. PDT |
| UTC start | 2026-10-12T00:39:36.533236621Z |
| UTC cutoff | 2026-10-13T04:15:15.466427639Z |
| Membership | DS21-001 through DS21-108, ordered by acquisition start |
| Complete / incomplete recordings | 108 / 0 |
| Fast recordings with pinned tracking inputs | 53 of 54 |
| Index-digest / payload-size integrity errors | 0 |
| Admission gates | No channel-count, GLRT-quality, analysis-readiness or position gate |

The authority is [local/manifest.json](local/manifest.json), protected by
[local/seal.json](local/seal.json). Manifest SHA-256:
`b3316e1bad03b902d3c742ef65e5f83c083b832193aaf6566fdd2d89448c6b58`.
[verification.json](verification.json) records the reconciled counts and seal
verification. The 1.3 GB metadata snapshot is local and Git-ignored.

DS20 froze 18 acquisitions qualified by eight-channel GLRT evidence, from a
broader historical inventory. DS21 starts after DS20's frozen **inventory
cutoff**, rather than the last qualified acquisition. It does not re-admit
older DS20 exclusions. The exact parent manifest and its digest are copied into
the new snapshot; DS20 is unchanged. Disjointness is checked by acquisition
start and raw content identity.

Discovery covers DS20's ten raw roots and newly discovered `fast8-*` sibling
collections on NVMe and bulk storage. It also checks the published adaptive,
scanner, hop, native and conventional recording namespaces, and firmware spool.
The legacy census checked 9,453 manifests and found 54 newer adaptive recordings.
Fast raw copies are deduplicated by IQ/index digest sets; adaptive copies use
compressed/uncompressed chunk digest sets. Whole recordings are retained: a
recording starting before the boundary is not sliced into DS21.

Source manifests and available fast input/tracking documents are copied and
sealed. Adaptive recording manifests retain acquisition settings, receiver
identities, timing, receipt and chunk hashes. Adaptive analysis products were
not inventoried or copied; their analysis availability is explicitly marked
unassessed. Missing analysis must remain visible during evaluation, and all
108 members must stay in coverage accounting. This mint defines no scientific
training/validation split and makes no claim that these recordings are unseen.

Index bytes were rehashed for fast captures; compressed payload sizes were
checked for both formats. IQ hashes are pinned from source manifests; payloads
were neither copied nor rehashed. The cutoff was frozen at the first inventory
timestamp for this request; metadata/analysis availability reflects the later
inventory observation. This is not an atomic storage snapshot or a retention
hold. Discovery is limited to the enumerated recording roots; it does not claim
an exhaustive search of unrelated archives or QNAP. Unmanifested acquisitions
have no assigned member identity in this snapshot.

## Verification

```bash
.venv/bin/pytest -q reports/2026_10_12_ds21_post_ds20/test_mint.py
.venv/bin/ruff check reports/2026_10_12_ds21_post_ds20
python3 reports/2026_10_12_ds21_post_ds20/mint.py verify \
  --output reports/2026_10_12_ds21_post_ds20/local
```

All four offline tests, lint, and final seal/count verification pass. The mint
refuses to overwrite an existing snapshot. It adapts DS20's existing metadata
collector and adds whole-recording boundary checks and adaptive-format handling.
No RF collection or re-analysis was started.
