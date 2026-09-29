# Lean publication protocol

Do not run `publish.py` while benchmarks or cohort evaluations are active. The
experiment owner runs it once all selected manifests are complete, with an
existing isolated checkout as the destination:

```sh
python3 reports/2026_09_29_arm_subsecond/publish.py /path/to/isolated-checkout
cd /path/to/isolated-checkout
python3 reports/2026_09_29_arm_subsecond/verify_publication.py
```

The helper copies top-level source, test, build, audit, README, and JSON files
plus completed manifests, summaries, audits, exact `build-receipt.json` or
`build.json` receipts, unit results, qualification records, and collectors. It never copies row
files, IQ, NumPy arrays, binaries, `__pycache__`, incomplete cohort evidence, or
expanded build-source trees.

Before packing, every source hash declared by a receipt is checked against its
original file. Receipt commands are preserved byte-for-byte in the copied JSON.
Declared source sets are archived once by canonical content hash in
`source-archives/`; `publication-index.json` maps each original receipt and
source path to its hash and archive. To reproduce a build, unpack its mapped
archive into a scratch directory and apply the exact command from the receipt,
replacing only the recorded original source/output directory prefix and making
the external compiler/FFTW dependencies available.

Any receipt with missing or mismatched declared sources aborts publication.
The destination is treated as disposable staging: before copying, the helper
removes only the enumerated experiment directories beneath `DEST/reports` so
stale binaries or row files cannot survive a prior run. No other destination
paths are removed.
