"""Render the sealed field clock and position-information diagnostics."""

import argparse
import json
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
import numpy as np

from .external_clock_trial import REPORT, digest

CLOCK_MODELS = ("fixed-utc", "50ms-utc", "500ms-utc", "free-common-utc", "free-orbit-epochs")


def plot(directory):
    lock = json.loads((directory / "results-lock.json").read_bytes())
    if any(digest(directory / name) != expected for name, expected in lock["files"].items()):
        raise ValueError("field clock evidence does not match its immutable result lock")
    rows = json.loads((directory / "results.json").read_bytes())["rows"]
    primary = [r for r in rows if r["cohort"] == "primary"]
    repeats = [r for r in rows if r["cohort"] == "repeat"]
    error = [
        [r["fixed_utc_held_rms_hz"][0], r["local_clock_held_rms_hz"], r["donor_utc_held_rms_hz"][0]]
        for r in primary
    ]
    information = [[r["information"][key]["worst_sd_km"] for key in CLOCK_MODELS] for r in primary]
    quantization = [
        [r["bin_floor_information"][key]["worst_sd_km"] for key in CLOCK_MODELS] for r in primary
    ]

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10}):
        fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12.4, 5.5), width_ratios=(0.85, 1.15))
        fig.subplots_adjust(left=0.08, right=0.98, bottom=0.18, top=0.77, wspace=0.36)
        fig.text(
            0.08,
            0.94,
            "Clock calibration across measured field sites",
            fontsize=22,
            weight="bold",
            color="#172b36",
        )
        fig.text(
            0.08,
            0.875,
            "Eight site groups and three repeat captures from one field instrument",
            fontsize=12,
            color="#3d5765",
        )

        def series(axis, lines, count, label):
            for one in lines:
                axis.plot(range(count), one, color="#a9bac2", alpha=0.75, lw=0.9, marker=".")
            middle = [median(x) for x in zip(*lines, strict=True)]
            axis.plot(range(count), middle, color="#00766c", lw=2.7, marker="o", label=label)
            axis.set_yscale("log")
            axis.grid(axis="y", color="#dce5e8", which="major")
            axis.spines[["top", "right"]].set_visible(False)

        series(ax0, error, 3, "Primary-site median")
        for i, r in enumerate(repeats):
            held = (
                r["fixed_utc_held_rms_hz"][0],
                r["local_clock_held_rms_hz"],
                r["donor_utc_held_rms_hz"][0],
            )
            ax0.scatter(
                np.arange(3) + 0.04,
                held,
                facecolors="none",
                edgecolors="#8c4860",
                s=40,
                label="Repeat capture" if i == 0 else None,
                zorder=3,
            )
        ax0.set_title("Held Doppler after clock calibration", loc="left", weight="bold", pad=11)
        ax0.set_ylabel("Held RF RMS at surveyed site (Hz)")
        ax0.set_xticks(
            range(3), ("Reported\nUTC", "Early fit\non same capture", "Clock from\nother sites")
        )
        ax0.legend(loc="upper left", frameon=False, fontsize=9)

        series(ax1, information, len(CLOCK_MODELS), "Site-excluded held residual scale")
        bins = [median(x) for x in zip(*quantization, strict=True)]
        ax1.plot(
            range(len(CLOCK_MODELS)),
            bins,
            color="#9a5426",
            lw=2,
            marker="s",
            ls="--",
            label="FFT-bin scale only",
        )
        ax1.axhline(5, color="#526e79", ls=":", lw=1, label="5 km reference")
        ax1.set_title("Local position information", loc="left", weight="bold", pad=11)
        ax1.set_ylabel("Worst-axis conditional position scale (km)")
        ax1.set_xticks(
            range(5),
            (
                "Reported UTC\nfixed",
                "50 ms\nUTC prior",
                "500 ms\nUTC prior",
                "Free\ncommon UTC",
                "Free\norbit epochs",
            ),
        )
        ax1.legend(loc="upper left", frameon=False, fontsize=9)

        caveat = "Author-supplied orbit labels and GNSS survey geometry. Both c arms coincide."
        fig.text(0.08, 0.04, caveat, fontsize=10, color="#3d5765")
        fig.savefig(directory / "field-clock-evidence.png", dpi=150, facecolor="white")
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    plot(args.out)


if __name__ == "__main__":
    main()
