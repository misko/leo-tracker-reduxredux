"""Score saved schedule trials and plot solver CPU and all-recording error."""

import csv
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import NullFormatter, PercentFormatter
import numpy as np

from tools.pipeline_eval.scoring import ARMS, distance_km


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0016", "DS30-0374", "north", "south")


def measurements():
    with gzip.open(HERE/"measurements/channel-schedules.json.gz", "rt") as stream:
        trials = json.load(stream)
    physical = json.loads((HERE.parents[1]/"2026_11_21_ds30_full/reference-audit.json").read_bytes())
    truth = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
             for r in physical["cases"] if r["dataset_label"] in CASES}
    key = json.loads((HERE.parent/"regional-release/scoring-key.json").read_bytes())
    sites = {"0abe7b4514be674d9f5388e3": "north", "6bd1f26bfa0bedfcf3f100f8": "south"}
    truth.update({sites[v["recording"]]: v["truth"] for v in key["answers"].values()})
    rows = []
    for item in trials:
        case, policy, receipt = item["case"], item["policy"], item["receipt"]
        decision = receipt["decision"]
        row = dict(case=case, policy=policy, flip=item["flip"], state=decision["status"],
                   reason=decision.get("reason"), cpu_s=receipt["cpu_s"])
        info = receipt.get("input", {})
        row["input_sha256"] = info.get("parent_sha256", receipt.get("native_sha256"))
        row["warmup_lanes"] = info.get("warmup_lanes", 0)
        row["retained_lanes"] = info.get("selected", {}).get("lanes")
        row["retained_factors"] = info.get("selected", {}).get("factors")
        for arm in ARMS:
            row[arm+"_km"] = distance_km(decision.get("arms", {}).get(arm, {}).get("latlon"), truth[case])
        rows.append(row)
    for case in CASES:
        group = [r for r in rows if r["case"] == case]
        assert len({r["input_sha256"] for r in group}) == 1
        assert sum(r["policy"] == "all" for r in group) == 1
    return rows


def main():
    rows = measurements()
    with (HERE/"measurements/channel-schedules.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    fig, (time_ax, error_ax) = plt.subplots(1, 2, figsize=(10, 4))
    colors = ("#253964", "#00766c")
    for idx, (policy, label, color) in enumerate(zip(("all", "first-last-quarters"),
            ("All visits", "First and last quarters"), colors, strict=True)):
        data = [next(r for r in rows if r["case"] == c and r["policy"] == policy) for c in CASES]
        bars = time_ax.bar(np.arange(4)+(idx-.5)*.36, [r["cpu_s"] for r in data], .36, color=color, label=label)
        for bar, row in zip(bars, data, strict=True):
            if row["state"] != "ok":
                time_ax.annotate("Withheld", (bar.get_x()+bar.get_width()/2, bar.get_height()),
                                 xytext=(0, 4), textcoords="offset points", ha="left", size=8, rotation=50)
        for arm, name, line in zip(ARMS, ("zero", "fitted"), ("--", "-"), strict=True):
            values = sorted(r[arm+"_km"] for r in data if r[arm+"_km"] is not None)
            error_ax.step([.5, *values, 8], [0, *np.arange(1,len(values)+1)/len(data), len(values)/len(data)],
                          where="post", color=color, linestyle=line, label=f"{label}, {name}")
    time_ax.set_xticks(range(4), ["DS30-0016", "DS30-0374", "North sim.", "South sim."], rotation=12)
    time_ax.set(ylabel="Solver and grid CPU (seconds)", title="Time from saved detections")
    time_ax.legend(frameon=False, fontsize=8)
    error_ax.set(xscale="log", xlim=(.5, 8), ylim=(-.02, 1.03), xlabel="Horizontal error (km)",
                 ylabel="Fraction of four assigned recordings", title="Cumulative position error")
    error_ax.set_xticks([.5, 1, 2, 4, 8], labels=["0.5", "1", "2", "4", "8"])
    error_ax.xaxis.set_minor_formatter(NullFormatter())
    error_ax.set_yticks([0, .25, .5, .75, 1.])
    error_ax.yaxis.set_major_formatter(PercentFormatter(1))
    error_ax.legend(frameon=False, fontsize=8, loc="lower right")
    for ax in (time_ax, error_ax):
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
    fig.tight_layout()
    fig.savefig(HERE/"time-arcs.png", dpi=155)
    plt.close(fig)
    plot_raw_alternation()


def plot_raw_alternation():
    pair = json.loads((HERE/"measurements/DS30-0016-alternate.json").read_bytes())
    audit = json.loads((HERE.parents[1]/"2026_11_21_ds30_full/reference-audit.json").read_bytes())
    ref = next(r["reference"] for r in audit["cases"] if r["dataset_label"] == "DS30-0016")
    truth = (ref["latitude_deg"], ref["longitude_deg"])
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4))
    for i, (label, mode, color) in enumerate([("ALGO08v2", "baseline", "#253964"),
                                               ("Alternate visits", "candidate", "#00766c")]):
        run = pair["runs"][mode]
        errors = [distance_km(run["arms"][a]["latlon"], truth) for a in ARMS]
        for ax, values in zip(axes, ([run["elapsed_s"], run["cpu_s"]], errors), strict=True):
            bars = ax.bar(np.arange(2)+(i-.5)*.37, values, width=.37, label=label, color=color)
            ax.bar_label(bars, fmt="%.2f", fontsize=9, padding=2)
    for ax, labels, unit in zip(axes, (["Elapsed", "Single-core CPU"], ["Fixed zero", "Fitted calibration"]),
                                ["Raw I/Q through eight PNGs (s)", "Horizontal error (km)"], strict=True):
        ax.set_xticks([0, 1], labels=labels)
        ax.set_ylabel(unit)
        ax.margins(y=.15)
        ax.spines[["top","right"]].set_visible(False)
    axes[0].legend(frameon=False, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.01), fontsize=9)
    fig.suptitle("DS30-0016  ·  one physical recording, both algorithms returned a fix", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(HERE/"alternate-visits.png", dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    main()
