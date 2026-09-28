"""Plot held-window orbit-increment scores and frozen negative controls."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent

SERIES = (
    ("T − reference", "held_frequency:orbit_increment_T-causal_reference", "model"),
    ("T − D", "held_frequency:orbit_increment_T-D", "geometry_gain"),
    ("T − S", "held_frequency:orbit_increment_T-S", "geometry_gain"),
    (
        "orbit T − static T",
        "held_frequency:orbit_increment_T-static_causal_T",
        "kernel",
    ),
    ("T − zero motion", "held_frequency:orbit_increment_T-T_zero_motion", "motion"),
    ("T − reverse motion", "held_frequency:orbit_increment_T-T_reverse_motion", "motion"),
    ("T − RX swap", "held_frequency:orbit_increment_T-T_swap", "geometry_control"),
    (
        "T − geometry permute",
        "held_frequency:orbit_increment_T-T_geometry_permute",
        "geometry_control",
    ),
    (
        "T − geometry reverse",
        "held_frequency:orbit_increment_T-T_geometry_reverse",
        "geometry_control",
    ),
)

COLORS = {
    "model": "#334e68",
    "geometry_gain": "#2a9d8f",
    "kernel": "#6a4c93",
    "motion": "#e76f51",
    "geometry_control": "#e9c46a",
}


def _load(path):
    document = json.loads(path.read_text())
    if document.get("schema") != "rx-orbit-increment-score/v1" or document.get(
        "status"
    ) != "complete":
        raise ValueError(f"invalid orbit-increment score: {path}")
    if document.get("coverage", {}).get("recordings") != 4:
        raise ValueError(f"expected four equal-weight recordings: {path}")
    return document


def _values(document, key):
    row = document.get("aggregate_equal_record", {}).get(key)
    if row is None or row.get("eligible_recordings") != 4:
        raise ValueError(f"missing four-record aggregate {key}")
    values = row.get("records", {})
    if len(values) != 4 or any(not np.isfinite(value) for value in values.values()):
        raise ValueError(f"invalid per-record values for {key}")
    mean = float(np.mean(list(values.values())))
    if not np.isclose(mean, row["equal_record_mean"], rtol=0, atol=1e-12):
        raise ValueError(f"equal-record mean mismatch for {key}")
    return mean, list(values.values())


def plot(pilot, ds8, output_stem):
    documents = (("Original pilot evaluation", pilot), ("DS8 transfer (previously explored)", ds8))
    figure, axes = plt.subplots(2, 1, figsize=(13.5, 8.5), sharex=True, constrained_layout=True)
    positions = np.arange(len(SERIES))
    for axis, (title, document) in zip(axes, documents, strict=True):
        means, points = [], []
        for _, key, _ in SERIES:
            mean, values = _values(document, key)
            means.append(mean)
            points.append(values)
        colors = [COLORS[group] for _, _, group in SERIES]
        axis.bar(positions, means, color=colors, edgecolor="#263238", linewidth=0.6, width=0.72)
        offsets = np.linspace(-0.19, 0.19, 4)
        for position, values in zip(positions, points, strict=True):
            axis.scatter(
                position + offsets,
                values,
                s=24,
                facecolor="white",
                edgecolor="#263238",
                linewidth=0.7,
                zorder=3,
            )
        axis.axhline(0, color="#455a64", linewidth=0.9)
        axis.axvline(3.5, color="#90a4ae", linewidth=0.8, linestyle="--")
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_ylabel("held log score / window")
        axis.grid(axis="y", color="#cfd8dc", linewidth=0.6, alpha=0.7)
        axis.set_axisbelow(True)
        axis.text(
            1.5,
            1.005,
            "model and geometry gains",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8.5,
            color="#455a64",
        )
        axis.text(
            6.0,
            1.005,
            "frozen motion and geometry controls",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8.5,
            color="#455a64",
        )
    axes[-1].set_xticks(positions, [label for label, _, _ in SERIES], rotation=25, ha="right")
    figure.suptitle(
        "Causal orbit-increment geometry: held-window evidence and controls",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.002,
        "Bars are equal-record means; points are the four recording-level means. "
        "Motion controls alter the frequency kernel; geometry controls retain that kernel.",
        ha="center",
        fontsize=9,
        color="#455a64",
    )
    figure.savefig(output_stem.with_suffix(".png"), dpi=180)
    figure.savefig(output_stem.with_suffix(".svg"))
    plt.close(figure)


def main():
    plot(_load(HERE / "pilot.json"), _load(HERE / "ds8.json"), HERE / "orbit_increment")


if __name__ == "__main__":
    main()
