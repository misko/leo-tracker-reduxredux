# Source snapshot archive

`source-inputs.tar.gz` preserves all2,345 raw source files: `source-snapshot.json`, `source-preflight.json` and2,343 checkpoint-value JSONs. Raw local files remain unchanged. Archive size is14,969,677bytes; SHA256 is `437a1a2bc876b138e318162a1c7d5a9b063a979314ab342fe8921e7794c697df`.

`source-inputs-manifest.json` records every uncompressed file hash and size. Archive creation fixes gzip/tar timestamps, names and modes and verifies each member by readback against the raw source. Re-running `archive_sources.py` refuses a differing existing archive or manifest.

To restore beside the driver after cloning the published report:

```sh
.venv/bin/python reports/2026_10_09_position_error_iter105/unpack_sources.py reports/2026_10_09_position_error_iter105
```

The restore utility verifies the archive digest, exact membership, per-file digest and size before writes. It rejects absolute/traversal paths, links, duplicate names and mismatching existing files. Matching existing files are verified and left untouched. Fresh extraction, matching-file reuse and conflicting-file refusal were tested in a temporary directory; all2,345 members passed. No production or QNAP paths are written.

These are source-integrity checks, not model-compatibility or accuracy validation. Driver preflight must still verify numerical input/model/bank identity and freeze any explicit compatible key mapping before reuse. The archive contains only the five development pilot members; reserve recordings remain closed.
