"""Draw measured two-sided peak selections and the strict availability ceiling."""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output, save_json
from . import bracketed_peak_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file


def table(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def render(out):
    for name in ("measurement-lock.json", "availability-lock.json", "selection-lock.json"):
        for entry, expected in trial.read(out / name)["files"].items():
            if _sha(out / entry) != expected:
                raise ValueError(f"the sealed {entry} changed")
    measures = {(r["id"], r["mode"]): r for r in table(out / "bracketed-peaks.csv")}
    available = table(out / "availability.csv")
    if {r["id"] for r in available} != set(trial.CASES) or len(available) != len(trial.CASES):
        raise ValueError("incomplete availability roster")

    def total(column):
        return sum(int(r[column]) for r in available)

    cases = trial.CASES
    actual = [int(measures[k, "bracketed"]["selected"]) for k in cases]
    matched = [int(measures[k, "bracketed"]["same_capture_winner"]) for k in cases]
    sham = [int(measures[k, "sham"]["selected"]) for k in cases]
    n = total("capture_positive_wide_negative")
    stages = {
        "Capture-only detections": n,
        "Any complete wide peak": n - total("no_complete_row"),
        "Epoch within 2 samples": n - total("no_complete_row") - total("no_near_epoch"),
        "Epoch and CFO match": total("family_nonpositive_margin") + total("family_positive_margin"),
        "Also has positive margin": total("family_positive_margin"),
        "Recovered by the selector": sum(matched),
    }
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.1, 5), gridspec_kw={"width_ratios": [1, 1.25]})
    fig.subplots_adjust(left=0.105, right=0.953, bottom=0.18, top=0.78, wspace=0.75)
    y = np.arange(len(cases))
    ax.barh(
        y,
        np.array(actual) - matched,
        left=matched,
        color="#a8b6c8",
        height=0.52,
        label="Other measured peak",
    )
    ax.barh(y, matched, color="#008675", height=0.52, label="Capture-era match")
    ax.scatter(
        sham, y, marker="|", color="#a3571e", s=105, linewidths=2.3, label="Half-frame control"
    )
    ax.set(
        yticks=y,
        yticklabels=cases,
        xlim=(-0.16, max(actual) + 0.7),
        xticks=range(max(actual) + 1),
        xlabel="Probes with a new detection",
    )
    ax.invert_yaxis()
    ax.set_title("Fixed-lag selections", loc="left", fontsize=13, fontweight="bold")
    positions = np.arange(len(stages))
    bx.hlines(positions, 1, list(stages.values()), color="#bcc7ce", lw=2.6)
    bx.scatter(
        list(stages.values()), positions, s=53, color=["#375473"] * 3 + ["#008675"] * 3, zorder=3
    )
    for at, count in enumerate(stages.values()):
        bx.annotate(
            f"{count:,}",
            (count, at),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    bx.set_xscale("log")
    bx.set(
        yticks=positions,
        yticklabels=list(stages),
        xlim=(0.85, 5500),
        xticks=[1, 10, 100, 1000],
        xticklabels=["1", "10", "100", "1,000"],
        xlabel="Probes across all eight recordings (log scale)",
    )
    bx.invert_yaxis()
    bx.set_title("What the wide detector exported", loc="left", fontsize=13, fontweight="bold")
    for axis in (ax, bx):
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="both", length=0)
        axis.set_axisbelow(True)
        axis.grid(True, axis="x", color="#e1e8ea", lw=0.8)
    fig.text(
        0.025,
        0.946,
        "Most missed pilots have no matching exported peak",
        fontsize=20,
        fontweight="bold",
        color="#182e37",
    )
    fig.text(
        0.025, 0.896, "Eight roof recordings  ·  104,162 receiver probes  ·  10 MS/s", fontsize=10.5
    )
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(-0.32, -0.13),
        frameon=False,
        ncol=3,
        columnspacing=1.25,
        fontsize=8,
    )
    fig.text(
        0.025,
        0.026,
        "The capture-era detector is a reference. Agreement requires a measured peak "
        "within two samples and 1 kHz after folding CFO.",
        fontsize=9,
        color="#425761",
    )
    stem = "bracketed-peaks"
    fig.savefig(out / f"{stem}.png", dpi=180, facecolor="white")
    fig.savefig(out / f"{stem}.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    values = [
        dict(panel="weak-peak selection", recording=case, measurement=title, count=count)
        for case, a, m, z in zip(cases, actual, matched, sham, strict=True)
        for title, count in (("Selected", a), ("Capture-era matches", m), ("Half-frame control", z))
    ]
    values.extend(
        dict(panel="Availability", recording="All eight", measurement=k, count=v)
        for k, v in stages.items()
    )
    csv_file(out / "figure-rows.csv", values)
    filenames = (
        "bracketed-peaks.png",
        "bracketed-peaks.pdf",
        "figure-rows.csv",
        "selection.csv",
        "bracketed-peaks.csv",
        "availability.csv",
        "selection-lock.json",
        "measurement-lock.json",
        "availability-lock.json",
    )
    save_json(
        out / "result-lock.json",
        dict(files={f: _sha(out / f) for f in filenames}, renderer_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    render(parser.parse_args().out)
