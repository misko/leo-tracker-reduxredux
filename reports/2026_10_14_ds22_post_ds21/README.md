# DS22: all recordings after DS21

Minted **137 whole recordings: 69 fast and 68 adaptive**, preserving both
receivers. All 137 are complete in the observed metadata snapshot. They contain
**611,967 retained windows/visits** and reference **750,250,564,801 bytes
(750.25 GB)** of compressed IQ in place.

| Property | Frozen value |
|---|---|
| Parent capture-start boundary, exclusive | October 12, 2026, 9:15:15.466427639 p.m. PDT |
| Capture-start cutoff, inclusive | October 14, 2026, 7:34:20.030821438 a.m. PDT |
| UTC start | 2026-10-13T04:15:15.466427639Z |
| UTC cutoff | 2026-10-14T14:34:20.030821438Z |
| Membership | DS22-001 through DS22-137, ordered by acquisition start |
| Complete / incomplete | 137 / 0 |
| Fast recordings with pinned tracking inputs | 68 of 69 |
| Index-digest / payload-size integrity errors | 0 |
| Admission gates | No channel-count, signal-quality, analysis-readiness or position gate |

The authority is [local/manifest.json](local/manifest.json), protected by
[local/seal.json](local/seal.json). Manifest SHA-256:
`705380facbea54e6a1142eab07f1114f7ae99d3066e4f8bd9210cb55014768f3`.
[verification.json](verification.json) records the reconciled counts and final
verification. Metadata snapshots are local and Git-ignored; IQ remains in its
original locations.

DS21's full seal was verified before minting. Its exact manifest and digest are
copied into DS22. The prior dataset is unchanged. DS22 admits acquisitions
starting strictly after DS21's frozen cutoff, through the first inventory
timestamp of this request. It preserves whole recordings and checks raw-content
disjointness from DS21; recordings crossing the lower boundary are not sliced.

Discovery uses the same raw roots as DS21, including new `fast8-*` siblings,
and the adaptive, scanner, hop, native, conventional recording and firmware-spool
namespaces. The legacy census checked 9,521 manifests without read or timing
errors. Duplicate copies are collapsed by raw content identity. Discovery is
limited to those enumerated roots; it is not an exhaustive search of unrelated
archives or QNAP, and unmanifested acquisitions have no assigned identity.

Source manifests and available fast input/tracking documents are copied and
sealed. Adaptive manifests preserve receipt, timing, acquisition settings,
receiver identities and chunk digests. Adaptive analysis availability remains
explicitly unassessed; its analysis products were not copied. All 137 assigned
members must remain in evaluation coverage even when analysis is unavailable.
No training/validation split or claim of previously unseen data is implied.

Fast index bytes were rehashed and compressed payload sizes checked for both
formats. Payload hashes are pinned from manifests, not freshly rehashed. The
metadata/analysis snapshot reflects inventory observation after the frozen
capture-start cutoff. It is not an atomic storage snapshot or retention hold.

## Verification

```bash
.venv/bin/pytest -q reports/2026_10_14_ds22_post_ds21/test_mint.py
.venv/bin/ruff check reports/2026_10_14_ds22_post_ds21
python3 reports/2026_10_14_ds22_post_ds21/mint.py verify \
  --output reports/2026_10_14_ds22_post_ds21/local
```

Four offline tests, lint and final seal/count/disjointness verification pass.
The mint reuses DS21's collector, freezes its own source and tests, and refuses
to overwrite an existing dataset. No RF capture or re-analysis was initiated.
