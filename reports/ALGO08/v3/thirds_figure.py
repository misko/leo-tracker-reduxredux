"""Plot two sparse receiver policies on identical recorded signals and regional offers."""

import argparse
import gzip
import json
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import NullFormatter


ROOT = Path(__file__).parent / "measurements"
LABELS = {"DS30-0008": "Dense DS30", "south-containing": "South inside", "south-far": "South omitted"}
STYLES = (("ALGO08v3", "#293c5d", "o"), ("Full joint fit", "#00846a", "D"),
          ("First third", "#a7550a", "^"), ("Staggered RF blocks", "#79508d", "s"))


def comparisons(data=ROOT):
    contiguous = json.loads(gzip.decompress((data / "contiguous-third.json.gz").read_bytes()))
    blocks = json.loads((data / "rf-block.json").read_bytes())["cases"]
    result = {}
    for name in LABELS:
        block = blocks[name]
        if block["input"] != contiguous["cases"][name]["identity"]:
            raise ValueError("Sparse cases differ in input authority or offered region")
        modes = contiguous["scores"][name]["modes"]
        values = [(modes[k]["solve"]["cpu_s"], modes[k]["horizontal_error_km"], modes[k]["decision"])
                  for k in ("stock", "signed-full", "signed-third")]
        decision = block["decision"]
        errors = {k: arm["error_km"] for k, arm in block["scores"]["block"]["arms"].items()}
        values.append((decision["charged"]["cpu_s"], errors, decision["status"]))
        result[name] = values
    return result


def figure(output, data=ROOT):
    rows = comparisons(data)
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.85), layout="constrained")
    for i, (name, values) in enumerate(rows.items()):
        all_withheld = all(state == "withheld" for _, _, state in values)
        for j, ((cpu, errors, _), (_, color, marker)) in enumerate(zip(values, STYLES, strict=True)):
            y = i + (j - 1.5) * .12
            for ax, value in zip(axes, (cpu, errors["c0"], errors["fitted_c"]), strict=True):
                if value is not None:
                    ax.scatter(value, y, color=color, marker=marker, s=36, zorder=2)
        if all_withheld:
            for ax in axes[1:]:
                ax.text(.5, i, "All four withheld", ha="center", va="center", transform=ax.get_yaxis_transform(),
                        color="#525b60", fontsize=9)
    axes[0].set_xscale("log")
    axes[0].xaxis.set_minor_formatter(NullFormatter())
    axes[0].set_xticks((3, 5, 10, 25, 50), ("3", "5", "10", "25", "50"))
    for i, (ax, title) in enumerate(zip(axes, ("Solver + grid CPU (s)", "Error (km), fixed c = 0",
                                                "Error (km), fitted c"), strict=True)):
        ax.set(yticks=range(3), yticklabels=list(LABELS.values()) if i == 0 else [""] * 3,
               ylim=(2.45, -.5), xlabel=title)
        if i:
            ax.set_xlim(0, 4.5)
        ax.grid(axis="x", alpha=.22)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    handles = [Line2D([], [], marker=m, color=c, linestyle="", label=label) for label, c, m in STYLES]
    fig.suptitle("Position from all visits and from two one-third schedules")
    fig.legend(handles=handles, loc="outside lower center", ncols=4, frameon=False)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    figure(cli.parse_args().output)
