"""Plot two prospective same-detector solver comparisons from their saved receipts."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from solver_transfer_budget import DATA, receipt


def figure(output):
    first = receipt("prospective-0316-solver.json.gz")
    second = receipt("prospective-0160-partial-pair.json.gz")
    confirmed = receipt("prospective-0160-confirmation.json.gz")
    if first["case"] != "DS30-0316" or second["case"] != confirmed["case"] or confirmed["case"] != "DS30-0160":
        raise ValueError("Prospective solver cases changed")
    colors = ("#3d536d", "#00776d")
    modes = ("stock", "cumulative")
    cpu = [[first["runs"][mode]["worker"]["solve"]["cpu_s"] for mode in modes],
           [confirmed["original_stock_solve_cpu_s"], confirmed["candidate_solve_cpu_s"]]]
    errors = []
    for arm in ("c0", "fitted_c"):
        errors.append([first["scores"]["horizontal_error_km"][mode][arm] for mode in modes])
    for arm in ("c0", "fitted_c"):
        errors.append([second["runs"][mode]["horizontal_error_km"][arm] for mode in modes])
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.55), gridspec_kw={"wspace": .62})
    fig.subplots_adjust(left=.11, right=.98, top=.72, bottom=.18)
    fig.suptitle("The solver sped up on both recordings. Its position error diverged.",
                 x=.018, y=.98, ha="left", fontsize=17, fontweight="bold", color="#20354a")
    fig.legend([Patch(color=color) for color in colors], ["ALGO08v3", "Cumulative solver"],
               loc="upper left", bbox_to_anchor=(.012, .908), ncol=2, frameon=False)
    specs = ((axes[0], "Numerical solver CPU", "Seconds", ["DS30-0316", "DS30-0160"], cpu, 16.8),
             (axes[1], "Horizontal position error", "Kilometres",
              ["0316 · fixed c = 0", "0316 · fitted c", "0160 · fixed c = 0", "0160 · fitted c"], errors, 2.35))
    for ax, title, xlabel, labels, rows, limit in specs:
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel(xlabel)
        ax.set_xlim(0, limit)
        ax.set_yticks(range(len(labels)), labels)
        ax.set_ylim(len(rows) - .53, -.53)
        ax.grid(axis="x", alpha=.15)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        for i, pair in enumerate(rows):
            for value, color, offset in zip(pair, colors, (-.18, .18), strict=True):
                ax.barh(i + offset, value, height=.31, color=color)
                ax.text(value + .015 * limit, i + offset, f"{value:.2f}", va="center", fontsize=9)
    fig.text(.018, .03, "Each comparison uses the same signed detector output. DS30-0160 CPU uses the separate successful candidate replay.",
             fontsize=9, color="#405264")
    fig.savefig(output, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    figure(DATA.parent / "development/saved-solver-transfer.png")
