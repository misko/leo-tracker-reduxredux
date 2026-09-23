#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt

here = Path(__file__).parent
rows = [
    row for row in json.loads((here / "results.json").read_text())["rows"] if "failure" not in row
]
fig, axes = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)
for prior, marker in (("sacramento", "o"), ("reno", "s")):
    selected = sorted(
        (row for row in rows if row["prior"] == prior), key=lambda row: row["view_scan_count"]
    )
    counts = [row["view_scan_count"] for row in selected]
    axes[0].plot(
        counts, [row["reference_error_km"] for row in selected], marker=marker, label=prior
    )
    axes[1].plot(
        counts, [row["held_capped_rms_hz"] for row in selected], marker=marker, label=prior
    )
axes[0].set(xlabel="TEST prefix scans", ylabel="Reference error (km)", yscale="log")
axes[1].set(xlabel="TEST prefix scans", ylabel="Held capped RMS (Hz)")
for axis in axes:
    axis.set_xticks([1, 6, 16])
    axis.grid(alpha=0.3)
    axis.legend()
fig.suptitle("Selected global 0.2 s rule; full 64-scan view failed")
fig.savefig(here / "test_results.png", dpi=180)
