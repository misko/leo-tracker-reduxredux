"""Draw the matched published times and horizontal errors on four original DS30 packets."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def draw(result, output):
    cases = {row["case"]: row for row in [*result["development"], result["challenge"]]}
    rows = [
        cases[case] for case in ("DS30-0316", "DS30-0160", "DS30-0155", "DS30-0402")
    ]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.9), sharey=True)
    fig.subplots_adjust(left=0.14, right=0.985, top=0.75, bottom=0.19, wspace=0.18)
    colors = {"stock": "#324d70", "cumulative": "#00846c"}
    titles = [
        "Saved detections through exit",
        "Fixed-zero position error",
        "Fitted position error",
    ]
    for ax, metric, title in zip(
        axes, ("elapsed", "c0", "fitted_c"), titles, strict=True
    ):
        for y, row in enumerate(rows):
            values = (
                row["saved_elapsed_s"]
                if metric == "elapsed"
                else {
                    mode: arm[metric]
                    for mode, arm in row["horizontal_errors_km"].items()
                }
            )
            if all(values.get(k) is not None for k in colors):
                ax.plot(
                    [values["stock"], values["cumulative"]],
                    [y, y],
                    color="#a2acb0",
                    lw=2,
                )
            for mode, color in colors.items():
                if values.get(mode) is not None:
                    ax.plot(
                        values[mode],
                        y,
                        marker="o" if mode == "stock" else "D",
                        color=color,
                        markersize=7 if mode == "stock" else 5.5,
                    )
        ax.set_title(title, fontsize=11, loc="left", fontweight="bold")
        ax.set_xlabel("Seconds" if metric == "elapsed" else "Kilometers")
        ax.set_xlim(left=0)
        ax.grid(axis="x", color="#e1e7e7")
        ax.tick_params(length=0, pad=5)
        ax.spines[:].set_visible(False)
    error_max = max(axes[1].get_xlim()[1], axes[2].get_xlim()[1])
    for ax in axes[1:]:
        ax.set_xlim(0, error_max)
    axes[0].set_yticks(range(len(rows)), [r["case"] for r in rows])
    axes[0].set_ylim(len(rows) - 0.55, -0.45)
    fig.suptitle(
        "Same detector measurements, different position solvers",
        ha="left",
        x=0.025,
        y=0.995,
        fontsize=15,
        fontweight="bold",
    )
    fig.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                color=colors["stock"],
                label="Original ALGO08v3",
            ),
            Line2D(
                [],
                [],
                marker="D",
                ls="",
                color=colors["cumulative"],
                label="Cumulative candidate",
            ),
        ],
        loc="upper left",
        bbox_to_anchor=(0.015, 0.915),
        frameon=False,
        ncol=2,
        fontsize=9,
    )
    fig.savefig(output, dpi=155, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("png", type=Path)
    args = parser.parse_args()
    draw(json.loads(args.receipt.read_text()), args.png)
