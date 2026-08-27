#!/usr/bin/env python3
"""Render the capture-170330 quality-comparison report figures.

This is a pure presentation layer over a checked-in, machine-readable summary.
It does not read IQ, rerun the timing experiment, contact radios, or treat this
observational capture pair as a controlled RF-bandwidth experiment.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

DEFAULT_DATA = Path(
    "reports/figures/2026_08_27_170330_capture_quality/capture-quality-results.json"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA.parent
EXPECTED_SCHEMA = "org.leo.report.capture-170330-quality-comparison/v1"

FIGURE_NAMES = {
    "integrity": "capture-integrity.png",
    "glrt": "glrt-quality.png",
    "timing": "timing-repeatability.png",
    "claims": "claim-boundary.png",
}

INK = "#17354a"
PRIOR = "#b9673f"
NEW = "#287c64"
BLUE = "#2f83b7"
AMBER = "#d7972b"
RED = "#b5534c"
GRAY = "#8a99a3"
LIGHT_GRAY = "#d5dce1"
VERY_LIGHT_GRAY = "#f0f3f5"
PALE_GREEN = "#e5f1eb"
PALE_AMBER = "#fbf0dc"
PALE_RED = "#f8e7e5"
WHITE = "#ffffff"


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
    captures = document.get("captures")
    if not isinstance(captures, dict) or set(captures) != {"prior", "new"}:
        raise ValueError("exactly prior and new captures are required")
    for key in ("prior", "new"):
        capture = captures[key]
        if capture.get("sample_rate_hz") != 5_000_000:
            raise ValueError("comparison requires 5 MS/s captures")
        glrt = capture.get("glrt")
        if not isinstance(glrt, dict):
            raise ValueError(f"{key} GLRT summary is missing")
        if glrt["passing_windows"] > glrt["valid_windows"]:
            raise ValueError(f"{key} passing GLRT count exceeds valid count")
        if capture["segment_count"] != capture["gap_count"] + 1:
            raise ValueError(f"{key} continuity segment accounting does not close")
    time_bins = document.get("glrt_time_bins")
    if not isinstance(time_bins, dict) or len(time_bins.get("columns", [])) != 7:
        raise ValueError("seven-column GLRT time bins are required")
    for key in ("prior", "new"):
        rows = time_bins.get(key)
        if not isinstance(rows, list) or len(rows) != 30:
            raise ValueError(f"{key} must have thirty two-second GLRT bins")
        if any(not isinstance(row, list) or len(row) != 7 for row in rows):
            raise ValueError(f"{key} GLRT bins have the wrong shape")
    timing = document.get("timing_evaluation")
    if not isinstance(timing, dict) or not timing.get("method"):
        raise ValueError("timing evaluation summary is required")
    claims = document.get("claim_boundary")
    if not isinstance(claims, dict):
        raise ValueError("claim boundary is required")
    if claims.get("bandwidth_causality_claimed") is not False:
        raise ValueError("this observational comparison cannot claim bandwidth causality")
    if claims.get("absolute_toa_accuracy_measured") is not False:
        raise ValueError("the evaluation did not measure absolute TOA accuracy")
    if claims.get("blind_end_to_end") is not False:
        raise ValueError("the timing evaluation is not blind end-to-end")
    phase = document.get("phase_tracking_comparison")
    if not isinstance(phase, dict) or phase.get("absolute_carrier_phase_resolved") is not False:
        raise ValueError("phase tracking must preserve the unresolved absolute-phase boundary")


def _style_axis(axis: Axes, *, grid_axis: str = "y") -> None:
    axis.grid(True, axis=grid_axis, color=LIGHT_GRAY, linewidth=0.8, alpha=0.7)
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


def _two_bar_metric(
    axis: Axes,
    *,
    title: str,
    values: tuple[float, float],
    formatter: Callable[[float], str],
    ylabel: str,
) -> None:
    bars = axis.bar(
        [0, 1],
        values,
        width=0.58,
        color=[PRIOR, NEW],
        edgecolor=INK,
        linewidth=0.8,
    )
    top = max(values)
    axis.set_ylim(0.0, max(top * 1.26, 1.0))
    for bar, value in zip(bars, values, strict=True):
        y = value + max(top * 0.035, 0.04)
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            y,
            formatter(value),
            ha="center",
            va="bottom",
            color=INK,
            fontweight="bold",
            fontsize=10,
        )
    axis.set_xticks([0, 1], ["Prior\n182310", "New\n170330"])
    axis.set_ylabel(ylabel)
    axis.set_title(title, loc="left", fontsize=12, fontweight="bold")
    _style_axis(axis)


def render_integrity(path: Path, document: dict[str, Any]) -> None:
    """Show device-axis continuity and refill-pressure evidence."""

    prior = document["captures"]["prior"]
    new = document["captures"]["new"]
    figure = Figure(figsize=(16.0, 9.2), constrained_layout=True)
    axes = figure.subplots(2, 3)
    figure.suptitle(
        "Capture integrity: the selected new 5 MS/s path is continuous for 60 seconds",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )

    metrics: list[tuple[str, tuple[float, float], Callable[[float], str], str]] = [
        (
            "Missing device samples",
            (prior["missing_samples"] / 1_000_000, new["missing_samples"] / 1_000_000),
            lambda value: f"{value:.2f} M" if value else "0",
            "missing samples (millions)",
        ),
        (
            "Counter gaps",
            (prior["gap_count"], new["gap_count"]),
            lambda value: f"{value:.0f}",
            "gap count",
        ),
        (
            "Continuity segments",
            (prior["segment_count"], new["segment_count"]),
            lambda value: f"{value:.0f}",
            "segment count",
        ),
        (
            "Longest contiguous interval",
            (prior["longest_contiguous_s"], new["longest_contiguous_s"]),
            lambda value: f"{value:.2f} s" if value < 10 else f"{value:.0f} s",
            "seconds",
        ),
        (
            "Refill service calls",
            (prior["refill_count"], new["refill_count"]),
            lambda value: f"{value:,.0f}",
            "calls in 60 s",
        ),
        (
            "Writer queue high-water",
            (prior["queue_high_water_refills"], new["queue_high_water_refills"]),
            lambda value: f"{value:.0f} / 32",
            "queued refills",
        ),
    ]
    for axis, (title, values, formatter, ylabel) in zip(axes.flat, metrics, strict=True):
        _two_bar_metric(
            axis,
            title=title,
            values=values,
            formatter=formatter,
            ylabel=ylabel,
        )
    figure.supxlabel(
        "Selected lower-edge RX1 path · refill size changed 262,144 → 1,048,576 samples; "
        "these configuration changes co-occurred and do not isolate causality.",
        color=INK,
        fontsize=10,
    )
    _save(figure, path)


def render_glrt(path: Path, document: dict[str, Any]) -> None:
    """Show known-pilot GLRT quality through time and in aggregate."""

    prior = document["captures"]["prior"]
    new = document["captures"]["new"]
    bins = document["glrt_time_bins"]
    figure = Figure(figsize=(16.0, 10.2), constrained_layout=True)
    grid = figure.add_gridspec(2, 2, height_ratios=(1.2, 1.0))
    score_axis = figure.add_subplot(grid[0, :])
    pass_axis = figure.add_subplot(grid[1, 0])
    aggregate_axis = figure.add_subplot(grid[1, 1])
    figure.suptitle(
        "Known-pilot GLRT: stronger and more persistent evidence on the selected new path",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )

    for key, color in (("prior", PRIOR), ("new", NEW)):
        rows = bins[key]
        times = [row[0] for row in rows]
        medians = [row[1] for row in rows]
        p10 = [row[2] for row in rows]
        p90 = [row[3] for row in rows]
        label = document["captures"][key]["label"]
        score_axis.fill_between(times, p10, p90, color=color, alpha=0.14)
        score_axis.plot(
            times,
            medians,
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=3.5,
            label=f"{label} · median (P10–P90 band)",
        )
    score_axis.set_xlim(0, 60)
    score_axis.set_ylim(0, 0.92)
    score_axis.set_xlabel("elapsed capture time (s)")
    score_axis.set_ylabel("exact known-pilot score")
    score_axis.set_title(
        "Two-second summaries of valid 20 ms windows",
        loc="left",
        fontsize=12,
        fontweight="bold",
    )
    score_axis.legend(loc="lower right", frameon=False, ncol=2)
    _style_axis(score_axis)

    for key, color in (("prior", PRIOR), ("new", NEW)):
        rows = bins[key]
        times = [row[0] for row in rows]
        pass_fractions = [row[5] * 100 for row in rows]
        capture = document["captures"][key]
        glrt = capture["glrt"]
        pass_axis.plot(
            times,
            pass_fractions,
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=3.5,
            label=(f"{capture['label']}: {glrt['passing_windows']:,}/{glrt['valid_windows']:,}"),
        )
    pass_axis.set_xlim(0, 60)
    pass_axis.set_ylim(40, 102)
    pass_axis.set_xlabel("elapsed capture time (s)")
    pass_axis.set_ylabel("margin-gate pass fraction (%)")
    pass_axis.set_title("Detection availability", loc="left", fontsize=12, fontweight="bold")
    pass_axis.legend(loc="lower right", frameon=False)
    _style_axis(pass_axis)

    metric_labels = [
        "Median exact\nscore",
        "Median GLRT\nmargin",
        "Known-pilot hard\nsymbol accuracy",
    ]
    prior_values = [
        prior["glrt"]["passing_median_exact_score"],
        prior["glrt"]["passing_median_margin"],
        prior["known_pilot_hard_symbol_accuracy"],
    ]
    new_values = [
        new["glrt"]["passing_median_exact_score"],
        new["glrt"]["passing_median_margin"],
        new["known_pilot_hard_symbol_accuracy"],
    ]
    x_positions = list(range(len(metric_labels)))
    width = 0.35
    old_bars = aggregate_axis.bar(
        [x - width / 2 for x in x_positions],
        prior_values,
        width,
        color=PRIOR,
        edgecolor=INK,
        linewidth=0.7,
        label="Prior 182310",
    )
    new_bars = aggregate_axis.bar(
        [x + width / 2 for x in x_positions],
        new_values,
        width,
        color=NEW,
        edgecolor=INK,
        linewidth=0.7,
        label="New 170330",
    )
    for bars in (old_bars, new_bars):
        for bar in bars:
            value = bar.get_height()
            aggregate_axis.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.018,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=INK,
                fontweight="bold",
            )
    aggregate_axis.set_xticks(x_positions, metric_labels)
    aggregate_axis.set_ylim(0, 0.82)
    aggregate_axis.set_ylabel("unitless score or fraction")
    aggregate_axis.set_title(
        "Aggregate selected-path quality",
        loc="left",
        fontsize=12,
        fontweight="bold",
    )
    aggregate_axis.legend(loc="upper left", frameon=False)
    _style_axis(aggregate_axis)
    _save(figure, path)


def render_timing(path: Path, document: dict[str, Any]) -> None:
    """Separate timing repeatability from physical correlation-lobe width."""

    timing = document["timing_evaluation"]
    prior = timing["prior"]
    new = timing["new"]
    figure = Figure(figsize=(16.0, 10.0), constrained_layout=True)
    grid = figure.add_gridspec(2, 2, height_ratios=(1.3, 1.0))
    residual_axis = figure.add_subplot(grid[0, :])
    lobe_axis = figure.add_subplot(grid[1, 0])
    split_axis = figure.add_subplot(grid[1, 1])
    figure.suptitle(
        "Frame timing: conditional repeatability improved; first-window lobe width was similar",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )

    labels = [
        "Integer epoch\nRMS",
        "Integer epoch\nP90",
        "Pilot-refined\nRMS",
        "Pilot-refined\nP90",
    ]
    prior_values = [
        prior["integer_epoch_rms_ns"],
        prior["integer_epoch_p90_ns"],
        prior["matched_pilot_refined_rms_ns"],
        prior["matched_pilot_refined_p90_ns"],
    ]
    new_values = [
        new["integer_epoch_rms_ns"],
        new["integer_epoch_p90_ns"],
        new["matched_pilot_refined_rms_ns"],
        new["matched_pilot_refined_p90_ns"],
    ]
    x_positions = list(range(len(labels)))
    width = 0.34
    old_bars = residual_axis.bar(
        [x - width / 2 for x in x_positions],
        prior_values,
        width,
        color=PRIOR,
        edgecolor=INK,
        linewidth=0.7,
        label="Prior 182310",
    )
    new_bars = residual_axis.bar(
        [x + width / 2 for x in x_positions],
        new_values,
        width,
        color=NEW,
        edgecolor=INK,
        linewidth=0.7,
        label="New 170330",
    )
    for bars in (old_bars, new_bars):
        for bar in bars:
            value = bar.get_height()
            residual_axis.text(
                bar.get_x() + bar.get_width() / 2,
                value + 3.0,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=INK,
                fontweight="bold",
            )
    residual_axis.axvline(1.5, color=LIGHT_GRAY, linewidth=1.3)
    residual_axis.text(
        2.5,
        139,
        f"Matched pilot-refined RMS is {timing['prior_to_new_matched_rms_ratio']:.2f}× smaller",
        ha="center",
        va="top",
        color=NEW,
        fontsize=11,
        fontweight="bold",
    )
    residual_axis.set_xticks(x_positions, labels)
    residual_axis.set_ylim(0, 145)
    residual_axis.set_ylabel("absolute residual (ns)")
    residual_axis.set_title(
        "In-sample residual to a quadratic receiver-relative frame-epoch track",
        loc="left",
        fontsize=12,
        fontweight="bold",
    )
    residual_axis.legend(loc="upper left", frameon=False)
    _style_axis(residual_axis)

    _two_bar_metric(
        lobe_axis,
        title="First selected-window half-prominence lobe",
        values=(
            prior["half_prominence_lobe_width_ns"],
            new["half_prominence_lobe_width_ns"],
        ),
        formatter=lambda value: f"{value:.0f} ns",
        ylabel="nanoseconds",
    )
    lobe_axis.set_xlabel("first selected window · median baseline · ±12-sample grid")

    _two_bar_metric(
        split_axis,
        title="Disjoint pilot-half disagreement",
        values=(
            prior["disjoint_pilot_half_std_ns"],
            new["disjoint_pilot_half_std_ns"],
        ),
        formatter=lambda value: f"{value:.1f} ns",
        ylabel="detrended standard deviation (ns)",
    )
    figure.supxlabel(
        "20 ms windows centered 0.01–4.13 s (covering 0–4.14 s) · 290 matched "
        "50%-overlapping windows · post-hoc branch-conditioned in-sample residuals · "
        "not TOA accuracy, resolution, pseudorange, or phase lock.",
        color=INK,
        fontsize=10,
    )
    _save(figure, path)


def _box(
    axis: Axes,
    *,
    xy: tuple[float, float],
    width: float,
    height: float,
    facecolor: str,
    edgecolor: str,
    title: str,
    lines: list[str],
    title_color: str = INK,
) -> None:
    x, y = xy
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.012",
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=1.4,
        )
    )
    axis.text(
        x + 0.018,
        y + height - 0.035,
        title,
        ha="left",
        va="top",
        color=title_color,
        fontsize=12,
        fontweight="bold",
    )
    axis.text(
        x + 0.018,
        y + height - 0.085,
        "\n".join(lines),
        ha="left",
        va="top",
        color=INK,
        fontsize=10.2,
        linespacing=1.42,
    )


def render_claim_boundary(path: Path, document: dict[str, Any]) -> None:
    """Make the observational experiment and its claim boundary explicit."""

    prior = document["captures"]["prior"]
    new = document["captures"]["new"]
    figure = Figure(figsize=(16.0, 9.2), constrained_layout=True)
    axis = figure.subplots()
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    figure.suptitle(
        "What this capture comparison can—and cannot—establish",
        fontsize=18,
        fontweight="bold",
        color=INK,
    )

    _box(
        axis,
        xy=(0.035, 0.68),
        width=0.36,
        height=0.24,
        facecolor=VERY_LIGHT_GRAY,
        edgecolor=PRIOR,
        title="Prior capture · 182310",
        lines=[
            f"{prior['starlink_channel']} {prior['starlink_edge']} · RX1 · 5 MS/s",
            f"RF BW {prior['rf_bandwidth_hz'] / 1e6:g} MHz · {prior['gain_mode']}",
            f"refill {prior['refill_samples']:,} · {prior['gap_count']} gaps",
            "observed on 2026-08-26",
        ],
    )
    _box(
        axis,
        xy=(0.605, 0.68),
        width=0.36,
        height=0.24,
        facecolor=VERY_LIGHT_GRAY,
        edgecolor=NEW,
        title="New capture · 170330",
        lines=[
            f"{new['starlink_channel']} {new['starlink_edge']} · RX1 · 5 MS/s",
            f"RF BW {new['rf_bandwidth_hz'] / 1e6:g} MHz · manual {new['gain_db']:.0f} dB",
            f"refill {new['refill_samples']:,} · {new['gap_count']} gaps",
            "observed on 2026-08-27",
        ],
    )
    axis.add_patch(
        FancyArrowPatch(
            (0.415, 0.80),
            (0.585, 0.80),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=1.8,
            color=AMBER,
        )
    )
    axis.text(
        0.5,
        0.855,
        "observational comparison",
        ha="center",
        va="center",
        color=INK,
        fontsize=11,
        fontweight="bold",
    )
    axis.text(
        0.5,
        0.65,
        "channel · gain · RF bandwidth · refill geometry · software revision all changed",
        ha="center",
        va="center",
        color=RED,
        fontsize=10,
    )

    method_labels = [
        "Persisted device-axis\ncontinuity",
        "20 ms known-pilot\nGLRT windows",
        "Post-hoc timing branch +\n3-point peak refinement",
        "Receiver-relative\nrepeatability metrics",
    ]
    centers = [0.13, 0.38, 0.63, 0.88]
    for index, (center, label) in enumerate(zip(centers, method_labels, strict=True)):
        axis.add_patch(
            FancyBboxPatch(
                (center - 0.10, 0.535),
                0.20,
                0.09,
                boxstyle="round,pad=0.008,rounding_size=0.01",
                facecolor=WHITE,
                edgecolor=BLUE,
                linewidth=1.2,
            )
        )
        axis.text(center, 0.58, label, ha="center", va="center", color=INK, fontsize=9.5)
        if index < len(centers) - 1:
            axis.add_patch(
                FancyArrowPatch(
                    (center + 0.105, 0.58),
                    (centers[index + 1] - 0.105, 0.58),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    linewidth=1.2,
                    color=GRAY,
                )
            )

    _box(
        axis,
        xy=(0.025, 0.08),
        width=0.30,
        height=0.37,
        facecolor=PALE_GREEN,
        edgecolor=NEW,
        title="Observed on selected path",
        lines=[
            "✓ gaps: 61 → 0",
            "✓ GLRT pass: 89.0% → 99.8%",
            "✓ pilot accuracy: 48.4% → 70.6%",
            "✓ matched timing RMS: 21.1 → 4.83 ns",
            "✓ first-window lobe: ~609 → ~599 ns",
        ],
    )
    _box(
        axis,
        xy=(0.35, 0.08),
        width=0.30,
        height=0.37,
        facecolor=PALE_AMBER,
        edgecolor=AMBER,
        title="Detection is not phase lock",
        lines=[
            "• new RX1 GLRT 5,987/5,999; phase 0/256",
            "• new RX0 GLRT 5,649/5,999; phase 10/224",
            "• best new/old innovation: 0.0637/0.151 rad",
            "• fit RMS: 12.14/32.63 Hz",
            "• held-out RMS: 12.87/35.25 Hz",
            "• timing replay uses RX1, not phase-qualified RX0",
        ],
    )
    _box(
        axis,
        xy=(0.675, 0.08),
        width=0.30,
        height=0.37,
        facecolor=PALE_RED,
        edgecolor=RED,
        title="Not established",
        lines=[
            "× bandwidth caused the increase",
            "× blind end-to-end timing accuracy",
            "× absolute TOA or pseudorange",
            "× persistent, absolute, or cross-radio phase lock",
            "× same-channel / same-satellite pairing",
        ],
    )
    _save(figure, path)


def render_all(output_root: Path, document: dict[str, Any]) -> list[Path]:
    """Render every report figure and return their paths."""

    paths = {key: output_root / name for key, name in FIGURE_NAMES.items()}
    render_integrity(paths["integrity"], document)
    render_glrt(paths["glrt"], document)
    render_timing(paths["timing"], document)
    render_claim_boundary(paths["claims"], document)
    return list(paths.values())


def main() -> None:
    args = _arguments()
    document = _load(args.data)
    for path in render_all(args.output_root, document):
        print(path)


if __name__ == "__main__":
    main()
