"""Reproduce the tiny sealed DS16-055 endpoint change from reporting statistics."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "DS16_055_REPLAY.json").read_text())
    arms = data["row"]["arms"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    labels = list(arms)
    axes[0].bar(labels, [v["candidate"]["error_km"] for v in arms.values()])
    axes[1].bar(labels, [v["error_delta_km"] * 1e6 for v in arms.values()])
    axes[0].set_ylabel("Candidate position error km")
    axes[1].set_ylabel("Candidate − baseline error (mm)")
    fig.suptitle("DS16-055: selected region changes; endpoint difference is submillimetre")
    fig.tight_layout()
    fig.savefig(HERE / "ds16-055-replay.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
