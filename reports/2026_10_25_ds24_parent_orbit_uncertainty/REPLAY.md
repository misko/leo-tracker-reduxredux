This report preserves all new source, tests, protocols, audit receipts, derived
scientific outputs, evaluation tables and reviewed figures. It does not contain
a full historical runtime or scan-input closure. No release assets, IQ payloads
or new recordings are required for the compact report itself.

The larger, repeated numerical JSON checkpoints and NPZ arrays are stored
losslessly in `publication/derived_outputs.tar.xz`. The
[archive inventory](publication/archive_inventory.json) lists every original
relative path, byte count and SHA-256. After checking the archive hash against
that inventory, extract it into a clean copy of this report:

```bash
tar -xJf publication/derived_outputs.tar.xz
```

This restores the original `scientific/arrays`, `scientific/fixed`,
`scientific/fits`, `scientific/fixed_summary.json` and
`scientific/fits_summary.json` paths. The published seal files retain their
original absolute research paths; resolve study-owned paths relative to this
report when verifying the restored copy. The
[restore receipt](publication/restore_receipt.json) records an independent clean
extraction and comparison of every member. Restoration validates saved bytes;
it is not numerical replay or proof of an independently reproducible environment.

[publication_manifest.json](publication_manifest.json) covers the compact Git
files, excluding itself. It preserves exact frozen scientific bytes. The raw
numerical archive contains those newly derived research results, including
duplicated producer summaries; it does not duplicate historical source trees,
banks or raw recordings.

Scientific execution originally used the repository `.venv`, NumPy, SciPy and
Matplotlib, the existing feasible-recovery dependency directory, and imported
research helpers under the paths bound by
[scientific/protocol.json](scientific/protocol.json). It requires the original
DS24 fast-scan inputs for 0010–0013, stored in the shared `ds25-20261024`
research directory, causal histories and complete original accepted-ID ledgers.
Source hashes, scan receipts and exact dependencies remain in that protocol.
Some imported working-tree sources were already dirty; their frozen hashes
identify the actual bytes, and this compact report does not claim to restore
them from a clean repository checkout alone. The original research corpus or
corresponding exact prior archives is needed for numerical replay.

[scientific/REPLAY.md](scientific/REPLAY.md) describes the source APIs, original
test command, checkpoints, caps and immutable execution stages. Its absolute
paths refer to that environment. Re-running any scientific stage would be a new
bounded experiment, not restoration of this report; the original runner refuses
overwriting its outputs. The separately preserved evaluation preparation01 is
superseded by revision02, frozen before fits and before new geography.

The evaluation needs only the restored case result JSONs, the source-frozen
evaluator and seals/release metadata. It uses the predeclared site only to report
errors. The saved evaluation already contains all 40 rows and full precision;
reproduction must not choose a new endpoint or qualification view. The
coordinator independently checked all distances and exact fallback outputs.
`evaluation/figures.py` renders the saved sealed tables using Matplotlib and
NumPy, with no propagation or position fitting. Library/font changes may alter
rendered bytes; the committed PNG/PDF artifacts are the reviewed versions.
