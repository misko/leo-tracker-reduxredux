"""Plot the measured time and geographic error of the same complete receiver run."""

import matplotlib

from ..__main__ import save_json
from ..scoring import ARMS
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402


def draw(out, rows, labels):
    styles = (("#30395c", "o"), ("#b46113", "s"), ("#427881", "^"), ("#007d66", "D"))
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.8), sharey=True, sharex=True)
    handles = []
    for arm, ax in zip(ARMS, axes, strict=True):
        ax.axvspan(0, 1, color="#f3f6f6", zorder=0)
        ax.axvline(1, color="#646c74", linewidth=1)
        ax.axhline(1.10, color="#646c74", linestyle="--", linewidth=1)
        for (method, label), (color, marker) in zip(labels.items(), styles, strict=True):
            data = [
                r
                for r in rows
                if r["arm"] == arm
                and r["method"] == method
                and r["service_over_span"] is not None
                and r["error_km"] is not None
                and r["baseline_km"] is not None
                and r["baseline_km"] > 0
            ]
            dots = ax.scatter(
                [r["service_over_span"] for r in data],
                [r["error_km"] / r["baseline_km"] for r in data],
                color=color,
                marker=marker,
                alpha=0.82,
                s=39,
                edgecolors="white",
                linewidths=0.55,
                label=f"{label} ({len(data)})",
            )
            if ax is axes[0]:
                handles.append(dots)
        ax.set_title("Zero calibration" if arm == "c0" else "Fitted calibration", loc="left")
        ax.set_xlabel("Complete host replay time / recorded duration")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}×"))
        ax.grid(axis="both", color="#dfE5E8", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_xlim(left=0)
    axes[0].set_ylabel("Position error / original v5 error")
    axes[0].set_ylim(bottom=0)
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}×"))
    fig.subplots_adjust(left=0.085, right=0.985, bottom=0.21, top=0.75, wspace=0.10)
    fig.suptitle(
        "Position error and processing time on the same recording",
        x=0.045,
        y=0.975,
        ha="left",
        fontsize=19,
        weight="bold",
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.037, 0.917),
        ncol=4,
        frameon=False,
        fontsize=10,
    )
    fig.text(
        0.045,
        0.066,
        "Left of the vertical line, replay finished within the recorded duration. "
        "Below the dashed line, position error met the +10% allowance.",
        fontsize=10,
    )
    fig.text(
        0.045,
        0.023,
        "Each dot requires a recorded raw-to-position time and a published fix. "
        "Core assignments varied across archived runs.",
        fontsize=10,
    )
    fig.savefig(out / "budget.png", dpi=145)
    fig.savefig(out / "budget.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    files = ("accuracy-and-time.csv", "budget.png", "budget.pdf")
    save_json(
        out / "budget-figure-lock.json", dict(files={name: _sha(out / name) for name in files})
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="one-lane-time-and-accuracy",
            title="Geographic error and complete replay time",
            sample="22 roof recordings with method-specific raw clock availability",
            boundary="Unpaced saved-I/Q replay through both calibrated position decisions",
            note="Reconstructed detector inputs have no complete host replay clock. "
            "Dots use original no-repair v5 as the geographic reference.",
            seal="budget-figure-lock.json",
            csv="accuracy-and-time.csv",
            image="budget.png",
            pdf="budget.pdf",
        ),
    )
