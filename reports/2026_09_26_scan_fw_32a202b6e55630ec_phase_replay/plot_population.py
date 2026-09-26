"""Render audited acquisition population; no IQ or phase estimation is performed."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    root = Path(__file__).resolve().parent
    with (root / "acquisition/visit-inventory.csv").open() as stream:
        visits = list(csv.DictReader(stream))
    selection = json.loads((root / "selection.json").read_text())
    audit = json.loads((root / "capture-audit/capture-audit.json").read_text())
    if len(visits) != audit["visit_count"] or not audit["integrity_all_chunks_ok"]:
        raise ValueError("population figure requires a complete integrity-qualified census")
    origin = audit["device_counter_origin"]
    times = np.array([(int(v["valid_start_counter"]) - origin) / 1e7 for v in visits])
    channels = np.array([int(v["channel"]) for v in visits])
    rx0 = np.array([v["rx0_passed"] == "True" for v in visits])
    rx1 = np.array([v["rx1_passed"] == "True" for v in visits])
    category = rx0.astype(int) + 2 * rx1.astype(int)
    colors = ["#c9cdd1", "#e49c45", "#4c9ac5", "#267252"]
    labels = ["Neither RX", "RX0 only", "RX1 only", "Both RX"]
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)
    for code, color, label in zip(range(4), colors, labels, strict=True):
        mask = category == code
        axes[0].scatter(
            times[mask],
            channels[mask],
            s=12,
            color=color,
            label=f"{label}: {int(mask.sum()):,}",
            alpha=0.85,
        )
    axes[0].set(
        yticks=range(1, 5),
        ylabel="Upper-edge channel",
        xlim=(0, 300),
        title="Corrected sparse GLRT census · all 2,214 dwells",
    )
    axes[0].legend(ncols=4, loc="upper center", bbox_to_anchor=(0.5, 1.25), frameon=False)
    axes[0].axvline(75, color="#463b68", linestyle="--", linewidth=1)
    axes[0].set_xlabel("Device time from session origin (s)")
    left = np.zeros(4)
    for code, color, label in zip(range(4), colors, labels, strict=True):
        counts = np.array([np.sum((channels == ch) & (category == code)) for ch in range(1, 5)])
        axes[1].barh(range(1, 5), counts, left=left, color=color, label=label)
        for channel, width, start in zip(range(1, 5), counts, left, strict=True):
            if width > 20:
                axes[1].text(
                    start + width / 2,
                    channel,
                    str(width),
                    ha="center",
                    va="center",
                    color="white" if code == 3 else "#20242a",
                    fontsize=10,
                )
        left += counts
    axes[1].set(
        yticks=range(1, 5),
        ylabel="Upper-edge channel",
        xlabel="Dwell count",
        title="Availability is reported before any phase selection",
    )
    by_visit = {int(v["visit_index"]): v for v in visits}
    counts = np.zeros((2, 4), dtype=int)
    for item in selection["visits"]:
        v = by_visit[item["visit_index"]]
        code = int(v["rx0_passed"] == "True") + 2 * int(v["rx1_passed"] == "True")
        counts[int(item["split"] == "evaluation"), code] += 1
    bottom = np.zeros(2)
    for code, color, _label in zip(range(4), colors, labels, strict=True):
        axes[2].bar([0, 1], counts[:, code], bottom=bottom, color=color)
        for index in range(2):
            if counts[index, code] >= 6:
                axes[2].text(
                    index,
                    bottom[index] + counts[index, code] / 2,
                    str(counts[index, code]),
                    ha="center",
                    va="center",
                    color="white" if code == 3 else "#20242a",
                )
        bottom += counts[:, code]
    axes[2].set(
        xticks=[0, 1],
        xticklabels=["Development: 32 dwells", "Evaluation: 96 dwells"],
        ylabel="Dwell count",
        title="Frozen 128-dwell cohort includes weak and negative acquisitions",
    )
    fig.suptitle("scan-fw-32a202b6e55630ec · 10 MS/s · simultaneous RX0/RX1", fontsize=15)
    fig.supxlabel(
        "GLRT gate 0.025; first 20 ms per 120 ms dwell. "
        "Both-RX passage is not phase lock or emitter identity.",
        fontsize=10,
    )
    for extension in ("png", "svg"):
        fig.savefig(root / f"population-overview.{extension}", dpi=150)


if __name__ == "__main__":
    main()
