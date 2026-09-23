"""Plot the frozen random-holdout CFO and phase-advance comparisons."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports/figures/2026_09_23_longarc_phase"


def main():
    cfo = json.loads((OUTPUT / "evaluation.json").read_text())
    phase = json.loads((OUTPUT / "phase-advances.json").read_text())
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    rows = cfo["held_odd_visits"]
    for name, label, marker in (
        ("archived_glrt", "GLRT trained", "o"),
        ("training_even_pilot", "Pilot CFO trained", "x"),
    ):
        axes[0].plot(
            [row["time_s"] for row in rows],
            [row[f"{name}_mean_residual_hz"] for row in rows],
            marker=marker,
            label=label,
            alpha=0.8,
            linewidth=1,
        )
    axes[0].axhline(0, color="gray", linewidth=0.7)
    axes[0].set(
        xlabel="Time from capture reference (s)",
        ylabel="Mean held CFO residual (Hz)",
        title="Shared residual structure on 36 random held dwells",
    )
    axes[0].legend()
    x = np.arange(len(cfo["candidate_norad"]))
    for shift, key, label in (
        (-0.18, "glrt_model", "GLRT trained"),
        (0.18, "pilot_model", "Pilot CFO trained"),
    ):
        rms = cfo["sigma_hz"] * np.sqrt(cfo[key]["all_training_chi2_per_visit"])
        axes[1].bar(x + shift, rms, 0.36, label=label)
    axes[1].set_xticks(x, [str(value) for value in cfo["candidate_norad"]], rotation=45)
    axes[1].set(
        yscale="log",
        ylabel="Training RMS (Hz; logarithmic)",
        title="Both training arms select NORAD 67330",
    )
    axes[1].legend()
    fig.suptitle("15 MS/s long arc • 42 train / 36 random held dwells • no identity claim")
    fig.savefig(OUTPUT / "cfo-comparison.png", dpi=170)
    plt.close(fig)

    models = phase["models"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.1), layout="constrained")
    labels = ["Constant\nrate"] + [str(model["candidate"]) for model in models[1:]]
    axes[0].plot(
        np.arange(len(models)),
        [model["held_rms_rad"] for model in models],
        "o-",
        label="Correct-time geometry",
    )
    axes[0].plot(
        np.arange(1, len(models)),
        [model["held_rms_rad"] for model in phase["wrong_time_models"]],
        "x--",
        label="Wrong-time geometry",
    )
    axes[0].set_xticks(np.arange(len(models)), labels, rotation=45)
    axes[0].set(
        ylabel="Held phase-increment RMS (rad, modulo π)",
        title="Curvature does not resolve satellite identity",
        ylim=(0.25, 0.32),
    )
    axes[0].legend(loc="upper left")
    for y, (key, _label) in enumerate(
        (
            ("selected_vs_constant_rate", "vs constant rate"),
            ("selected_vs_wrong_time", "vs wrong-time geometry"),
        )
    ):
        row = phase[key]
        mean = row["mean_score_gain"]
        low, high = row["percentile_95_interval"]
        axes[1].errorbar(mean, y, xerr=[[mean - low], [high - mean]], fmt="o", capsize=5)
        axes[1].text(mean, y + 0.10, f"{mean:+.6f}", ha="center")
    axes[1].axvline(0, color="gray", linewidth=1)
    axes[1].set_yticks([0, 1], ["vs constant rate", "vs wrong-time geometry"])
    axes[1].set(
        xlabel="Held mean cos(2 × phase residual) gain",
        title="Training-selected candidate 67702\nPaired-visit bootstrap 95% intervals",
        ylim=(-0.4, 1.5),
    )
    fig.suptitle("Phase advances • identical random held odd responses • local even calibration")
    fig.savefig(OUTPUT / "phase-advance-comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
