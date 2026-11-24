"""Show the measured cost of preparing the split archive on the two physical replays."""

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def elapsed_rows(ordinary, cairo, packed, frame_scores=None):
    rows = {"Installed ALGO08v3": [], "20/8 ms": [], "20/8 ms + Cairo": [],
            "Split archive ready": [], "Split archive first use": []}
    if cairo["qualified"] is not True or packed["qualified"] is not True:
        raise ValueError("Expected qualified storage and renderer comparisons")
    if frame_scores is not None:
        if len(frame_scores) != 2 or {score["case"] for score in frame_scores} != {"DS30-0107", "DS30-0016"}:
            raise ValueError("Both enrolled compatible-archive replays are required")
        frames_by_case = {score["case"]: score for score in frame_scores}
        rows["Standard frames · full read"] = []
        rows["Standard frames · indexed read"] = []
    for case, source in (("DS30-0107", "costs"), ("DS30-0016", "positive_costs")):
        costs = packed[source]
        original = ordinary["cases"][case]
        baseline = original["stock"]["clock"]["elapsed_s"]
        if baseline != costs["stock"]["elapsed_s"] or baseline != cairo["clocks"][case]["stock"]["elapsed_s"]:
            raise ValueError("The comparisons require the same installed clocks")
        rows["Installed ALGO08v3"].append(baseline)
        rows["20/8 ms"].append(original["candidate"]["clock"]["elapsed_s"])
        rows["20/8 ms + Cairo"].append(cairo["clocks"][case]["candidate"]["elapsed_s"])
        rows["Split archive ready"].append(costs["scopes"]["ready"][0])
        rows["Split archive first use"].append(costs["scopes"]["first"][0])
        if frame_scores is not None:
            score = frames_by_case[case]
            if score["qualified"] is not True or score["historical_named"]["elapsed_s"] != baseline:
                raise ValueError("Expected qualified frame replays and the same installed comparator")
            for mode, label in (("ordinary", "Standard frames · full read"), ("frames", "Standard frames · indexed read")):
                clock = score["measured_children"][mode]["clock"]
                if clock["exit_code"] != 0 or not 0 < clock["elapsed_s"] < float("inf"):
                    raise ValueError("Expected a successful compatible-archive process clock")
                rows[label].append(clock["elapsed_s"])
    return rows


def render(rows, output):
    fig, ax = plt.subplots(figsize=(9, 1.8 + 0.4 * len(rows)), layout="constrained")
    fig.suptitle("End-to-end wall time on two physical DS30 recordings", fontweight="bold", fontsize=14)
    y = range(len(rows))
    withheld, fix = zip(*rows.values(), strict=True)
    ax.barh(y, withheld, color="#90abbe", label="DS30-0107 · withheld", height=0.65)
    ax.barh(y, fix, left=withheld, color="#234c63", label="DS30-0016 · fix", height=0.65)
    for i, times in enumerate(rows.values()):
        ax.text(sum(times) + 0.10, i, f"{sum(times):.2f} s", va="center", fontsize=10)
    baseline = sum(rows["Installed ALGO08v3"])
    for speed, color in ((2, "#9a5235"), (1.6, "#53744d")):
        ax.axvline(baseline / speed, color=color, linestyle="--", lw=1.4, label=f"{speed}× total-time target")
    ax.set_yticks(y, rows.keys())
    ax.invert_yaxis()
    ax.set_xlim(0, 1.13 * max(map(sum, rows.values())))
    ax.set_xlabel("Summed elapsed seconds")
    ax.spines[["left", "top", "right"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.48, -0.24), frameon=False, ncol=2, fontsize=9)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ordinary", type=Path)
    parser.add_argument("cairo", type=Path)
    parser.add_argument("packed", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--frame-scores", nargs=2, type=Path,
                        help="Add both complete compatible-archive scores in either order")
    args = parser.parse_args()
    receipts = []
    for path in (args.ordinary, args.cairo, args.packed, *(args.frame_scores or [])):
        data = path.read_bytes()
        receipts.append(json.loads(gzip.decompress(data) if path.suffix == ".gz" else data))
    render(elapsed_rows(*receipts[:3], frame_scores=receipts[3:] or None), args.output)
