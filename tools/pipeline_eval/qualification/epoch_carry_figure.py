"""Draw the three-way timing histogram over its common evaluation support."""

import json

import matplotlib.pyplot as plt
import numpy as np

from .epoch_carry_trial import OUT


def main():
    summary = json.loads((OUT / "cycle/scores.json").read_bytes())["aggregate"]
    labels = ("≤1", "1–2", "2–5", "5–20", "20–100", "100–1000", ">1000")
    bins = (("0.5", "1"), ("2",), ("5",), ("20",), ("100",), ("1000",), ("above_1000",))
    keys = (("own", "Same lane"), ("wrong_channel", "Wrong channel"), ("wrong_time", "Wrong time"))
    figure, axis = plt.subplots(figsize=(8.2, 3.4), layout="constrained")
    x = np.arange(len(labels))
    totals = []
    for i, (key, name) in enumerate(keys):
        values = summary[f"teacher/{key}/epoch/common_null"]
        totals.append(sum(values.values()))
        counts = [sum(values.get(k, 0) for k in group) for group in bins]
        axis.bar(x + 0.24 * (i - 1), counts, width=0.22, label=name)
    assert len(set(totals)) == 1
    axis.set(
        title=f"Pilot timing after one retune cycle · {totals[0]} common reference probes",
        ylabel="Forecasts",
        xlabel="Nearest archived positive epoch error (samples)",
        xticks=x,
        xticklabels=labels,
        ylim=(0, max(totals) + 2),
    )
    axis.legend(frameon=False, loc="upper left")
    axis.grid(axis="y", alpha=0.2)
    axis.set_axisbelow(True)
    for side in ("right", "top"):
        axis.spines[side].set_visible(False)
    figure.savefig(OUT / "cycle/timing-histogram.png", dpi=150)
    plt.close(figure)


if __name__ == "__main__":
    main()
