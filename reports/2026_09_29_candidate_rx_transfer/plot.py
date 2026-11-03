"""Validate result bindings and plot matched-control paired gains."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
result = json.loads((HERE / "results.json").read_text())
for path, expected in result["hashes"].items():
    assert hashlib.sha256((HERE.parent.parent / path).read_bytes()).hexdigest() == expected
rows = result["rows"]
assert len({(r["unit_id"], r["track_id"], r["number"]) for r in rows}) == 3983
assert sum(r["candidate_predictor"] is not None for r in rows) == 1847
for r in rows:
    for arm in ("candidate", "other"):
        prediction = r[f"{arm}_predictor"]
        if prediction is None:
            assert r[arm] == r["zero"]
        else:
            assert prediction["donors"]
            for d in prediction["donors"]:
                assert (d["number"] == r["number"]) == (arm == "candidate")
                assert d["track_id"] != r["track_id"]
datasets = ["DS7", "DS8", "DS9"]
fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
for i, (arm, label, color) in enumerate(
    (
        ("candidate", "Same candidate, other RX", "#247b9e"),
        ("other", "Other candidates, other RX", "#b85b45"),
    )
):
    values = []
    for ds in datasets:
        selected = [
            r
            for r in rows
            if r["unit_id"].startswith(ds) and r["candidate_predictor"] and r["other_predictor"]
        ]
        values.append(np.median([r["zero"] - r[arm] for r in selected]))
    ax.bar(np.arange(3) + (i - 0.5) * 0.32, values, 0.32, label=label, color=color)
ax.axhline(0, color="black", lw=0.8)
ax.set_xticks(range(3), ["DS7 (95 cases)", "DS8 (85 cases)", "DS9 (77 cases)"])
ax.set_ylabel("Median paired held-residual reduction (canonical Hz)")
ax.set_title("Same matched targets; positive is better than zero slope")
ax.legend()
fig.savefig(HERE / "matched.png", dpi=160)
print(
    "Verified hashes, membership, candidate separation and fallback identity; "
    "plotted matched targets."
)
