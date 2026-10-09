# Complete raw receipt archive

Archiving began only after both numerical workers exited successfully and all
148 members had terminal receipts. Every receipt was checked against the frozen
protocol and member identity; completed raw attempts match their terminal copies.
All original local files remain intact.

| Contents | Count |
|---|---:|
| Complete member results | 148 |
| Complete independently qualified fits | 592 |
| Failed/unqualified fits | 0 / 0 |
| Controller launch and exit receipts | 296 |
| Total archived files | 1,036 |

The deterministic gzip/tar archive is **151,736,346 bytes** (144.71 MiB). Its
SHA256 is `4a94157a98bd275c5ce3c96c5603ee87ce8bfc03d8e447fe31d343b08cb14d98`.
It binds protocol SHA256
`97a5a9338773e7ec675986b19c3bccffac199f281b09d5560baa2ca783615ce3`.
Because the archive exceeds the predeclared 90 MiB threshold, four parts of at
most 40 MiB are available for publication. The full local archive is retained.

[The manifest](results-receipts-manifest.json) records every file's byte count
and SHA256, the archive digest and all four part digests. Restore using:

```sh
python reports/2026_10_09_position_error_iter106/unpack_results.py DESTINATION
```

The unpacker accepts the full archive or reconstructs it from its verified parts.
It verifies all members before writing, rejects links and path traversal, and
never overwrites a differing file. Existing identical files are reusable.

[Verification](result-archive-verification.json) confirms a fresh restore of
all 1,036 files from the parts, identical reuse from the full archive, rejection
of a deliberately conflicting restored file, and unchanged hashes for every
original local receipt. Verification used a temporary destination, removed after
the checks; it did not modify original scientific outputs.

These are integrity and coverage checks. They establish neither position
improvement nor generalization; those conclusions belong to the separate
evaluation report.
