"""Show published coverage and the fraction within one kilometre over elapsed time."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output
from ..scoring import ARMS
from .online_full import OUT
from .online_full_results import METHOD


def curve(ax, timestamps, n, **style):
    data = sorted(timestamps)
    x = [176, *data, max(325, data[-1] if data else 325)]
    y = np.r_[0, np.arange(1, len(data) + 1) / n, len(data) / n]
    ax.step(x, y, where="post", **style)


def draw(report):
    rows = json.loads((report / "scores.json").read_bytes())["rows"]
    match = {(r["id"], r["arm"], r["method"]): r for r in rows if r["condition"] == "matched"}
    fig, pairs = plt.subplots(1, 2, figsize=(10.2, 4.15), sharey=True, layout="constrained")
    for i, (ax, arm) in enumerate(zip(pairs, ARMS, strict=True)):
        online, terminal = [], []
        for row in match.values():
            if row["arm"] != arm or row["method"] != METHOD:
                continue
            if row["published"] and row["elapsed_host_s"] is not None:
                online.append((row["elapsed_host_s"], row["error_km"]))
            ref = match[row["id"], arm, "online-full-terminal"]
            if ref["published"] and row["terminal_elapsed_host_s"] is not None:
                terminal.append((row["terminal_elapsed_host_s"], ref["error_km"]))
        for series, color, title in (
            (online, "#075c77", "Stable stop"),
            (terminal, "#ab512d", "Terminal only"),
        ):
            curve(ax, (t for t, _ in series), 135, label=title, color=color)
            curve(
                ax,
                (t for t, error in series if error <= 1),
                135,
                color=color,
                linestyle="--",
                label=title + " ≤1 km",
            )
        ax.set_title("Zero calibration" if i == 0 else "Fitted calibration", weight="bold")
        ax.set_xticks((180, 210, 240, 270, 300, 330))
        ax.set_xlim(174, 331)
        ax.set_ylim(0, 1.01)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="#dbe3e7", linewidth=0.7)
    pairs[0].set_ylabel("Share of the 135 roof recordings")
    pairs[1].legend(loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Published accuracy over the acquisition and host-work scenario", weight="bold")
    fig.supxlabel("Elapsed seconds from acquisition start")
    fig.savefig(report / "published-by-time.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    draw(local_output(parser.parse_args().report))
