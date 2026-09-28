"""Plot frozen-prediction transfer and descriptive residual slopes."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "diagnostics.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
panels = data["chronological_panels"]
axes[0].bar(np.arange(1, 12), [p["joint_minus_independent_held"] for p in panels], color="#4e7998")
axes[0].axhline(0, color="black", linewidth=0.8)
axes[0].set(
    xlabel="Chronological eight-record panel",
    ylabel="Held log score: joint − independent",
    title="Shared-position fit loses held density",
)
axes[0].set_xticks(np.arange(1, 12))
axes[0].text(
    0.02,
    0.03,
    "Panel 8: 7 qualified controls; all panels retain 8 joint records",
    transform=axes[0].transAxes,
    fontsize=8,
)
groups = data["receiver_channel_slopes"]
offsets = {(0, 1): (6, 12), (0, 3): (-62, 8), (1, 4): (10, -16)}
for row in groups:
    x, y = [row[role + "_slope_hz_per_normalized_recording"] for role in ("training", "held")]
    axes[1].scatter(x, y, s=40)
    axes[1].annotate(
        f"RX{row['receiver_id']} ch{row['channel']}",
        (x, y),
        fontsize=8,
        xytext=offsets.get((row["receiver_id"], row["channel"]), (4, 4)),
        textcoords="offset points",
    )
axes[1].plot([-3500, 0], [-3500, 0], linestyle="--", color="grey", linewidth=0.8)
axes[1].set(
    xlabel="Training slope (Hz / normalized recording)",
    ylabel="Held slope (Hz / normalized recording)",
    title="Descriptive slopes; no correction fitted",
)
fig.savefig(HERE / "residual_transfer.png", dpi=170)
fig.savefig(HERE / "residual_transfer.svg")
