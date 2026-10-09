"""Reproduce the sealed newer45 figure from the reporting snapshot only."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    data = json.loads((HERE / "NEWER45_COMPLETE_SNAPSHOT.json").read_text())
    rows = data["rows"]
    assert len(rows) == 45 and not data["metrics"]["full_census_position_metrics_withheld"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for arm in ("fitted-c", "zero-c"):
        baseline = [r["arms"][arm]["baseline"]["error_km"] for r in rows]
        candidate = [r["arms"][arm]["candidate"]["error_km"] for r in rows]
        for phase, values, style in (("baseline", baseline, "--"), ("candidate", candidate, "-")):
            axes[0].step(
                sorted(values),
                np.arange(1, 46) / 45,
                where="post",
                linestyle=style,
                label=arm + " " + phase,
            )
        axes[1].scatter(baseline, candidate, label=arm)
    maximum = max(
        r["arms"][a][p]["error_km"]
        for r in rows
        for a in ("fitted-c", "zero-c")
        for p in ("baseline", "candidate")
    )
    axes[1].plot([0, maximum], [0, maximum], color="gray")
    axes[0].set(xlabel="Position error km", ylabel="Cumulative fraction")
    axes[1].set(xlabel="Fresh baseline error km", ylabel="Recovery candidate error km")
    for axis in axes:
        axis.legend(fontsize=7)
        axis.grid(alpha=0.2)
    fig.suptitle("All45 consumed newer development members; reserves009–016 excluded by authority")
    fig.tight_layout()
    fig.savefig(HERE / "newer45-complete.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
