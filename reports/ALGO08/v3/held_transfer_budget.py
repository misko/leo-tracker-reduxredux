"""Compare through-exit clocks and location accuracy in the two sealed transfers."""

import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"


def load(name):
    path = MEASUREMENTS / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as source:
            return json.load(source)
    return json.loads(path.read_text())


def row(site, named, candidate, raw, old, new):
    phases = raw["phases"]
    acquisition = phases["authenticated_raw_acquisition"]["elapsed_s"]
    finish = phases["decision_and_publication"]["elapsed_s"]
    return {
        "site": site,
        "named": named,
        "candidate": candidate,
        "acquisition": acquisition,
        "finish": finish,
        "other": candidate - acquisition - finish,
        "gap": candidate - named / 2,
        "cfo_cpu": raw["receiver_audit"]["native"]["cfo_refinement"]["cpu_ns"] / 1e9,
        "errors_m": [(old[a]["error_km"] * 1000, new[a]["error_km"] * 1000)
                     for a in ("c0", "fitted_c")],
    }


def comparisons():
    north = load("joint-held-north-raw-sealed.json.gz")
    scores = load("joint-held-north-raw-score.json")["outcomes"]
    south = load("south-cfo-route.json.gz")
    case = south["cases"]["containing"]
    return [
        row("North", north["stock_clock"]["elapsed_s"], north["clock"]["elapsed_s"],
            north["raw"], scores["named"], scores["joint_held"]),
        row("South", case["named_historical"]["raw_elapsed_s"], case["clock"]["elapsed_s"],
            south["raw"], case["named"], case["arms"]),
    ]


def draw(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, (time, error) = plt.subplots(1, 2, figsize=(10, 4.7))
    fig.subplots_adjust(left=.11, right=.97, top=.72, bottom=.25, wspace=.38)
    navy, teal, gold, grey = "#344767", "#087e78", "#d59638", "#cdd6df"
    for i, data in enumerate(rows):
        y = 2 - 2 * i
        time.barh(y + .24, data["named"], height=.33, color=navy)
        left = 0
        for field, color in (("acquisition", teal), ("finish", gold), ("other", grey)):
            time.barh(y - .22, data[field], left=left, height=.33, color=color)
            left += data[field]
        target = data["named"] / 2
        time.vlines(target, y - .53, y + .02, color="#19222d", lw=2)
        for j, (before, after) in enumerate(data["errors_m"]):
            ey = y + .25 - .54 * j
            error.plot([before, after], [ey, ey], color=grey, lw=2)
            error.scatter(before, ey, s=55, facecolors="white", edgecolors=navy, zorder=3)
            error.scatter(after, ey, marker="D", color=teal, s=30, zorder=4)
    for ax in (time, error):
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", alpha=.2)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(-.72, 2.73)
    time.set_yticks([2, 0], ["North", "South"])
    error.set_yticks([2.25, 1.71, .25, -.29],
                     ["North · c = 0", "North · fitted", "South · c = 0", "South · fitted"])
    time.set_xlabel("Single-core elapsed time (s)")
    error.set_xlabel("Horizontal position error (m)")
    error.set_xlim(left=0)
    time.set_title("Original samples through exit", loc="left", fontweight="bold")
    error.set_title("Same containing search region", loc="left", fontweight="bold")
    fig.text(.06, .92, "Two geographic transfers against ALGO08v3", fontsize=19, weight="bold")
    fig.text(.06, .85, "One simulated recording per site. Each baseline was timed in an earlier run.", fontsize=10)
    handles = [Patch(color=c, label=l) for c, l in
               ((navy, "v3"), (teal, "Acquisition"), (gold, "Decision + publication"), (grey, "Other"))]
    handles.append(Line2D([], [], color="black", marker="|", markersize=13, linestyle="", label="Half v3 time"))
    time.legend(handles=handles, loc="upper left", fontsize=8, ncol=2,
                frameon=False, bbox_to_anchor=(-.15, -.24))
    error.legend(handles=[
        Line2D([], [], marker="o", color=navy, markerfacecolor="white", linestyle="", label="ALGO08v3"),
        Line2D([], [], marker="D", color=teal, linestyle="", label="Candidate")],
        loc="upper left", bbox_to_anchor=(0, -.24), fontsize=8, frameon=False, ncol=2)
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    draw(comparisons(), HERE / "development" / "held-transfer-budget.png")
