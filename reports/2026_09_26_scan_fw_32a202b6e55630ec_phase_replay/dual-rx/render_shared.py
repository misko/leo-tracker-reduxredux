"""Render compact historical shared-residual control comparisons."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
data = json.loads((HERE / "method21-22-shared-residual.json").read_text())
durations = (23, 47, 95)

fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), constrained_layout=True)
for label, key in (
    ("exact", "exact"),
    ("RX1 +4093 samples", "wrong_rx_time_4093_samples"),
    ("20 ms recurrence", "wrong_time_20ms"),
):
    values = []
    for duration in durations:
        rows = [
            row
            for row in data["primary_rows"]
            if row["split"] == "evaluation" and row["duration_ms"] == duration
        ]
        values.append(np.median([row[key]["resultant_length"] for row in rows]))
    axes[0].plot(durations, values, marker="o", label=label)
axes[0].set(
    xlabel="window (ms)",
    ylabel="median frame resultant",
    ylim=(0, 1),
    title="Primary dual-RX phase",
)
axes[0].legend(fontsize=8)

width = 5
for offset, (label, key) in enumerate(
    (
        ("exact", "double_difference_rad"),
        ("RX1 +4093", "wrong_rx_time_double_difference_rad"),
        ("20 ms", "wrong_time_double_difference_rad"),
    )
):
    values = []
    for duration in durations:
        phases = np.asarray(
            [row[key] for row in data["two_mode_rows"] if row["duration_ms"] == duration]
        )
        values.append(abs(np.mean(np.exp(1j * phases))))
    axes[1].bar(
        np.asarray(durations) + (offset - 1) * width,
        values,
        width=width,
        label=label,
    )
axes[1].set(
    xlabel="window (ms)",
    ylabel="double-difference R",
    ylim=(0, 1),
    title="Two-mode diagnostic",
)
axes[1].legend(fontsize=8)
fig.savefig(HERE / "method21-22-shared-residual.png", dpi=170)
