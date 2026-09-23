"""Display training-only waveform feasibility for the independent phase arc."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DIRECTORY = Path(__file__).resolve().parents[2] / "reports/figures/2026_09_23_independent_phase"


def main():
    with gzip.open(DIRECTORY / "train-frames.json.gz", "rt") as stream:
        document = json.load(stream)
    rows = sorted(document["rows"], key=lambda row: row["observation"]["time_s"])
    times = [row["observation"]["time_s"] for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), layout="constrained")
    for key, label in (("exact_coherence", "Exact pilot"), ("control_coherence", "Rolled control")):
        axes[0].plot(times, [row["train_odd_diagnostic"][key] for row in rows], "o-", label=label)
    axes[0].set(
        xlabel="Capture-relative time (s)",
        ylabel="Mean odd-frame coherence",
        title="Training waveform evidence; no held prediction result",
        ylim=(0, 0.15),
    )
    axes[0].legend()
    for key, label in (
        ("calibration_even_eligible", "Calibration even"),
        ("diagnostic_odd_eligible", "Diagnostic odd"),
    ):
        axes[1].plot(times, [row["frame_coverage"][key] for row in rows], "o-", label=label)
    axes[1].set(
        xlabel="Capture-relative time (s)",
        ylabel="Eligible frames per dwell",
        title="All 15 training dwells retain usable frames",
        ylim=(0, 13),
    )
    axes[1].legend()
    fig.suptitle("Independent 2.5 MS/s arc • RX1 / channel 3 lower • random training subset only")
    fig.savefig(DIRECTORY / "training-feasibility.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
