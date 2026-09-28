"""Visualize held gains alongside fixed-anchor shift bias."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "scores.json").read_text())["summaries"]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
for i, (method, label, color) in enumerate(
    (
        ("acquisition_broad", "Acquisition + broad", "#51758c"),
        ("acquisition_broad_null", "Acquisition + broad + null", "#d3992e"),
    )
):
    selected = [r for r in rows if r["method"] == method]
    x = np.arange(3) + (i - 0.5) * 0.36
    axes[0].bar(
        x, [r["gain_vs_acquisition"] for r in selected], width=0.34, label=label, color=color
    )
    axes[1].bar(x, [r["max_reliable_shift_error_hz"] for r in selected], width=0.34, color=color)
for ax in axes:
    ax.set_xticks(range(3), ["DS7-001", "DS8-001", "DS9-001"])
axes[0].axhline(0, color="black", linewidth=0.8)
axes[0].set_ylabel("Held gain vs acquisition (nats/frame)")
axes[0].legend(loc="upper left", fontsize=9)
axes[1].set_yscale("log")
axes[1].axhline(5, color="black", linestyle=":", label="5 Hz gate")
axes[1].set_ylabel("Maximum shift error in model-reliable pairs (Hz)")
axes[1].legend()
fig.suptitle("An acquisition point mass reduces held loss but introduces residual-shift bias")
fig.savefig(HERE / "acquisition-mixture.png", dpi=160)
fig.savefig(HERE / "acquisition-mixture.svg")
