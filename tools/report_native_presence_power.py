#!/usr/bin/env python3
"""Plot the measured runtime/quality checkpoint; never labels GLRT as signal truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def quality_counts(rows, variant, rate):
    positive = [
        r
        for r in rows
        if r["variant"] == variant and r["result"]["rate_hz"] == rate and r["reference_positive"]
    ]
    return (
        sum(r["matched_reference"] for r in positive),
        sum(r["detected"] and not r["matched_reference"] for r in positive),
        sum(not r["detected"] for r in positive),
    )


def render(directory: Path, output: Path):
    if (
        output.exists()
        or output.resolve().is_relative_to(Path("/mnt/qnap01"))
        or output.resolve().is_relative_to(Path("/srv/bulk/leo"))
    ):
        raise ValueError("new non-archive figure output required")
    runtime = json.loads((directory / "arm-ci16-summary.json").read_text())
    rows = json.loads((directory / "wide-project-v1/results.json").read_text())
    rates = [2500000, 5000000]
    x = np.arange(2)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.9), constrained_layout=True)
    for offset, field, label, color in (
        (-0.18, "total_cpu_ms", "Detector CPU p99", "#207f87"),
        (0.18, "total_wall_ms", "Wall p99", "#659cce"),
    ):
        values = [runtime["rates"][str(r)]["warmed"][field]["p99"] for r in rates]
        bars = axes[0].bar(x + offset, values, width=0.34, label=label, color=color)
        axes[0].bar_label(bars, fmt="%.1f", padding=3)
    axes[0].axhline(100, linestyle="--", color="#a95336", label="100 ms CPU target")
    axes[0].set(title="ARM replay: native CI16 input", ylabel="Milliseconds", ylim=(0, 125))
    axes[0].legend(loc="upper left", fontsize=8)
    counts = np.array([quality_counts(rows, runtime["variant"], r) for r in rates])
    bottom = np.zeros(2)
    for column, label, color in (
        (0, "Reference-associated", "#207f87"),
        (1, "Positive, different CFO/time", "#d9a24a"),
        (2, "No passing evidence", "#a95336"),
    ):
        bars = axes[1].bar(x, counts[:, column], bottom=bottom, color=color, label=label, width=0.6)
        axes[1].bar_label(
            bars,
            labels=[str(n) if n else "" for n in counts[:, column]],
            label_type="center",
            color="white",
            weight="bold",
        )
        bottom += counts[:, column]
    axes[1].set(
        title="Wider scan sample: first 20 ms only",
        ylabel="Reference-positive probes",
        ylim=(0, 16),
    )
    axes[1].legend(loc="upper left", fontsize=8)
    for ax in axes:
        ax.set_xticks(x, ["2.5 MS/s", "5 MS/s"])
        ax.spines[["right", "top"]].set_visible(False)
    fig.suptitle(
        "Single-candidate pilot-power proposal + fractional GLRT\n"
        "Runtime is promising; detection quality is not qualified",
        fontsize=14,
    )
    fig.supxlabel(
        "640 executions of 32 saved probes (19 warmed repeats each); "
        "quality: 80 development probes across two 300 s scans.\n"
        "Not a streaming test. Reference agreement is not verified Starlink truth.",
        fontsize=9,
    )
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.directory, args.output)


if __name__ == "__main__":
    main()
