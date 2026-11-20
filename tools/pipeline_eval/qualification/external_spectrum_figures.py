"""Render passive-spectrum evidence from the sealed predictions and position score."""

import argparse
import csv
import json
from hashlib import sha256
from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from . import scout_stage_figures as stage
from .external_spectrum_trial import preserve, serialize

TITLE = "Short power-scan ridges did not locate the independent station"
BOUNDARY = "Recorded one-second mean spectral power and prior-night catalogue through tile ranking"
NOTE = (
    "Markers represent 30-minute windows with ranked locations. The later-ridge fit uses an offset "
    "selected on earlier samples. Blank rows mean the grid did not rank any location. Visibility "
    "alone supplies a geographic rank without a frequency fit."
)
METHODS = {
    "spectrum": "Measured spectrum",
    "directional": "+ fixed antenna constraint",
    "time_shuffle": "Shifted ridge times",
    "oneweb": "OneWeb elements",
    "geometry": "Visibility only",
    "off_band": "Off-frequency IF",
    "no_detection": "No detections",
}
WINDOW_STYLES = ("o", "s", "^", "D", "P", "X")


def table(rows):
    stream = StringIO(newline="")
    columns = (
        "window",
        "mode",
        "ridges",
        "support",
        "margin",
        "early_khz",
        "held_khz",
        "forced_error_km",
        "true_tile_better",
        "present_forced_error_km",
        "present_published",
        "omitted_forced_error_km",
        "omitted_published",
    )
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for result in rows:
        row = {c: result.get(c) for c in columns}
        for condition in ("present", "omitted"):
            for name in ("forced_error_km", "published"):
                row[f"{condition}_{name}"] = result[condition][name]
        writer.writerow(row)
    return stream.getvalue().encode()


def render(report):
    stage.verify(report, "prediction-lock.json")
    results = json.loads((report / "scores.json").read_bytes())
    rows = results["rows"]
    windows = sorted({row["window"] for row in rows})
    markers = dict(zip(windows, WINDOW_STYLES, strict=True))
    fig, (freq, geo) = stage.canvas(
        TITLE, "Four held Ku-band windows and two off-frequency controls", NOTE
    )
    fig.subplots_adjust(bottom=0.28)
    y_index = {key: i for i, key in enumerate(METHODS)}
    maximum_khz = max((r["held_khz"] for r in rows if r["held_khz"] is not None), default=1)
    maximum_km = max(
        (r["forced_error_km"] for r in rows if r["forced_error_km"] is not None), default=1
    )
    stage.header(
        freq,
        "Later-ridge frequency fit",
        "Median RMS residual (kHz)",
        list(METHODS.values()),
        maximum_khz * 1.15,
    )
    stage.header(
        geo,
        "Position from broad grid rank",
        "Forced position error (km)",
        [""] * len(METHODS),
        maximum_km * 1.15,
    )
    for row in rows:
        mode = row["mode"]
        y = y_index[mode] + (windows.index(row["window"]) - 2.5) * 0.095
        color = stage.CANDIDATE if mode == "spectrum" else stage.DIAGNOSTIC
        for ax, value in ((freq, row["held_khz"]), (geo, row["forced_error_km"])):
            if value is not None:
                ax.scatter(
                    value,
                    y,
                    marker=markers[row["window"]],
                    s=48,
                    color=color,
                    edgecolor="white",
                    linewidth=0.5,
                    zorder=3,
                )
    fig.legend(
        handles=[
            Line2D(
                [0],
                [0],
                color=stage.SECONDARY,
                ls="",
                marker=markers[name],
                label=f"Mar {name[4:6]} {name[-2:]} UTC",
            )
            for name in windows
        ],
        loc="lower left",
        bbox_to_anchor=(0.05, 0.145),
        ncol=6,
        frameon=False,
        fontsize=9,
    )
    fig.savefig(report / "external-spectrum.png", dpi=170)
    fig.savefig(report / "external-spectrum.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    preserve(report / "external-spectrum.csv", table(rows))
    description = dict(
        version=1,
        id="watson-external-spectrum",
        title=TITLE,
        sample="Two held days at the Watson installation, plus a recorded off-frequency IF",
        boundary=BOUNDARY,
        note=NOTE,
        seal="stage-figure-lock.json",
        image="external-spectrum.png",
        pdf="external-spectrum.pdf",
        csv="external-spectrum.csv",
    )
    preserve(report / "stage-figure.json", serialize(description))
    names = [description[key] for key in ("image", "pdf", "csv")] + [
        "prediction-lock.json",
        "scores.json",
    ]
    preserve(
        report / description["seal"],
        serialize(
            dict(files={name: sha256((report / name).read_bytes()).hexdigest() for name in names})
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    render(parser.parse_args().report)


if __name__ == "__main__":
    main()
