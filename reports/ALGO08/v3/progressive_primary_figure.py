"""Render paired native-search times and signed-factor discrepancies."""

import json
from pathlib import Path

import matplotlib.pyplot as plt


def render(data, output):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), layout="constrained")
    for ax, label, name in zip(axes, ("Dense DS30", "Weak DS26"), ("dense", "weak"), strict=True):
        panel = data["panels"][name]
        for pair in panel["repeats_ns"]:
            ax.plot([0, 1], [pair["direct_ns"]/1e6, pair["candidate_ns"]/1e6],
                    color="#68839b", marker="o", lw=1.5)
        effects = panel["effects"]
        ax.set_title(f"{label} · {panel['lanes']} antenna visits", loc="left", weight="bold")
        ax.set_xticks([0, 1], ["Direct 12 ms", "8 ms + restart"])
        ax.set_xlim(-.26, 1.26)
        ax.set_ylim(0, ax.get_ylim()[1]*1.13)
        ax.set_ylabel("CPU per sample set (ms)")
        ax.grid(axis="y", color="#dfe8ed")
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(.03,.05,f"{effects['restarts']} restarts\n{effects['missed_restarts']} outputs outside tolerance",
                transform=ax.transAxes, fontsize=10)
    fig.suptitle("Three paired runs of the same signed antenna searches", weight="bold", fontsize=14)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    render(json.loads((here / "measurements/progressive-primary.json").read_bytes()),
           here / "development/progressive-primary.png")
