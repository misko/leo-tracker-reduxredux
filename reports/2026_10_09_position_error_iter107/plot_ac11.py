"""Reproduce the consumed ac11 replay figure from saved reporting statistics."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "AC11_FULL107_REPLAY.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for i, arm in enumerate(("fitted-c", "zero-c")):
        values = data["row"]["arms"][arm]
        x = np.arange(2) + (i - 0.5) * 0.3
        axes[0].bar(x, [values[p]["error_km"] for p in ("baseline", "candidate")], 0.3, label=arm)
        axes[1].bar(
            x, [values[p]["posterior_rms_hz"] for p in ("baseline", "candidate")], 0.3, label=arm
        )
    for axis in axes:
        axis.set_xticks([0, 1], ["Fresh B7 baseline", "Recovery candidate"])
        axis.legend()
    axes[0].set_ylabel("Position error km (evaluation only)")
    axes[1].set_ylabel("Model-specific posterior RMS Hz")
    fig.suptitle("ac11 full107 replay: same consumed sample; regional banks differ")
    fig.tight_layout()
    fig.savefig(HERE / "ac11-full107.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
