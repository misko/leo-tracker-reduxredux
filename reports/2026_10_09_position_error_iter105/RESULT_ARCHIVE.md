# Complete pilot receipt archive

All395 baseline, candidate, stage and slice receipts are preserved locally and in a deterministic gzip/tar archive. Archive size is224,669,581bytes; SHA256 is `beadb0d7e0c1897e8c800efdd9446fc78fe6dd42acf7b0392a731898083a5f42`.

For repository publication the archive is split into six deterministic parts, each at most40MiB, named `results-receipts.tar.gz.part000` through `part005`. Publish those parts and `results-receipts-manifest.json`; the full archive and every raw receipt remain local. The manifest records archive SHA256, part hashes and sizes, every uncompressed file hash and size, protocol identity and successful archive readback against original bytes.

Restore from a fresh clone:

```sh
.venv/bin/python reports/2026_10_09_position_error_iter105/unpack_results.py reports/2026_10_09_position_error_iter105
```

When the full archive is absent, the utility verifies each published part and reassembles into a temporary archive. It verifies the whole digest, exact membership, payload hashes and sizes before writes. Paths, links and duplicate entries are checked; matching existing receipts remain untouched and conflicting files cause refusal. No production or QNAP files are written.

Raw receipt preservation and full archive readback were verified. Multipart fresh extraction, matching-existing reuse and conflict refusal all passed in a temporary directory. `result-archive-verification.json` records those checks; all395 original receipt hashes and all six part hashes were also rechecked. These checks verify receipt integrity; they do not change or qualify scientific outcomes.
