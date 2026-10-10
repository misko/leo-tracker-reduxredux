The deterministic [results-summary.tar.gz](results-summary.tar.gz) contains all 84 raw JSON receipts and SUMMARY.json. Originals remain on disk. The archive is 23,802,752 bytes; its SHA256 is `88402f2f57a76e1e548e80cb9e24bc1d9918819a4f471e6c49ce657e24850bef`. [RESULT_ARCHIVE.json](RESULT_ARCHIVE.json) records every member's size and SHA256. Creation verified a fresh extraction against this manifest.

From the repository root, restore into a fresh directory:

```sh
PYTHONPATH=src:. python3 reports/2026_10_10_position_error_iter148/archive_results.py --restore-to /tmp/iteration148-restored
```

The helper verifies the archive and every extracted file, rejects unsafe paths, and refuses to overwrite differing existing files. Restored files retain the relative paths `results/…` and `SUMMARY.json`; no numerical work or reference lookup is performed.

The protocol **file bytes** have SHA256 `d7a7bec07697c851933341abdabb15c578984d3ae96b9d22c05fc78f16f667f0`. Receipts instead bind the protocol's **canonical JSON digest**, `sha256:70b70caaad3eff6f371dc6006f3f2312d524a424a357e9cace9dadaddac21f10`. These are distinct, verified identities.
