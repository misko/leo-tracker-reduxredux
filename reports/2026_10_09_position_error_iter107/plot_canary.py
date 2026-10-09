"""Plot the fixed first-four runtime check; not a full-census accuracy report."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "coverage-report.json").read_text())
labels = ["DS16-001", "DS17-001", "DS18-001", "POST18-NEWER-20261009-001"]
rows = [next(row for row in data["members"] if row["label"] == label) for label in labels]
assert all(row["paired_terminal"] for row in rows)
fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
for axis, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
    x = np.arange(4)
    for offset, phase, color in ((-.18, "baseline", "#506b83"), (.18, "candidate", "#319b83")):
        axis.bar(x + offset, [r["arms"][arm][phase]["error_km"] for r in rows],
                 width=.34, color=color, label=phase)
    axis.set_xticks(x, ["DS16-001", "DS17-001", "DS18-001", "Newer-001"], rotation=20)
    axis.set(title=arm, ylabel="Position error (km)")
    axis.legend(frameon=False)
fig.suptitle("First four metadata-ordered checks: zero recovery triggers; all results unchanged\n"
             "Consumed development only; 189 members still pending")
fig.savefig(HERE / "canary.png", dpi=170)
