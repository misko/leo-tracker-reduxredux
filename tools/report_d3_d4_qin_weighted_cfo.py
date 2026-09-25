#!/usr/bin/env python3
"""Plot D3/D4 GLRT windows and frame CFOs with Qin-weighted opacity."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

DEFAULT_RESULTS = Path(
    "reports/figures/2026_08_24_five_dwell_multiscale_local_rates/"
    "five-dwell-multiscale-local-rates.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_d3_d4_underlying_rates")
DEFAULT_FIGURE = DEFAULT_OUTPUT_ROOT / "d3-d4-qin-weighted-cfo.png"

PROBE_DURATION_S = 0.020
INK = "#17354a"
GRAY = "#96a2ab"
LIGHT_GRAY = "#d2d9de"
BLUE = "#2f83b7"
AMBER = "#d9881f"
RED = "#bd5b52"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_FIGURE)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def select_d3_d4(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    dwells = document.get("dwells")
    if not isinstance(dwells, list):
        raise ValueError("result does not contain a dwell list")
    selected = [
        item
        for item in dwells
        if str(item.get("spec", {}).get("label", "")).startswith(("D3 ", "D4 "))
    ]
    if len(selected) != 2:
        raise ValueError("result must contain exactly one D3 and one D4 dwell")
    return selected[0], selected[1]


def model_frequency(document: dict[str, Any], times_s: np.ndarray) -> np.ndarray:
    spec = document["spec"]
    return np.polyval(
        np.asarray(spec["branch_coefficients_hz"], dtype=float),
        np.asarray(times_s, dtype=float) - float(spec["branch_reference_time_s"]),
    )


def qin_frame_quality(frames: list[dict[str, Any]]) -> np.ndarray:
    """Return 0..1 Qin-specific confidence from exact strength and control margin.

    Both factors are required: a large exact score alone is not Qin-specific if
    the rolled control is equally large. P95 scaling prevents one exceptional
    frame from making the rest of a dwell visually transparent.
    """

    exact = np.asarray([float(item["train_exact_score"]) for item in frames])
    margin = np.maximum(
        0.0,
        np.asarray([float(item["train_margin"]) for item in frames]),
    )
    positive_exact = exact[exact > 0.0]
    positive_margin = margin[margin > 0.0]
    if not len(positive_exact) or not len(positive_margin):
        return np.zeros(len(frames), dtype=float)
    exact_scale = max(float(np.percentile(positive_exact, 95)), 1e-12)
    margin_scale = max(float(np.percentile(positive_margin, 95)), 1e-12)
    exact_strength = np.clip(exact / exact_scale, 0.0, 1.0)
    qin_specificity = np.clip(margin / margin_scale, 0.0, 1.0)
    return np.sqrt(exact_strength * qin_specificity)


def frame_rgba(quality: np.ndarray) -> np.ndarray:
    """Map Qin quality to opacity while leaving rejected maxima barely visible."""

    values = np.clip(np.asarray(quality, dtype=float), 0.0, 1.0)
    alpha = 0.025 + 0.925 * values**1.25
    rgb = np.asarray(matplotlib.colors.to_rgb(BLUE), dtype=float)
    colors = np.empty((len(values), 4), dtype=float)
    colors[:, :3] = rgb
    colors[:, 3] = alpha
    return colors


def _residual_limit(document: dict[str, Any], quality: np.ndarray) -> float:
    frames = document["frames"]
    times = np.asarray([float(item["time_s"]) for item in frames])
    residual = np.asarray([float(item["train_cfo_hz"]) for item in frames]) - model_frequency(
        document, times
    )
    support = residual[quality >= 0.20]
    if not len(support):
        support = residual
    limit = 1.18 * float(np.percentile(np.abs(support), 99.5))
    return min(3_000.0, max(500.0, limit))


def _plot_dwell(
    absolute_axis: Any,
    residual_axis: Any,
    document: dict[str, Any],
) -> None:
    windows = document["windows"]
    frames = document["frames"]
    window_times = np.asarray([float(item["detection_time_s"]) for item in windows])
    window_cfo = np.asarray([float(item["initial_cfo_hz"]) for item in windows])
    frame_times = np.asarray([float(item["time_s"]) for item in frames])
    frame_cfo = np.asarray([float(item["train_cfo_hz"]) for item in frames])
    quality = qin_frame_quality(frames)
    colors = frame_rgba(quality)

    model_at_frames = model_frequency(document, frame_times)
    frame_residual = frame_cfo - model_at_frames
    start_s = float(document["spec"]["branch_start_s"])
    end_s = float(document["spec"]["branch_end_s"])

    for index, (time_s, cfo_hz) in enumerate(zip(window_times, window_cfo, strict=True)):
        end = min(time_s + PROBE_DURATION_S, end_s)
        absolute_axis.plot(
            (time_s, end),
            (cfo_hz, cfo_hz),
            color=AMBER,
            linewidth=2.0,
            alpha=0.76,
            solid_capstyle="butt",
            label="20 ms GLRT CFO" if index == 0 else None,
            zorder=2,
        )
        residual_axis.plot(
            (time_s, end),
            (
                cfo_hz - float(model_frequency(document, np.asarray([time_s]))[0]),
                cfo_hz - float(model_frequency(document, np.asarray([end]))[0]),
            ),
            color=AMBER,
            linewidth=2.0,
            alpha=0.76,
            solid_capstyle="butt",
            label="20 ms GLRT CFO" if index == 0 else None,
            zorder=2,
        )
        residual_axis.axvline(
            time_s,
            color=RED,
            linewidth=0.45,
            linestyle=(0, (3, 4)),
            alpha=0.15,
            zorder=0,
        )

    absolute_axis.scatter(
        frame_times,
        frame_cfo,
        s=8,
        facecolors=colors,
        edgecolors="none",
        rasterized=True,
        zorder=3,
    )
    residual_axis.scatter(
        frame_times,
        frame_residual,
        s=9,
        facecolors=colors,
        edgecolors="none",
        rasterized=True,
        zorder=3,
    )
    absolute_axis.plot(
        (start_s, end_s),
        model_frequency(document, np.asarray((start_s, end_s))),
        color=INK,
        linewidth=1.0,
        alpha=0.68,
        label="frozen GLRT line",
        zorder=1,
    )
    residual_axis.axhline(0.0, color=INK, linewidth=1.0, alpha=0.68, zorder=1)
    residual_axis.set_ylim(-_residual_limit(document, quality), _residual_limit(document, quality))
    absolute_axis.set_xlim(start_s, end_s)
    residual_axis.set_xlim(start_s, end_s)

    strong = int(np.count_nonzero(quality >= 0.50))
    label = document["spec"]["label"]
    absolute_axis.set_title(
        f"{label} · absolute CFO · {len(windows)} GLRT windows, {len(frames)} frames",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    residual_axis.set_title(
        f"{label} · residual close-up · {strong} frames have Qin confidence ≥ 0.50",
        loc="left",
        color=INK,
        fontweight="bold",
    )
    absolute_axis.set_ylabel("absolute CFO (Hz)")
    residual_axis.set_ylabel("CFO − frozen GLRT line (Hz)")
    residual_axis.set_xlabel("capture time (s)")
    absolute_axis.ticklabel_format(axis="y", style="plain", useOffset=False)

    confidence_handles = [
        Line2D(
            [],
            [],
            linestyle="none",
            marker="o",
            markersize=6,
            markerfacecolor=BLUE,
            markeredgecolor="none",
            alpha=alpha,
            label=label,
        )
        for alpha, label in ((0.08, "weak Qin"), (0.45, "moderate Qin"), (0.95, "strong Qin"))
    ]
    absolute_handles, absolute_labels = absolute_axis.get_legend_handles_labels()
    absolute_axis.legend(
        absolute_handles + confidence_handles,
        absolute_labels + [item.get_label() for item in confidence_handles],
        loc="best",
        ncol=3,
        frameon=False,
    )
    residual_axis.legend(loc="best", frameon=False)

    for axis in (absolute_axis, residual_axis):
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)


def render(path: Path, document: dict[str, Any]) -> None:
    d3, d4 = select_d3_d4(document)
    figure = Figure(figsize=(18, 15), constrained_layout=True)
    axes = figure.subplots(4, 1)
    figure.suptitle(
        "D3/D4 GLRT windows and Qin-weighted 1.333 ms frame CFO",
        fontsize=20,
        color=INK,
        fontweight="bold",
    )
    _plot_dwell(axes[0], axes[1], d3)
    _plot_dwell(axes[2], axes[3], d4)
    figure.text(
        0.5,
        0.002,
        (
            "Frame opacity = joint exact-Qin strength and positive exact-minus-rolled-control "
            "margin, P95-normalized within each dwell. Red dashed lines mark 20 ms probe starts."
        ),
        ha="center",
        color=GRAY,
        fontsize=10,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def main() -> None:
    arguments = _arguments()
    if not math.isclose(PROBE_DURATION_S, 0.020, abs_tol=1e-12):
        raise RuntimeError("unexpected GLRT probe duration")
    render(arguments.output, _load(arguments.results))
    print(arguments.output)


if __name__ == "__main__":
    main()
