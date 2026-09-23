#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt

here = Path(__file__).parent
data = json.loads((here / "results.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
for arm in data["arms"]:
    levels, gaps = [], []
    for row in arm["beam_history"]:
        if len(row["beam"]) > 1 and arm["new_evaluation_count_by_level"][str(row["level_km"])] > 0:
            levels.append(row["level_km"])
            gaps.append(row["beam"][1]["objective_rmse_hz"] - row["beam"][0]["objective_rmse_hz"])
    label = f"{arm['group'].replace('_train', '')} {arm['scan_count']} {arm['prior'][0].upper()}"
    axes[0].plot(levels, gaps, marker=".", alpha=0.7, label=label)
axes[0].set(
    xscale="log", yscale="symlog", xlabel="Grid level (km)", ylabel="Second-beam objective gap (Hz)"
)
for row in data["prior_comparisons"]:
    axes[1].scatter(
        row["scan_count"],
        row["coordinate_separation_km"],
        label=f"{row['group'].replace('_train', '')} {row['scan_count']}",
    )
axes[1].set(xlabel="TRAIN scans", ylabel="Sacramento/Reno solution separation (km)", yscale="log")
for axis in axes:
    axis.grid(alpha=0.3)
axes[0].legend(fontsize=6, ncol=2)
fig.savefig(here / "ambiguity.png", dpi=180)
