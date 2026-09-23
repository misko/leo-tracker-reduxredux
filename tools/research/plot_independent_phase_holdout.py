"""Render the frozen independent phase comparison without selecting models."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DIRECTORY = Path(__file__).resolve().parents[2] / "reports/figures/2026_09_23_independent_phase"


def main():
    result = json.loads((DIRECTORY / "held-evaluation.json").read_text())
    models = result["models"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    labels = [name.replace("_", " ") for name in models]
    colors = ["#5076a8" if name.startswith("glrt") else "#c26628" for name in models]
    rms = [model["conditional_equal_visit_rms_hz"] for model in models.values()]
    axes[0].barh(labels, rms, color=colors)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Held odd-pilot CFO RMS (Hz); equal dwell weight")
    axes[0].set_xlim(0, max(rms) * 1.18)
    for i, value in enumerate(rms):
        axes[0].text(value + max(rms) * 0.015, i, f"{value:.1f}", va="center")
    times = {row["visit_index"]: row["observation_time_s"] for row in result["responses"]}
    for name in ("glrt_candidate", "phase_candidate", "phase_constant_rate", "phase_wrong_time"):
        rows = sorted(models[name]["visits"], key=lambda row: times[row["visit_index"]])
        covered = [row for row in rows if not row["abstention"]]
        axes[1].plot(
            [times[row["visit_index"]] for row in covered],
            [row["mean_residual_hz"] for row in covered],
            "o-",
            label=name.replace("_", " "),
            alpha=0.8,
        )
    axes[1].axhline(0, color="0.5", linewidth=0.8)
    axes[1].set_xlabel("Seconds from capture start")
    axes[1].set_ylabel("Dwell mean held residual (Hz)")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.2)
    coverage = models["phase_candidate"]
    fig.suptitle(
        "Independent 2.5 MS/s arc — frozen prediction, random whole-dwell holdout\n"
        f"{coverage['covered_held_visits']}/{coverage['total_held_visits']} held dwells covered; "
        "conditional CFO comparison, no confirmed identity/position"
    )
    fig.savefig(DIRECTORY / "held-comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
