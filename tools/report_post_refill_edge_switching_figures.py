#!/usr/bin/env python3
"""Render publication figures for the post-refill edge-switching replay.

The renderer is intentionally a pure presentation layer over the persisted
``edge-switching-results.json`` receipt.  It does not read the radio corpus,
rerun an estimator, or reinterpret a virtual mask as hardware evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle  # noqa: E402

DEFAULT_RESULTS = Path(
    "reports/figures/2026_08_27_post_refill_edge_switching/edge-switching-results.json"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_RESULTS.parent
EXPECTED_SCHEMA = "org.leo.research.post-refill-edge-switching/v1"

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

CHANNEL_COLORS = {
    "ch1": BLUE,
    "ch2": GREEN,
    "ch3": AMBER,
    "ch4": PURPLE,
}

FIGURE_NAMES = {
    "approach": "edge-switching-approach.png",
    "data_retention": "edge-switching-data-retention.png",
    "closure": "opposite-edge-closure.png",
    "sensitivity": "virtual-switching-sensitivity.png",
}

PRIMARY_CLOSURE_TIMES = {"085623", "101702", "103607", "115401", "130425"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def load_results(path: Path) -> dict[str, Any]:
    """Load and validate the published presentation receipt."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    document = value.get("payload", value)
    if not isinstance(document, dict):
        raise ValueError(f"expected object payload: {path}")
    validate_results(document)
    return document


def validate_results(document: dict[str, Any]) -> None:
    """Fail closed when a receipt cannot support every promised figure."""

    if document.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(f"expected schema {EXPECTED_SCHEMA!r}, got {document.get('schema')!r}")
    inventory = document.get("inventory")
    retrospective = document.get("retrospective")
    method = document.get("method")
    if not isinstance(inventory, dict) or not isinstance(inventory.get("captures"), list):
        raise ValueError("inventory.captures is required")
    if not isinstance(retrospective, dict) or not retrospective.get("opposite_edge_events"):
        raise ValueError("retrospective.opposite_edge_events is required")
    if not isinstance(method, dict) or int(method.get("phase_count", 0)) <= 0:
        raise ValueError("method.phase_count must be positive")

    _fine_case(document)


def _fine_case(document: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    cases = document.get("prototype_cases", {})
    if not isinstance(cases, dict):
        raise ValueError("prototype_cases must be an object")
    for capture_id, case in cases.items():
        if isinstance(case, dict) and isinstance(case.get("fine"), dict):
            candidates.append((str(capture_id), case, case["fine"]))
    if not candidates:
        raise ValueError("at least one prototype case with fine measurements is required")
    return max(
        candidates,
        key=lambda item: int(item[2].get("baseline", {}).get("observation_count", 0)),
    )


def _coarse_case(case: dict[str, Any]) -> dict[str, Any]:
    coarse = case.get("coarse")
    if not isinstance(coarse, dict) or not isinstance(coarse.get("schedules"), list):
        raise ValueError("the fine prototype must also include coarse schedules")
    return coarse


def _schedule_rows(fine: dict[str, Any]) -> list[dict[str, Any]]:
    schedules = fine.get("schedules")
    sensitivity = fine.get("relative_timing_sensitivity", {}).get("schedules")
    if not isinstance(schedules, list) or not isinstance(sensitivity, list):
        raise ValueError("fine schedules and relative timing sensitivity are required")
    timing_by_label = {str(item["label"]): item for item in sensitivity}
    rows = []
    for schedule in schedules:
        label = str(schedule["label"])
        if schedule.get("status") != "complete" or label not in timing_by_label:
            raise ValueError(f"fine schedule is incomplete: {label}")
        rows.append({**schedule, "timing": timing_by_label[label]})
    if not rows:
        raise ValueError("at least one complete fine schedule is required")
    return rows


def _short_schedule_label(row: dict[str, Any]) -> str:
    dwell_ms = 1_000.0 * float(row["dwell_s"])
    if dwell_ms >= 999.5:
        return "1,000"
    if abs(dwell_ms - round(dwell_ms)) < 0.01:
        return f"{dwell_ms:.0f}"
    return f"{dwell_ms:.1f}"


def _capture_time(session_id: str) -> str:
    match = re.search(r"T(\d{6})-", session_id)
    return match.group(1) if match else session_id


def _innovation_gate_hz(fine: dict[str, Any]) -> float:
    semantics = str(fine.get("measurement_semantics", ""))
    match = re.search(r"absolute innovation\s*<=\s*([0-9.]+)\s*Hz", semantics)
    if match is None:
        raise ValueError("fine measurement semantics do not declare an innovation gate")
    return float(match.group(1))


def _style_axis(axis: Axes, *, grid_axis: str = "y") -> None:
    axis.grid(True, axis=grid_axis, color=LIGHT_GRAY, linewidth=0.8, alpha=0.58)
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


def render_approach(path: Path, document: dict[str, Any]) -> None:
    """Render the switching schedule and presentation-level estimator flow."""

    _capture_id, _case, fine = _fine_case(document)
    schedules = _schedule_rows(fine)
    shortest = min(schedules, key=lambda item: float(item["dwell_s"]))
    dwell_ms = 1_000.0 * float(shortest["dwell_s"])
    guard_ms = 1_000.0 * float(shortest["guard_s"])
    support_ms = 1_000.0 * float(shortest["measurement_duration_s"])
    phase_count = int(document["method"]["phase_count"])
    valid_frame_count = round((dwell_ms - guard_ms) * 0.750)
    frame_ms = dwell_ms / (valid_frame_count + 2)

    figure = Figure(figsize=(15.2, 8.0), constrained_layout=True)
    axes = figure.subplots(2, 1, gridspec_kw={"height_ratios": (1.12, 1.0)})
    timeline, flow = axes
    figure.suptitle(
        "Single-radio edge switching: conditional availability replay",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )

    cycles = 4
    timeline.set_xlim(0.0, cycles * dwell_ms)
    timeline.set_ylim(-0.45, 1.70)
    timeline.set_yticks((0.25, 1.05), ("lower edge", "upper edge"))
    timeline.set_xlabel("receiver-local time (ms)")
    timeline.set_title(
        f"A · Shortest schedule: 2 guard + {valid_frame_count} valid frames per dwell",
        loc="left",
        fontweight="bold",
    )
    timeline.grid(True, axis="x", color=LIGHT_GRAY, linewidth=0.8, alpha=0.58)
    timeline.set_axisbelow(True)
    for index in range(cycles):
        start = index * dwell_ms
        edge_y = 0.05 if index % 2 == 0 else 0.85
        edge_color = BLUE if index % 2 == 0 else AMBER
        edge_label = "L" if index % 2 == 0 else "U"
        timeline.add_patch(
            Rectangle(
                (start, edge_y),
                guard_ms,
                0.40,
                facecolor=GRAY,
                edgecolor="none",
                alpha=0.72,
                zorder=2,
            )
        )
        timeline.add_patch(
            Rectangle(
                (start + guard_ms, edge_y),
                dwell_ms - guard_ms,
                0.40,
                facecolor=edge_color,
                edgecolor="none",
                alpha=0.86,
                zorder=2,
            )
        )
        timeline.text(
            start + dwell_ms / 2.0,
            edge_y + 0.20,
            edge_label,
            ha="center",
            va="center",
            color=WHITE,
            fontweight="bold",
            fontsize=12,
            zorder=4,
        )
        for frame_index in range(valid_frame_count):
            center = start + guard_ms + (frame_index + 0.5) * frame_ms
            timeline.plot(
                center,
                edge_y + 0.48,
                marker="o",
                markersize=4.0,
                color=edge_color,
                markeredgecolor=WHITE,
                markeredgewidth=0.6,
                zorder=5,
            )
        timeline.axvline(start, color=INK, linewidth=0.8, alpha=0.45, zorder=1)
    timeline.axvline(cycles * dwell_ms, color=INK, linewidth=0.8, alpha=0.45)
    timeline.annotate(
        f"guard {guard_ms:.3f} ms",
        xy=(guard_ms / 2.0, 0.05),
        xytext=(guard_ms / 2.0, -0.18),
        ha="center",
        va="top",
        color=INK,
        arrowprops={"arrowstyle": "-[,widthB=1.0", "color": GRAY, "lw": 1.0},
    )
    timeline.annotate(
        f"valid {dwell_ms - guard_ms:.3f} ms",
        xy=((guard_ms + dwell_ms) / 2.0, 0.05),
        xytext=((guard_ms + dwell_ms) / 2.0, -0.18),
        ha="center",
        va="top",
        color=INK,
        arrowprops={"arrowstyle": "-[,widthB=2.4", "color": BLUE, "lw": 1.0},
    )
    timeline.legend(
        handles=(
            Patch(facecolor=GRAY, alpha=0.72, label="post-retune guard"),
            Patch(facecolor=BLUE, alpha=0.86, label="lower-edge valid support"),
            Patch(facecolor=AMBER, alpha=0.86, label="upper-edge valid support"),
            Line2D(
                (),
                (),
                color=INK,
                marker="o",
                linestyle="none",
                markersize=5,
                label="retained frame-CFO opportunity",
            ),
        ),
        loc="upper center",
        ncol=4,
        frameon=False,
    )
    timeline.tick_params(colors=INK)
    for spine in timeline.spines.values():
        spine.set_color(LIGHT_GRAY)

    flow.set_xlim(0.0, 1.0)
    flow.set_ylim(0.0, 1.0)
    flow.axis("off")
    flow.set_title("B · Presentation-level replay path", loc="left", fontweight="bold")
    boxes = (
        (
            0.02,
            f"Accepted frame CFO\n{support_ms * 1_000.0:.1f} µs pilot support",
            BLUE,
        ),
        (
            0.27,
            f"Strict interval mask\nwhole support after guard · {phase_count} phases",
            GREEN,
        ),
        (
            0.52,
            "Robust joint rate fit\n"
            r"$z_i=a_{path}+r_c t_i+s_i r_\Delta t_i/2+\epsilon_i$",
            PURPLE,
        ),
        (
            0.77,
            "Conditional sensitivity\n"
            r"$|r_{\Delta,masked}-r_{\Delta,full}|$ quantiles",
            AMBER,
        ),
    )
    for x, text, color in boxes:
        flow.add_patch(
            FancyBboxPatch(
                (x, 0.40),
                0.20,
                0.30,
                boxstyle="round,pad=0.016",
                facecolor=color,
                edgecolor=WHITE,
                linewidth=1.4,
                alpha=0.96,
            )
        )
        flow.text(
            x + 0.10,
            0.55,
            text,
            ha="center",
            va="center",
            color=WHITE,
            fontsize=10.2,
        )
    for x in (0.225, 0.475, 0.725):
        flow.annotate(
            "",
            xy=(x + 0.035, 0.55),
            xytext=(x, 0.55),
            arrowprops={"arrowstyle": "->", "color": INK, "lw": 1.8},
        )
    flow.text(
        0.50,
        0.17,
        (
            "Virtual masks test product availability only; they do not simulate Fast Lock "
            "settling, phase return, or reacquisition."
        ),
        ha="center",
        va="center",
        color=RED,
        fontsize=11,
        fontweight="bold",
    )
    _save(figure, path)


def render_data_retention(path: Path, document: dict[str, Any]) -> None:
    """Render the declared hyperparameters and successive retention stages."""

    _capture_id, _case, fine = _fine_case(document)
    schedules = _schedule_rows(fine)
    captures = document["inventory"]["captures"]
    track_inventory = sorted(
        fine["track_inventory"],
        key=lambda item: (
            str(item["path_id"]).split("/")[0],
            str(item["path_id"]).split("/")[-1],
        ),
    )
    phase_count = int(document["method"]["phase_count"])
    gate_hz = _innovation_gate_hz(fine)
    support_us = float(track_inventory[0]["pilot_support_duration_us"])

    figure = Figure(figsize=(15.2, 9.6), constrained_layout=True)
    layout_engine = figure.get_layout_engine()
    if layout_engine is not None:
        layout_engine.set(rect=(0.0, 0.0, 1.0, 0.90))
    axes = figure.subplots(2, 2)
    figure.text(
        0.5,
        0.975,
        "Post-refill corpus and replay-retention audit",
        ha="center",
        va="top",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )
    figure.text(
        0.5,
        0.928,
        (
            f"Hyperparameters: {phase_count} schedule phases · 2-frame guard "
            f"({1_000.0 * float(document['method']['guard_s']):.3f} ms) · "
            f"{support_us:.1f} µs pilot support · |innovation| ≤ {gate_hz:.0f} Hz"
        ),
        ha="center",
        color=INK,
        fontsize=11,
    )

    rates = sorted({int(item["sample_rate_hz"]) for item in captures})
    clean_counts = np.asarray(
        [
            sum(bool(item["clean"]) and int(item["sample_rate_hz"]) == rate for item in captures)
            for rate in rates
        ]
    )
    degraded_counts = np.asarray(
        [
            sum(
                not bool(item["clean"]) and int(item["sample_rate_hz"]) == rate for item in captures
            )
            for rate in rates
        ]
    )
    positions = np.arange(len(rates))
    axes[0, 0].bar(positions, clean_counts, color=GREEN, label="clean")
    axes[0, 0].bar(
        positions,
        degraded_counts,
        bottom=clean_counts,
        color=RED,
        label="degraded",
    )
    axes[0, 0].set_xticks(positions, [f"{rate / 1e6:g}" for rate in rates])
    axes[0, 0].set_xlabel("sample rate (MS/s)")
    axes[0, 0].set_ylabel("capture count")
    axes[0, 0].set_ylim(0.0, 1.15 * float(np.max(clean_counts + degraded_counts)))
    axes[0, 0].set_title("A · Authoritative capture inventory", loc="left", fontweight="bold")
    axes[0, 0].legend(frameon=False)
    for position, clean, degraded in zip(positions, clean_counts, degraded_counts, strict=True):
        total = int(clean + degraded)
        axes[0, 0].text(
            position,
            total + 0.45,
            str(total),
            ha="center",
            va="bottom",
            color=INK,
            fontweight="bold",
        )
    _style_axis(axes[0, 0])

    path_labels = []
    returned = []
    gated = []
    for item in track_inventory:
        path_id = str(item["path_id"])
        path_labels.append(
            path_id.split("/")[0].replace("stream-", "S") + " · " + path_id.split("/")[-1]
        )
        returned.append(int(item["returned_frame_count"]))
        gated.append(int(item["gated_measurement_count"]))
    track_positions = np.arange(len(path_labels))
    axes[0, 1].bar(track_positions, returned, color=VERY_LIGHT_GRAY, label="returned frames")
    axes[0, 1].bar(track_positions, gated, color=BLUE, label="innovation-gated")
    axes[0, 1].set_xticks(track_positions, path_labels)
    axes[0, 1].set_ylabel("frame count")
    axes[0, 1].set_title("B · Receiver-local frame measurement gate", loc="left", fontweight="bold")
    axes[0, 1].legend(frameon=False)
    for position, accepted, total in zip(track_positions, gated, returned, strict=True):
        axes[0, 1].text(
            position,
            accepted + 100,
            f"{accepted / total:.1%}",
            ha="center",
            va="bottom",
            color=INK,
            fontsize=9,
        )
    _style_axis(axes[0, 1])

    frame_schedules = [row for row in schedules if "valid frames" in str(row["label"])]
    schedule_positions = np.arange(len(frame_schedules))
    guard_fraction = np.asarray(
        [float(row["guard_s"]) / float(row["dwell_s"]) for row in frame_schedules]
    )
    valid_fraction = 1.0 - guard_fraction
    axes[1, 0].barh(schedule_positions, guard_fraction, color=GRAY, label="guard")
    axes[1, 0].barh(
        schedule_positions,
        valid_fraction,
        left=guard_fraction,
        color=GREEN,
        label="nominal valid dwell",
    )
    axes[1, 0].set_yticks(
        schedule_positions,
        [f"{_short_schedule_label(row)} ms" for row in frame_schedules],
    )
    axes[1, 0].set_xlim(0.0, 1.0)
    fraction_ticks = np.linspace(0.0, 1.0, 6)
    axes[1, 0].set_xticks(fraction_ticks, [f"{value:.0%}" for value in fraction_ticks])
    axes[1, 0].set_xlabel("share of each edge dwell")
    axes[1, 0].set_title("C · Frame-schedule geometry", loc="left", fontweight="bold")
    axes[1, 0].invert_yaxis()
    for position, row, guard in zip(
        schedule_positions, frame_schedules, guard_fraction, strict=True
    ):
        match = re.search(r"\+\s*(\d+)\s+valid", str(row["label"]))
        label = f"{match.group(1)} valid frames" if match else "valid support"
        axes[1, 0].text(
            guard + (1.0 - guard) / 2.0,
            position,
            label,
            ha="center",
            va="center",
            color=WHITE,
            fontsize=9,
            fontweight="bold",
        )
    axes[1, 0].text(
        guard_fraction[0] / 2.0,
        schedule_positions[0],
        "guard",
        ha="center",
        va="center",
        color=INK,
        fontsize=9,
        fontweight="bold",
    )
    _style_axis(axes[1, 0], grid_axis="x")

    dwell_positions = np.arange(len(schedules))
    dwell_labels = [_short_schedule_label(row) for row in schedules]
    lower_retention = 100.0 * np.asarray(
        [float(row["retained_lower_fraction_of_baseline_median"]) for row in schedules]
    )
    upper_retention = 100.0 * np.asarray(
        [float(row["retained_upper_fraction_of_baseline_median"]) for row in schedules]
    )
    envelope_lower = 100.0 * np.asarray(
        [
            float(row["timing"]["uncertainty_envelope_retained_lower_fraction_of_baseline_median"])
            for row in schedules
        ]
    )
    envelope_upper = 100.0 * np.asarray(
        [
            float(row["timing"]["uncertainty_envelope_retained_upper_fraction_of_baseline_median"])
            for row in schedules
        ]
    )
    axes[1, 1].plot(
        dwell_positions,
        lower_retention,
        color=BLUE,
        marker="o",
        linewidth=1.8,
        label="lower · nominal support",
    )
    axes[1, 1].plot(
        dwell_positions,
        upper_retention,
        color=AMBER,
        marker="s",
        linewidth=1.8,
        label="upper · nominal support",
    )
    axes[1, 1].plot(
        dwell_positions,
        envelope_lower,
        color=BLUE,
        marker="o",
        markerfacecolor=WHITE,
        linestyle=(0, (4, 3)),
        linewidth=1.3,
        label="lower · UTC-support envelope",
    )
    axes[1, 1].plot(
        dwell_positions,
        envelope_upper,
        color=AMBER,
        marker="s",
        markerfacecolor=WHITE,
        linestyle=(0, (4, 3)),
        linewidth=1.3,
        label="upper · UTC-support envelope",
    )
    axes[1, 1].set_xticks(dwell_positions, dwell_labels)
    axes[1, 1].set_ylim(0.0, 55.0)
    axes[1, 1].set_xlabel("dwell per edge (ms)")
    axes[1, 1].set_ylabel("median retained share of that edge's baseline (%)")
    axes[1, 1].set_title("D · Edge-balanced fine-product retention", loc="left", fontweight="bold")
    axes[1, 1].legend(frameon=False, fontsize=8.5, loc="lower right")
    axes[1, 1].text(
        0.02,
        0.96,
        "Oracle-gated conditional availability; not hardware duty or estimator accuracy.",
        transform=axes[1, 1].transAxes,
        ha="left",
        va="top",
        color=RED,
        fontsize=9.0,
        fontweight="bold",
    )
    _style_axis(axes[1, 1])
    _save(figure, path)


def render_closure(path: Path, document: dict[str, Any]) -> None:
    """Render observed versus RF-scaling-predicted opposite-edge closure."""

    retrospective = document["retrospective"]
    events = list(retrospective["opposite_edge_events"])
    prediction = np.abs(
        np.asarray([float(item["pure_rf_scaling_prediction_hz_s"]) for item in events])
    )
    observed = np.abs(np.asarray([float(item["differential_rate_hz_s"]) for item in events]))
    residual_rms = float(retrospective["opposite_edge_scaling_residual_hz_s"]["rms"])
    closure_summary = retrospective["opposite_edge_closure_ratio"]

    figure = Figure(figsize=(15.2, 7.0), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Opposite-edge RF-scaling closure is descriptive, not confirmatory",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )

    limit = 1.08 * max(float(np.max(prediction)), float(np.max(observed)))
    axes[0].plot(
        (0.0, limit),
        (0.0, limit),
        color=INK,
        linewidth=1.4,
        linestyle=(0, (5, 4)),
        label="observed = predicted",
    )
    for channel in sorted(CHANNEL_COLORS):
        indexes = [index for index, item in enumerate(events) if item["channel"] == channel]
        axes[0].scatter(
            prediction[indexes],
            observed[indexes],
            s=58,
            color=CHANNEL_COLORS[channel],
            alpha=0.84,
            linewidths=0,
            label=channel.upper(),
            zorder=3,
        )
    primary_offsets = {
        "085623": (-35, -18),
        "101702": (15, -5),
        "103607": (-42, 19),
        "115401": (13, -15),
        "130425": (12, 14),
    }
    for index, item in enumerate(events):
        capture_time = _capture_time(str(item["session_id"]))
        if capture_time not in PRIMARY_CLOSURE_TIMES:
            continue
        axes[0].scatter(
            prediction[index],
            observed[index],
            s=110,
            facecolors="none",
            edgecolors=INK,
            linewidths=1.4,
            zorder=4,
        )
        axes[0].annotate(
            capture_time,
            (prediction[index], observed[index]),
            xytext=primary_offsets[capture_time],
            textcoords="offset points",
            color=INK,
            fontsize=8.5,
            arrowprops={"arrowstyle": "-", "color": GRAY, "lw": 0.8},
        )
    axes[0].set_xlim(0.0, limit)
    axes[0].set_ylim(0.0, limit)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlabel("pure RF-scaling prediction |upper − lower| (Hz/s)")
    axes[0].set_ylabel("observed edge-group contrast |upper − lower| (Hz/s)")
    axes[0].set_title(
        f"A · Observed versus predicted · residual RMS {residual_rms:.2f} Hz/s",
        loc="left",
        fontweight="bold",
    )
    axes[0].legend(frameon=False, ncol=3, loc="upper left")
    _style_axis(axes[0], grid_axis="both")

    ordered = sorted(events, key=lambda item: float(item["closure_ratio"]))
    ranks = np.arange(1, len(ordered) + 1)
    ratios = np.asarray([float(item["closure_ratio"]) for item in ordered])
    axes[1].axhspan(
        float(closure_summary["p10"]),
        float(closure_summary["p90"]),
        color=GRAY,
        alpha=0.15,
        label="event P10–P90",
    )
    axes[1].axhline(1.0, color=INK, linewidth=1.5, linestyle=(0, (5, 4)), label="unity")
    axes[1].axhline(
        float(closure_summary["median"]),
        color=RED,
        linewidth=1.4,
        label=f"median {float(closure_summary['median']):.3f}",
    )
    for channel in sorted(CHANNEL_COLORS):
        indexes = [index for index, item in enumerate(ordered) if item["channel"] == channel]
        axes[1].scatter(
            ranks[indexes],
            ratios[indexes],
            s=58,
            color=CHANNEL_COLORS[channel],
            alpha=0.84,
            linewidths=0,
            zorder=3,
        )
    for rank, item in zip(ranks, ordered, strict=True):
        if _capture_time(str(item["session_id"])) in PRIMARY_CLOSURE_TIMES:
            axes[1].scatter(
                rank,
                float(item["closure_ratio"]),
                s=110,
                facecolors="none",
                edgecolors=INK,
                linewidths=1.4,
                zorder=4,
            )
    axes[1].set_xlim(0.2, len(ordered) + 0.8)
    axes[1].set_xticks((1, 5, 10, 15, 20, len(ordered)))
    axes[1].set_xlabel("event rank by closure ratio")
    axes[1].set_ylabel("closure = observed contrast / RF-scaling prediction")
    axes[1].set_title(
        f"B · Selected event closure · n = {len(events)}",
        loc="left",
        fontweight="bold",
    )
    axes[1].legend(frameon=False, loc="upper left")
    axes[1].text(
        0.98,
        0.03,
        "Branches were selected partly by RF-normalized slope agreement.",
        transform=axes[1].transAxes,
        ha="right",
        va="bottom",
        color=RED,
        fontsize=9.5,
        fontweight="bold",
    )
    _style_axis(axes[1])
    _save(figure, path)


def render_sensitivity(path: Path, document: dict[str, Any]) -> None:
    """Render phase/timing deviation and retained-product sensitivity by dwell."""

    _capture_id, case, fine = _fine_case(document)
    coarse = _coarse_case(case)
    rows = _schedule_rows(fine)
    labels = [_short_schedule_label(row) for row in rows]
    positions = np.arange(len(rows), dtype=float)
    nominal_p90 = np.asarray(
        [float(row["absolute_masked_minus_unmasked_rate_deviation_p90_hz_s"]) for row in rows]
    )
    nominal_median = np.asarray(
        [float(row["absolute_masked_minus_unmasked_rate_deviation_median_hz_s"]) for row in rows]
    )
    support_p90 = np.asarray(
        [
            float(
                row["timing"]["uncertainty_envelope_p90_masked_minus_unmasked_rate_deviation_hz_s"]
            )
            for row in rows
        ]
    )
    fine_retention = 100.0 * np.asarray([float(row["retained_fraction_median"]) for row in rows])
    coarse_by_label = {str(row["label"]): row for row in coarse["schedules"]}
    coarse_retention = np.asarray(
        [
            100.0 * float(coarse_by_label[str(row["label"])]["retained_fraction_median"])
            if coarse_by_label[str(row["label"])].get("status") == "complete"
            else np.nan
            for row in rows
        ]
    )
    unresolved = np.isnan(coarse_retention)
    baseline_rate = abs(float(fine["baseline"]["differential_rate_hz_s"]))
    uncertainty_ms = float(fine["relative_timing_sensitivity"]["upper_timing_uncertainty_ns"]) / 1e6

    figure = Figure(figsize=(15.2, 7.2), constrained_layout=True)
    axes = figure.subplots(1, 2)
    figure.suptitle(
        "Virtual switching: deviation–retention tradeoff across dwell schedules",
        fontsize=19,
        fontweight="bold",
        color=INK,
    )

    width = 0.34
    axes[0].bar(
        positions - width / 2.0,
        nominal_p90,
        width=width,
        color=BLUE,
        label="nominal support P90",
    )
    axes[0].bar(
        positions + width / 2.0,
        support_p90,
        width=width,
        color=AMBER,
        label=f"support expanded ±{uncertainty_ms:.3f} ms P90",
    )
    axes[0].plot(
        positions,
        nominal_median,
        color=INK,
        marker="o",
        markersize=5,
        linewidth=1.2,
        label="nominal median",
        zorder=4,
    )
    axes[0].set_xticks(positions, labels)
    axes[0].set_xlabel("dwell per edge (ms)")
    axes[0].set_ylabel("|masked − unmasked edge-group rate| (Hz/s)")
    axes[0].set_title(
        "A · Fine frame-CFO schedule-phase sensitivity", loc="left", fontweight="bold"
    )
    axes[0].legend(frameon=False)
    axes[0].text(
        0.98,
        0.95,
        f"unmasked contrast = {baseline_rate:.2f} Hz/s",
        transform=axes[0].transAxes,
        ha="right",
        va="top",
        color=INK,
        fontsize=9.5,
    )
    _style_axis(axes[0])

    axes[1].bar(
        positions - width / 2.0,
        fine_retention,
        width=width,
        color=GREEN,
        label=f"fine support ({float(rows[0]['measurement_duration_s']) * 1e6:.1f} µs)",
    )
    axes[1].bar(
        positions + width / 2.0,
        np.nan_to_num(coarse_retention),
        width=width,
        color=PURPLE,
        label=(
            f"coarse support "
            f"({float(coarse['schedules'][0]['measurement_duration_s']) * 1e3:.0f} ms)"
        ),
    )
    if bool(np.any(unresolved)):
        axes[1].scatter(
            positions[unresolved] + width / 2.0,
            np.full(int(np.sum(unresolved)), 2.0),
            marker="x",
            s=70,
            linewidths=2.0,
            color=RED,
            label="coarse product not resolvable",
            zorder=4,
        )
    axes[1].set_xticks(positions, labels)
    axes[1].set_ylim(0.0, 55.0)
    axes[1].set_xlabel("dwell per edge (ms)")
    axes[1].set_ylabel("median retained observations (%)")
    axes[1].set_title(
        "B · Measurement duration controls usable duty", loc="left", fontweight="bold"
    )
    axes[1].legend(frameon=False, loc="lower right")
    axes[1].text(
        0.03,
        0.95,
        "Complete measurement support must lie after guard and before retune.",
        transform=axes[1].transAxes,
        ha="left",
        va="top",
        color=INK,
        fontsize=9.5,
    )
    _style_axis(axes[1])
    _save(figure, path)


def render_all(document: dict[str, Any], output_root: Path) -> dict[str, Path]:
    """Render all report figures and return stable logical names."""

    validate_results(document)
    paths = {key: output_root / name for key, name in FIGURE_NAMES.items()}
    render_approach(paths["approach"], document)
    render_data_retention(paths["data_retention"], document)
    render_closure(paths["closure"], document)
    render_sensitivity(paths["sensitivity"], document)
    return paths


def main() -> None:
    arguments = _arguments()
    document = load_results(arguments.results)
    paths = render_all(document, arguments.output_root)
    print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
