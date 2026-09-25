#!/usr/bin/env python3
"""Plot 1.333 ms residual CFO plus its 20 ms window CFO explicitly."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

try:
    import report_470384_semicoherent_recovery as semicoherent
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_470384_semicoherent_recovery as semicoherent


DEFAULT_FRAME_RESULTS = Path(
    "reports/figures/2026_08_23_470384_direct_frame_cfo/direct-frame-cfo-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_frame_plus_window_cfo")
START_S = 33.7
END_S = 37.7
ZOOM_START_S = 35.5
ZOOM_END_S = 36.1
BRANCH_INDEX = 3

INK = "#17354a"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"
AMBER = "#d9881f"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
RED = "#bd5b52"


@dataclass(frozen=True, slots=True)
class Components:
    association_index: int
    frame_index: int
    time_s: float
    window_start_s: float
    window_cfo_hz: float
    frame_residual_cfo_hz: float
    summed_cfo_hz: float
    direct_raw_cfo_hz: float
    qin_supported: bool


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-frame-results",
        type=Path,
        default=semicoherent.DEFAULT_FRAME_RESULTS,
    )
    parser.add_argument("--direct-frame-results", type=Path, default=DEFAULT_FRAME_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def build_components(
    source_document: dict[str, Any],
    direct_document: dict[str, Any],
) -> tuple[Components, ...]:
    windows = {
        int(item["association_index"]): item
        for item in source_document["candidate_windows"]
        if int(item["branch_index"]) == BRANCH_INDEX
        and START_S <= float(item["detection_time_s"]) < END_S
        and float(item["selection_model_error_hz"]) <= semicoherent.MAXIMUM_MODEL_ERROR_HZ
    }
    output = []
    for item in direct_document["frame_fits"]:
        association_index = int(item["association_index"])
        window = windows[association_index]
        window_cfo = float(window["initial_cfo_hz"])
        summed_cfo = float(item["old_local_curve_cfo_hz"])
        output.append(
            Components(
                association_index=association_index,
                frame_index=int(item["frame_index"]),
                time_s=float(item["time_s"]),
                window_start_s=float(window["detection_time_s"]),
                window_cfo_hz=window_cfo,
                frame_residual_cfo_hz=summed_cfo - window_cfo,
                summed_cfo_hz=summed_cfo,
                direct_raw_cfo_hz=float(item["direct_cfo_hz"]),
                qin_supported=float(item["validation_exact_control_db"]) > 0.0,
            )
        )
    return tuple(output)


def _groups(values: tuple[Components, ...]) -> tuple[tuple[Components, ...], ...]:
    groups: dict[int, list[Components]] = {}
    for item in values:
        groups.setdefault(item.association_index, []).append(item)
    return tuple(tuple(group) for group in groups.values())


def render(
    path: Path,
    *,
    values: tuple[Components, ...],
    branch: semicoherent.Branch,
    start_s: float,
    end_s: float,
) -> None:
    selected = tuple(item for item in values if start_s <= item.time_s <= end_s)
    times = np.asarray([item.time_s for item in selected])
    window_cfo = np.asarray([item.window_cfo_hz for item in selected])
    residual = np.asarray([item.frame_residual_cfo_hz for item in selected])
    summed = np.asarray([item.summed_cfo_hz for item in selected])
    direct = np.asarray([item.direct_raw_cfo_hz for item in selected])
    supported = np.asarray([item.qin_supported for item in selected])
    model = np.asarray(branch.frequency_hz(times))
    figure = Figure(figsize=(18, 13), constrained_layout=True)
    axes = figure.subplots(3, 1, sharex=True)
    figure.suptitle(
        "Explicit CFO decomposition: 1.333 ms residual + 20 ms window CFO",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )
    selected_groups = tuple(
        tuple(item for item in group if start_s <= item.time_s <= end_s)
        for group in _groups(values)
    )
    selected_groups = tuple(group for group in selected_groups if group)
    for group in selected_groups:
        window_start = group[0].window_start_s
        for axis in axes:
            axis.axvline(
                window_start,
                color=RED,
                linewidth=0.65,
                linestyle=(0, (3, 3)),
                alpha=0.28,
                zorder=0,
            )
        group_times = np.asarray([item.time_s for item in group])
        group_model = np.asarray(branch.frequency_hz(group_times))
        axes[0].plot(
            group_times,
            np.asarray([item.window_cfo_hz for item in group]) - group_model,
            color=AMBER,
            linewidth=2.0,
            solid_capstyle="butt",
        )
    axes[0].scatter(times, window_cfo - model, s=8, color=AMBER, alpha=0.65, linewidths=0)
    axes[1].scatter(
        times[~supported],
        residual[~supported],
        s=8,
        color=GRAY,
        alpha=0.22,
        linewidths=0,
        label="Qin≤control",
    )
    axes[1].scatter(
        times[supported],
        residual[supported],
        s=10,
        color=BLUE,
        alpha=0.62,
        linewidths=0,
        label="Qin>control",
    )
    axes[1].legend(loc="lower left", ncol=2)
    axes[2].scatter(
        times[~supported],
        summed[~supported] - model[~supported],
        s=8,
        color=GRAY,
        alpha=0.22,
        linewidths=0,
    )
    axes[2].scatter(
        times[supported],
        summed[supported] - model[supported],
        s=10,
        color=GREEN,
        alpha=0.62,
        linewidths=0,
        label="window CFO + frame residual CFO",
    )
    axes[2].scatter(
        times[supported],
        direct[supported] - model[supported],
        s=18,
        facecolors="none",
        edgecolors=INK,
        linewidths=0.35,
        alpha=0.34,
        label="direct raw-frame absolute CFO check",
    )
    axes[2].legend(loc="lower left", ncol=2)
    titles = (
        "A · 20 ms window CFO (displayed relative to frozen B4)",
        "B · 1.333 ms frame residual CFO relative to its window CFO",
        "C · Explicit sum: window CFO + frame residual CFO (relative to B4)",
    )
    ylabels = (
        "window CFO − B4 (Hz)",
        "frame residual CFO (Hz)",
        "summed CFO − B4 (Hz)",
    )
    for axis, title, ylabel in zip(axes, titles, ylabels, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.set_ylabel(ylabel, color=INK)
        axis.grid(True, alpha=0.16)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[-1].set_xlabel("capture time (s)", color=INK)
    axes[-1].set_xlim(start_s, end_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def main() -> None:
    arguments = _arguments()
    source_document = _load(arguments.source_frame_results)
    direct_document = _load(arguments.direct_frame_results)
    branches, _windows = semicoherent.parse_inputs(source_document)
    branch = next(item for item in branches if item.index == BRANCH_INDEX)
    values = build_components(source_document, direct_document)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    full_path = arguments.output_root / "frame-plus-window-cfo-full.png"
    zoom_path = arguments.output_root / "frame-plus-window-cfo-zoom.png"
    render(full_path, values=values, branch=branch, start_s=START_S, end_s=END_S)
    render(zoom_path, values=values, branch=branch, start_s=ZOOM_START_S, end_s=ZOOM_END_S)
    arithmetic_error = max(
        abs(item.window_cfo_hz + item.frame_residual_cfo_hz - item.summed_cfo_hz)
        for item in values
    )
    direct_difference = np.asarray(
        [item.direct_raw_cfo_hz - item.summed_cfo_hz for item in values]
    )
    summary = {
        "frame_count": len(values),
        "maximum_sum_identity_error_hz": arithmetic_error,
        "median_absolute_direct_minus_sum_hz": float(np.median(np.abs(direct_difference))),
        "p99_absolute_direct_minus_sum_hz": float(np.percentile(np.abs(direct_difference), 99)),
        "full_figure": str(full_path),
        "zoom_figure": str(zoom_path),
    }
    results_path = arguments.output_root / "frame-plus-window-cfo-summary.json"
    results_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
