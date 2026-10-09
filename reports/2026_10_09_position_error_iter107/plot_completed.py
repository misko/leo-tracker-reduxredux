"""Plot a completed snapshot; never loads recording inputs or reference ports."""

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter


def plot(data, destination):
    rows = data["rows"]
    assert len(rows) in (63, 193)
    assert len({r["label"] for r in rows}) == len(rows)
    if data["metrics"]["full_census_position_metrics_withheld"]:
        raise ValueError("Full comparison withheld: missing or failed members")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for arm in ("fitted-c", "zero-c"):
        for phase, style in (("baseline", "--"), ("candidate", "-")):
            errors = np.array([r["arms"][arm][phase]["error_km"] for r in rows])
            axes[0].step(
                np.sort(errors),
                np.arange(1, len(rows) + 1) / len(rows),
                where="post",
                linestyle=style,
                label=arm + " " + phase,
            )
        baseline = [r["arms"][arm]["baseline"]["error_km"] for r in rows]
        candidate = [r["arms"][arm]["candidate"]["error_km"] for r in rows]
        axes[1].scatter(baseline, candidate, s=12, label=arm)
    axes[0].set(xlabel="Position error (km)", ylabel="Cumulative fraction", xscale="log")
    axes[1].set(
        xlabel="Fresh baseline error (km)",
        ylabel="Candidate error (km)",
        xscale="log",
        yscale="log",
    )
    limits = axes[1].get_xlim() + axes[1].get_ylim()
    axes[1].plot([min(limits), max(limits)], [min(limits), max(limits)], "k:", linewidth=1)
    for axis in axes:
        axis.xaxis.set_minor_formatter(NullFormatter())
        axis.yaxis.set_minor_formatter(NullFormatter())
        axis.legend(fontsize=7)
        axis.grid(alpha=0.2)
    fig.suptitle(f"{len(rows)} consumed development members: matched c controls")
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot(json.loads(args.snapshot.read_text()), args.output)
