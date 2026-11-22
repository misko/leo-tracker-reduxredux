"""Evaluate a constraint-boundary diagnostic using locked positions and public simulations."""
import argparse
import csv
import hashlib
import json
from math import cos, radians, ulp
from pathlib import Path

from tools.pipeline_eval.scoring import ARMS, distance_km


HERE = Path(__file__).resolve().parent
REGIONAL = HERE.parent / "regional-release"


def on_face(point, offer):
    if point is None:
        return False
    (lat, lon), (a, b) = point, offer["center"]
    scales = (111., 111.32 * cos(radians(a)))
    tolerance = 32 * max(ulp(float(v))*scale for v,scale in ((lat,scales[0]),(a,scales[0]),(lon,scales[1]),(b,scales[1])))
    gap = offer["width_km"]/2 - max(abs((lat-a)*scales[0]), abs((lon-b)*scales[1]))
    return gap <= tolerance


def near_offer(recording, truth, width):
    # Select the face before looking at either solver result.
    tag = hashlib.sha256(recording.encode()).digest()[0]
    axis, sign = tag % 2, (1 if tag & 2 else -1)
    center = list(truth)
    scale = 111. if axis == 0 else 111.32 * cos(radians(truth[0]))
    center[axis] += sign * (width/2 - .1) / scale
    return dict(center=center, width_km=width)


def plot(output):
    import gzip
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    with gzip.open(HERE / "measurements/edge-solvers.json.gz", "rt") as stream:
        trials = json.load(stream)
    with (REGIONAL / "blind-scores.csv").open() as stream:
        historical = list(csv.DictReader(stream))
    keys = json.loads((REGIONAL / "scoring-key.json").read_bytes())["answers"]
    keys_by_recording = {r["recording"]: r["truth"] for r in keys.values()}
    rows = ["Containing", "100 m inside", "1.5 km outside", "52.5 km outside"]
    colors = ["#27477a", "#b45623"]
    fig, axes = plt.subplots(1, 2, sharex=True, sharey=True, figsize=(9, 3.8))
    for ax, site, recording in zip(axes, ["north", "south"],
            ["0abe7b4514be674d9f5388e3", "6bd1f26bfa0bedfcf3f100f8"], strict=True):
        solver = trials[f"{site}-solver.json"]
        offer = trials[f"{recording}.json"]
        for arm, color, delta in zip(ARMS, colors, [-.10, .10], strict=True):
            point = solver["decision"]["arms"][arm]["latlon"]
            points = [(1, distance_km(point, keys_by_recording[recording]), on_face(point, offer))]
            for row in historical:
                if row["site"] == site:
                    index = {"containing": 0, "omitted": 2, "far": 3}[row["condition"]]
                    points.append((index, float(row[arm+"_km"]), abs(float(row[arm+"_edge_distance_km"])) < 1e-8))
            for index, error, clipped in points:
                ax.scatter(error, index+delta, marker="X" if clipped else "o", color=color, s=57)
        ax.set(xscale="log", title=site.capitalize()+" simulation", xlabel="Horizontal error (km)")
        ax.set_xlim(.075, 90)
        ax.set_xticks([.1, 1, 10, 50], labels=["0.1", "1", "10", "50"])
        ax.grid(axis="x", alpha=.25)
    axes[0].set_yticks(range(4), labels=rows)
    axes[0].invert_yaxis()
    legend = [Line2D([], [], color=c, lw=3, label=s) for c, s in zip(colors, ["Fixed zero", "Fitted calibration"])]
    legend.extend(Line2D([], [], marker=m, ls="", color="#444", label=s)
                  for m, s in [("o", "Interior fix"), ("X", "Boundary fix")])
    fig.legend(handles=legend, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("A boundary fix can occur even when the receiver is inside the search region")
    fig.tight_layout(rect=(0, .09, 1, .94))
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("station_offer", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--plot", type=Path, help="Plot the saved and scored regional results")
    args = parser.parse_args()
    if args.plot:
        plot(args.plot)
        return
    if not args.station_offer or not args.output:
        parser.error("supply station_offer and output to generate the development offers")
    args.output.mkdir(exist_ok=False)
    station = json.loads(args.station_offer.read_bytes())
    with (REGIONAL/"ds30-replay.csv").open() as stream:
        physical = {}
        for r in csv.DictReader(stream):
            arms = physical.setdefault(r["case"], {})
            arms[r["arm"]] = (on_face((float(r["latitude"]), float(r["longitude"])), station)
                              if r["state"] == "ok" else None)
    keys = json.loads((REGIONAL/"scoring-key.json").read_bytes())["answers"]
    known = json.loads((REGIONAL/"predictions.json").read_bytes())["rows"]
    cases = []
    for r in known:
        offer, label = r["region"], keys[r["offer"]]
        cases.append(dict(recording=r["recording"], condition=label["condition"],
                          clipped={arm:on_face(r["arms"][arm]["latlon"],offer) for arm in ARMS}))
        if label["condition"] == "containing":
            (args.output/(r["recording"]+".json")).write_text(
                json.dumps(near_offer(r["recording"], label["truth"], offer["width_km"])) + "\n")
    fixed = [arms for arms in physical.values() if all(arms.get(a) is not None for a in ARMS)]
    print(json.dumps(dict(assigned=len(physical), fixed=len(fixed), any_face=sum(any(s.values()) for s in fixed),
                          both_faces=sum(all(s.values()) for s in fixed), public_regressions=cases), indent=2))


if __name__ == "__main__":
    main()
