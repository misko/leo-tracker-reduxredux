#!/usr/bin/env python3
"""Render the native-rate production deployment retrospective figures.

This is a pure presentation layer over a checked-in, machine-readable summary.
It does not read radio IQ, rerun analysis, contact production services, or turn
an unqualified sample rate into production evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle  # noqa: E402

DEFAULT_DATA = Path(
    "reports/figures/2026_08_27_native_sample_rate_production_retrospective/"
    "deployment-retrospective-data.json"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA.parent
EXPECTED_SCHEMA = "org.leo.report.native-sample-rate-production-retrospective/v1"

INK = "#17354a"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
PURPLE = "#7b65a8"
RED = "#bd5b52"
GRAY = "#96a2ab"
LIGHT_GRAY = "#d2d9de"
VERY_LIGHT_GRAY = "#eef1f3"
WHITE = "#ffffff"

FIGURE_NAMES = {
    "rf_geometry": "rf-bandwidth-and-if-geometry.png",
    "transport": "transport-headroom.png",
    "continuity": "capture-continuity-and-queue.png",
    "performance": "analysis-and-http-performance.png",
    "timeline": "deployment-timeline.png",
    "flow": "native-standard-dataflow.png",
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("report data must be one JSON object")
    _validate(value)
    return value


def _validate(document: dict[str, Any]) -> None:
    if document.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(f"expected schema {EXPECTED_SCHEMA!r}")
    rates = document.get("native_rates")
    transport = document.get("transport")
    live = document.get("live_canaries")
    http = document.get("http_artifact_checks")
    timeline = document.get("timeline")
    if not isinstance(rates, list) or len(rates) != 3:
        raise ValueError("exactly three production native rates are required")
    if not isinstance(transport, dict) or not transport.get("modes"):
        raise ValueError("transport modes are required")
    if not isinstance(live, list) or len(live) < 4:
        raise ValueError("at least four live canaries are required")
    if not isinstance(http, list) or len(http) != 4:
        raise ValueError("HTTP checks for 2.5, 3, 5, and mixed are required")
    if not isinstance(timeline, list) or len(timeline) < 8:
        raise ValueError("deployment timeline is incomplete")
    for rate in rates:
        if rate["sample_rate_hz"] != rate["rf_bandwidth_hz"]:
            raise ValueError("native RF bandwidth must equal native sample rate")
    for check in http:
        if check["subject_count"] != 7 or check["artifact_count"] != 59:
            raise ValueError("every HTTP check must close seven subjects and 59 PNGs")


def _style_axis(axis: Axes, *, grid_axis: str = "y") -> None:
    axis.grid(True, axis=grid_axis, color=LIGHT_GRAY, linewidth=0.8, alpha=0.62)
    axis.set_axisbelow(True)
    axis.tick_params(colors=INK)
    axis.xaxis.label.set_color(INK)
    axis.yaxis.label.set_color(INK)
    axis.title.set_color(INK)
    for spine in axis.spines.values():
        spine.set_color(LIGHT_GRAY)


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        facecolor=WHITE,
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )


def render_rf_geometry(path: Path, document: dict[str, Any]) -> None:
    """Show exact bandwidth equality and common-IF nesting."""

    rates = document["native_rates"]
    figure = Figure(figsize=(13.8, 7.4), constrained_layout=True)
    axis = figure.subplots()
    figure.suptitle(
        "Native-rate RF geometry: one IF, bandwidth equals sample rate",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    colors = (BLUE, GREEN, PURPLE)
    y_positions = list(reversed(range(len(rates))))
    for y, rate, color in zip(y_positions, rates, colors, strict=True):
        width_mhz = rate["rf_bandwidth_hz"] / 1_000_000.0
        left = -width_mhz / 2.0
        axis.add_patch(
            Rectangle(
                (left, y - 0.28),
                width_mhz,
                0.56,
                facecolor=color,
                edgecolor=INK,
                linewidth=1.2,
                alpha=0.87,
            )
        )
        axis.text(
            0.0,
            y,
            f"{rate['label']}  ·  RF BW {width_mhz:g} MHz",
            color=WHITE,
            ha="center",
            va="center",
            fontsize=12,
            fontweight="bold",
        )
        axis.text(
            left,
            y - 0.38,
            f"IF − {width_mhz / 2:g} MHz",
            color=INK,
            ha="center",
            va="top",
            fontsize=9,
        )
        axis.text(
            -left,
            y - 0.38,
            f"IF + {width_mhz / 2:g} MHz",
            color=INK,
            ha="center",
            va="top",
            fontsize=9,
        )
    axis.axvline(0.0, color=RED, linewidth=2.0, linestyle="--", label="exact applied IF")
    axis.set_xlim(-3.0, 3.0)
    axis.set_ylim(-0.85, len(rates) - 0.15)
    axis.set_yticks([])
    axis.set_xlabel("frequency offset from exact selected channel-edge IF (MHz)")
    axis.set_title(
        "Mixed captures use the same exact IF on both radios; "
        "the higher-rate leg covers a wider nested span",
        loc="left",
        fontsize=11,
    )
    axis.legend(loc="upper right", frameon=False)
    _style_axis(axis, grid_axis="x")
    _save(figure, path)


def render_transport(path: Path, document: dict[str, Any]) -> None:
    """Compare raw dual-RX demand with sealed writer capacity."""

    transport = document["transport"]
    modes = transport["modes"]
    labels = [item["label"] for item in modes]
    demands = [item["aggregate_raw_bytes_per_second"] / 1_000_000.0 for item in modes]
    colors = [GREEN if item["enabled"] else RED for item in modes]
    writer = transport["writer_benchmark_bytes_per_second"] / 1_000_000.0
    gate = transport["writer_gate_bytes_per_second"] / 1_000_000.0

    figure = Figure(figsize=(14.4, 7.5), constrained_layout=True)
    axis = figure.subplots()
    figure.suptitle(
        "Raw capture demand versus measured incompressible writer capacity",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    bars = axis.bar(labels, demands, color=colors, edgecolor=INK, linewidth=0.8, alpha=0.88)
    axis.axhline(writer, color=PURPLE, linewidth=2.4, label=f"measured writer: {writer:.1f} MB/s")
    axis.axhline(
        gate,
        color=AMBER,
        linewidth=1.8,
        linestyle="--",
        label=f"qualification gate: {gate:.0f} MB/s",
    )
    for bar, demand, item in zip(bars, demands, modes, strict=True):
        state = "enabled" if item["enabled"] else "disabled"
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            demand + 2.5,
            f"{demand:.0f}\n{state}",
            ha="center",
            va="bottom",
            color=INK,
            fontweight="bold",
        )
    axis.set_ylabel("aggregate uncompressed CI16 input (MB/s)")
    axis.set_ylim(0.0, max(demands) * 1.22)
    axis.set_title(
        "Two receivers per radio × 4 bytes per CI16 sample; "
        "compression is not credited as transport headroom",
        loc="left",
        fontsize=11,
    )
    axis.legend(loc="upper left", frameon=False)
    _style_axis(axis)
    _save(figure, path)


def render_continuity(path: Path, document: dict[str, Any]) -> None:
    """Show missing-refill evidence and queue high-water together."""

    rows = [*document["qualification_captures"], *document["live_canaries"][:4]]
    labels = [item["label"] for item in rows]
    x_values = list(range(len(rows)))
    refill = document["runtime"]["refill_samples"]

    figure = Figure(figsize=(16.0, 9.0), constrained_layout=True)
    loss_axis, queue_axis = figure.subplots(2, 1, sharex=True)
    figure.suptitle(
        "Capture continuity and host-queue evidence",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    for stream_index, (offset, color, marker) in enumerate(
        ((-0.13, BLUE, "o"), (0.13, PURPLE, "s"))
    ):
        loss_refills = [item["missing_samples"][stream_index] / refill for item in rows]
        high_water = [item["queue_high_water_refills"][stream_index] for item in rows]
        loss_axis.scatter(
            [x + offset for x in x_values],
            loss_refills,
            color=color,
            marker=marker,
            s=72,
            zorder=3,
            label=f"stream {stream_index}",
        )
        queue_axis.scatter(
            [x + offset for x in x_values],
            high_water,
            color=color,
            marker=marker,
            s=72,
            zorder=3,
            label=f"stream {stream_index}",
        )
    loss_axis.set_ylabel("missing 1,048,576-sample refills")
    loss_axis.set_ylim(-0.15, 1.25)
    loss_axis.set_title(
        "A · Only two stream trials lost one refill; both retained a full logical device-time axis",
        loc="left",
        fontweight="bold",
    )
    loss_axis.legend(frameon=False, loc="upper left", ncol=2)
    _style_axis(loss_axis)

    queue_axis.axhline(
        24, color=RED, linewidth=1.8, linestyle="--", label="qualification maximum: 24/32"
    )
    queue_axis.set_ylabel("queue high-water (refills)")
    queue_axis.set_ylim(0, 32)
    queue_axis.set_title(
        "B · Every observed high-water remained far below the 24/32 acceptance ceiling",
        loc="left",
        fontweight="bold",
    )
    queue_axis.set_xticks(x_values, labels, rotation=28, ha="right")
    queue_axis.legend(frameon=False, loc="upper left", ncol=3)
    _style_axis(queue_axis)
    _save(figure, path)


def render_performance(path: Path, document: dict[str, Any]) -> None:
    """Compare sealed analysis latency and HTTP delivery by mode."""

    run_by_label = {item["label"]: item for item in document["live_canaries"]}
    checks = document["http_artifact_checks"]
    live_labels = ("live 2.5", "live 3", "live 5", "live mixed")
    labels = [check["label"] for check in checks]
    durations = [run_by_label[label]["analysis_duration_seconds"] / 60.0 for label in live_labels]
    throughput = [check["bytes_per_second"] / 1_000_000.0 for check in checks]
    payload = [check["total_bytes"] / 1_000_000.0 for check in checks]

    figure = Figure(figsize=(15.2, 7.8), constrained_layout=True)
    latency_axis, http_axis = figure.subplots(1, 2)
    figure.suptitle(
        "Native Standard analysis and sealed-PNG delivery",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    latency_bars = latency_axis.bar(
        labels, durations, color=(BLUE, GREEN, PURPLE, AMBER), edgecolor=INK, linewidth=0.8
    )
    for bar, value in zip(latency_bars, durations, strict=True):
        latency_axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 0.55,
            f"{value:.1f} min",
            ha="center",
            color=INK,
            fontweight="bold",
        )
    latency_axis.set_ylabel("capture-to-sealed analysis latency (minutes)")
    latency_axis.set_ylim(0.0, max(durations) * 1.18)
    latency_axis.set_title("A · Same 12-job / 98-product graph", loc="left", fontweight="bold")
    _style_axis(latency_axis)

    x_values = list(range(len(labels)))
    http_bars = http_axis.bar(
        x_values, throughput, color=(BLUE, GREEN, PURPLE, AMBER), edgecolor=INK, linewidth=0.8
    )
    for bar, speed, size in zip(http_bars, throughput, payload, strict=True):
        http_axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            speed + 1.7,
            f"{speed:.1f} MB/s\n{size:.1f} MB",
            ha="center",
            color=INK,
            fontsize=9,
            fontweight="bold",
        )
    http_axis.set_xticks(x_values, labels)
    http_axis.set_ylabel("aggregate HTTP PNG throughput (MB/s)")
    http_axis.set_ylim(0.0, max(throughput) * 1.22)
    http_axis.set_title(
        "B · 59 pre-rendered sealed PNGs per capture", loc="left", fontweight="bold"
    )
    _style_axis(http_axis)
    _save(figure, path)


def render_timeline(path: Path, document: dict[str, Any]) -> None:
    """Render the qualification, deployment, and canary sequence."""

    events = document["timeline"]
    times = [datetime.fromisoformat(item["utc"].replace("Z", "+00:00")) for item in events]
    origin = min(times)
    minutes = [(value - origin).total_seconds() / 60.0 for value in times]
    colors = {"gate": BLUE, "deploy": GREEN, "capture": PURPLE, "incident": RED}
    y_positions = list(reversed(range(len(events))))

    figure = Figure(figsize=(15.5, 9.2), constrained_layout=True)
    axis = figure.subplots()
    figure.suptitle(
        "Release qualification, deployment, and live-verification timeline",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    for y, minute, event, timestamp in zip(y_positions, minutes, events, times, strict=True):
        color = colors[event["category"]]
        axis.hlines(y, 0.0, minute, color=color, linewidth=2.1, alpha=0.72)
        axis.scatter(
            minute,
            y,
            color=color,
            s=88,
            zorder=3,
            edgecolor=INK,
            linewidth=0.7,
        )
        axis.text(
            minute + 2.1,
            y,
            f"{timestamp.strftime('%H:%M:%S')} UTC",
            ha="left",
            va="center",
            color=INK,
            fontsize=9,
            fontweight=("bold" if event["category"] in {"deploy", "incident"} else "normal"),
        )
    axis.set_yticks(y_positions, [item["label"] for item in events])
    axis.set_xlim(-1.0, max(minutes) + 18.0)
    axis.set_xlabel(f"minutes since {origin.strftime('%H:%M:%S')} UTC on 2026-08-27")
    axis.set_title(
        "The API restart occurred after qualification and live capture; "
        "it did not alter sealed recording or product bytes",
        loc="left",
        fontsize=11,
    )
    legend = [
        Patch(facecolor=color, edgecolor="none", label=label)
        for label, color in (
            ("qualification gate", BLUE),
            ("deployment", GREEN),
            ("capture", PURPLE),
            ("incident", RED),
        )
    ]
    axis.legend(handles=legend, frameon=False, loc="lower right", ncol=4)
    _style_axis(axis, grid_axis="x")
    _save(figure, path)


def _flow_box(
    axis: Axes, x: float, y: float, width: float, height: float, title: str, detail: str, color: str
) -> None:
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.02,rounding_size=0.025",
            facecolor=color,
            edgecolor=INK,
            linewidth=1.2,
            alpha=0.9,
        )
    )
    axis.text(
        x + width / 2.0,
        y + height * 0.64,
        title,
        ha="center",
        va="center",
        color=WHITE,
        fontsize=11,
        fontweight="bold",
    )
    axis.text(
        x + width / 2.0,
        y + height * 0.28,
        detail,
        ha="center",
        va="center",
        color=WHITE,
        fontsize=8.7,
    )


def render_flow(path: Path, document: dict[str, Any]) -> None:
    """Render the common no-resampling capture-to-browser flow."""

    figure = Figure(figsize=(16.0, 8.2), constrained_layout=True)
    axis = figure.subplots()
    figure.suptitle(
        "One native-rate, validity-aware pipeline from radio to browser",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    boxes = (
        (0.03, 0.61, 0.16, 0.20, "Radio capture", "Fs = RF BW\nexact IF readback", BLUE),
        (
            0.22,
            0.61,
            0.16,
            0.20,
            "Device-axis V3/V4",
            "fixed logical size\nphysical zero fill",
            GREEN,
        ),
        (
            0.41,
            0.61,
            0.16,
            0.20,
            "Validity authority",
            "timeline + gap map\nsegment inventory",
            AMBER,
        ),
        (0.60, 0.61, 0.16, 0.20, "Four path jobs", "native Fs kernels\nno cross-gap state", PURPLE),
        (
            0.79,
            0.61,
            0.18,
            0.20,
            "Radio + pair reducers",
            "valid-time intersection\nsufficient statistics",
            RED,
        ),
        (0.16, 0.20, 0.20, 0.20, "Run seal", "12 jobs\n98 products", INK),
        (0.41, 0.20, 0.20, 0.20, "PNG projection", "11 path families\n59 sealed PNGs", BLUE),
        (0.66, 0.20, 0.20, 0.20, "HTTP + Web UI", "serve catalog bytes\nno IQ re-analysis", GREEN),
    )
    for box in boxes:
        _flow_box(axis, *box)
    arrow_pairs = (
        ((0.19, 0.71), (0.22, 0.71)),
        ((0.38, 0.71), (0.41, 0.71)),
        ((0.57, 0.71), (0.60, 0.71)),
        ((0.76, 0.71), (0.79, 0.71)),
        ((0.88, 0.61), (0.30, 0.40)),
        ((0.36, 0.30), (0.41, 0.30)),
        ((0.61, 0.30), (0.66, 0.30)),
    )
    for start, stop in arrow_pairs:
        axis.annotate(
            "",
            xy=stop,
            xytext=start,
            arrowprops={
                "arrowstyle": "-|>",
                "color": INK,
                "lw": 1.7,
                "connectionstyle": "arc3,rad=0.0",
            },
        )
    axis.text(
        0.5,
        0.05,
        "Lossless captures are the one-segment special case. Gapped captures keep the "
        "same logical axis, but invalid samples never become RF evidence.",
        ha="center",
        va="center",
        color=INK,
        fontsize=11,
        fontweight="bold",
    )
    _save(figure, path)


def main() -> None:
    arguments = _arguments()
    document = _load(arguments.data)
    output = arguments.output_root
    render_rf_geometry(output / FIGURE_NAMES["rf_geometry"], document)
    render_transport(output / FIGURE_NAMES["transport"], document)
    render_continuity(output / FIGURE_NAMES["continuity"], document)
    render_performance(output / FIGURE_NAMES["performance"], document)
    render_timeline(output / FIGURE_NAMES["timeline"], document)
    render_flow(output / FIGURE_NAMES["flow"], document)


if __name__ == "__main__":
    main()
