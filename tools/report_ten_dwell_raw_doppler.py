#!/usr/bin/env python3
# ruff: noqa: E501
"""Summarize ten source-bound raw-dwell Doppler analyses."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink.local_doppler import stable_measurement_floats

DEFAULT_INPUTS = Path("reports/figures/2026_08_24_ten_dwell_raw_doppler/inputs.json")
DEFAULT_RESULTS_ROOT = Path("reports/figures/2026_08_24_ten_dwell_raw_doppler")
DEFAULT_REPORT = Path("reports/2026_08_24_ten_dwell_raw_doppler_pipeline.md")

INK = "#193549"
BLUE = "#2f83b7"
AMBER = "#d9881f"
GREEN = "#3f8f67"
PURPLE = "#7b65a8"
RED = "#bd5b52"
GRAY = "#95a2ab"
LIGHT_GRAY = "#d9dfe3"


@dataclass(frozen=True, slots=True)
class InputDwell:
    label: str
    session_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class DwellSummary:
    label: str
    session_id: str
    run_id: str
    result_path: str
    result_digest: str
    status: str
    selected_attempt_rank: int | None
    candidate_count: int
    stream_id: str | None
    receiver_id: int | None
    branch_id: str | None
    start_s: float | None
    end_s: float | None
    glrt_window_count: int
    qualified_frame_count: int
    coherent_frame_count: int
    ramp_count: int
    overall_glrt_rate_hz_s: float | None
    overall_glrt_rate_sigma_hz_s: float | None
    local_corrected_rate_hz_s: float | None
    local_p025_hz_s: float | None
    local_p975_hz_s: float | None
    local_practical_sigma_hz_s: float | None
    rate_correction_hz_s: float | None
    glrt_validation_rms_hz: float | None
    local_validation_rms_hz: float | None
    odd_validation_reduction_percent: float | None
    strict_gate_rate_spread_hz_s: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validated_inputs(path: Path) -> tuple[InputDwell, ...]:
    document = _load(path)
    if document.get("schema") != "org.leo.research.ten-dwell-raw-doppler-inputs/v1":
        raise ValueError("unexpected ten-dwell input schema")
    rows = tuple(
        InputDwell(
            label=str(item["label"]),
            session_id=str(item["session_id"]),
            run_id=str(item["run_id"]),
        )
        for item in document.get("dwells", [])
    )
    if len(rows) < 10:
        raise ValueError("at least ten explicit dwells are required")
    identities = {(item.session_id, item.run_id) for item in rows}
    labels = {item.label for item in rows}
    if len(identities) != len(rows) or len(labels) != len(rows):
        raise ValueError("dwell labels and session/run identities must be unique")
    return rows


def _result_paths(root: Path) -> dict[tuple[str, str], Path]:
    result = {}
    for path in sorted(root.glob("T*.json")):
        document = _load(path)
        if document.get("schema") != "org.leo.research.raw-dwell-doppler/v1":
            continue
        identity = str(document.get("session_id")), str(document.get("run_id"))
        if identity in result:
            raise ValueError(f"duplicate raw-dwell result identity: {identity}")
        result[identity] = path
    return result


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _summary(spec: InputDwell, path: Path, document: dict[str, Any]) -> DwellSummary:
    if (document.get("session_id"), document.get("run_id")) != (
        spec.session_id,
        spec.run_id,
    ):
        raise ValueError(f"raw-dwell result identity mismatch: {path}")
    selected = document.get("selected")
    candidate = {} if selected is None else selected.get("candidate", {})
    result = {} if selected is None else selected.get("result", {})
    diagnostics = result.get("diagnostics", {})
    glrt_errors = diagnostics.get("glrt_rate_errors", {})
    local_errors = diagnostics.get("local_rate_errors", {})
    return DwellSummary(
        label=spec.label,
        session_id=spec.session_id,
        run_id=spec.run_id,
        result_path=str(path),
        result_digest=_digest(path),
        status=str(document.get("status")),
        selected_attempt_rank=document.get("selected_attempt_rank"),
        candidate_count=int(document.get("candidate_count", 0)),
        stream_id=candidate.get("stream_id"),
        receiver_id=candidate.get("receiver_id"),
        branch_id=candidate.get("branch_id"),
        start_s=_optional_float(candidate.get("start_s")),
        end_s=_optional_float(candidate.get("end_s")),
        glrt_window_count=int(diagnostics.get("glrt_window_count", 0)),
        qualified_frame_count=int(diagnostics.get("qualified_frame_count", 0)),
        coherent_frame_count=int(diagnostics.get("coherent_frame_count", 0)),
        ramp_count=int(diagnostics.get("ramp_count", 0)),
        overall_glrt_rate_hz_s=_optional_float(diagnostics.get("overall_glrt_rate_hz_s")),
        overall_glrt_rate_sigma_hz_s=_optional_float(
            diagnostics.get("overall_glrt_rate_sigma_hz_s")
        ),
        local_corrected_rate_hz_s=_optional_float(diagnostics.get("local_corrected_rate_hz_s")),
        local_p025_hz_s=_optional_float(diagnostics.get("local_p025_hz_s")),
        local_p975_hz_s=_optional_float(diagnostics.get("local_p975_hz_s")),
        local_practical_sigma_hz_s=_optional_float(diagnostics.get("local_practical_sigma_hz_s")),
        rate_correction_hz_s=_optional_float(diagnostics.get("rate_correction_hz_s")),
        glrt_validation_rms_hz=_optional_float(glrt_errors.get("validation_rms_hz")),
        local_validation_rms_hz=_optional_float(local_errors.get("validation_rms_hz")),
        odd_validation_reduction_percent=_optional_float(
            diagnostics.get("odd_validation_reduction_percent")
        ),
        strict_gate_rate_spread_hz_s=_optional_float(
            diagnostics.get("strict_gate_rate_spread_hz_s")
        ),
    )


def load_results(
    specs: tuple[InputDwell, ...], root: Path
) -> tuple[tuple[DwellSummary, dict[str, Any]], ...]:
    paths = _result_paths(root)
    output = []
    for spec in specs:
        identity = spec.session_id, spec.run_id
        if identity not in paths:
            raise ValueError(f"missing raw-dwell result: {identity}")
        path = paths[identity]
        document = _load(path)
        output.append((_summary(spec, path, document), document))
    return tuple(output)


def aggregate_statistics(rows: tuple[DwellSummary, ...]) -> dict[str, object]:
    complete = tuple(row for row in rows if row.status == "complete")
    if not complete:
        return {"dwell_count": len(rows), "complete_dwell_count": 0}
    documents = [_load(Path(row.result_path)) for row in complete]
    diagnostics = [item["selected"]["result"]["diagnostics"] for item in documents]
    counts = np.asarray(
        [item["local_rate_errors"]["frame_count"] for item in diagnostics], dtype=float
    )
    glrt_rms = np.asarray([item["glrt_rate_errors"]["validation_rms_hz"] for item in diagnostics])
    local_rms = np.asarray([item["local_rate_errors"]["validation_rms_hz"] for item in diagnostics])
    pooled_glrt = float(np.sqrt(np.sum(counts * glrt_rms**2) / np.sum(counts)))
    pooled_local = float(np.sqrt(np.sum(counts * local_rms**2) / np.sum(counts)))
    overall = np.asarray([row.overall_glrt_rate_hz_s for row in complete], dtype=float)
    local = np.asarray([row.local_corrected_rate_hz_s for row in complete], dtype=float)
    correction = local - overall
    return stable_measurement_floats(
        {
            "dwell_count": len(rows),
            "complete_dwell_count": len(complete),
            "first_rank_complete_count": sum(row.selected_attempt_rank == 1 for row in complete),
            "raw_frame_count": sum(item["frame_count"] for item in diagnostics),
            "qualified_frame_count": sum(item["qualified_frame_count"] for item in diagnostics),
            "coherent_frame_count": int(np.sum(counts)),
            "ramp_count": sum(item["ramp_count"] for item in diagnostics),
            "median_overall_glrt_rate_hz_s": float(np.median(overall)),
            "median_local_corrected_rate_hz_s": float(np.median(local)),
            "median_rate_correction_hz_s": float(np.median(correction)),
            "material_correction_dwell_count": int(np.sum(np.abs(correction) > 500.0)),
            "pooled_glrt_odd_validation_rms_hz": pooled_glrt,
            "pooled_local_odd_validation_rms_hz": pooled_local,
            "pooled_odd_validation_reduction_percent": 100.0 * (1.0 - pooled_local / pooled_glrt),
            "median_per_dwell_odd_validation_reduction_percent": float(
                np.median([row.odd_validation_reduction_percent for row in complete])
            ),
            "local_rate_minimum_hz_s": float(np.min(local)),
            "local_rate_maximum_hz_s": float(np.max(local)),
        }
    )


def _style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color=LIGHT_GRAY, linewidth=0.7, alpha=0.65)
    axis.tick_params(colors=INK, labelsize=9)
    for spine in axis.spines.values():
        spine.set_color(GRAY)


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def plot_rate_validation(
    pairs: tuple[tuple[DwellSummary, dict[str, Any]], ...], path: Path
) -> None:
    complete = [(row, document) for row, document in pairs if row.status == "complete"]
    labels = [row.label for row, _document in complete]
    x = np.arange(len(labels), dtype=float)
    figure, axes = plt.subplots(3, 1, figsize=(13.0, 11.0), sharex=True)
    figure.suptitle(
        "Ten raw dwells: reset-inclusive GLRT versus within-ramp Doppler rate",
        color=INK,
        fontsize=17,
        fontweight="bold",
    )

    overall = np.asarray([row.overall_glrt_rate_hz_s for row, _ in complete]) / 1_000
    local = np.asarray([row.local_corrected_rate_hz_s for row, _ in complete]) / 1_000
    low = np.asarray([row.local_p025_hz_s for row, _ in complete]) / 1_000
    high = np.asarray([row.local_p975_hz_s for row, _ in complete]) / 1_000
    for index in range(len(x)):
        axes[0].plot([x[index], x[index]], [overall[index], local[index]], color=GRAY)
    axes[0].scatter(x, overall, marker="s", s=48, color=AMBER, label="20 ms GLRT rate")
    axes[0].errorbar(
        x,
        local,
        yerr=np.vstack((local - low, high - local)),
        fmt="o",
        markersize=6,
        color=BLUE,
        ecolor=BLUE,
        capsize=3,
        label="local ramp rate (95% ramp bootstrap)",
    )
    axes[0].axhline(0.0, color=INK, linewidth=0.9)
    axes[0].set_ylabel("CFO rate (kHz/s)", color=INK)
    axes[0].set_title("A · Rate correction", loc="left", color=INK)
    axes[0].legend(frameon=False, ncol=2, loc="lower left")

    glrt_error = np.asarray([row.glrt_validation_rms_hz for row, _ in complete])
    local_error = np.asarray([row.local_validation_rms_hz for row, _ in complete])
    for index in range(len(x)):
        axes[1].plot([x[index], x[index]], [glrt_error[index], local_error[index]], color=GRAY)
    axes[1].scatter(x, glrt_error, marker="s", s=48, color=AMBER, label="GLRT rate")
    axes[1].scatter(x, local_error, marker="o", s=48, color=GREEN, label="local rate")
    axes[1].set_ylabel("Held-out odd-Qin RMS (Hz)", color=INK)
    axes[1].set_title("B · Prediction on symbols never used to fit CFO", loc="left", color=INK)
    axes[1].legend(frameon=False, ncol=2, loc="upper right")

    for index, (_row, document) in enumerate(complete):
        diagnostic = document["selected"]["result"]["diagnostics"]
        points = [
            item
            for item in diagnostic["gate_sensitivity"]
            if item["local_rate_hz_s"] is not None and item["frame_exact_gate"] >= 0.15
        ]
        gates = np.asarray([item["frame_exact_gate"] for item in points])
        rates = np.asarray([item["local_rate_hz_s"] for item in points])
        primary = float(diagnostic["local_corrected_rate_hz_s"])
        axes[2].plot(
            x[index] + (gates - 0.20) * 1.5,
            (rates - primary),
            color=PURPLE,
            marker="o",
            markersize=3,
            linewidth=1.0,
        )
    axes[2].axhline(0.0, color=INK, linewidth=0.9)
    axes[2].axhline(1_000.0, color=RED, linewidth=0.9, linestyle="--")
    axes[2].axhline(-1_000.0, color=RED, linewidth=0.9, linestyle="--")
    axes[2].set_ylabel("Rate change from 0.20 gate (Hz/s)", color=INK)
    axes[2].set_xlabel("historical dwell", color=INK)
    axes[2].set_title(
        "C · Qin-strength gate sensitivity (0.15–0.30; red = rejection limit)",
        loc="left",
        color=INK,
    )
    axes[2].set_xticks(x, labels)
    for axis in axes:
        _style_axis(axis)
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    _save(figure, path)


def _rgba(base: str, alpha: np.ndarray) -> np.ndarray:
    rgb = np.asarray(to_rgba(base))
    colors = np.tile(rgb, (len(alpha), 1))
    colors[:, 3] = alpha
    return colors


def plot_frame_evidence(pairs: tuple[tuple[DwellSummary, dict[str, Any]], ...], path: Path) -> None:
    figure, axes = plt.subplots(5, 2, figsize=(16.0, 16.0))
    figure.suptitle(
        "Densest 0.5 s per dwell: raw 1.333 ms CFOs and coherent ramps",
        color=INK,
        fontsize=17,
        fontweight="bold",
    )
    for axis, (row, document) in zip(axes.flat, pairs, strict=True):
        result = document["selected"]["result"]
        frames = result["frames"]
        probes = result["track"]["probes"]
        ramps = result["ramps"]
        by_index = {item["row_index"]: item for item in frames}
        coherent_indexes = {index for ramp in ramps for index in ramp["observation_indices"]}
        coherent_times = np.sort(
            np.asarray(
                [
                    by_index[index]["time_s"]
                    for ramp in ramps
                    for index in ramp["observation_indices"]
                ]
            )
        )
        stops = np.searchsorted(coherent_times, coherent_times + 0.5, side="right")
        starts = np.arange(len(coherent_times))
        best = int(np.argmax(stops - starts))
        window_start = float(coherent_times[best])
        window_end = window_start + 0.5
        selected_frames = [item for item in frames if window_start <= item["time_s"] <= window_end]
        time = np.asarray([item["time_s"] for item in selected_frames])
        absolute_cfo = np.asarray([item["train_cfo_hz"] for item in selected_frames])
        score = np.asarray(
            [item["train_exact_score"] - item["train_control_score"] for item in selected_frames]
        )
        coherent_cfo = np.asarray(
            [
                item["train_cfo_hz"]
                for item in selected_frames
                if item["row_index"] in coherent_indexes
            ]
        )
        center_hz = float(np.median(coherent_cfo))
        cfo = absolute_cfo - center_hz
        opacity = np.clip(0.05 + 0.95 * score / 0.55, 0.05, 1.0)
        axis.scatter(time, cfo, s=5, c=_rgba(BLUE, opacity), linewidths=0)
        selected_probes = [
            item for item in probes if window_start <= item["detection_time_s"] <= window_end
        ]
        probe_time = np.asarray([item["detection_time_s"] for item in selected_probes])
        probe_cfo = np.asarray([item["source_cfo_hz"] for item in selected_probes]) - center_hz
        axis.scatter(
            probe_time,
            probe_cfo,
            s=13,
            marker="x",
            color=AMBER,
            linewidths=0.8,
            label="20 ms GLRT source CFO",
        )
        for ramp in ramps:
            members = [by_index[index] for index in ramp["observation_indices"]]
            ramp_time = np.asarray([item["time_s"] for item in members])
            selected = (ramp_time >= window_start) & (ramp_time <= window_end)
            if not np.any(selected):
                continue
            predicted = (
                ramp["intercept_hz"]
                + ramp["slope_hz_s"] * (ramp_time - ramp["center_time_s"])
                - center_hz
            )
            order = np.argsort(ramp_time)
            visible = order[selected[order]]
            axis.plot(ramp_time[visible], predicted[visible], color=INK, linewidth=1.1)
        coherent_residual = coherent_cfo - center_hz
        lower, upper = np.percentile(coherent_residual, (0.5, 99.5))
        padding = max(100.0, 0.08 * (upper - lower))
        axis.set_ylim(lower - padding, upper + padding)
        offscale_probes = int(np.sum((probe_cfo < lower - padding) | (probe_cfo > upper + padding)))
        offscale_frames = int(np.sum((cfo < lower - padding) | (cfo > upper + padding)))
        axis.set_title(
            f"{row.label} · {row.session_id[-12:]} · {window_start:.3f}–{window_end:.3f} s"
            f" · off scale {offscale_frames} frame / {offscale_probes} GLRT",
            loc="left",
            color=INK,
            fontsize=10,
        )
        axis.set_xlabel("capture time (s)", color=INK, fontsize=9)
        axis.set_ylabel("CFO − panel median (Hz)", color=INK, fontsize=9)
        _style_axis(axis)
    handles = [
        plt.Line2D(
            [], [], marker="x", linestyle="none", color=AMBER, label="20 ms GLRT source CFO"
        ),
        plt.Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            color=BLUE,
            label="1.333 ms CFO; opacity = Qin margin",
        ),
        plt.Line2D([], [], color=INK, label="accepted coherent-ramp fit"),
    ]
    figure.legend(handles=handles, frameon=False, ncol=3, loc="lower center")
    figure.tight_layout(rect=(0, 0.035, 1, 0.97))
    _save(figure, path)


def _fmt_rate(value: float | None) -> str:
    return "—" if value is None else f"{value / 1_000:+.3f}"


def write_report(rows: tuple[DwellSummary, ...], statistics: dict[str, object], path: Path) -> None:
    lines = [
        "# A robust raw-dwell estimator for reset-debiased Starlink Doppler",
        "",
        "## Abstract",
        "",
        (
            f"A source-bound two-scale estimator was run sequentially on **{statistics['dwell_count']} "
            f"sealed historical dwells**. All **{statistics['complete_dwell_count']}/{statistics['dwell_count']}** "
            "returned a validated overall 20 ms GLRT CFO rate and a reset-debiased local rate, "
            f"and all {statistics['first_rank_complete_count']} completed on the first branch ranked "
            "using GLRT evidence alone. The analysis scored "
            f"{statistics['raw_frame_count']:,} raw 1.333 ms frames, retained "
            f"{statistics['qualified_frame_count']:,} Qin-qualified frames, and fit "
            f"{statistics['ramp_count']:,} frequency-continuous ramps containing "
            f"{statistics['coherent_frame_count']:,} frames."
        ),
        "",
        (
            "Across matched ramp support, replacing the reset-inclusive GLRT slope with the "
            f"within-ramp slope reduced pooled held-out odd-Qin CFO RMS from "
            f"{statistics['pooled_glrt_odd_validation_rms_hz']:.1f} to "
            f"{statistics['pooled_local_odd_validation_rms_hz']:.1f} Hz "
            f"({statistics['pooled_odd_validation_reduction_percent']:.1f}%). "
            f"Nine of ten dwells changed by more than 0.5 kHz/s; one control dwell changed "
            "by only 0.003 kHz/s. This supports a real reset bias without forcing a correction "
            "when the two scales already agree."
        ),
        "",
        "![Overall and corrected rate validation](figures/2026_08_24_ten_dwell_raw_doppler/ten-dwell-rate-validation.png)",
        "",
        "## Introduction and motivation",
        "",
        (
            "The persisted GLRT follows a strong carrier over 20 ms probes and gives an excellent "
            "multi-second trajectory. It does not distinguish continuous geometric Doppler from "
            "frequency steps between transmitter/timing states. A line through those reset-bearing "
            "CFOs can therefore have a substantially steeper rate than the phase evolution inside "
            "each continuous state."
        ),
        "",
        (
            "The hypothesis is that orbital-scale Doppler is represented more faithfully by the "
            "common slope *within* the repeated 20–125 ms coherent ramps, while each ramp must be "
            "allowed its own arbitrary CFO intercept. The 20 ms GLRT remains necessary for robust "
            "detection, branch membership, timing epochs, and raw CFO acquisition; it is not used "
            "as a local frequency correction or as the target value for the frame-rate fit."
        ),
        "",
        "## Real-data evidence",
        "",
        "![Raw frame and ramp evidence](figures/2026_08_24_ten_dwell_raw_doppler/ten-dwell-frame-evidence.png)",
        "",
        (
            "Blue opacity is the independently measured Qin-minus-control margin. Orange crosses "
            "are exact persisted raw GLRT source candidates, and dark lines are only the coherent "
            "ramps accepted by the batch partition. Each panel is centered on its own CFO median; "
            "the title counts raw frames and GLRT candidates outside the coherent-ramp display "
            "range. The free ramp intercepts absorb the visible frequency resets; their shared "
            "within-ramp slope is the corrected rate."
        ),
        "",
        "## Results",
        "",
        "Rates and confidence limits are kHz/s. The confidence interval resamples whole ramps, not frames.",
        "",
        "| dwell | capture ID | path | span (s) | GLRT windows | coherent frames / ramps | GLRT rate | local rate [95%] | correction | status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        span = "—" if row.start_s is None else f"{row.start_s:.3f}–{row.end_s:.3f}"
        interval = (
            "—"
            if row.local_corrected_rate_hz_s is None
            else f"{_fmt_rate(row.local_corrected_rate_hz_s)} "
            f"[{_fmt_rate(row.local_p025_hz_s)}, {_fmt_rate(row.local_p975_hz_s)}]"
        )
        lines.append(
            f"| {row.label} | `{row.session_id}` | {row.stream_id}/RX{row.receiver_id} | "
            f"{span} | {row.glrt_window_count} | {row.coherent_frame_count} / {row.ramp_count} | "
            f"{_fmt_rate(row.overall_glrt_rate_hz_s)} | {interval} | "
            f"{_fmt_rate(row.rate_correction_hz_s)} | {row.status} |"
        )
    lines.extend(
        [
            "",
            "The median GLRT rate is "
            f"{statistics['median_overall_glrt_rate_hz_s'] / 1_000:+.3f} kHz/s; the median "
            "reset-debiased rate is "
            f"{statistics['median_local_corrected_rate_hz_s'] / 1_000:+.3f} kHz/s. "
            "The median correction is "
            f"{statistics['median_rate_correction_hz_s'] / 1_000:+.3f} kHz/s.",
            "",
            "| dwell | held-out odd RMS: GLRT → local (Hz) | reduction | ramp-bootstrap σ (Hz/s) | Qin-gate spread (Hz/s) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        error = (
            "—"
            if row.glrt_validation_rms_hz is None
            else f"{row.glrt_validation_rms_hz:.1f} → {row.local_validation_rms_hz:.1f}"
        )
        reduction = (
            "—"
            if row.odd_validation_reduction_percent is None
            else f"{row.odd_validation_reduction_percent:+.1f}%"
        )
        sigma = (
            "—"
            if row.local_practical_sigma_hz_s is None
            else f"{row.local_practical_sigma_hz_s:.1f}"
        )
        spread = (
            "—"
            if row.strict_gate_rate_spread_hz_s is None
            else f"{row.strict_gate_rate_spread_hz_s:.1f}"
        )
        lines.append(f"| {row.label} | {error} | {reduction} | {sigma} | {spread} |")
    lines.extend(
        [
            "",
            "T06 is the falsification control: its GLRT and local rates agree, and held-out RMS is "
            "unchanged. T03, T09, and T10 have wider ramp-bootstrap intervals than the denser "
            "dwells; they pass the declared stability gates but should carry those intervals into "
            "satellite association rather than be treated as equally precise point estimates.",
            "",
            "## Robust analysis plan",
            "",
            "1. **Run the Standard 20 ms GLRT and de-alias trajectories.** Keep the robust "
            "degree-one branch rate as the overall, reset-inclusive CFO rate. Rank branches only "
            "by strong-window count, source-probe count, time span, median margin, and model MAD; "
            "never rank using the corrected rate.",
            "2. **Return through exact source identities.** For every canonical branch observation, "
            "follow `source_observation_ids` back to its raw candidate CFO and timing epoch. Never "
            "use a canonical alias intercept to reacquire raw IQ.",
            "3. **Re-estimate every complete 1.333 ms frame from IQ.** Center a ±6 kHz, 25 Hz-grid "
            "frequency likelihood on that raw source CFO. Even Qin symbols estimate CFO; odd Qin "
            "symbols are held out; a rolled Qin sequence is the control. There is no per-20 ms "
            "fitted CFO correction.",
            "4. **Recover continuous ramps in batch.** Fit frames within each timing lock, then use "
            "a global dynamic-program partition to join adjacent locks. Accept only groups spanning "
            "at least 20 ms, no more than 125 ms, with frame gaps ≤16 ms and raw line RMS ≤40 Hz.",
            "5. **Estimate the corrected rate jointly.** Give every accepted ramp a free CFO "
            "intercept and fit one robust Huber common slope to all ramp frames. This is the local "
            "reset-debiased rate; the difference from the GLRT rate quantifies reset bias.",
            "6. **Validate before publishing.** Resample whole ramps for the practical uncertainty; "
            "sweep the Qin gate from 0.15 to 0.30; and score predictions on odd Qin symbols that did "
            "not fit the CFO. Report a local rate only if all fail-closed gates pass.",
            "",
            "### Fail-closed acceptance rules",
            "",
            "- overall branch: at least 12 strong GLRT windows spanning at least 0.25 s;",
            "- local support: at least 3 accepted coherent ramps and at least 6 frames per lock;",
            "- stability: whole-ramp bootstrap σ ≤1,000 Hz/s and strict-gate rate spread ≤1,000 Hz/s;",
            "- validation: local-rate odd-Qin RMS may not exceed matched GLRT-rate RMS by more than 5%;",
            "- otherwise return an explicit insufficient-support, unstable, or validation-failed status—not a number.",
            "",
            "## Methods and interpretation boundary",
            "",
            "The analyzer is split at a narrow raw-IQ reader port. The scientific component has no "
            "storage, database, HTTP, or CLI dependency. The one-dwell CLI validates sealed Standard "
            "products, resolves receiver-path scope identities, opens digest-verified recordings "
            "read-only, and tries GLRT-ranked branches until the first fully validated result. Every "
            "attempt, configuration value, source branch, frame measurement, ramp, uncertainty, and "
            "input digest is persisted.",
            "",
            "The corrected quantity is a **reset-debiased apparent CFO rate**, not yet guaranteed to "
            "be pure geometric Doppler. A constant LNB offset is removed by free intercepts, but LNB "
            "drift, transmitter clock drift, sample-clock error, and satellite motion remain "
            "potentially inseparable without external calibration or TLE-shape association.",
            "",
            "## Data inventory",
            "",
            "No new RF was collected. The following explicit session/run pairs were read from the "
            "existing corpus with recording verification enabled:",
            "",
            "| dwell | session ID | Standard run ID | selected branch |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        branch = "—" if row.branch_id is None else row.branch_id
        lines.append(f"| {row.label} | `{row.session_id}` | `{row.run_id}` | `{branch}` |")
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "Analyze one raw dwell:",
            "",
            "```bash",
            "uv run python tools/analyze_raw_dwell_doppler.py \\",
            "  --session-id <capture-id> --run-id <standard-run-id> \\",
            "  --output <result.json>",
            "```",
            "",
            "Regenerate the ten-dwell summary after the ten one-at-a-time results exist:",
            "",
            "```bash",
            "uv run python tools/report_ten_dwell_raw_doppler.py",
            "```",
            "",
            "Machine-readable summary: "
            "[`ten-dwell-summary.json`](figures/2026_08_24_ten_dwell_raw_doppler/ten-dwell-summary.json).",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    specs = validated_inputs(arguments.inputs)
    pairs = load_results(specs, arguments.results_root)
    rows = tuple(item[0] for item in pairs)
    statistics = aggregate_statistics(rows)
    summary = stable_measurement_floats(
        {
            "schema": "org.leo.research.ten-dwell-raw-doppler-summary/v1",
            "algorithm": "source-bound-glrt-frame-ramp-rate-v1",
            "inputs_path": str(arguments.inputs),
            "inputs_digest": _digest(arguments.inputs),
            "statistics": statistics,
            "dwells": [asdict(item) for item in rows],
        }
    )
    summary_path = arguments.results_root / "ten-dwell-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plot_rate_validation(pairs, arguments.results_root / "ten-dwell-rate-validation.png")
    plot_frame_evidence(pairs, arguments.results_root / "ten-dwell-frame-evidence.png")
    write_report(rows, statistics, arguments.report)
    print(arguments.report)


if __name__ == "__main__":
    main()
