"""Render the measured pilot-epoch forecast and its same-lane negative control."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .track_timing_trial import CASES, DEFAULT_OUT, SOURCES


def render(out):
    lock = json.loads((out / "prediction-lock.json").read_bytes())
    if any(_sha(out / file) != digest for file, digest in lock["files"].items()):
        raise ValueError("timing data changed since the prediction seal")
    with (out / "track-timing.csv").open(newline="") as stream:
        by_key = {(r["id"], r["source"]): r for r in csv.DictReader(stream)}
    if set(by_key) != {(case, s) for case in CASES for s in SOURCES}:
        raise ValueError("the figure needs every paired recording")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout="constrained")
    methods = (
        ("linear", "Past epoch slope", "#28537b"),
        ("doppler", "Doppler-corrected", "#008471"),
        ("shuffle", "Shuffled target", "#b46931"),
    )
    for axis, source in zip(axes, SOURCES, strict=True):
        rows = [by_key[case, source] for case in CASES]
        for j, (key, label, color) in enumerate(methods):
            values = [
                100 * int(r[key + "_within_2"]) / int(r["comparable"])
                if int(r["comparable"])
                else np.nan
                for r in rows
            ]
            axis.barh(
                np.arange(len(rows)) + (j - 1) * 0.21, values, height=0.19, color=color, label=label
            )
        axis.set_yticks(np.arange(len(rows)), [f"{r['id']}  (n={r['comparable']})" for r in rows])
        axis.invert_yaxis()
        axis.set_xlim(0, 100)
        axis.set_xlabel("Forecasts within two samples (%)")
        axis.set_title({"capture-era": "Capture-era GLRT", "wide": "Four-start wide GLRT"}[source])
        axis.grid(axis="x", alpha=0.18)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
    fig.suptitle(
        "Predicting the next pilot epoch on measured Doppler tracks", fontsize=16, fontweight="bold"
    )
    fig.legend(
        *axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=3, frameon=False
    )
    fig.savefig(out / "track-timing.png", dpi=160)
    fig.savefig(out / "track-timing.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    files = [*lock["files"], "prediction-lock.json", "track-timing.png", "track-timing.pdf"]
    save_json(
        out / "result-lock.json",
        {
            "files": {name: _sha(out / name) for name in files},
            "renderer_sha256": _sha(Path(__file__)),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=local_output, default=DEFAULT_OUT)
    render(parser.parse_args().out)
