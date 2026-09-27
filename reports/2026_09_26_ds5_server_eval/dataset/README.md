# DS5 server-evaluation dataset

`cases.json` is the public, outcome-free dataset contract. Each real case is one
120 ms visit with RX0 and RX1 grouped in one NumPy array. Load a case with:

```python
import json
from pathlib import Path
import numpy as np

root = Path("reports/2026_09_26_ds5_server_eval/dataset")
manifest = json.loads((root / "cases.json").read_text())
case = next(c for c in manifest["cases"] if c["split"] == "dev")
iq = np.load(root / case["raw_npy"]["path"], allow_pickle=False)
# iq.dtype == np.dtype("<i2")
# iq.shape == (case["rate_hz"] * 120 // 1000, 2, 2)
# axes: sample, receiver (RX0/RX1), component (I/Q)
```

The real cases are unlabeled. A baseline positive is reference-relative evidence,
not ground truth; a baseline miss is not a negative. Detector outcomes are kept
outside this directory, especially for holdout. Synthetic pilot, noise, and tone
controls have deterministic construction truth, but they are smoke controls rather
than false-alarm or RF-specificity calibration.

The 96 real visits comprise eight consecutive visits for every rate in every split.
Sessions are disjoint across development, validation, and holdout. Every split has
all four rates, both edges, all four target channels, and both receivers. The 24
synthetic controls cross all four rates with pilot/noise/tone and lower/upper
edge strata in a separate `control` split. Every control receiver and rate has a
distinct deterministic seed.

Rate and edge are not fully crossed: each split has one single-edge session for
each rate, balanced to two lower-edge and two upper-edge rate blocks. A block is
only eight visits (0.96 seconds of valid IQ), so it cannot measure long-track
continuity, rare-event behavior, or deployment p99 latency. `coverage_audit` in
`cases.json` lists every observed and missing rate/edge pair explicitly.

Rebuild in at most five minutes with the workspace environment:

```sh
.venv/bin/python reports/2026_09_26_ds5_server_eval/dataset/build_dataset.py \
  --deadline-seconds 300
```

The tool reads the source archive with `sudo -n cat`, verifies the frozen recording
manifest plus compressed and uncompressed chunk hashes, and only writes beneath
this dataset directory. It never writes to the archive and never opens radio
hardware.
