"""Reproduce the completed DS18 figure from the immutable reporting snapshot."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    snapshot = json.loads((HERE / "DS18_COMPLETE_SNAPSHOT.json").read_text())
    rows = snapshot["rows"]
    assert len(rows) == 34
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for arm in ("fitted-c", "zero-c"):
        errors = [r["arms"][arm]["baseline"]["error_km"] for r in rows]
        y = np.arange(1, len(errors) + 1) / len(errors)
        assert y[0] == 1 / 34 and y[-1] == 1
        axes[0].step(sorted(errors), y, where="post", label=arm + " baseline = candidate")
        axes[1].plot(range(1, 35), errors, "o", label=arm)
    axes[0].set(xlabel="Position error km (log scale)", ylabel="Cumulative fraction", xscale="log")
    axes[1].set(xlabel="DS18 member number", ylabel="Position error km", yscale="log")
    for axis in axes:
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    fig.suptitle("All34 DS18: exact selected baseline/candidate parity; matched c arms")
    fig.tight_layout()
    fig.savefig(HERE / "ds18-complete.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
