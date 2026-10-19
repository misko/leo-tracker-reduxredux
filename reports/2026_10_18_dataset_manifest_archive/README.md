# All located DS dataset membership manifests

This directory publishes the **exact original authority bytes** for every located named DS dataset, the DS2-22 revision, the DS3 inference authority, and the new DS23 dataset. No membership was reconstructed from an analysis subset. DS14, DS15 and DS19 remain unlocated and are not fabricated.

The [catalogue](catalogue.json) maps every dataset ID to its original source, uncompressed SHA-256 and length, storage encoding, and the SHA-256/length of each published file. Every archive was decompressed and checked against its original complete authority. These full-byte checks are stronger than the earlier inventory's prefix bindings.

Large authorities are losslessly Zstandard-compressed. Streams larger than 40 MiB are split into ordered parts so every Git object remains below GitHub's per-file limit. The compression changes storage only; decompression recovers the original JSON bytes and original checksum. Existing published manifests and their seals are unchanged. Raw IQ and the many separate analysis snapshots referenced by the manifests are not included.

Examples, from this directory:

```bash
# An uncompressed authority is already usable as JSON.
sha256sum DS7.manifest.json

# A single compressed stream.
zstd -d -c DS22.manifest.json.zst > DS22.manifest.json
sha256sum DS22.manifest.json

# DS23's ordered parts form one compressed stream.
cat DS23.manifest.json.zst.part000 DS23.manifest.json.zst.part001 | zstd -d -c > DS23.manifest.json
sha256sum DS23.manifest.json
```

Compare recovered checksums to `original_sha256` in the catalogue. `tools/archive_dataset_manifests.py` performs this round-trip check automatically and rejects changed parts or a decompressed mismatch.

See the [dataset date inventory](../2026_10_18_ds_dataset_inventory/README.md), [new DS23 membership and sampling protocol](../2026_10_18_ds23_post_ds22/README.md), and [ten-scan phase-refreshed evaluation](../2026_10_18_ds23_phase_refreshed_evaluation/README.md).

The scope is named scientific dataset membership authorities, not every derived report's orbit-bank or analysis-cache manifest. Some source paths in the catalogue are local historical worktrees; the bytes themselves are now available here on remote main.
