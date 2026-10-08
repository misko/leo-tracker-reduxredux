"""Render audited coverage with a visible unfilled plus marker."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "audit.json").read_text())
points = data["points"]
xy = np.array([[r["east_km"], r["north_km"]] for r in points])
fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
for ax in axes:
    artist = ax.scatter(xy[:, 0], xy[:, 1], c=[r["rank"] for r in points], cmap="viridis_r", s=15)
    ax.scatter(
        *data["reference_xy_km"], color="black", marker="*", s=140, label="Reference: audit only"
    )
    for sep, marker, color in (("12.5", "s", "red"), ("25", "+", "orange"), ("50", "o", "blue")):
        selected = np.array(
            [[r["east_km"], r["north_km"]] for r in data["retention_simulations"][sep]]
        )
        style = dict(color=color) if marker == "+" else dict(facecolors="none", edgecolors=color)
        ax.scatter(
            selected[:, 0],
            selected[:, 1],
            marker=marker,
            s=100,
            label=f"Separation {sep} km",
            **style,
        )
    ax.set(xlabel="East of prior km", ylabel="North of prior km", aspect="equal")
    ax.grid(alpha=0.2)
axes[0].set_title("All 400 sampled points")
axes[0].legend(fontsize=7)
axes[1].set(xlim=(-115, -65), ylim=(-110, -60), title="Correct region was refined to 5 km")
fig.colorbar(artist, ax=axes, label="Coarse score rank")
fig.savefig(HERE / "coverage.png", dpi=160)
