"""Render the committed adaptive GLRT replay summary."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "2026_09_25_glrt_tuning_recovery.json").read_text())
rows = DATA["visits"]
visits = [str(row["visit"]) for row in rows]
x = np.arange(len(rows))
threshold = DATA["threshold"]

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(8.4, 4.6), constrained_layout=True)
width = 0.34
before = [row["rx0_before"] for row in rows]
after = [row["rx0_after"] for row in rows]
ax.bar(x - width / 2, before, width, label="Before: DC-centred acquisition", color="#8f9aaa")
ax.bar(x + width / 2, after, width, label="After: capture-aware acquisition", color="#167d65")
ax.axhline(threshold, color="#b23a48", linestyle="--", linewidth=1.5, label="GLRT gate 0.025")
for index, values in enumerate((before, after)):
    offset = -width / 2 if index == 0 else width / 2
    for xi, value in zip(x, values, strict=True):
        ax.text(xi + offset, value + 0.014, f"{value:.3f}", ha="center", va="bottom", fontsize=9)
ax.set(
    title="10 MS/s RX0 GLRT recovery",
    xlabel="Retained visit",
    ylabel="Fractional exact − control margin",
)
ax.set_xticks(x, visits)
ax.set_ylim(0, 0.66)
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
fig.savefig(ROOT / "2026_09_25_glrt_tuning_recovery.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8.4, 4.6), constrained_layout=True)
old_min, old_max = -400_000, 400_000
nominal = -312_500
new_min, new_max = nominal - 800_000, nominal + 800_000
ax.axvspan(old_min / 1000, old_max / 1000, color="#8f9aaa", alpha=0.22, label="Old search")
ax.axvspan(
    new_min / 1000, new_max / 1000, color="#167d65", alpha=0.18, label="Capture-aware search"
)
for index, row in enumerate(rows):
    y = index + 1
    ax.scatter(row["rx0_cfo_hz"] / 1000, y, marker="o", s=65, color="#167d65")
    ax.scatter(row["rx1_cfo_hz"] / 1000, y, marker="^", s=70, color="#7357a5")
    ax.text(row["rx0_cfo_hz"] / 1000 - 18, y + 0.13, "RX0", ha="right", fontsize=9)
    ax.text(row["rx1_cfo_hz"] / 1000 + 18, y + 0.13, "RX1", ha="left", fontsize=9)
ax.axvline(
    nominal / 1000,
    color="#167d65",
    linestyle="--",
    linewidth=1.4,
    label="Nominal pilot at −312.5 kHz",
)
ax.set(
    title="Why the old acquisition missed RX0",
    xlabel="Pilot centre in captured baseband (kHz)",
    ylabel="Retained visit",
)
ax.set_yticks(range(1, len(rows) + 1), visits)
ax.set_xlim(-1200, 850)
ax.set_ylim(0.4, len(rows) + 0.7)
ax.legend(frameon=False, loc="upper right")
fig.savefig(ROOT / "2026_09_25_glrt_search_geometry.png", dpi=180)
plt.close(fig)
