import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
doc = json.loads((HERE / "results.json").read_text())
for path, digest in doc["hashes"].items():
    assert hashlib.sha256((HERE.parent.parent / path).read_bytes()).hexdigest() == digest
rows = doc["rows"]
assert len({(r["unit_id"], r["session_id"], r["track_id"], r["number"]) for r in rows}) == 3983
out = {}
for label in ["all", "DS7", "DS8", "DS9"] + sorted({r["unit_id"] for r in rows}):
    subset = [r for r in rows if label == "all" or r["unit_id"].startswith(label)]
    out[label] = {}
    for population in ("all", "changed"):
        selected = [r for r in subset if population == "all" or r["changed"]]
        arms = {}
        for arm in ("fitted", "older", "extrapolate"):
            g = np.asarray([r["zero"] - r[arm] for r in selected])
            arms[arm] = dict(
                wins=int((g > 1e-6).sum()),
                losses=int((g < -1e-6).sum()),
                median_gain_hz=float(np.median(g)) if len(g) else None,
                mean_gain_hz=float(np.mean(g)) if len(g) else None,
            )
        out[label][population] = dict(cases=len(selected), **arms)
(HERE / "summary.json").write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
for label in out:
    print(label, out[label]["changed"]["cases"], out[label]["changed"]["fitted"])
