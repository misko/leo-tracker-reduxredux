# DS5 causal cached-tracking sequences

`cases.json` freezes four 64-visit, dual-receiver blocks for causal acquisition,
cache-hit, fallback, and reacquisition experiments. Load each visit with NumPy and
process a block strictly by `block_offset`:

```python
import json
from pathlib import Path
import numpy as np

root = Path("reports/2026_09_27_ds5_cached_tracking/dataset")
dataset = json.loads((root / "cases.json").read_text())
block = sorted(
    (case for case in dataset["cases"] if case["block_id"] == "dev-r2500000-lower"),
    key=lambda case: case["block_offset"],
)
iq = np.load(root / block[0]["raw_npy"]["path"], allow_pickle=False)
# axes: sample, receiver (RX0/RX1), component (I/Q)
```

Development contains exposed 2.5 and 5 MS/s sessions extended around the prior
suite's eight-visit cuts. Fresh holdout contains new 2.5 and 5 MS/s sessions and
excludes all 12 sessions from the prior suite and both earlier speed-probe sessions.
Selection used source metadata and hashes only; real cases remain unlabeled and the
manifest contains no detector outcomes.

The `stress_protocol` keeps source IQ intact. The primary state policy has a 2.0 s
maximum age. Its 0.5 s short-age sensitivity, state drops, four-visit processing
outage, and wrong-channel cache remap are independent replay policies. Evaluators
must never manufacture replacement samples or update state from a skipped visit.
The all-visits primary replay remains the comparison baseline.

Development and holdout each cover both rates and both edges, although each rate
appears on only one edge per split. A block spans only 7.68 seconds and cannot
qualify long-duration drift, rare false alarms, deployment p99, or cross-session
state continuity.

Rebuild from the read-only archive in at most three minutes:

```sh
.venv/bin/python reports/2026_09_27_ds5_cached_tracking/dataset/build_dataset.py \
  --deadline-seconds 180
```

The builder verifies the source dataset manifest, wrapped recording manifests,
compressed chunks, decompressed CI16 payloads, and generated NumPy files. It writes
only beneath this directory and enforces a 1.2 GB hard cap.
