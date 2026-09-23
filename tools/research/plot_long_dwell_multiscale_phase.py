"""Plot cached 105915 multiscale phase rows without reading IQ."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_long_dwell_multiscale_phase"


def main() -> None:
    document = json.loads((DIRECTORY / "results.json").read_text())
    durations = (600, 300, 150, 120, 60, 20)
    figure, axes = plt.subplots(
        2, 3, figsize=(13, 8), sharex=True, sharey=True, layout="constrained"
    )
    for axis, duration in zip(axes.ravel(), durations, strict=True):
        rows = [row for row in document["rows"] if row["duration_ms"] == duration]
        reference = sorted({(row["center_s"], row["reference_phase_rad"]) for row in rows})
        axis.plot(
            [row[0] for row in reference],
            np.degrees([row[1] for row in reference]),
            "k--",
            linewidth=1.5,
            label="retained 20 ms reference",
        )
        for mode, marker, color in (
            ("frozen_timing", "o", "tab:blue"),
            ("local_timing", "s", "tab:orange"),
        ):
            selected = sorted(
                (row for row in rows if row["mode"] == mode), key=lambda row: row["center_s"]
            )
            axis.scatter(
                [row["center_s"] for row in selected],
                np.degrees([row["double_difference_rad"] for row in selected]),
                marker=marker,
                color=color,
                label=mode.replace("_", " "),
            )
        axis.set_title(f"{duration} ms independent chunks")
        axis.set_ylim(-180, 180)
        axis.grid(alpha=0.2)
    for axis in axes[-1]:
        axis.set_xlabel("Capture time (s)")
    for axis in axes[:, 0]:
        axis.set_ylabel("Restored held DD phase (deg)")
    axes[0, 0].legend(fontsize=8)
    figure.suptitle("105915 phase recovery from independently processed chunks")
    figure.savefig(DIRECTORY / "phase-recovery-by-duration.png", dpi=160)


if __name__ == "__main__":
    main()
