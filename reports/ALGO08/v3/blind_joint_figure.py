"""Plot saved-packet solver clocks and actual returned positions under both calibration fits."""

import argparse
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.ticker import NullFormatter


def figure(cases, output, method):
    order = ("DS30-0008", "south-containing", "south-far")
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.15), layout="constrained")
    colors = ("#354968", "#007667")
    for index, name in enumerate(order):
        case = cases[name]
        clocks = case["timing"]
        stock = clocks["stock"]["cpu_s"] if clocks["stock"] else clocks["archived_stock_cpu_s"]
        for arm, (time, result, label, mark, color) in enumerate(zip(
                (stock, clocks["charged"]["cpu_s"]), (case["stock"], case["returned"]),
                ("ALGO08v3", method), ("o", "D"), colors, strict=True)):
            y = index + (arm - 0.5) * 0.23
            axes[0].scatter(time, y, color=color, marker=mark, s=37, label=label if index == 0 else None)
            for ax, key in zip(axes[1:], ("c0", "fitted_c")):
                error = result["arms"][key]["error_km"]
                if error is not None:
                    ax.scatter(error, y, color=color, marker=mark, s=37)
                elif arm == 0 and case["returned"]["arms"][key]["error_km"] is None:
                    ax.text(.5, index, "Both withheld", ha="center", va="center",
                            transform=ax.get_yaxis_transform(), color="#54595c", fontsize=9)
    axes[0].set_xscale("log")
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    axes[0].set(xticks=(3, 5, 10, 25, 50, 90), xticklabels=("3", "5", "10", "25", "50", "90"),
                xlabel="Saved solve CPU (seconds)")
    for ax, arm in zip(axes[1:], ("fixed c = 0", "fitted c")):
        ax.set(xlabel=f"Horizontal error (km), {arm}", xlim=(0, None))
    for i, ax in enumerate(axes):
        ax.set(yticks=range(3), yticklabels=("Dense DS30", "South inside", "South omitted") if i == 0 else [""] * 3,
               ylim=(2.5, -.5))
        ax.grid(axis="x", alpha=.23)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("Saved solver inputs through the numerical result, including any fallback")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncols=2, frameon=False)
    fig.savefig(output, dpi=165)
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("summary", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--method", default="Joint curved and predictive fit")
    args = cli.parse_args()
    figure(json.loads(args.summary.read_bytes())["cases"], args.output, args.method)
