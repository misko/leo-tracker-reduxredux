"""Plot the measured CPU budget and short-recording position errors."""

import argparse
import json
from pathlib import Path

from matplotlib import pyplot as plt


MEASUREMENTS = Path(__file__).resolve().parent / "measurements"


def figure(output):
    saved = json.loads((MEASUREMENTS / "signed-short-DS30-0316.json").read_bytes())
    floor = json.loads((MEASUREMENTS / "short-floor-DS30-0316.json").read_bytes())
    stock, signed = saved["runs"]["stock"], saved["runs"]["signed"]
    cpu = [floor["historical_v3"]["cpu_s"], floor["publication_cpu_s"],
           stock["publication_cpu_s"], signed["publication_cpu_s"]]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.3), layout="constrained", width_ratios=(1.35, 1))
    ax = axes[0]
    ax.barh(range(4), cpu, color=["#253d64", "#a86224", "#687d9c", "#23745e"])
    ax.set_yticks(range(4), ["v3 · raw through exit", "Joint · raw with detector bypass",
                             "v3 · from saved signals", "Joint · from saved signals"])
    ax.invert_yaxis()
    ax.set(xlabel="CPU seconds", xlim=(0, 45))
    for i, value in enumerate(cpu):
        ax.text(value + .5, i, f"{value:.2f}", va="center", fontsize=9)
    ax.axvline(cpu[0] / 2, color="#8e3734", linestyle="--", label="Half of archived v3 CPU")
    ax.legend(loc="upper right", bbox_to_anchor=(1.02, -.15), frameon=False, fontsize=8)
    ax = axes[1]
    for i, (mode, label, color) in enumerate((("stock", "ALGO08v3", "#253d64"), ("signed", "Full signed joint", "#23745e"))):
        vals = [saved["horizontal_error_km"][mode][arm] for arm in ("c0", "fitted_c")]
        ax.bar([-.18 + .36*i, .82 + .36*i], vals, width=.32, color=color, label=label)
        for col, val in enumerate(vals):
            ax.text(col - .18 + .36*i, val + .018, f"{val:.3f}", ha="center", fontsize=8)
    ax.set(xticks=[0, 1], xticklabels=["Fixed-zero c", "Fitted c"], ylabel="Horizontal error (km)", ylim=(0, 2.2))
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.15), ncols=2, frameon=False, fontsize=8)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(length=0)
    fig.suptitle("DS30-0316 · one recording, one CPU core")
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    figure(parser.parse_args().output)
