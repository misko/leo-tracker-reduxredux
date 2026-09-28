"""Plot six-fold nominal-beam transfer contrasts from frozen fold artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROLES = ("reception", "held_frequency")
SERIES = (
    ("B − reference", "B", None, "model"),
    ("B − E", "B", "E", "increment"),
    ("B − D", "B", "D", "increment"),
    ("B − RX swap", "B", "B_swap", "geometry_control"),
    ("B − geometry reverse", "B", "B_geometry_reverse", "geometry_control"),
    ("B − nominee permute", "B", "B_geometry_permute", "geometry_control"),
    ("B − zero motion", "B", "B_zero_motion", "motion_control"),
    ("B − reverse motion", "B", "B_reverse_motion", "motion_control"),
)
COLORS = {
    "model": "#38566f",
    "increment": "#2a9d8f",
    "geometry_control": "#e9c46a",
    "motion_control": "#e76f51",
}


def _load_folds():
    folds = [json.loads((HERE / f"fold-{index}.json").read_text()) for index in range(6)]
    if any(
        fold.get("schema") != "rx-nominal-beam-cv-fold/v1"
        or fold.get("status") != "complete"
        or fold.get("fold") != index
        for index, fold in enumerate(folds)
    ):
        raise ValueError("six complete canonical folds are required")
    sessions = [fold.get("held_session") for fold in folds]
    if len(set(sessions)) != 6:
        raise ValueError("folds do not hold out six unique recordings")
    required = {name for _, left, right, _ in SERIES for name in (left, right) if name}
    if any(set(fold.get("evaluations", {})) < required for fold in folds):
        raise ValueError("fold is missing a frozen evaluation")
    return folds


def _contrast(fold, role, left, right):
    evaluations = fold["evaluations"]
    value = evaluations[left]["roles"][role]["relative_log_score_per_window"]
    if right is not None:
        value -= evaluations[right]["roles"][role]["relative_log_score_per_window"]
    if not np.isfinite(value):
        raise ValueError("nonfinite fold contrast")
    return float(value)


def plot(folds, output_stem):
    figure, axes = plt.subplots(2, 1, figsize=(13.2, 8.2), sharex=True, constrained_layout=True)
    positions = np.arange(len(SERIES))
    offsets = np.linspace(-0.24, 0.24, len(folds))
    titles = {"reception": "Reception windows", "held_frequency": "Later held windows"}
    for axis, role in zip(axes, ROLES, strict=True):
        values = [
            [_contrast(fold, role, left, right) for fold in folds]
            for _, left, right, _ in SERIES
        ]
        means = [float(np.mean(row)) for row in values]
        axis.bar(
            positions,
            means,
            width=0.72,
            color=[COLORS[group] for _, _, _, group in SERIES],
            edgecolor="#263238",
            linewidth=0.6,
        )
        for position, row in zip(positions, values, strict=True):
            axis.scatter(
                position + offsets,
                row,
                s=22,
                facecolor="white",
                edgecolor="#263238",
                linewidth=0.7,
                zorder=3,
            )
        axis.axhline(0, color="#455a64", linewidth=0.9)
        axis.axvline(2.5, color="#90a4ae", linestyle="--", linewidth=0.8)
        axis.axvline(5.5, color="#90a4ae", linestyle="--", linewidth=0.8)
        axis.set_title(titles[role], loc="left", fontweight="bold")
        axis.set_ylabel("log score / window")
        axis.grid(axis="y", color="#cfd8dc", linewidth=0.6, alpha=0.7)
        axis.set_axisbelow(True)
        sections = (
            (1.0, "model increments"),
            (4.0, "geometry controls"),
            (6.5, "motion controls"),
        )
        for x, label in sections:
            axis.text(
                x,
                1.005,
                label,
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#455a64",
            )
    axes[-1].set_xticks(
        positions,
        [label for label, _, _, _ in SERIES],
        rotation=24,
        ha="right",
    )
    figure.suptitle(
        "Constrained nominal beam: six-record calibration transfer",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.002,
        "Bars are equal-record means; points are held-record means. Geometry controls retain the "
        "orbit kernel; motion controls retain fitted beam geometry.",
        ha="center",
        fontsize=9,
        color="#455a64",
    )
    figure.savefig(output_stem.with_suffix(".png"), dpi=180)
    figure.savefig(output_stem.with_suffix(".svg"))
    plt.close(figure)


def main():
    plot(_load_folds(), HERE / "nominal_beam_cv")


if __name__ == "__main__":
    main()
