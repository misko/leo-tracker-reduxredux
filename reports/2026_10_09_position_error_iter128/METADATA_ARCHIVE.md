# Verified metadata archive

`metadata.tar.gz` contains 27 files: the authoritative inventory, resource
receipt, and all metadata preparation receipts, including the earlier explicit
failures. Originals remain on disk; only the inventory selects authoritative
per-member metadata. Uncompressed total71,162,571 bytes, archive11,130,498 bytes.
SHA256 `d30773fc614ecca2b309d7a74f87281975d4f1e2b4358769a6104b48a9c07e67`.
`METADATA_ARCHIVE.json` lists every file size and digest.

Every decompressed member was verified against its original digest. The safe
unpacker was exercised into a fresh temporary directory (27 files), repeated
without rewriting matching files (27), and rejected an intentionally conflicting
inventory. It checks the archive digest, complete allowed membership, content
digests, regular files, safe relative paths and no symlink destinations before
writing anything. No extraction into the corpus and no IQ reads occurred.

Restore metadata after checkout with
`PYTHONPATH=src:.:reports/2026_10_09_position_error_iter128 python reports/2026_10_09_position_error_iter128/unpack_metadata.py`.
Use the production Python environment with NumPy, since common helpers import
the evaluation module. The archive is deterministic (zero timestamps/owners).

Public capture-manifest inspection found maximum uncompressed chunks2.4MB at
2.5MS/s and9.6MB at10MS/s. All twelve are below the32MiB visit and64MiB chunk
guards; these are allocation checks, not a total process memory bound.
