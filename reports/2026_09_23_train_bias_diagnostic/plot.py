#!/usr/bin/env python3
"""Render exact TRAIN block deletion displacements from sealed JSON."""

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "results/inference.json"
OUTPUT = HERE / "block_displacements.png"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


data = json.loads(SOURCE.read_text())
fig, axis = plt.subplots(figsize=(6.4, 5.2))
colors = {1: "#2864a8", 2: "#d45d35"}
for row in data["blocks"]:
    east = 1000 * row["east_displacement_km"]
    north = 1000 * row["north_displacement_km"]
    axis.arrow(
        0, 0, east, north, color=colors[row["group"]], alpha=0.72,
        length_includes_head=True, head_width=13,
    )
    label = row["block_id"].replace("group", "G").replace("_block", "-")
    axis.text(east, north, label, fontsize=8)
for group in (1, 2):
    east, north = data["summary"][f"group{group}_mean_displacement_en_km"]
    axis.scatter(
        1000 * east, 1000 * north, marker="X", s=100, color=colors[group],
        label=f"Group {group} mean",
    )
axis.axhline(0, color="0.7", linewidth=0.8)
axis.axvline(0, color="0.7", linewidth=0.8)
axis.set_aspect("equal", adjustable="datalim")
axis.set_xlabel("Leave-block-out east displacement (m)")
axis.set_ylabel("Leave-block-out north displacement (m)")
axis.set_title("Pooled TRAIN solution sensitivity to block deletion")
axis.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUTPUT, dpi=180)
plt.close(fig)
(HERE / "render_manifest.json").write_text(
    json.dumps(
        {"source": digest(SOURCE), "renderer": digest(Path(__file__)), "output": digest(OUTPUT)},
        indent=2,
        sort_keys=True,
    ) + "\n"
)
