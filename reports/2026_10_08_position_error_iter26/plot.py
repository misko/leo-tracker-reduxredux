"""Visualize the reserved metadata-only random assignment."""

import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "newer-random-split.json").read_text())
fig, ax = plt.subplots(figsize=(10, 3), layout="constrained")
for row in data["captures"]:
    time = datetime.fromtimestamp(row["capture_start_utc_ns"] / 1e9, UTC)
    group = row["group"]
    y = int(group == "validation")
    ax.scatter(time, y, s=90, color="tab:orange" if y else "tab:blue")
    ax.annotate(row["label"], (time, y), xytext=(0, 12), textcoords="offset points", ha="center")
ax.set_yticks([0, 1], ["Development, unopened", "Validation, unopened"])
ax.set(
    ylim=(-0.5, 1.5),
    xlabel="Capture start (UTC)",
    title=f"Whole-scan random assignment; PCG64 seed {data['seed']}",
)
ax.grid(alpha=0.2)
fig.savefig(HERE / "assignments.png", dpi=160)
