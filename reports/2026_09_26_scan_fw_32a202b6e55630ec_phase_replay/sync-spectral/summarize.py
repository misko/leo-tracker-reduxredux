#!/usr/bin/env python3
"""Summarize split-safe spectral replay and render bandwidth-bin increments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def run(source: Path, output: Path) -> None:
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    complete = [row for row in rows if row["status"] == "complete"]
    fields = (
        "direct_fft_parseval_rms_rad",
        "random_train_r",
        "random_held_r",
        "forward_train_r",
        "forward_held_r",
        "derived_2p5_random_train_r",
        "derived_2p5_random_held_r",
        "derived_2p5_forward_train_r",
        "derived_2p5_forward_held_r",
    )
    summary = {
        "total": len(rows),
        "complete": len(complete),
        "unsupported": len(rows) - len(complete),
    }
    for split in ("development", "evaluation"):
        chosen = [row for row in complete if row["split"] == split]
        summary[split] = {"complete": len(chosen)}
        for field in fields:
            summary[split][f"median_{field}"] = (
                float(np.median([row[field] for row in chosen])) if chosen else None
            )
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    widths = sorted({float(key) for row in complete for key in row["bandwidth_phase_r"]})
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for split, color in (("development", "#4477aa"), ("evaluation", "#cc6677")):
        chosen = [row for row in complete if row["split"] == split]
        medians = [
            np.median([row["bandwidth_phase_r"][str(int(width))] for row in chosen])
            for width in widths
        ]
        ax.plot(
            np.asarray(widths) / 1e6,
            medians,
            marker="o",
            label=f"{split} (n={len(chosen)})",
            color=color,
        )
    ax.set(xlabel="retained common FFT bandwidth (MHz)", ylabel="median phase concentration R")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output.with_suffix(".png"), dpi=160)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
