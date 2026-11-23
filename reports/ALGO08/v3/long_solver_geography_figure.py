"""Plot saved-solver latency separately from the refined receiver's location transfer."""

import argparse
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def receipt(name):
    with gzip.open(HERE / "measurements" / (name + ".json.gz"), "rt") as f:
        return json.load(f)


def comparisons():
    medium = receipt("family-endpoint-transfer-0169")["results"]
    long = receipt("named-final-0374")["pair"]["runs"]
    dense = receipt("named-survivor-fit-0402")
    timings = [
        ("DS30-0169", medium["stock"]["process"]["elapsed_s"], medium["combined"]["process"]["elapsed_s"]),
        ("DS30-0374", long["stock"]["process"]["elapsed_s"], long["combined"]["process"]["elapsed_s"]),
        ("DS30-0402", dense["comparator_process"]["named"]["elapsed_s"], dense["clocks"]["fixed"]["timing"]["elapsed_s"]),
    ]
    roof = receipt("raw-cfo-0016")["geographic"]["runs"]
    north = receipt("raw-cfo-north")["cases"]["containing"]
    deltas = {}
    for arm in ("c0", "fitted_c"):
        deltas[arm] = [1000 * (roof["refined"]["horizontal_error_km"][arm] - roof["named"]["horizontal_error_km"][arm]),
                       1000 * (north["candidate"][arm]["error_km"] - north["named"][arm]["error_km"])]
    return timings, deltas


def render(output):
    from matplotlib import pyplot as plt

    timings, deltas = comparisons()
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.2, 3.75), layout="constrained")
    for i, (case, named, current) in enumerate(timings):
        a.barh(i, current / named, height=.34, color="#20776c")
        a.text(current / named + .016, i, f"{named:.1f} → {current:.1f} s", va="center", fontsize=9)
    a.axvline(.5, color="#99542d", ls="--", lw=1.2)
    a.set(yticks=range(3), yticklabels=[r[0] for r in timings], ylim=(2.55, -.65), xlim=(0, 1.08),
          xticks=[0,.25,.5,.75,1], xticklabels=["0%", "25%", "50%", "75%", "100%"],
          xlabel="Share of named v3 elapsed time")
    a.set_title("Saved detections through process exit", loc="left", weight="bold", fontsize=12)
    b.axvline(0, color="#5b6168", lw=.8)
    b.axvline(250, color="#99542d", ls="--", lw=1.2)
    for arm, offset, label, color in (("c0", -.13, "Fixed zero", "#375577"), ("fitted_c", .13, "Fitted", "#20776c")):
        for i, delta in enumerate(deltas[arm]):
            b.barh(i + offset, delta, height=.18, color=color, label=label if i == 0 else None)
            left = delta < 0
            b.text(delta + (-12 if left else 12), i + offset, f"{delta:+.0f}", va="center",
                   ha="right" if left else "left", fontsize=9)
    b.set(yticks=[0, 1], yticklabels=["DS30-0016\nphysical", "North\nsimulated"], ylim=(1.63, -.64),
          xlim=(-800,540), xlabel="Change in horizontal error vs named v3 (m)")
    b.set_title("Refined receiver on containing regions", loc="left", weight="bold", fontsize=12)
    b.legend(loc="lower left", frameon=False, fontsize=9, ncols=2)
    for ax in (a, b):
        ax.spines[["top","right","left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", alpha=.12)
        ax.set_axisbelow(True)
    fig.savefig(output, dpi=160, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    render(cli.parse_args().output)
