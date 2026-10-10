The deterministic [results-summary.tar.gz](results-summary.tar.gz) retains every raw receipt and SUMMARY.json; originals remain on disk. Size: 48,696,537 bytes. SHA256: `a9f85a94ca2949701e1b2f0f92070df763ad574429d71ef9dd753e43f9031a8b`. [RESULT_ARCHIVE.json](RESULT_ARCHIVE.json) gives per-file sizes and hashes; fresh extraction verified all members.

Restore from the repository root into a fresh directory:

```sh
PYTHONPATH=src:. python3 reports/2026_10_10_position_error_iter150/archive_results.py --restore-to /tmp/iteration150-restored
```

Archive and extracted hashes are checked; unsafe paths and differing existing files are rejected. No model or reference calls occur. Protocol file SHA256 is `8a63f6c53bdf47bf931e61356c251228f4dd587ba184ec38940a4a623f12e6e9`; the distinct canonical receipt digest is stored in the archive manifest.
