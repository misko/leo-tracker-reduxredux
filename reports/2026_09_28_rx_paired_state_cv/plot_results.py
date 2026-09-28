"""Plot model and control differences, retaining every recording point."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / "results-summary.json").read_text())
    labels = ("O-reference", "U-P", "O-U", "O-P", "O-swap", "O-reverse", "O-permute")
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    for axis, role, title in zip(
        axes, ("reception", "held_frequency"), ("Reception", "Later held windows"), strict=True
    ):
        values = summary["roles"][role]
        positions = np.arange(len(labels))
        axis.bar(
            positions,
            [values[label]["mean"] for label in labels],
            color=["#466985", "#39988a", "#39988a", "#39988a", "#d7a547", "#d7a547", "#d7a547"],
            alpha=0.85,
        )
        for position, label in enumerate(labels):
            axis.scatter(
                position + np.linspace(-0.22, 0.22, 6),
                values[label]["per_record"],
                s=24,
                facecolors="white",
                edgecolors="#263238",
                zorder=3,
            )
        axis.axhline(0, color="#263238", linewidth=0.8)
        axis.set_xticks(positions, [label.replace("-", " − ") for label in labels])
        axis.set_ylabel("log score / window")
        axis.set_title(title, loc="left")
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    figure.suptitle("Joint receiver-state prediction: six-record development CV")
    figure.supxlabel(
        "Bars: equal-record means. Points: omitted recordings. Positive favors left model."
    )
    figure.savefig(HERE / "paired_state_cv.png", dpi=170)
    figure.savefig(HERE / "paired_state_cv.svg")
    plt.close(figure)


if __name__ == "__main__":
    main()
