# Cross-rate phase evidence

See the [association and motion report](../../2026_09_23_phase_association_and_motion.md).

`selection.json` freezes five pre-rotation scans and two strongest paired-margin
dwells per available RF channel. The 2.5 MS/s replay is reused from
`../2026_09_23_scan_1aa_phase_methods/comparison.json`; the two high-rate scans
without pairs remain in the inventory and have empty replay results.

Large JSON evidence is preserved as gzip files, with hashes in
`artifact-manifest.json`. `summarize.py` reads plain or compressed evidence and
recreates the two PNGs, summary, per-dwell tables and parity receipt using only
NumPy/Matplotlib and local evidence. It does not read IQ or production storage.

```sh
python summarize.py
```

Numerical replay requires the original host's saved scans and a compatible
production Python environment. `inventory.py` uses read-only storage adapters.
`replay.py` imports the published scan-1aa runner and its declared same-repository
research modules. `matched_duration.py` reuses the numerical implementations,
verifies identical IQ hashes, and changes FFT duration. Source digests accompany
each replay. No production storage is written.

To reconstruct the ignored uncompressed JSON before rerunning numerical stages:

```python
import gzip
from pathlib import Path
for path in Path('.').rglob('*.json.gz'):
    target = path.with_suffix('')
    if not target.exists():
        target.write_bytes(gzip.decompress(path.read_bytes()))
```

The new full-method replays used a combined 600-second wall-clock limit and
finished in about 428 seconds; the equal-duration ablation used a 240-second
limit and finished in 21 seconds. The 2.5 MS/s input was not recollected or
reselected. Individual replay checkpoints duplicate the full comparison documents
and are not committed separately. Statistical support gates are heuristic; no
named-satellite truth, geometric calibration, or orbit/speed estimate is claimed.
