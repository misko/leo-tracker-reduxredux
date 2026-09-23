#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt

root = Path(__file__).parent
data = json.loads((root / "results/results.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
for prior, marker in (("sacramento", "o"), ("reno", "s")):
    rows = [a for a in data["arms"] if a["prior"] == prior]
    for scale in (0.2, 1.0, 5.0):
        selected = [a for a in rows if a["scale_s"] == scale]
        axes[0].plot(
            [a["scan_count"] for a in selected],
            [a["reference_error_km"] for a in selected],
            marker=marker,
            label=f"{prior}, {scale:g} s",
        )
        axes[1].plot(
            [a["scan_count"] for a in selected],
            [a["reserved_capped800_rmse_hz"] for a in selected],
            marker=marker,
            label=f"{prior}, {scale:g} s",
        )
axes[0].set(xlabel="TRAIN scans", ylabel="Post-seal reference error (km)", xscale="log")
axes[1].set(xlabel="TRAIN scans", ylabel="Complementary-row RMS (Hz)", xscale="log")
for axis in axes:
    axis.grid(alpha=0.3)
    axis.set_xticks([6, 16, 72], labels=["6", "16", "72"])
    axis.minorticks_off()
fig.suptitle("One global epoch term · nested TRAIN views · fixed identities", fontsize=11)
axes[1].legend(fontsize=7, ncol=2)
fig.savefig(root / "global_epoch_results.png", dpi=180)
