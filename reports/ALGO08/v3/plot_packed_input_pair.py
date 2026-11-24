"""Plot matched DS30 timing boundaries from the recorded process clocks."""

import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Patch


def main():
    root = Path(__file__).resolve().parent
    measurements = root / "measurements"
    with gzip.open(measurements / "integrated-packed-full.json.gz", "rt") as stream:
        pair = json.load(stream)["pair"]["document"]
    cost = json.loads((measurements / "integrated-packed-cost.json").read_text())
    assert pair["cases"] == cost["cases"] == ["DS30-0016", "DS30-0107"]
    stock = [case["elapsed_s"] for case in pair["fresh_stock"]]
    first, reverse = (
        [case["elapsed_s"] for case in pair["current_original"][order]]
        for order in ("positive_first", "withholding_first")
    )
    ready = [pair["paid"][case]["elapsed_s"] for case in pair["cases"]]
    conversion = sum(cost["historical_strict"]["conversion_and_readback_s"])
    series = [stock, first, reverse, ready, ready]
    labels = [
        "Installed ALGO08v3",
        "Original · fix first",
        "Original · withhold first",
        "Packed · already prepared",
        "Packed · include preparation¹",
    ]
    colors = ["#24465d", "#57a1a4", "#e6ded0"]
    figure, axes = plt.subplots(figsize=(9.8, 4.4))
    figure.subplots_adjust(left=0.29, right=0.97, top=0.73, bottom=0.23)
    for index, (fix, withheld) in enumerate(series):
        axes.barh(index, fix, height=0.53, color=colors[0])
        axes.barh(index, withheld, left=fix, height=0.53, color=colors[1])
        total = fix + withheld
        if index == len(series) - 1:
            axes.barh(index, conversion, left=total, height=0.53, color=colors[2],
                      edgecolor="#897858", linewidth=0.5, hatch="//")
            total += conversion
        axes.text(total + 0.12, index, f"{total:.2f} s", va="center", fontsize=10)
    half = sum(stock) / 2
    axes.axvline(half, ls="--", color="#b14629", lw=1.4)
    axes.text(half, 1.015, f"2× target  {half:.2f} s", ha="center",
              transform=axes.get_xaxis_transform(), color="#913b24", fontsize=9)
    axes.set(xlim=(0, 13.7), yticks=range(len(labels)), yticklabels=labels,
             xlabel="Total elapsed time across the two recordings (seconds)")
    axes.invert_yaxis()
    axes.set_axisbelow(True)
    axes.grid(axis="x", color="#e5e9e9")
    axes.tick_params(axis="both", length=0, pad=6)
    for spine in axes.spines.values():
        spine.set_visible(False)
    figure.text(0.025, 0.94, "Same two DS30 recordings, different starting formats",
                weight="bold", fontsize=16)
    figure.legend([Patch(color=color) for color in colors],
                  ["0016 · fix", "0107 · withhold", "Earlier conversion and readback"],
                  loc="upper left", bbox_to_anchor=(0.017, 0.90), frameon=False, ncol=3)
    figure.text(0.025, 0.04, "¹ First-use estimate adds previously measured preparation "
                "to the timed packed run. All worker runs used one core.", fontsize=9)
    figure.savefig(root / "development" / "packed-input-pair.png", dpi=165)
    plt.close(figure)


if __name__ == "__main__":
    main()
