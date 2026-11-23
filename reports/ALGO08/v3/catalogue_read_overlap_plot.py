"""Draw the measured read and prime intervals relative to each demand."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

COLORS = {
    "Actual member read": "#48637e",
    "Controlled hold": "#d9deea",
    "Paid TLE priming": "#087c70",
    "Remaining wait": "#d59638",
}


def draw(source, destination):
    rows = {r["label"]: r for r in json.loads(source.read_bytes())["runs"]}
    groups = (
        ("Warm tmpfs", "natural-a-serial", "natural-a-overlap"),
        ("Controlled hold, pair A", "controlled-a-serial", "controlled-a-overlap"),
        ("Controlled hold, pair B", "controlled-b-serial", "controlled-b-overlap"),
    )
    fig, axes = plt.subplots(3, figsize=(10.8, 6.9), layout="constrained")
    for axis, (title, serial, overlap) in zip(axes, groups, strict=True):
        labels = []
        for index, name in enumerate((serial, overlap)):
            row = rows[name]
            for j, demand in enumerate(row["demands"]):
                y = 2 * index + j
                labels.append(f"{'Serial' if index == 0 else 'Overlap'}, read {j + 1}")
                anchor = demand["start_ns"]
                member = demand["member"]
                spans = (
                    ("Controlled hold", row["controlled_holds"]),
                    ("Actual member read", row["reads"]),
                    ("Paid TLE priming", row["paid_primes"]),
                    ("Remaining wait", [dict(demand, start_ns=demand["wait_start_ns"])]),
                )
                for name, intervals in spans:
                    for event in intervals:
                        if event["member"] == member:
                            start = (event["start_ns"] - anchor) / 1e6
                            duration = (event["end_ns"] - event["start_ns"]) / 1e6
                            axis.barh(y, duration, left=start, color=COLORS[name], height=0.42)
                for hold in row["controlled_holds"]:
                    if hold["member"] == member:
                        nominal_end = (hold["start_ns"] - anchor) / 1e6 + 1e3 * row[
                            "simulated_delay_s"
                        ]
                        axis.vlines(
                            nominal_end, y - 0.32, y + 0.32, color="#515e6c", linestyle="--"
                        )
        axis.axvline(0, color="#39444e", linewidth=1, linestyle="--")
        axis.set(title=title, yticks=range(len(labels)), yticklabels=labels)
        axis.set_xlim(-65, 235 if "pair B" in title else 145 if "pair A" in title else 8)
        axis.invert_yaxis()
        axis.spines[["right", "top"]].set_visible(False)
        axis.grid(axis="x", color="#e2e7ed")
        axis.set_axisbelow(True)
    axes[-1].set_xlabel("Monotonic milliseconds relative to member demand")
    fig.legend(
        [
            *(Patch(facecolor=color) for color in COLORS.values()),
            Line2D([], [], color="#515e6c", linestyle="--"),
        ],
        [*COLORS, "Scheduled hold end"],
        loc="outside lower center",
        ncols=5,
        frameon=False,
    )
    fig.savefig(destination, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("destination", type=Path)
    args = cli.parse_args()
    draw(args.source, args.destination)
