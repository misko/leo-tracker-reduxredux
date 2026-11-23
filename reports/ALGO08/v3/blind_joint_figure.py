"""Plot saved-packet solver clocks and actual returned positions under both calibration fits."""

import argparse
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.ticker import NullFormatter


def figure(cases, output, method):
    labels = {"DS30-0008": "Dense DS30", "south-containing": "South inside", "south-far": "South omitted",
              "north-containing": "North inside", "north-far": "North omitted"}
    order = [name for name in labels if name in cases]
    if set(order) != set(cases):
        raise ValueError("Unknown offer in saved joint comparison")
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 2.1 + .35 * len(order)), layout="constrained")
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
        ax.set(yticks=range(len(order)), yticklabels=[labels[k] if i == 0 else "" for k in order],
               ylim=(len(order) - .5, -.5))
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
    cli.add_argument("--transfer", type=Path)
    cli.add_argument("--family-search", action="store_true", help="Read the iterative family-search score format.")
    args = cli.parse_args()
    records = json.loads(args.summary.read_bytes())["cases"]
    if args.family_search:
        records = {case: dict(timing=dict(stock=dict(cpu_s=row["stock_cpu_s"]), charged=row["result"]),
                              stock=row["stock_fit"], returned=row["versus"]["signed-full"])
                   for case, row in records.items()}
    if args.transfer:
        additional = json.loads(args.transfer.read_bytes())["cases"]
        if records.keys() & additional.keys():
            raise ValueError("Duplicate offer across the two summaries")
        records.update(additional)
    figure(records, args.output, args.method)
