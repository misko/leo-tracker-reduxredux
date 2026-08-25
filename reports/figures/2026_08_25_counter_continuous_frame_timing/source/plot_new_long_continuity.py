#!/usr/bin/env python3
"""Render plain Matplotlib PNGs for the Aug-25 long continuity probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("frame rows must be nonempty JSON objects")
    return rows


def values(rows: list[dict[str, Any]], field: str) -> np.ndarray:
    return np.asarray(
        [math.nan if row.get(field) is None else float(row[field]) for row in rows],
        dtype=float,
    )


def trajectory_values(evidence: dict[str, Any], times: np.ndarray) -> np.ndarray:
    trajectory = evidence["trajectory"]
    slope, intercept = (float(value) for value in trajectory["absolute_coefficients_hz"])
    reference = float(trajectory["reference_time_s"])
    return intercept + slope * (times - reference)


def draw_refills(axis: plt.Axes, refill_times: np.ndarray, *, label: bool = False) -> None:
    for index, refill_time in enumerate(refill_times):
        axis.axvline(
            refill_time,
            color="#7f7f7f",
            alpha=0.10,
            linewidth=0.55,
            zorder=0,
            label="counter-contiguous refill" if label and index == 0 else None,
        )


def draw_anchor_events(
    axis: plt.Axes,
    anchors: list[dict[str, Any]],
    *,
    start: float,
    stop: float,
    label: bool = False,
) -> None:
    span_labeled = False
    switch_labeled = False
    for index, anchor in enumerate(anchors):
        left = float(anchor["acquisition_start_sample"]) / 2_500_000.0
        right = float(anchor["acquisition_stop_sample"]) / 2_500_000.0
        if right > start and left < stop:
            axis.axvspan(
                max(left, start),
                min(right, stop),
                color="#f59e0b",
                alpha=0.055,
                linewidth=0,
                zorder=0,
                label="selected 20 ms acquisition" if label and not span_labeled else None,
            )
            span_labeled = True
        if index == 0:
            continue
        switch = float(anchor["ownership_start_sample"]) / 2_500_000.0
        if start <= switch < stop:
            axis.axvline(
                switch,
                color="#5b4bb7",
                linestyle="--",
                linewidth=0.65,
                alpha=0.30,
                zorder=0,
                label="anchor ownership switch" if label and not switch_labeled else None,
            )
            switch_labeled = True


def render_full(
    evidence: dict[str, Any],
    rows: list[dict[str, Any]],
    output: Path,
) -> None:
    interval = evidence["interval"]
    start = float(interval["time_start_s"])
    stop = float(interval["time_stop_s"])
    times = values(rows, "reference_time_s")
    even = values(rows, "even_absolute_cfo_hz")
    odd = values(rows, "odd_absolute_cfo_hz")
    predicted = values(rows, "predicted_cfo_hz")
    trailing = values(rows, "trailing_20ms_prediction_hz")
    trajectory = trajectory_values(evidence, times)
    refill_times = np.asarray(evidence["refill_audit_boundary_samples"], dtype=float) / 2_500_000.0

    anchors = evidence["anchors"]
    anchor_times = np.asarray(
        [float(anchor["acquisition_start_sample"]) / 2_500_000.0 for anchor in anchors]
    )
    anchor_cfo = np.asarray([float(anchor["tracking_cfo_hz"]) for anchor in anchors])

    first_epoch = int(anchors[0]["absolute_epoch_sample"])
    period = 2_500_000.0 / 750.0
    epoch_offsets = []
    for anchor in anchors:
        epoch = int(anchor["absolute_epoch_sample"])
        lattice_index = round((epoch - first_epoch) / period)
        epoch_offsets.append(epoch - (first_epoch + lattice_index * period))

    common = np.asarray(
        [bool(row["odd_scored"] and row["trailing_20ms_scored"]) for row in rows],
        dtype=bool,
    )
    block_summary = evidence["result"]["common_mask_trailing_20ms"]
    blocks = block_summary["blocks"]
    block_times = np.asarray(
        [
            (max(start, float(block["time_start_s"])) + min(stop, float(block["time_stop_s"])))
            / 2.0
            for block in blocks
        ]
    )
    filter_rms = np.asarray([float(block["filter_rms_hz"]) for block in blocks])
    trailing_rms = np.asarray([float(block["trailing_line_rms_hz"]) for block in blocks])
    pooled_filter = float(block_summary["filter_error"]["rms_hz"])
    pooled_trailing = float(block_summary["causal_trailing_line_error"]["rms_hz"])
    pooled_ratio = float(block_summary["filter_to_line_rms_ratio"])
    win_count = int(block_summary["filter_win_block_count"])

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 8,
            "figure.titlesize": 13,
        }
    )
    figure, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        dpi=150,
        sharex=True,
        gridspec_kw={"height_ratios": (2.0, 1.25, 1.0)},
        constrained_layout=True,
    )
    figure.suptitle(
        "Aug-25 dwell: 13.825 s exploratory candidate-branch frame track\n"
        "one locklet across 132 counter-contiguous refills · post-hoc 4-sample refresh tolerance\n"
        "delayed-causal fold evaluation conditional on the offline persisted all-Qin branch"
    )

    ax = axes[0]
    draw_refills(ax, refill_times)
    draw_anchor_events(ax, anchors, start=start, stop=stop, label=True)
    ax.scatter(
        times[np.isfinite(even)],
        (even - trajectory)[np.isfinite(even)],
        s=2.0,
        color="#9ecae1",
        alpha=0.22,
        linewidths=0,
        label="1.333 ms even-Qin training CFO",
    )
    ax.scatter(
        times[common],
        (odd - trajectory)[common],
        s=3.0,
        color="#377eb8",
        alpha=0.35,
        linewidths=0,
        label="held-out odd-Qin CFO (common mask)",
    )
    ax.plot(
        times,
        np.where(common, predicted - trajectory, np.nan),
        color="#178a52",
        linewidth=0.9,
        label="Kalman pre-update prediction",
    )
    ax.plot(
        times,
        np.where(common, trailing - trajectory, np.nan),
        color="#555555",
        linewidth=0.75,
        alpha=0.85,
        label="causal trailing-20-ms prediction",
    )
    ax.scatter(
        anchor_times,
        anchor_cfo - trajectory_values(evidence, anchor_times),
        s=22,
        marker="D",
        color="#d97706",
        edgecolors="white",
        linewidths=0.45,
        zorder=4,
        label="selected GLRT64 refresh anchor",
    )
    ax.axhline(0.0, color="#202020", linewidth=0.8)
    ax.set_ylabel("Residual to persisted trajectory (Hz)")
    ax.set_title("Recovered frames and delayed-causal predictions")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=3)

    ax = axes[1]
    ax.plot(
        block_times,
        filter_rms,
        color="#178a52",
        marker="o",
        markersize=3.5,
        linewidth=1.4,
        label="Kalman pre-update RMS",
    )
    ax.plot(
        block_times,
        trailing_rms,
        color="#555555",
        marker="o",
        markersize=3.5,
        linewidth=1.4,
        label="causal trailing-20-ms line RMS",
    )
    ax.axhline(
        pooled_filter,
        color="#178a52",
        linestyle=":",
        linewidth=1.0,
        label=f"Kalman pooled RMS {pooled_filter:.2f} Hz",
    )
    ax.axhline(
        pooled_trailing,
        color="#555555",
        linestyle=":",
        linewidth=1.0,
        label=f"20-ms line pooled RMS {pooled_trailing:.2f} Hz",
    )
    ax.set_ylabel("Block held-out RMS (Hz)")
    ax.set_title(
        "Same-mask 1 s blocks (last block 0.825 s): "
        f"Kalman wins {win_count}/{len(blocks)} · pooled ratio {pooled_ratio:.3f}×"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", ncol=2)

    ax = axes[2]
    draw_refills(ax, refill_times, label=True)
    draw_anchor_events(ax, anchors, start=start, stop=stop)
    ax.plot(
        anchor_times,
        epoch_offsets,
        color="#5b4bb7",
        marker="o",
        markersize=3.2,
        linewidth=1.2,
        label="selected refresh-anchor signed offset",
    )
    ax.axhline(0.0, color="#202020", linewidth=0.8)
    ax.set_ylabel("Epoch offset (samples)")
    ax.set_xlabel("Time from dwell start (s)")
    ax.set_title(
        "Signed drift from first-anchor fixed lattice: selected anchors peak at "
        f"{max(epoch_offsets):.1f} samples; adjacent joins ≤4"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2)
    ax.set_xlim(start, stop)

    figure.savefig(output, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def render_zoom(
    evidence: dict[str, Any],
    rows: list[dict[str, Any]],
    output: Path,
    *,
    zoom_start: float,
    zoom_stop: float,
) -> None:
    times = values(rows, "reference_time_s")
    even = values(rows, "even_absolute_cfo_hz")
    odd = values(rows, "odd_absolute_cfo_hz")
    predicted = values(rows, "predicted_cfo_hz")
    trailing = values(rows, "trailing_20ms_prediction_hz")
    trajectory = trajectory_values(evidence, times)
    selected = (times >= zoom_start) & (times < zoom_stop)
    common = selected & np.asarray(
        [bool(row["odd_scored"] and row["trailing_20ms_scored"]) for row in rows],
        dtype=bool,
    )
    refill_times = np.asarray(evidence["refill_audit_boundary_samples"], dtype=float) / 2_500_000.0
    refill_times = refill_times[(refill_times >= zoom_start) & (refill_times < zoom_stop)]

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(14, 7.5),
        dpi=150,
        sharex=True,
        constrained_layout=True,
        gridspec_kw={"height_ratios": (1.5, 1.0)},
    )
    figure.suptitle(
        f"One-second detail: {zoom_start:.3f}–{zoom_stop:.3f} s\n"
        "conditional odd fold · post-hoc 4-sample refresh tolerance · "
        "grey lines are contiguous refills"
    )
    t = times[selected]
    ref = trajectory[selected]

    ax = axes[0]
    draw_refills(ax, refill_times, label=True)
    draw_anchor_events(
        ax,
        evidence["anchors"],
        start=zoom_start,
        stop=zoom_stop,
        label=True,
    )
    ax.scatter(
        t,
        even[selected] - ref,
        s=5,
        color="#9ecae1",
        alpha=0.35,
        linewidths=0,
        label="even-Qin training measurement",
    )
    ax.scatter(
        times[common],
        (odd - trajectory)[common],
        s=7,
        color="#377eb8",
        alpha=0.55,
        linewidths=0,
        label="held-out odd-Qin measurement",
    )
    ax.plot(
        times,
        np.where(common, predicted - trajectory, np.nan),
        color="#178a52",
        linewidth=1.0,
        label="Kalman pre-update prediction",
    )
    ax.plot(
        times,
        np.where(common, trailing - trajectory, np.nan),
        color="#555555",
        linewidth=1.0,
        label="causal trailing-20-ms prediction",
    )
    ax.set_ylabel("Residual to persisted trajectory (Hz)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2)

    ax = axes[1]
    draw_refills(ax, refill_times)
    ax.scatter(
        times[common],
        odd[common] - predicted[common],
        s=7,
        color="#178a52",
        alpha=0.45,
        linewidths=0,
        label="odd − Kalman prediction",
    )
    ax.scatter(
        times[common],
        odd[common] - trailing[common],
        s=7,
        color="#555555",
        alpha=0.35,
        linewidths=0,
        label="odd − trailing-20-ms prediction",
    )
    ax.axhline(0.0, color="#202020", linewidth=0.8)
    ax.set_ylabel("Held-out error (Hz)")
    ax.set_xlabel("Time from dwell start (s)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", ncol=2)
    ax.set_xlim(zoom_start, zoom_stop)

    figure.savefig(output, dpi=150, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--zoom-start", type=float, default=45.575)
    parser.add_argument("--zoom-stop", type=float, default=46.575)
    args = parser.parse_args()

    evidence_path = args.input_root / "evidence.json"
    rows_path = args.input_root / "frame-rows.jsonl"
    evidence = load_json(evidence_path)
    declared = evidence["artifacts"]["frame_rows_sha256"]
    actual = sha256(rows_path)
    if actual != declared:
        raise ValueError(f"frame-row hash mismatch: {actual} != {declared}")
    rows = load_rows(rows_path)
    if len(rows) != int(evidence["result"]["opportunity_count"]):
        raise ValueError("row count does not match evidence")

    full_path = args.input_root / "long-track-full.png"
    zoom_path = args.input_root / "long-track-one-second-zoom.png"
    render_full(evidence, rows, full_path)
    render_zoom(
        evidence,
        rows,
        zoom_path,
        zoom_start=args.zoom_start,
        zoom_stop=args.zoom_stop,
    )
    manifest = {
        "schema": "org.leo.research.long-continuity-matplotlib-plots/v1",
        "input_evidence_sha256": sha256(evidence_path),
        "input_rows_sha256": actual,
        "plot_script_sha256": sha256(Path(__file__)),
        "plots": {
            full_path.name: {"sha256": sha256(full_path), "bytes": full_path.stat().st_size},
            zoom_path.name: {"sha256": sha256(zoom_path), "bytes": zoom_path.stat().st_size},
        },
        "renderer": "matplotlib",
        "zoom": [args.zoom_start, args.zoom_stop],
    }
    (args.input_root / "plot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
