The deterministic [results-summary.tar.gz](results-summary.tar.gz) retains the full terminal raw receipts and SUMMARY.json. Original files remain on disk. The archive is 24,366,085 bytes; SHA256 `2b3be4f0af061d9016c39d70ddcf73ed3fc03183364a72056eaca91c2648e383`. [RESULT_ARCHIVE.json](RESULT_ARCHIVE.json) records every file's size and SHA256; fresh extraction verified all members.

From the repository root, restore into a fresh directory:

```sh
PYTHONPATH=src:. python3 reports/2026_10_10_position_error_iter149/archive_results.py --restore-to /tmp/iteration149-restored
```

Archive and extracted file hashes are checked, unsafe paths are rejected, and differing existing files are never overwritten. This performs no numerical work or reference lookup.

Protocol file bytes SHA256: `1b06e34a631e53caac522a30cc7119609f798f0c922ccd0be7584700731042fc`. Receipts bind its distinct canonical JSON digest: `sha256:b541cc0fa6b56cc6acf94dc1a1a9fe0d03563d7ba3b166acb2e6531c262537a8`.
