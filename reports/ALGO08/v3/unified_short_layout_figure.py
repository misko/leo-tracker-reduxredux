"""Plot the sealed raw bootstrap, graph-proof and explicit-layout comparison."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt


def draw(receipt, output):
    obs = receipt["observations"]
    names = ("stock", "candidate")
    colors = ("#354365", "#00796b")
    fig, (runtime, error) = plt.subplots(1, 2, figsize=(10, 3.55), layout="constrained")
    for i, (name, color) in enumerate(zip(names, colors, strict=True)):
        y = [1.16 - .32 * i, .16 - .32 * i]
        times = [obs[c]["rows"][name]["clock"]["elapsed_s"] for c in ("weak", "tiny")]
        distances = [obs["weak"]["rows"][name]["errors_km"][arm] for arm in ("c0", "fitted_c")]
        for ax, values, fmt in ((runtime, times, "%.3f"), (error, distances, "%.3f")):
            bars = ax.barh(y, values, height=.25, color=color, label=("ALGO08v3", "Prototype")[i])
            ax.bar_label(bars, fmt=fmt, padding=4, fontsize=9)
    for y, case in ((1, "weak"), (0, "tiny")):
        half = obs[case]["rows"]["stock"]["clock"]["elapsed_s"] / 2
        runtime.plot([half, half], [y+.01, y+.31], linestyle=":", color="#a1470b",
                     label="Half of v3" if case == "weak" else None)
    runtime.set(yticks=[1, 0], yticklabels=["DS30-0016\nfix", "DS30-0227\nwithheld"],
                xlabel="Elapsed time through process exit (s)", xlim=(0, 12.6), title="Original I/Q through publication")
    runtime.legend(loc="upper center", bbox_to_anchor=(.5, -.22), ncol=3, frameon=False, fontsize=9)
    error.set(yticks=[1, 0], yticklabels=["Zero calibration", "Fitted calibration"], xlabel="Horizontal error (km)",
              xlim=(0, 2.05), title="Position on DS30-0016")
    for ax in (runtime, error):
        ax.set_ylim(-.45, 1.5)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e4e8e9", linewidth=.7)
        ax.set_axisbelow(True)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("png", type=Path)
    args = parser.parse_args()
    payload = args.receipt.read_bytes()
    if args.receipt.suffix == ".gz":
        payload = gzip.decompress(payload)
    draw(json.loads(payload), args.png)
