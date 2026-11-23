"""Plot the effective raw acquisition rate required to halve both elapsed gates."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from regional_dense_budget import DATA, minimum_rate, select


def frontier(rows, model, dense_solve_s):
    fraction = dense_solve_s / model["historical_installed_solve_cpu_s"]
    rates = [minimum_rate(rows, fraction, gate, startup_s=model["common_charge_s"])
             for gate in (0, 1)]
    return None if None in rates else max(rates)


def render(output):
    model = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    inventory = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    fig, ax = plt.subplots(figsize=(8.3, 4.7), layout="constrained")
    costs = list(range(27))
    for size, color in [("4", "#284e82"), ("16", "#137c70")]:
        rows = select(inventory, model["panels"][size]["cases"])
        rates = [frontier(rows, model, cost) for cost in costs]
        ax.plot(costs, rates, label=f"First {size} recordings", color=color, linewidth=2.7)
    scenarios = model["panels"]["4"]["scenarios"]
    for assumption, label, color in [("observed_dense", "Whole dense recording", "#585865"),
                                     ("fastest_prefix", "Fast short prefix", "#9b622a")]:
        rate = scenarios[assumption]["reader_MB_s"]
        ax.axhline(rate, color=color, linestyle="--", linewidth=1.4)
        ax.text(0.5, rate + 2.6, f"{label} · {rate:.0f} MB/s", color=color, fontsize=9)
    ax.scatter([14], [250], marker="D", s=45, color="#23272e", zorder=3)
    ax.annotate("Design target", (14, 250), xytext=(9, 262),
                arrowprops={"arrowstyle": "-", "color": "#434953"}, fontsize=9)
    ax.set(xlabel="Dense numerical solve CPU (seconds)",
           ylabel="Effective acquisition rate (compressed MB/s)", xlim=(0, 26), ylim=(120, 325))
    ax.set_title("Acquisition rate required to halve end-to-end time", loc="left", weight="bold")
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", frameon=False)
    fig.savefig(output, dpi=165, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    render(parser.parse_args().output)
