#!/usr/bin/env python3
"""Render held-out coverage and paced-worker measurements without reclassifying RF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def render(holdout, runs, output):
    if any(
        Path(output).resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")
    ):
        raise ValueError("figure cannot be written beneath archive storage")
    if Path(output).exists():
        raise FileExistsError(output)
    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8), layout="constrained")
    colors = ("#2376a5", "#d57826")
    for i, (rate, label, color) in enumerate(
        zip((2500000, 5000000), ("2.5 MS/s", "5 MS/s"), colors, strict=True)
    ):
        metrics = holdout["rates"][str(rate)]
        matched = [metrics[k]["reference_associated"] for k in ("first_window", "all_windows")]
        positive = [metrics[k]["reference_positive"] for k in ("first_window", "all_windows")]
        x = np.arange(2) + (i - 0.5) * 0.34
        values = 100 * np.asarray(matched) / positive
        axes[0].bar(x, values, 0.32, color=color, label=label)
        for xx, yy, n, d in zip(x, values, matched, positive, strict=True):
            axes[0].text(xx, yy + 2, f"{n}/{d}", ha="center", fontsize=10)
        schedules = metrics["temporal_schedules"]
        denominator = schedules[0]["reference_positive_visits_anywhere"]
        observed = [s["native_reference_associated_at_scheduled_windows"] for s in schedules]
        ceiling = [s["reference_seen_at_scheduled_windows"] for s in schedules]
        axes[1].plot(
            range(3), 100 * np.asarray(observed) / denominator, "o-", color=color, label=label
        )
        axes[1].plot(range(3), 100 * np.asarray(ceiling) / denominator, ":", color=color, alpha=0.7)
        for xx, n in enumerate(observed):
            axes[1].annotate(
                f"{n}/{denominator}",
                (xx, 100 * n / denominator),
                xytext=(0, 10 if i == 0 else -17),
                textcoords="offset points",
                ha="center",
                fontsize=10,
                color=color,
            )
        run = runs[str(rate)]
        if not run["all_outputs_match_desktop"] or run["terminal"]["duration_ms"] != 300000:
            raise ValueError("figure requires verified 300 s runs")
        keys = ("total_cpu_ms", "total_wall_ms", "delivery_latency_ms")
        x = np.arange(3) + (i - 0.5) * 0.34
        axes[2].bar(x, [run["timings"][k]["p99"] for k in keys], 0.32, color=color, label=label)
        axes[2].scatter(x, [run["timings"][k]["max"] for k in keys], marker="x", color=color)
    axes[0].set(
        xticks=range(2),
        xticklabels=["First 20 ms", "All six windows"],
        ylim=(0, 114),
        ylabel="Reference-positive probes associated (%)",
        title="Within-probe agreement\nNot independent Starlink truth",
    )
    axes[1].set(
        xticks=range(3),
        xticklabels=["0", "0, 40, 100", "0, 20, …, 100"],
        ylim=(0, 114),
        xlabel="Checked 20 ms probe offsets (ms)",
        ylabel="Reference-positive visits recovered (%)",
        title="Temporal coverage\nDotted: dense-reference sampling ceiling",
    )
    axes[2].set(
        xticks=range(3),
        xticklabels=["Detector CPU", "Detector wall", "Copy → delivery"],
        ylabel="Milliseconds",
        title="300 s repeated-probe ARM load\nBars: p99; ×: maximum",
    )
    axes[2].axhline(126, color="#555555", linestyle=":", label="126 ms arrivals")
    axes[2].plot([-0.35, 0.35], [100, 100], color="#222222", linewidth=2, label="100 ms CPU target")
    for axis in axes:
        axis.grid(axis="y", alpha=0.15)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(fontsize=8, loc="lower left")
    figure.suptitle(
        "Single-RX ARM candidate evidence: coverage and scheduling are separate gates", fontsize=15
    )
    figure.savefig(output, dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(
        json.loads((args.evidence / "holdout-summary.json").read_text()),
        {
            str(rate): json.loads((args.evidence / f"paced-{rate}-summary.json").read_text())
            for rate in (2500000, 5000000)
        },
        args.output,
    )


if __name__ == "__main__":
    main()
