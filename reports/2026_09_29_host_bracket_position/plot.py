"""Plot every planned panel with audit failures visibly distinguished."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "summary.json").read_text())["rows"]
x = np.arange(len(rows))
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, layout="constrained")
axes[0].bar(
    x - 0.17,
    [r.get("baseline_error_m", np.nan) / 1000 for r in rows],
    0.34,
    label="Free timing baseline",
    color="#607c8e",
)
bars = axes[0].bar(
    x + 0.17,
    [r.get("error_m", np.nan) / 1000 for r in rows],
    0.34,
    label="Shared bias + capture brackets",
    color="#c88c32",
)
for bar, r in zip(bars, rows, strict=True):
    if not r["audited"]:
        bar.set_hatch("//")
axes[0].axhline(1, color="black", ls="--", lw=1)
axes[0].set_ylabel("Error to exposed reference (km)")
axes[0].legend()
axes[1].bar(x, [r.get("held_change_nats", np.nan) for r in rows], color="#607c8e")
axes[1].axhline(0, color="black", lw=1)
axes[1].set_ylabel("Held log-score change (nats)")
axes[1].set_xticks(
    x, [r["unit"].replace("_8", "").replace("_", " ") for r in rows], rotation=30, ha="right"
)
fig.suptitle("Eight-scan panels: capture-bracket timing sensitivity")
fig.savefig(HERE / "comparison.png", dpi=160)
