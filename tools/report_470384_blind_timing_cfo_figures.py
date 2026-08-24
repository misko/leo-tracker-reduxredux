#!/usr/bin/env python3
"""Render the comprehensive blind timing/CFO report figures from frozen results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

DEFAULT_RESULTS = Path(
    "reports/figures/2026_08_23_470384_blind_timing_cfo/blind-timing-cfo-results.json"
)
DEFAULT_BOUNDARY_AUDIT = Path(
    "reports/figures/2026_08_23_470384_shifted_pilot_grid/shifted-grid-boundary-audit.json"
)
DEFAULT_OUTPUT = Path("reports/figures/2026_08_23_470384_blind_timing_cfo_comprehensive")
DEFAULT_COMPARISON = DEFAULT_OUTPUT / "postfit-boundary-comparison.json"

INK = "#17354a"
BLUE = "#2f83b7"
AMBER = "#d9881f"
GREEN = "#3f8f67"
RED = "#bd5b52"
PURPLE = "#7b65a8"
GRAY = "#9aa6ae"
LIGHT_GRAY = "#d4dade"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--boundary-audit", type=Path, default=DEFAULT_BOUNDARY_AUDIT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def line_frequency(line: dict[str, Any], times: np.ndarray) -> np.ndarray:
    return np.asarray(line["frequency_at_reference_hz"], dtype=float) + np.asarray(
        line["slope_hz_s"], dtype=float
    ) * (times - np.asarray(line["reference_time_s"], dtype=float))


def blind_boundaries(document: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        [
            item["preceding_boundary_time_s"]
            for item in document["primary_segments"]
            if item["preceding_boundary_time_s"] is not None
        ],
        dtype=float,
    )


def old_boundary_times(audit: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        [
            item["nominal_boundary_time_s"]
            for item in audit["boundary_audits"]
            if item["boundary_mode_separation_hz"] is not None
        ],
        dtype=float,
    )


def build_boundary_comparison(
    document: dict[str, Any],
    audit: dict[str, Any],
) -> dict[str, Any]:
    blind_times = blind_boundaries(document)
    old_times = old_boundary_times(audit)
    offsets = nearest_boundary_offsets(blind_times, old_times)
    rows = []
    for old_time, offset in zip(old_times, offsets, strict=True):
        rows.append(
            {
                "old_boundary_time_s": round(float(old_time), 9),
                "nearest_blind_boundary_time_s": round(float(old_time + offset), 9),
                "signed_offset_ms": round(float(offset * 1e3), 9),
            }
        )
    return {
        "schema_version": 1,
        "blind_algorithm": document["algorithm"],
        "external_audit_scope": audit.get("analysis_scope"),
        "loaded_after_blind_fit": True,
        "rows": rows,
        "summary": {
            "old_boundary_count": len(rows),
            "old_boundaries_within_12_ms": int(np.count_nonzero(np.abs(offsets) <= 0.012)),
            "median_absolute_offset_ms": round(float(np.median(np.abs(offsets)) * 1e3), 9),
            "p90_absolute_offset_ms": round(float(np.percentile(np.abs(offsets), 90) * 1e3), 9),
        },
    }


def nearest_boundary_offsets(
    blind_times: np.ndarray,
    old_times: np.ndarray,
) -> np.ndarray:
    if not len(blind_times) or not len(old_times):
        return np.asarray([], dtype=float)
    differences = blind_times[None, :] - old_times[:, None]
    indexes = np.argmin(np.abs(differences), axis=1)
    return differences[np.arange(len(old_times)), indexes]


def twenty_ms_grid(start_s: float, end_s: float) -> np.ndarray:
    count = int(np.floor((end_s - start_s) / 0.020 + 1e-9))
    return start_s + 0.020 * np.arange(count + 1, dtype=float)


def _path_arrays(
    document: dict[str, Any],
    name: str = "primary_path",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = document[name]
    return (
        np.asarray([item["cell_center_s"] for item in path], dtype=float),
        np.asarray([item["absolute_cfo_hz"] for item in path], dtype=float),
        np.asarray([item["refined_epoch_sample"] for item in path], dtype=float),
    )


def _segment_values(
    segment: dict[str, Any],
    line: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray] | None:
    if segment["slope_hz_s"] is None:
        return None
    times = np.asarray([segment["start_s"], segment["end_s"]], dtype=float)
    frequency = segment["frequency_at_reference_hz"] + segment["slope_hz_s"] * (
        times - segment["reference_time_s"]
    )
    return times, frequency - line_frequency(line, times)


def _style(axis, *, title: str, ylabel: str, xlabel: str | None = None) -> None:
    axis.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold")
    axis.set_ylabel(ylabel, color=INK)
    if xlabel is not None:
        axis.set_xlabel(xlabel, color=INK)
    axis.grid(True, alpha=0.16)
    axis.tick_params(colors=INK)
    for spine in axis.spines.values():
        spine.set_color(LIGHT_GRAY)


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    figure.clear()


def render_abstract(document: dict[str, Any], path: Path) -> None:
    times, frequencies, epochs = _path_arrays(document)
    primary = document["primary_line"]
    residuals = frequencies - line_frequency(primary, times)
    boundaries = blind_boundaries(document)
    statistics = document["primary_segment_statistics"]
    figure = Figure(figsize=(16, 9), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": (1.2, 1)})
    figure.suptitle(
        "Raw-IQ result in one view: CFO ramps reset with the recovered timing mode",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    axes[0].scatter(times, residuals, s=9, color=GREEN, alpha=0.62, linewidths=0)
    for index, segment in enumerate(document["primary_segments"]):
        values = _segment_values(segment, primary)
        if values is None:
            continue
        segment_times, segment_residuals = values
        axes[0].plot(
            segment_times,
            segment_residuals,
            color=AMBER,
            linewidth=1.15,
            label="independent segment line" if index == 0 else None,
        )
    for index, boundary in enumerate(boundaries):
        axes[0].axvline(
            boundary,
            color=RED,
            linewidth=0.7,
            alpha=0.25,
            linestyle=(0, (4, 3)),
            label="blind timing boundary" if index == 0 else None,
        )
    axes[0].legend(loc="lower left", ncol=2)
    axes[0].text(
        0.99,
        0.96,
        "global rate  −7.013 kHz/s\n"
        f"median local rate  {statistics['median_local_slope_hz_s'] / 1e3:.3f} kHz/s\n"
        f"median spacing  {statistics['median_boundary_spacing_ms']:.0f} ms",
        transform=axes[0].transAxes,
        ha="right",
        va="top",
        color=INK,
        fontsize=12,
    )
    axes[1].scatter(
        times,
        epochs / 2_500_000.0 * 1e6,
        s=9,
        color=BLUE,
        alpha=0.68,
        linewidths=0,
    )
    for boundary in boundaries:
        axes[1].axvline(
            boundary,
            color=RED,
            linewidth=0.7,
            alpha=0.25,
            linestyle=(0, (4, 3)),
        )
    _style(
        axes[0],
        title="A · Primary CFO after subtracting one global line",
        ylabel="CFO residual (Hz)",
    )
    _style(
        axes[1],
        title="B · Independently recovered Qin timing phase in each 12 ms cell",
        ylabel="timing epoch (µs)",
        xlabel="capture time (s)",
    )
    _save(figure, path)


def render_introduction(document: dict[str, Any], path: Path) -> None:
    candidates = document["candidates"]
    candidate_times = np.asarray([item["cell_center_s"] for item in candidates])
    candidate_cfo = np.asarray([item["absolute_cfo_hz"] for item in candidates]) / 1e3
    primary_times, primary_cfo, _epochs = _path_arrays(document)
    secondary_times, secondary_cfo, _epochs = _path_arrays(document, "secondary_path")
    figure = Figure(figsize=(16, 7.5), constrained_layout=True)
    axis = figure.subplots()
    figure.suptitle(
        "Blind acquisition retains several real Qin-supported CFO modes",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    axis.scatter(
        candidate_times,
        candidate_cfo,
        s=9,
        color=GRAY,
        alpha=0.17,
        linewidths=0,
        rasterized=True,
        label="all retained timing/CFO candidates",
    )
    axis.scatter(
        primary_times,
        primary_cfo / 1e3,
        s=11,
        color=BLUE,
        alpha=0.68,
        linewidths=0,
        label="primary latent path",
    )
    axis.scatter(
        secondary_times,
        secondary_cfo / 1e3,
        s=11,
        color=AMBER,
        alpha=0.66,
        linewidths=0,
        label="secondary latent path",
    )
    plot_times = np.linspace(candidate_times.min(), candidate_times.max(), 500)
    for line, color, label in (
        (document["primary_line"], INK, "primary global fit"),
        (document["secondary_line"], PURPLE, "secondary global fit"),
    ):
        axis.plot(
            plot_times,
            line_frequency(line, plot_times) / 1e3,
            color=color,
            linewidth=1.8,
            label=f"{label}: {line['slope_hz_s'] / 1e3:.3f} kHz/s",
        )
    axis.legend(loc="lower left", ncol=2)
    _style(
        axis,
        title="The full 33.7–37.7 s raw-IQ search; no prior branch selected",
        ylabel="absolute CFO (kHz)",
        xlabel="capture time (s)",
    )
    _save(figure, path)


def render_hypothesis(document: dict[str, Any], path: Path) -> None:
    times, frequencies, epochs = _path_arrays(document)
    primary = document["primary_line"]
    residuals = frequencies - line_frequency(primary, times)
    start_s = 35.35
    end_s = 35.90
    selected = (times >= start_s) & (times <= end_s)
    boundaries = blind_boundaries(document)
    boundaries = boundaries[(boundaries >= start_s) & (boundaries <= end_s)]
    old_grid = twenty_ms_grid(document["configuration"]["start_s"], end_s)
    old_grid = old_grid[(old_grid >= start_s) & (old_grid <= end_s)]
    figure = Figure(figsize=(16, 9), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True)
    figure.suptitle(
        "Window-artifact hypothesis: blind ramps cross multiple old 20 ms probes",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    for axis in axes:
        for index, boundary in enumerate(old_grid):
            axis.axvline(
                boundary,
                color=RED,
                linewidth=0.7,
                alpha=0.20,
                linestyle=(0, (4, 4)),
                label="old 20 ms probe grid" if index == 0 else None,
            )
        for index, boundary in enumerate(boundaries):
            axis.axvline(
                boundary,
                color=INK,
                linewidth=1.25,
                alpha=0.58,
                label="blind timing boundary" if index == 0 else None,
            )
    axes[0].scatter(
        times[selected],
        residuals[selected],
        s=18,
        color=GREEN,
        alpha=0.74,
        linewidths=0,
        label="12 ms raw-IQ CFO estimates",
    )
    axes[1].scatter(
        times[selected],
        epochs[selected] / 2_500_000.0 * 1e6,
        s=18,
        color=BLUE,
        alpha=0.74,
        linewidths=0,
    )
    axes[0].legend(loc="lower left", ncol=3)
    _style(
        axes[0],
        title="A · CFO residual: resets occur after several probe boundaries",
        ylabel="CFO residual (Hz)",
    )
    _style(
        axes[1],
        title="B · Timing phase: one plateau per CFO ramp",
        ylabel="timing epoch (µs)",
        xlabel="capture time (s)",
    )
    _save(figure, path)


def render_approach(document: dict[str, Any], path: Path) -> None:
    times, frequencies, epochs = _path_arrays(document)
    primary = document["primary_line"]
    residuals = frequencies - line_frequency(primary, times)
    start_s = 35.42
    end_s = 35.58
    selected = (times >= start_s) & (times <= end_s)
    cell_hop_s = document["configuration"]["cell_hop_ms"] / 1e3
    cell_duration_s = document["configuration"]["cell_duration_ms"] / 1e3
    cell_starts = np.arange(start_s, end_s, cell_hop_s)
    figure = Figure(figsize=(16, 9), constrained_layout=True)
    axes = figure.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": (1.35, 1)})
    figure.suptitle(
        "Blind acquisition geometry on the real transition near 35.55 s",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    axes[0].scatter(
        times[selected],
        residuals[selected],
        s=24,
        color=GREEN,
        alpha=0.78,
        linewidths=0,
        label="independent CFO estimate",
    )
    timing_axis = axes[0].twinx()
    timing_axis.scatter(
        times[selected],
        epochs[selected] / 2_500_000.0 * 1e6,
        s=42,
        color=BLUE,
        alpha=0.78,
        linewidths=1.4,
        marker="x",
        zorder=5,
        label="independent timing epoch",
    )
    timing_axis.set_ylabel("timing epoch (µs)", color=BLUE)
    timing_axis.tick_params(colors=BLUE)
    handles, labels = axes[0].get_legend_handles_labels()
    other_handles, other_labels = timing_axis.get_legend_handles_labels()
    axes[0].legend(handles + other_handles, labels + other_labels, loc="lower left")
    for index, cell_start in enumerate(cell_starts):
        lane = index % 3
        axes[1].plot(
            [cell_start, cell_start + cell_duration_s],
            [lane, lane],
            color=(BLUE, AMBER, PURPLE)[lane],
            linewidth=7,
            alpha=0.55,
            solid_capstyle="butt",
        )
        axes[1].scatter(
            [cell_start + 0.5 * cell_duration_s],
            [lane],
            s=12,
            color=INK,
            linewidths=0,
            zorder=3,
        )
    axes[1].set_yticks([0, 1, 2], labels=["lane 1", "lane 2", "lane 3"])
    axes[1].text(
        0.01,
        0.93,
        "12 ms support · 4 ms hop · 8 ms overlap · full 1.333 ms phase search",
        transform=axes[1].transAxes,
        va="top",
        color=INK,
        fontsize=12,
    )
    _style(
        axes[0],
        title="A · Both CFO and timing change without any 20 ms candidate input",
        ylabel="CFO residual (Hz)",
    )
    _style(
        axes[1],
        title="B · Fixed overlapping acquisition supports used on this interval",
        ylabel="staggered cells",
        xlabel="capture time (s)",
    )
    axes[1].set_xlim(start_s, end_s)
    _save(figure, path)


def render_results(document: dict[str, Any], path: Path) -> None:
    fitted = [item for item in document["primary_segments"] if item["slope_hz_s"] is not None]
    midpoint = np.asarray([(item["start_s"] + item["end_s"]) / 2 for item in fitted])
    slopes = np.asarray([item["slope_hz_s"] for item in fitted]) / 1e3
    rms = np.asarray([item["rms_hz"] for item in fitted])
    statistics = document["primary_segment_statistics"]
    primary = document["primary_line"]
    figure = Figure(figsize=(16, 7.5), constrained_layout=True)
    axes = figure.subplots(1, 2, gridspec_kw={"width_ratios": (1.45, 1)})
    figure.suptitle(
        "Rate decomposition: straight local ramps plus discrete resets",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    axes[0].scatter(midpoint, slopes, s=34, color=BLUE, alpha=0.74, linewidths=0)
    axes[0].axhspan(
        statistics["p10_local_slope_hz_s"] / 1e3,
        statistics["p90_local_slope_hz_s"] / 1e3,
        color=BLUE,
        alpha=0.10,
        label="local 10–90% range",
    )
    axes[0].axhline(
        statistics["median_local_slope_hz_s"] / 1e3,
        color=BLUE,
        linewidth=1.8,
        label="median local rate",
    )
    axes[0].axhline(
        primary["slope_hz_s"] / 1e3,
        color=RED,
        linewidth=1.8,
        linestyle=(0, (5, 3)),
        label="single global rate",
    )
    axes[0].legend(loc="lower left")
    bins = np.linspace(0, max(primary["weighted_rms_hz"] * 1.05, rms.max()), 28)
    axes[1].hist(rms, bins=bins, color=GREEN, alpha=0.72, label="local segment RMS")
    axes[1].axvline(
        statistics["median_local_fit_rms_hz"],
        color=GREEN,
        linewidth=1.8,
        label=f"local median {statistics['median_local_fit_rms_hz']:.1f} Hz",
    )
    axes[1].axvline(
        primary["weighted_rms_hz"],
        color=RED,
        linewidth=1.8,
        linestyle=(0, (5, 3)),
        label=f"global RMS {primary['weighted_rms_hz']:.1f} Hz",
    )
    axes[1].legend(loc="upper right")
    _style(
        axes[0],
        title="A · One independently fitted rate per timing-coherent segment",
        ylabel="CFO rate (kHz/s)",
        xlabel="segment midpoint (s)",
    )
    _style(
        axes[1],
        title="B · Local lines fit far better than one global line",
        ylabel="segment count",
        xlabel="CFO fit RMS (Hz)",
    )
    _save(figure, path)


def _candidate_keys(items: list[dict[str, Any]]) -> set[tuple[int, int, int]]:
    return {
        (
            int(item["cell_index"]),
            int(item["refined_epoch_sample"]),
            round(float(item["absolute_cfo_hz"])),
        )
        for item in items
    }


def render_methods(
    document: dict[str, Any],
    comparison: dict[str, Any],
    path: Path,
) -> None:
    candidates = document["candidates"]
    primary_keys = _candidate_keys(document["primary_path"])
    secondary_keys = _candidate_keys(document["secondary_path"])
    groups: dict[str, list[dict[str, Any]]] = {"other": [], "primary": [], "secondary": []}
    for item in candidates:
        key = (
            int(item["cell_index"]),
            int(item["refined_epoch_sample"]),
            round(float(item["absolute_cfo_hz"])),
        )
        if key in primary_keys:
            groups["primary"].append(item)
        elif key in secondary_keys:
            groups["secondary"].append(item)
        else:
            groups["other"].append(item)
    figure = Figure(figsize=(16, 7.5), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Controls and post-fit validation",
        color=INK,
        fontsize=20,
        fontweight="bold",
    )
    for name, color, alpha in (
        ("other", GRAY, 0.16),
        ("primary", BLUE, 0.62),
        ("secondary", AMBER, 0.58),
    ):
        items = groups[name]
        axes[0].scatter(
            [item["control_score"] for item in items],
            [item["verify_score"] for item in items],
            s=12,
            color=color,
            alpha=alpha,
            linewidths=0,
            rasterized=True,
            label=f"{name} ({len(items)})",
        )
    score_max = max(item["verify_score"] for item in candidates) * 1.03
    score_axis = np.linspace(0, 0.060, 100)
    axes[0].plot(score_axis, score_axis + 0.03, color=RED, linestyle=(0, (5, 3)))
    axes[0].axhline(0.08, color=INK, linewidth=1.0, alpha=0.65)
    axes[0].set_xlim(-0.002, 0.060)
    axes[0].set_ylim(0.070, score_max)
    axes[0].legend(loc="lower right")
    old_times = np.asarray(
        [item["old_boundary_time_s"] for item in comparison["rows"]],
        dtype=float,
    )
    offsets_ms = np.asarray(
        [item["signed_offset_ms"] for item in comparison["rows"]],
        dtype=float,
    )
    axes[1].axhspan(-12, 12, color=GREEN, alpha=0.10, label="±12 ms agreement gate")
    axes[1].axhline(0, color=INK, linewidth=0.9)
    axes[1].scatter(old_times, offsets_ms, s=48, color=PURPLE, alpha=0.78, linewidths=0)
    axes[1].text(
        0.98,
        0.96,
        f"{int(np.count_nonzero(np.abs(offsets_ms) <= 12))}/{len(offsets_ms)} within 12 ms\n"
        f"median |offset| {np.median(np.abs(offsets_ms)):.1f} ms",
        transform=axes[1].transAxes,
        ha="right",
        va="top",
        color=INK,
        fontsize=12,
    )
    _style(
        axes[0],
        title="A · Exact Qin verification must beat the rolled control",
        ylabel="exact-Qin verification score",
        xlabel="rolled-control score",
    )
    _style(
        axes[1],
        title="B · Old boundaries were compared only after the blind fit froze",
        ylabel="nearest blind boundary − old boundary (ms)",
        xlabel="old audited boundary time (s)",
    )
    _save(figure, path)


def main() -> None:
    arguments = _arguments()
    document = _load(arguments.results)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    comparison_path = arguments.output_root / DEFAULT_COMPARISON.name
    if arguments.boundary_audit.exists():
        comparison = build_boundary_comparison(
            document,
            _load(arguments.boundary_audit),
        )
        comparison_path.write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        comparison = _load(comparison_path)
    render_abstract(document, arguments.output_root / "abstract-evidence-overview.png")
    render_introduction(document, arguments.output_root / "introduction-blind-modes.png")
    render_hypothesis(document, arguments.output_root / "motivation-window-hypothesis.png")
    render_approach(document, arguments.output_root / "approach-overlapping-cells.png")
    render_results(document, arguments.output_root / "results-rate-decomposition.png")
    render_methods(
        document,
        comparison,
        arguments.output_root / "methods-controls-and-validation.png",
    )
    print(f"wrote six figures to {arguments.output_root}")


if __name__ == "__main__":
    main()
