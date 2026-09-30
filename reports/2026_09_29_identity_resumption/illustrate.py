"""Scientific figures and a reviewable candidate-revisit table."""

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASE = Path(__file__).resolve().parent
OUT = BASE / "local"


def main():
    identity = json.loads((OUT / "identity.json").read_text())
    visits = json.loads((OUT / "within-visit.json").read_text())
    selected = [r for r in identity["experiments"] if "effect" in r]
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    labels = ["Same instrument/channel (1 pair)", "Mixed instruments, same channel (30 pairs)",
              "Different sessions/channels (7 pairs)"]
    names = ["Absolute phase", "Within-symbol relative phase",
             "Between-symbol relative phase", "Real signs"]
    for k, name in enumerate(names):
        ax.bar(np.arange(3) + (k - 1.5) * .18, [r["effect"][k] for r in selected],
               width=.18, label=name)
    ax.axhline(0, color="black", linewidth=.7)
    ax.set_xticks(np.arange(3), labels, fontsize=8)
    ax.set(ylabel="Matched similarity excess (cosine)",
           title="Early-feature transfer: descriptive effects, conditional identities")
    ax.legend(fontsize=8, ncol=2)
    fig.savefig(OUT / "identity-effects.png", dpi=180)
    plt.close(fig)
    rows = [r for r in visits["stability"] if r["mode"] == "consensus"]
    tags = sorted({r["donor"] for r in rows})
    matrix = np.array([[next(r["receiver_agreements"][1] for r in rows
                            if r["donor"] == a and r["target"] == b) for b in tags] for a in tags])
    fig, ax = plt.subplots(figsize=(5.5, 4), constrained_layout=True)
    im = ax.imshow(matrix, vmin=.5, vmax=1., cmap="viridis")
    ax.set_xticks(range(3), [t.split("-v")[1] for t in tags])
    ax.set_yticks(range(3), [t.split("-v")[1] for t in tags])
    ax.set(xlabel="Later-frame RX1 target visit", ylabel="Earlier-frame consensus donor visit",
           title="Stable-sign agreement (not identity specificity)")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{matrix[i, j]:.1%}", ha="center", va="center", color="white")
    fig.colorbar(im, ax=ax, label="Agreement")
    fig.savefig(OUT / "stable-transfer.png", dpi=180)
    plt.close(fig)
    with (OUT / "matched-revisits.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scope", "left", "right", "candidate_norad", "separation_s",
                         "cross_session", "shared_T_state", *names])
        for r in selected:
            for p in r["matched_pairs"]:
                writer.writerow([r["scope"], p["left"], p["right"], p["candidate"],
                                 p["separation_s"], p["cross_session"], p["shared_state"],
                                 *p["scores"]])


if __name__ == "__main__":
    main()
