"""Plot adjudicated stop readiness using the archived acquisition timing scenario."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from ..__main__ import local_output
from ..scoring import ARMS
from .online_prefix_trial import OUT


def draw(report):
    rows = json.loads((report / "scores.json").read_bytes())["rows"]
    observations = [r for r in rows if r["method"] == "native-clock-stable-stop"]
    ids = sorted({r["id"] for r in observations}, key=lambda i: (i.endswith("omitted"), i))
    y = {case: i for i, case in enumerate(ids)}
    label = [i.replace("-matched", "").replace("-omitted", " · omitted") for i in ids]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.25), sharey=True, layout="constrained")
    for i, (ax, arm) in enumerate(zip(axes, ARMS, strict=True)):
        for t in (120, 180, 240, 300):
            ax.axvline(t, linewidth=0.7, linestyle="--", color="#becbd4")
        for r in rows:
            if r["arm"] != arm or r["method"] in (
                "native-clock-stable-stop",
                "native-clock-terminal",
            ):
                continue
            if r["published"] and r["elapsed_host_s"] is not None:
                ax.scatter(np.mean(r["elapsed_host_s"]), y[r["id"]], s=17, color="#65a4ba")
        for r in observations:
            if r["arm"] != arm:
                continue
            yi = y[r["id"]]
            if r["published"]:
                ax.scatter(
                    np.mean(r["elapsed_host_s"]), yi, s=56, color="#0d506c", marker="D", zorder=4
                )
            else:
                ax.text(
                    124, yi, r["status"].replace("_", " "), va="center", color="#546a78", fontsize=8
                )
            terminal = next(
                a
                for a in rows
                if a["method"] == "native-clock-terminal" and a["id"] == r["id"] and a["arm"] == arm
            )
            end = r["policy"].get("terminal_only_elapsed_host_s")
            if end and terminal["published"]:
                ax.scatter(np.mean(end), yi, s=38, edgecolor="#26343c", facecolor="none", zorder=5)
        ax.set_xticks([120, 180, 240, 300])
        ax.set_xlim(113, 325)
        ax.set_ylim(len(ids) - 0.5, -0.5)
        ax.set_yticks(range(len(ids)), label)
        ax.set_title("Zero calibration" if i == 0 else "Fitted calibration", fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("When a fix becomes available from causal native prefixes", fontweight="bold")
    fig.supxlabel(
        "Seconds from acquisition start, with measured host work in the serial overlap scenario"
    )
    fig.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", color="#65a4ba", label="Ordinary prefix"),
            Line2D([], [], marker="D", linestyle="none", color="#0d506c", label="Stable-stop fix"),
            Line2D(
                [],
                [],
                marker="o",
                linestyle="none",
                markerfacecolor="none",
                color="#26343c",
                label="Terminal fix",
            ),
        ],
        loc="outside lower center",
        ncols=3,
        frameon=False,
        fontsize=8,
    )
    fig.savefig(report / "time-to-fix.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    draw(local_output(parser.parse_args().report))


if __name__ == "__main__":
    main()
