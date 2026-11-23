"""Draw complete and censored clocks and position changes on the three transfer controls."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def draw():
    diagnostic = json.loads((DATA / "short-raw-diagnostic.json").read_bytes())
    selection = json.loads((DATA / "bidirectional-selection.json").read_bytes())
    fig, (time_axis, error_axis) = plt.subplots(1, 2, figsize=(11.5, 3.6))
    fig.subplots_adjust(left=0.105, right=0.97, top=0.79, bottom=0.25, wspace=0.48)
    colors = ("#415b7c", "#178374")
    for i, case in enumerate(diagnostic["cases"]):
        for arm, offset, color in zip(("stock", "candidate"), (0.13, -0.13), colors, strict=True):
            run = case["runs"][arm]
            censored = run.get("elapsed_censored_at_s")
            elapsed = censored or run["elapsed_s"]
            label = (
                ("ALGO08v3" if arm == "stock" else "Short receiver + solver") if i == 0 else None
            )
            time_axis.barh(
                1 - i + offset,
                elapsed,
                color=color,
                height=0.22,
                label=label,
                alpha=0.5 if censored else 1,
            )
            if censored:
                time_axis.annotate(
                    "timeout",
                    (elapsed, 1 - i + offset),
                    (4, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8,
                )
    time_axis.set(
        xlim=(0, 180),
        ylim=(-0.5, 1.5),
        yticks=[1, 0],
        yticklabels=[r["case"] for r in diagnostic["cases"]],
        xlabel="Raw input to process exit (seconds)",
    )
    time_axis.set_title("Two physical DS30 recordings", loc="left", fontweight="bold")
    for arm, offset, color, label in zip(
        ("c0", "fitted_c"),
        (0.09, -0.09),
        colors,
        ("Fixed-zero calibration", "Fitted calibration"),
        strict=True,
    ):
        ordered = [selection[k] for k in ("north", "south-inside", "physical")]
        xs = [row["score"]["arms"][arm]["delta_error_km"] * 1000 for row in ordered]
        error_axis.scatter(xs, [2 - i + offset for i in range(3)], color=color, label=label, s=36)
    error_axis.axvline(0, color="#666", lw=0.9)
    error_axis.axvline(250, color="#963a29", ls="--", lw=1)
    error_axis.annotate("250 m limit", (250, -.42), xytext=(-4, 1), textcoords="offset points",
                        ha="right", fontsize=8, color="#963a29")
    error_axis.set(
        yticks=[2, 1, 0],
        yticklabels=["North simulation", "South simulation", "DS30-0016"],
        ylim=(-0.5, 2.5),
        xlabel="Change in horizontal error relative to v3 (m)",
    )
    error_axis.set_title("Earlier or later frequency support", loc="left", fontweight="bold")
    for ax in (time_axis, error_axis):
        ax.grid(axis="x", alpha=0.17)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.legend(
            loc="upper center", bbox_to_anchor=(0.5, -0.29), ncol=2, fontsize=8, frameon=False
        )
    fig.savefig(HERE / "development/short-subset-transfer.png", dpi=165, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    draw()
