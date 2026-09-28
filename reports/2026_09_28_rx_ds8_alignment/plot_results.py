"""Plot full-panel DS8 alignment summaries without case selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.results.read_text())
    aggregate = document["aggregate_equal_record"]
    fig, axes_grid = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    axes = axes_grid.flat
    roles = ("reception", "held_frequency")
    x = np.arange(2)
    for threshold, offset in ((500, -0.18), (1500, 0.18)):
        for receiver, hatch in (("rx0", ""), ("rx1", "//")):
            values = [
                aggregate["roles"][role]["metrics"][f"{receiver}_within_{threshold}hz"]
                for role in roles
            ]
            dx = offset + (-0.08 if receiver == "rx0" else 0.08)
            axes[0].bar(
                x + dx, values, width=0.15, hatch=hatch, label=f"{receiver.upper()} ≤{threshold} Hz"
            )
    axes[0].set_title("Prior-weighted receiver alignment")
    axes[0].set_xticks(x, ("reception", "held period"))
    axes[0].set_ylabel("prior-weighted alignment fraction")
    axes[0].legend(frameon=False, fontsize=8)

    states = ("both", "rx0_only", "rx1_only", "neither")
    colors = ("#228833", "#4477AA", "#CC6677", "#BBBBBB")
    bottom = np.zeros(2)
    for state, color in zip(states, colors, strict=True):
        values = np.array(
            [aggregate["roles"][role]["metrics"][f"paired_1500hz_{state}"] for role in roles]
        )
        axes[1].bar(x, values, bottom=bottom, color=color, label=state.replace("_", " "))
        bottom += values
    axes[1].set_title("Paired alignment states, 1500 Hz")
    axes[1].set_xticks(x, ("reception", "held period"))
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("prior-weighted state fraction")
    axes[1].legend(frameon=False, fontsize=8)

    bins = ("0-30", "30-60", "60-90", "90+")
    support_labels = []
    for role in ("reception", "held_frequency"):
        for receiver, marker in (("rx0", "o"), ("rx1", "s")):
            xs, ys = [], []
            for index, label in enumerate(bins):
                row = aggregate["elapsed_bins"].get(f"{role}:{label}")
                if row:
                    xs.append(index)
                    ys.append(row["metrics"][f"{receiver}_within_1500hz"])
            axes[2].scatter(
                xs,
                ys,
                marker=marker,
                label=f"{role.replace('_', ' ')} {receiver.upper()}",
            )
        for label in bins:
            row = aggregate["elapsed_bins"].get(f"{role}:{label}")
            if row:
                prefix = "rec" if role == "reception" else "held"
                support_labels.append(
                    f"{prefix} {label}: {row['records']} records / {row['windows']} windows"
                )
    axes[2].set_title("Alignment by lane elapsed bin, 1500 Hz")
    axes[2].set_xticks(range(4), bins)
    axes[2].set_xlabel("seconds from lane's first reception window")
    axes[2].legend(frameon=False, fontsize=8)
    axes[2].text(
        0.02,
        0.98,
        "Bin support\n" + "\n".join(support_labels),
        transform=axes[2].transAxes,
        va="top",
        fontsize=7.5,
        bbox={"facecolor": "white", "edgecolor": "0.8", "alpha": 0.9},
    )

    width = 0.22
    availability = axes[3]
    availability_metrics = (
        ("rx0_observed", "RX0 observed", "#4477AA"),
        ("rx1_observed", "RX1 observed", "#CC6677"),
        ("prior_weighted_visible", "prior-weighted visible", "#228833"),
    )
    for index, (metric, label, color) in enumerate(availability_metrics):
        values = [aggregate["roles"][role]["metrics"][metric] for role in roles]
        availability.bar(x + (index - 1) * width, values, width=width, color=color, label=label)
    availability.set_title("Candidate availability and nominee visibility")
    availability.set_xticks(x, ("reception", "held period"))
    availability.set_ylabel("equal-record fraction")
    availability.legend(frameon=False, fontsize=8)
    for ax in axes:
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color="0.9")
    fig.suptitle("DS8 prior-weighted forecast alignment — all four recordings")
    fig.savefig(args.output.with_suffix(".png"), dpi=180)
    fig.savefig(args.output.with_suffix(".svg"))
    plt.close(fig)


if __name__ == "__main__":
    main()
