#!/usr/bin/env python3
"""Render aligned GLRT and 1.333 ms frame CFO evidence for 33.7–37.7 s."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

SESSION_ID = "cap-20260821T140820-470384cc9284"
START_S = 33.7
END_S = 37.7
BRANCH_INDEX = 3
DEFAULT_CONTINUOUS_RESULTS = (
    Path("reports/figures/2026_08_23_470384_continuous_glrt")
    / "continuous-glrt-results.json"
)
DEFAULT_DENSE_EVIDENCE = Path(
    "reports/figures/2026_08_22_edge_pilot_phase_slope/detailed-results.json"
)
DEFAULT_OUTPUT = (
    Path("reports/figures/2026_08_23_470384_continuous_glrt")
    / "glrt-frame-cfo-33p7-37p7.png"
)

INK = "#17354a"
LIGHT_GRAY = "#d4dade"
GRAY = "#9aa6ae"
AMBER = "#d9881f"
BLUE = "#2f83b7"
RED = "#c94b43"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous-results", type=Path, default=DEFAULT_CONTINUOUS_RESULTS)
    parser.add_argument("--dense-evidence", type=Path, default=DEFAULT_DENSE_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-s", type=float, default=START_S)
    parser.add_argument("--end-s", type=float, default=END_S)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _branch_model(continuous_document: dict[str, Any]) -> tuple[np.ndarray, float, str]:
    frame_path = Path(continuous_document["input"]["frame_results"])
    frame_document = _load(frame_path)
    matches = [
        item["branch"]
        for item in frame_document["branches"]
        if int(item["branch"]["index"]) == BRANCH_INDEX
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one B4 frozen branch")
    branch = matches[0]
    return (
        np.asarray(branch["coefficients_hz"], dtype=float),
        float(branch["reference_time_s"]),
        str(branch["label"]),
    )


def select_evidence(
    continuous_document: dict[str, Any],
    dense_document: dict[str, Any],
    *,
    start_s: float,
    end_s: float,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], np.ndarray, float, str]:
    if start_s >= end_s:
        raise ValueError("zoom start must precede zoom end")
    expected = {
        "session_id": SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "edge": "upper",
    }
    for key, value in expected.items():
        if continuous_document["input"].get(key) != value:
            raise ValueError(f"continuous results have unexpected {key}")
        if dense_document["input"].get(key) != value:
            raise ValueError(f"dense evidence has unexpected {key}")
    windows = tuple(
        sorted(
            (
                item
                for item in continuous_document["rows"]
                if int(item["branch_index"]) == BRANCH_INDEX
                and start_s <= float(item["time_s"]) <= end_s
            ),
            key=lambda item: float(item["time_s"]),
        )
    )
    frames = tuple(
        item
        for item in dense_document["dense_tracking"]["frames"]
        if start_s <= float(item["reference_time_s"]) <= end_s
    )
    if not windows or not frames:
        raise ValueError("zoom contains no aligned GLRT or frame evidence")
    coefficients, reference_time_s, label = _branch_model(continuous_document)
    return windows, frames, coefficients, reference_time_s, label


def _model_frequency(
    times_s: np.ndarray, coefficients_hz: np.ndarray, reference_time_s: float
) -> np.ndarray:
    return np.polyval(coefficients_hz, np.asarray(times_s, dtype=float) - reference_time_s)


def render(
    path: Path,
    *,
    windows: tuple[dict[str, Any], ...],
    frames: tuple[dict[str, Any], ...],
    coefficients_hz: np.ndarray,
    reference_time_s: float,
    branch_label: str,
    start_s: float,
    end_s: float,
) -> None:
    figure = Figure(figsize=(18, 15), constrained_layout=True)
    axes = figure.subplots(4, 1, sharex=True, gridspec_kw={"height_ratios": (0.82, 1, 1, 1.25)})
    figure.suptitle(
        "GLRT-to-frame CFO ladder · cap-20260821T140820-470384cc9284",
        fontsize=21,
        color=INK,
        fontweight="bold",
    )

    window_times = np.asarray([item["time_s"] for item in windows], dtype=float)
    model = _model_frequency(window_times, coefficients_hz, reference_time_s)
    exact = np.asarray([item["persisted_exact_score"] for item in windows], dtype=float)
    control = np.asarray([item["persisted_control_score"] for item in windows], dtype=float)
    original_residual = (
        np.asarray([item["persisted_tracking_cfo_hz"] for item in windows], dtype=float) - model
    )
    continuous_residual = (
        np.asarray([item["continuous_tracking_cfo_hz"] for item in windows], dtype=float) - model
    )

    for window_index, time_s in enumerate(window_times):
        for axis_index, axis in enumerate(axes):
            axis.axvline(
                time_s,
                color=RED,
                linewidth=0.65,
                linestyle=(0, (3, 3)),
                alpha=0.24,
                zorder=0,
                label=(
                    "20 ms probe start"
                    if window_index == 0 and axis_index == 0
                    else None
                ),
            )

    axes[0].scatter(
        window_times,
        exact,
        s=24,
        color=AMBER,
        alpha=0.78,
        linewidths=0,
        label=f"exact Qin GLRT64 ({len(windows)})",
    )
    axes[0].scatter(
        window_times,
        control,
        s=20,
        color=GRAY,
        alpha=0.58,
        linewidths=0,
        label="rolled control",
    )
    axes[1].scatter(
        window_times,
        original_residual,
        s=22,
        color=AMBER,
        alpha=0.76,
        linewidths=0,
    )
    axes[2].scatter(
        window_times,
        continuous_residual,
        s=22,
        color=BLUE,
        alpha=0.76,
        linewidths=0,
    )

    frame_times = np.asarray([item["reference_time_s"] for item in frames], dtype=float)
    frame_residual = np.asarray(
        [item["absolute_cfo_measurement_hz"] - item["model_cfo_hz"] for item in frames],
        dtype=float,
    )
    accepted = np.asarray([item["frequency_update_applied"] for item in frames], dtype=bool)
    finite = np.isfinite(frame_residual)
    rejected = ~accepted & finite
    accepted &= finite
    axes[3].scatter(
        frame_times[rejected],
        frame_residual[rejected],
        s=8,
        color=GRAY,
        alpha=0.20,
        linewidths=0,
        rasterized=True,
        label=f"measured, not used for CFO update ({np.count_nonzero(rejected)})",
    )
    axes[3].scatter(
        frame_times[accepted],
        frame_residual[accepted],
        s=10,
        color=BLUE,
        alpha=0.70,
        linewidths=0,
        rasterized=True,
        label=f"accepted 1.333 ms frame CFO ({np.count_nonzero(accepted)})",
    )

    window_lower = min(float(np.min(original_residual)), float(np.min(continuous_residual)))
    window_upper = max(float(np.max(original_residual)), float(np.max(continuous_residual)))
    window_padding = max(50.0, 0.07 * (window_upper - window_lower))
    axes[1].set_ylim(window_lower - window_padding, window_upper + window_padding)
    axes[2].set_ylim(window_lower - window_padding, window_upper + window_padding)
    for axis in axes[1:]:
        axis.axhline(0.0, color=INK, linewidth=0.85, alpha=0.62)
        axis.set_ylabel("CFO − B4 model (Hz)", color=INK)
    axes[0].set_ylabel("normalized score", color=INK)
    axes[3].set_xlabel("capture time (s)", color=INK)
    axes[3].set_xlim(start_s, end_s)
    titles = (
        f"A · GLRT64 signal strength · {branch_label}",
        "B · Persisted 20 ms GLRT-window CFO",
        "C · Continuously refined 20 ms GLRT CFO",
        f"D · Every frame-local CFO in the interval ({len(frames)} frames)",
    )
    for axis, title in zip(axes, titles, strict=True):
        axis.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold")
        axis.grid(True, alpha=0.18)
        axis.tick_params(colors=INK)
        for spine in axis.spines.values():
            spine.set_color(LIGHT_GRAY)
    axes[0].legend(loc="lower left", ncol=2, frameon=True)
    axes[3].legend(loc="lower left", ncol=2, frameon=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def main() -> None:
    arguments = _arguments()
    continuous_document = _load(arguments.continuous_results)
    dense_document = _load(arguments.dense_evidence)
    windows, frames, coefficients, reference_time_s, label = select_evidence(
        continuous_document,
        dense_document,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    render(
        arguments.output,
        windows=windows,
        frames=frames,
        coefficients_hz=coefficients,
        reference_time_s=reference_time_s,
        branch_label=label,
        start_s=arguments.start_s,
        end_s=arguments.end_s,
    )
    print(
        json.dumps(
            {
                "session_id": SESSION_ID,
                "start_s": arguments.start_s,
                "end_s": arguments.end_s,
                "glrt_window_count": len(windows),
                "frame_count": len(frames),
                "accepted_frame_count": sum(
                    bool(item["frequency_update_applied"]) for item in frames
                ),
                "output": str(arguments.output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
