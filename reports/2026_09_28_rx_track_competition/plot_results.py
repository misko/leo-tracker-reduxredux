"""Plot full-population predictive support and optimistic competition ceilings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

MODES = (
    ("frozen_prior_weighted", "frozen prior-weighted", "#4477AA"),
    ("optimistic_track_conditional_max", "optimistic track max", "#EE7733"),
    ("any_nominee_ceiling", "optimistic any nominee", "#228833"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--ds8", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pilot, ds8 = json.loads(args.pilot.read_text()), json.loads(args.ds8.read_text())
    populations = (
        ("pilot cal", pilot, "calibration"),
        ("pilot eval", pilot, "evaluation"),
        ("DS8 eval", ds8, "evaluation"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    x = np.arange(6)
    labels = [
        f"{name}\n{role.replace('_', ' ')}"
        for name, _, _ in populations
        for role in ("reception", "held_frequency")
    ]
    for ax, (receiver, threshold) in zip(
        axes.flat, (("rx0", 500), ("rx1", 500), ("rx0", 1500), ("rx1", 1500)), strict=True
    ):
        for offset, (prefix, label, color) in zip((-0.22, 0, 0.22), MODES, strict=True):
            values = []
            for _, document, split in populations:
                for role in ("reception", "held_frequency"):
                    values.append(
                        document["aggregate_equal_record_by_split"][split][role]["metrics"][
                            f"{prefix}_{receiver}_within_{threshold}hz"
                        ]
                    )
            ax.bar(x + offset, values, width=0.21, color=color, label=label)
        ax.set_title(f"{receiver.upper()} within {threshold} Hz")
        ax.set_xticks(x, labels, rotation=25, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.set_ylabel("equal-record compatibility fraction")
        ax.grid(axis="y", color="0.9")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Frozen forecast compatibility and optimistic track ceilings")
    fig.text(
        0.5,
        0.005,
        "Optimistic ceilings use observed outcomes and are not predictive scores "
        "or deployable models.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(args.output.with_suffix(".png"), dpi=180, bbox_inches="tight")
    fig.savefig(args.output.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
