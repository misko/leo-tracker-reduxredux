"""Render a presentation-only view of the sealed whole-replay stage."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

from .native_pruning_whole import REPORT, ROLES

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(report=REPORT):
    raw = report / "raw-lock.json"
    files = ("native-stages.csv", *(f"{role}-raw.json" for role in ROLES))
    expected = json.loads(raw.read_bytes())["files"]
    for name in files:
        if digest(report / name) != expected[name]:
            raise ValueError(f"sealed timing source changed: {name}")
    with (report / files[0]).open(newline="") as stream:
        stages = {r["role"]: r for r in csv.DictReader(stream) if r["stage"] == "coarse"}
    timing = [json.loads((report / name).read_bytes()) for name in files[1:]]

    figure, (coarse, deadline) = plt.subplots(1, 2, figsize=(10.1, 4.65))
    green, blue, black = "#167f73", "#52728b", "#30343b"
    coarse.bar([0, 1], [float(stages[r]["p50"]) for r in ROLES], width=0.56, color=green)
    coarse.scatter(
        [0, 1], [float(stages[r]["p95"]) for r in ROLES], color=black, marker="D", zorder=3
    )
    coarse.set_ylabel("Summed coarse CPU (ms)")
    for i, row in enumerate(timing):
        denominator = row["native_packets_emitted"]
        for off, key, color in (
            (-0.17, "native_within_20ms", green),
            (0.17, "age_within_20ms", blue),
        ):
            deadline.bar(i + off, 100 * row[key] / denominator, width=0.31, color=color)
    deadline.set_ylabel("Emissions at or below 20 ms (%)")
    deadline.set_ylim(0, 103)
    for axis in (coarse, deadline):
        axis.set_xticks([0, 1], ["Active set", "Dense"])
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.2)

    legend = dict(loc="center", ncol=2, frameon=False, fontsize=9)
    figure.legend(
        [Patch(color=green), Line2D([], [], color=black, marker="D", linestyle="")],
        ["Median", "95th percentile"],
        bbox_to_anchor=(0.28, 0.075),
        **legend,
    )
    figure.legend(
        [Patch(color=green), Patch(color=blue)],
        ["Detector", "Arrival to emission"],
        bbox_to_anchor=(0.76, 0.075),
        **legend,
    )
    figure.text(
        0.08,
        0.93,
        "Four-region GLRT at the recorded pace",
        va="top",
        fontsize=17,
        fontweight="bold",
    )
    figure.text(
        0.08,
        0.85,
        "DS26-0197 · Active set first, dense second · Both receivers",
        va="top",
        fontsize=10.5,
    )
    figure.subplots_adjust(left=0.10, right=0.98, top=0.77, bottom=0.23, wspace=0.34)
    names = ("stage-presentation.png", "stage-presentation.pdf")
    figure.savefig(report / names[0], dpi=170)
    figure.savefig(report / names[1], metadata={"CreationDate": None, "ModDate": None})
    plt.close(figure)
    paths = (raw.name, *files, *names)
    (report / "stage-presentation-lock.json").write_text(
        json.dumps(
            dict(
                files={name: digest(report / name) for name in paths},
                publisher_sha256=digest(Path(__file__)),
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    render()
