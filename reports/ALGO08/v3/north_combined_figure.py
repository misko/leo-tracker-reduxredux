"""Plot the original published fixes and the two intervening saved-input fits."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def draw():
    def cases(name):
        return json.loads((HERE / "measurements" / name).read_bytes())["cases"]

    measured = cases("north-combined.json")
    diagnoses = cases("north-factor-swap.json")
    corrected = cases("north-causal-transfer.json")
    rows = [
        measured["stock"],
        diagnoses["stock-packet"],
        diagnoses["intersection"],
        measured["containing"],
        corrected["containing"],
    ]
    labels = [
        "Installed v3",
        "New solver, v3 factors",
        "New solver, shared lanes",
        "All short detections",
        "Causal filter, raw input",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.2), sharey=True)
    fig.subplots_adjust(left=0.21, right=0.97, top=0.76, bottom=0.2, wspace=0.26)
    for ax, (field, name, scale) in zip(
        axes,
        (
            ("error_km", "Horizontal error (m)", 1000),
            ("rf_rms_hz", "Frequency residual RMS (Hz)", 1),
        ),
        strict=True,
    ):
        for arm, label, color, offset in (
            ("c0", "Fixed-zero calibration", "#3f577c", 0.1),
            ("fitted_c", "Fitted calibration", "#0a8770", -0.1),
        ):
            xs = [row["score"]["arms"][arm][field] for row in rows]
            ax.scatter(
                [x * scale for x in xs],
                [4 - i + offset for i in range(5)],
                label=label,
                c=color,
                s=33,
            )
        ax.set_yticks([4, 3, 2, 1, 0], labels)
        ax.set_xlabel(name)
        ax.set_xlim(left=0)
        ax.set_ylim(-0.45, 4.45)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.18)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle(
        "Which change moved the northern fix?", x=0.035, ha="left", fontweight="bold", fontsize=15
    )
    fig.legend(
        *axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, frameon=False, fontsize=9
    )
    fig.savefig(HERE / "development/north-factor-transfer.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    draw()
