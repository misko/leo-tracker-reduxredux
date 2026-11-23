"""Plot four containing-offer transfers using separate physical and simulated rows."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def observations():
    def load(name):
        with gzip.open(HERE / "measurements" / name) as stream:
            return json.load(stream)

    initial = load("local-future-repair.json.gz")["results"]
    transfer = load("local-future-0057.json.gz")["runs"]
    rows = []
    for label, case in (("DS30-0016", "physical"), ("DS30-0057", None),
                        ("Northern simulation", "north"), ("Southern simulation", "south-inside")):
        forward, repair = ((transfer["forward"]["score"], transfer["repair"]["score"]) if case is None
                           else (initial[case]["forward"], initial[case]["score"]))
        stock = transfer["stock"]["score"] if case is None else initial[case]["stock"]
        for arm in ("c0", "fitted_c"):
            for name, result in (("Forward only", forward), ("Protected repair", repair)):
                rows.append((label, arm, name, 1000 * (result["arms"][arm]["error_km"] - stock["arms"][arm]["error_km"])))
    return rows


def plot(path):
    rows = observations()
    labels = list(dict.fromkeys(row[0] for row in rows))
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), sharey=True, sharex=True)
    for axis, arm, title in zip(axes, ("c0", "fitted_c"), ("Fixed calibration  ·  c = 0", "Fitted calibration"), strict=True):
        axis.axvline(0, color="#475569", linewidth=1)
        axis.axvline(250, color="#b45309", linewidth=1, linestyle="--", label="Development limit (+250 m)")
        for i, label in enumerate(labels):
            left, right = [row[3] for row in rows if row[0] == label and row[1] == arm]
            axis.plot([left, right], [i, i], color="#a7b3be", linewidth=2)
            axis.plot(left, i, "o", mfc="white", mec="#405977", ms=7, label="Forward only" if i == 0 else None)
            axis.plot(right, i, "D", color="#08796c", ms=6, label="Protected repair" if i == 0 else None)
        axis.axhline(1.5, color="#d8dfe4", linewidth=.8)
        axis.set(title=title, xlabel="Change in horizontal error (m)", yticks=range(len(labels)), yticklabels=labels)
        axis.grid(axis="x", color="#e4e9ed", zorder=0)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
    axes[0].invert_yaxis()
    axes[0].set_ylim(3.45, -.45)
    fig.text(.02, .96, "Position error relative to installed ALGO08v3", fontsize=16, weight="bold")
    fig.text(.02, .89, "Four saved containing offers. Values below zero are improvements.", color="#425466")
    handles, legend = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend, loc="lower center", ncols=3, frameon=False)
    fig.subplots_adjust(left=.19, right=.98, top=.74, bottom=.24, wspace=.13)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    plot(HERE / "development/local-future-transfer.png")
