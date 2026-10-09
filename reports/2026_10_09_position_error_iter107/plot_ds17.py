"""Reproduce DS17 comparison from the sealed reporting snapshot only."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "DS17_COMPLETE_SNAPSHOT.json").read_text())
    rows = data["rows"]
    assert len(rows) == 51 and not data["metrics"]["full_census_position_metrics_withheld"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for arm in ("fitted-c", "zero-c"):
        for phase, style in (("baseline", "--"), ("candidate", "-")):
            errors = [r["arms"][arm][phase]["error_km"] for r in rows]
            axes[0].step(
                sorted(errors),
                np.arange(1, 52) / 51,
                where="post",
                linestyle=style,
                label=arm + " " + phase,
            )
        axes[1].plot(
            range(1, 52), [r["arms"][arm]["candidate"]["error_km"] for r in rows], "o", label=arm
        )
    axes[0].set(xlabel="Position error km (log scale)", ylabel="Cumulative fraction", xscale="log")
    axes[1].set(xlabel="DS17 member number", ylabel="Candidate error km", yscale="log")
    for axis in axes:
        axis.legend(fontsize=7)
        axis.grid(alpha=0.2)
    fig.suptitle("All51 DS17 consumed members: matched fresh baseline and recovery candidate")
    fig.tight_layout()
    fig.savefig(HERE / "ds17-complete.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
