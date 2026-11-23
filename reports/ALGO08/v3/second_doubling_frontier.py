"""Draw the joint acquisition and solving budget from the 55 archived v3 process clocks."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from retained_wait import gates, threshold


LEDGER = Path(__file__).parent / "measurements/acquisition-throughput.json"
LEDGER_SHA = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"


def render(output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    data = LEDGER.read_bytes()
    if sha256(data).hexdigest() != LEDGER_SHA:
        raise ValueError("Archived stage clocks differ")
    rows = json.loads(data)["rows"]
    solver_saved = list(range(0, 101, 2))
    acquisition_needed = [100 * (1 - threshold(rows, 1-s/100, "scale_elapsed")) for s in solver_saved]
    fig, ax = plt.subplots(figsize=(8.5, 4.5), layout="constrained")
    ax.fill_between(solver_saved, acquisition_needed, 100, color="#d6eee6")
    ax.plot(solver_saved, acquisition_needed, color="#187362", linewidth=2.5)
    ax.text(44, 85, "Both timing gates pass in the model", color="#195b4e", ha="center")
    for x, y, label, offset in ((50, 50, "Halve both stages", (5, -18)), (60, 55, "Design target", (8, 6))):
        ratios = gates(rows, 1-y/100, 1-x/100, "scale_elapsed")
        ax.scatter(x, y, c="#174e77" if max(ratios) <= .5 else "#ab531b", s=44, zorder=3)
        ax.annotate(label, (x, y), xytext=offset, textcoords="offset points", fontsize=9)
    ax.set(xlim=(0, 100), ylim=(0, 100), xlabel="Reduction in detections-to-decision wall time",
           ylabel="Reduction in launch-to-detections wall time")
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=100))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    ax.set_title("What a second single-core doubling requires", loc="left", weight="bold", pad=13)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.13)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)

    # A hindsight limit for improvements confined to the 13 longest solves.
    cases = sorted((r for r in rows if r["stages"][0]), key=lambda r: r["stages"][1], reverse=True)
    long_solves = {row["case"] for row in cases[:13]}
    base = [sum(r["stages"]) for r in rows]
    for a in (1., .5):
        times = [a*r["stages"][0] + (0 if r["case"] in long_solves else r["stages"][1]) + r["stages"][2]
                 for r in rows]
        print(a, median(t/b for t, b in zip(times, base, strict=True)), sum(times)/sum(base))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    render(cli.parse_args().output)
