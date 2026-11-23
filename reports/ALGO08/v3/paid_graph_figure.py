"""Plot empirical component outcomes and a separate conditional whole-run timing budget."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

from retained_wait import gates


def render(root):
    cases = json.loads((root/"measurements/paid-quadratic.json").read_bytes())["cases"]
    budget = json.loads((root/"measurements/retained-wait.json").read_bytes())
    fig, (ax, south, timing) = plt.subplots(1, 3, figsize=(14, 4.6), constrained_layout=True)
    labels = ["Paid, quadratic", "Paid, graph support", "Paid, max. margin", "Complete control"]
    for panel, key, limit, title in ((ax, "DS30-0016", 6.15, "DS30-0016"),
                                     (south, "south-containing", 1.5, "Southern simulation")):
        for y, mode in enumerate(("quadratic", "graph", "margin", "complete")):
            r = cases[key][mode]["arms"]
            points = [r[k]["error_km"] for k in ("c0", "fitted_c")]
            if points[0] is None:
                panel.text(.05, y, "Withheld", color="#57636b", va="center")
                continue
            panel.plot(points, [y, y], color="#acb4bb")
            for x, marker, color, name in zip(points, ("o","D"), ("#196f75","#a3451d"), ("Fixed zero","Fitted")):
                panel.scatter(x, y, s=55, marker=marker, color=color, label=name if y==0 else None, zorder=3)
        panel.set(yticks=range(4), yticklabels=labels if panel is ax else [], xlabel="Horizontal position error (km)",
                  title=title, ylim=(-.8, 3.6), xlim=(0, limit))
    ax.legend(loc="lower right", frameon=False)
    x = np.linspace(0, 1, 101)
    for index, measure in enumerate(["Median paired", "Summed"]):
        y = np.array([[gates(budget["rows"], a, budget["solver_cpu_scale"], arm)[index] for a in x]
                      for arm in ("best","worst")])
        color = ["#407298","#dc8345"][index]
        timing.fill_between(x, y[0], y[1], color=color, alpha=.19)
        timing.plot(x, y[0], color=color, label=measure)
        timing.plot(x, y[1], color=color, lw=1)
    timing.axhline(.5, color="#222", ls="--", lw=1, label="2× target")
    timing.set(title="55 archived runs · retained-wait model", xlabel="Acquisition CPU remaining",
               ylabel="Projected fraction of v3 elapsed time", xlim=(0,1), ylim=(.25,1.05))
    timing.xaxis.set_major_formatter(PercentFormatter(1))
    timing.yaxis.set_major_formatter(PercentFormatter(1))
    timing.legend(loc="upper left",frameon=False)
    for panel in (ax, south, timing):
        panel.grid(axis="x", alpha=.16)
        panel.spines[["top","right"]].set_visible(False)
    fig.savefig(root/"development/paid-graph-timing.png", dpi=165)
    plt.close(fig)


if __name__ == "__main__":
    render(Path(__file__).resolve().parent)
