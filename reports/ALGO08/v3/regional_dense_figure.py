"""Plot the measured dense saved pair and the required reader rate for the frozen stages."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from acquisition_throughput import minimum_rate
from regional_dense_budget import select

HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def draw():
    rows = json.loads((DATA / "regional-dense-pair.json").read_bytes())["runs"]
    budget = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    inventory = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.8, 3.9), layout="constrained")
    for idx, (arm, color) in enumerate((("original", "#334a69"), ("native", "#087c69"))):
        row = rows[arm]
        vals = [row["proof_cpu_s"], row["solve_cpu_s"], row["process"]["cpu_s"]]
        bars = left.bar([x + (idx - .5) * .36 for x in range(3)], vals, width=.34, color=color, label=arm.title())
        left.bar_label(bars, fmt="%.1f", fontsize=8, padding=3)
    left.set_xticks([0, 1, 2], ["Region check", "Whole solve", "Through exit"])
    left.set_ylabel("CPU seconds")
    left.set_ylim(0, 40)
    left.set_title("DS30-0008  ·  saved detections", loc="left", fontweight="bold")
    left.legend(frameon=False, ncol=2, loc="upper left")
    xvals = list(range(0, 33))
    for n, color in (("4", "#9b5718"), ("16", "#75499c"), ("55", "#277482")):
        panel = select(inventory, budget["panels"][n]["cases"])
        rates = []
        for seconds in xvals:
            fraction = seconds / budget["historical_installed_solve_cpu_s"]
            requirements = [minimum_rate(panel, fraction, g, startup_s=budget["common_charge_s"]) for g in (0, 1)]
            rates.append(max(requirements) if None not in requirements else float("nan"))
        right.plot(xvals, rates, label=f"{n} recordings", color=color, lw=2)
        right.scatter(budget["solve_cpu_s"], max(budget["panels"][n]["required_MB_s_by_gate"]), color=color, s=22)
    right.axhline(231.52, ls=":", color="#363636", lw=1)
    right.text(.7, 236, "Fastest 192-visit prefix", fontsize=8)
    right.axhline(135.35, ls=":", color="#363636", lw=1)
    right.text(.7, 139, "Observed full dense recording", fontsize=8)
    right.set(xlabel="Assumed dense solve CPU (s)", ylabel="Required input rate (MB/s)", ylim=(125, 370))
    right.set_title("Reader rate needed for both 2× gates", loc="left", fontweight="bold")
    right.legend(frameon=False, fontsize=8, loc="upper left")
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False)
        axis.yaxis.grid(True, color="#d8dddf", lw=.6)
        axis.set_axisbelow(True)
    fig.savefig(HERE / "development/regional-dense-pair.png", dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    draw()
