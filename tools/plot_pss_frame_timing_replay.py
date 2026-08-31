#!/usr/bin/env python3
"""Render PSS detection and frame-phase PNGs from one replay document."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from leo.storage import RecordingStore  # noqa: E402

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
_QNAP_ROOT = Path("/mnt/qnap01")
_FRAME_RATE_HZ = 750.0
_PATH_COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")


@dataclass(frozen=True, slots=True)
class PlotTarget:
    label: str
    color: str
    sample_rate_hz: float
    first_sample_offset_s: float
    observed_spans_s: tuple[tuple[float, float], ...]
    diagnostic_times_s: tuple[float, ...]
    diagnostic_robust_z: tuple[float, ...]
    detection_times_s: tuple[float, ...]
    detection_robust_z: tuple[float, ...]
    window_times_s: tuple[float, ...]
    window_phase_us: tuple[float, ...]
    epoch_times_s: tuple[float, ...]
    epoch_phase_us: tuple[float, ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=200)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PSS replay input must contain one JSON object")
    if value.get("analysis_kind") != "candidate-only-rate-generic-pss-frame-timing-replay":
        raise ValueError("input is not a rate-generic PSS timing replay")
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("PSS replay contains no targets")
    return value


def _validate_output_directory(path: Path) -> None:
    canonical = path.resolve(strict=False)
    if canonical == _QNAP_ROOT or canonical.is_relative_to(_QNAP_ROOT):
        raise ValueError("PSS figures may not be written beneath the read-only QNAP root")


def _target_start_times_utc_ns(
    document: dict[str, Any],
    *,
    bulk_root: Path,
) -> dict[str, int]:
    capture_id = str(document["capture_id"])
    stream_ids = {str(target["stream_id"]) for target in document["targets"]}
    store = RecordingStore.open_read_only(bulk_root)
    try:
        bundle = store.inspect(capture_id)
        output = {}
        for stream in bundle.manifest.streams:
            if stream.stream_id not in stream_ids:
                continue
            if stream.timing is None:
                raise ValueError(f"recording stream has no first-sample timing: {stream.stream_id}")
            output[stream.stream_id] = stream.timing.first_sample.estimate_utc_ns
    finally:
        store.close()
    if set(output) != stream_ids:
        raise ValueError("replay target stream inventory disagrees with the recording manifest")
    return output


def _plot_targets(
    document: dict[str, Any],
    *,
    first_sample_utc_ns: dict[str, int],
) -> tuple[PlotTarget, ...]:
    origin_ns = min(first_sample_utc_ns.values())
    output = []
    for target_index, target in enumerate(document["targets"]):
        stream_id = str(target["stream_id"])
        receiver_id = int(target["receiver_id"])
        sample_rate_hz = float(target["sample_rate_hz"])
        first_offset_s = (first_sample_utc_ns[stream_id] - origin_ns) / 1e9
        observed_spans = []
        diagnostic_times = []
        diagnostic_z = []
        detection_times = []
        detection_z = []
        window_times = []
        window_phase = []
        epoch_times = []
        epoch_phase = []
        for block in target["blocks"]:
            result = block["result"]
            block_start = int(result["global_device_sample_start"])
            block_count = int(result["sample_count"])
            midpoint_s = first_offset_s + (block_start + 0.5 * block_count) / sample_rate_hz
            observed_spans.append(
                (
                    first_offset_s + block_start / sample_rate_hz,
                    block_count / sample_rate_hz,
                )
            )
            candidates = result["candidates"]
            if candidates:
                diagnostic_times.append(midpoint_s)
                diagnostic_z.append(float(candidates[0]["robust_z"]))
            for candidate in candidates:
                if not candidate["qualified"]:
                    continue
                detection_times.append(midpoint_s)
                detection_z.append(float(candidate["robust_z"]))
                epoch_times.append(midpoint_s)
                epoch_phase.append(float(candidate["frame_phase_samples"]) / sample_rate_hz * 1e6)
            for window in result["windows"]:
                window_times.append(
                    first_offset_s
                    + float(window["fractional_global_device_sample"]) / sample_rate_hz
                )
                window_phase.append(float(window["frame_phase_samples"]) / sample_rate_hz * 1e6)
        output.append(
            PlotTarget(
                label=f"{sample_rate_hz / 1e6:g} MS/s · {stream_id} RX{receiver_id}",
                color=_PATH_COLORS[target_index % len(_PATH_COLORS)],
                sample_rate_hz=sample_rate_hz,
                first_sample_offset_s=first_offset_s,
                observed_spans_s=tuple(observed_spans),
                diagnostic_times_s=tuple(diagnostic_times),
                diagnostic_robust_z=tuple(diagnostic_z),
                detection_times_s=tuple(detection_times),
                detection_robust_z=tuple(detection_z),
                window_times_s=tuple(window_times),
                window_phase_us=tuple(window_phase),
                epoch_times_s=tuple(epoch_times),
                epoch_phase_us=tuple(epoch_phase),
            )
        )
    return tuple(output)


def _time_limits(targets: tuple[PlotTarget, ...]) -> tuple[float, float]:
    starts = [start for target in targets for start, _duration in target.observed_spans_s]
    stops = [start + duration for target in targets for start, duration in target.observed_spans_s]
    if not starts:
        raise ValueError("PSS replay has no observed time spans")
    padding = max(0.5, 0.01 * (max(stops) - min(starts)))
    return min(starts) - padding, max(stops) + padding


def _style_axis(ax: Axes) -> None:
    ax.grid(True, color="#B8B8B8", linewidth=0.6, alpha=0.45)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=9)


def _detection_figure(
    targets: tuple[PlotTarget, ...],
    *,
    capture_id: str,
    threshold: float,
) -> Figure:
    figure, axes = plt.subplots(
        len(targets),
        1,
        figsize=(12, 3.2 * len(targets) + 1.2),
        sharex=True,
        squeeze=False,
        constrained_layout=True,
    )
    time_limits = _time_limits(targets)
    all_z = [value for target in targets for value in target.diagnostic_robust_z]
    upper = max(threshold + 1.0, math.ceil(max(all_z, default=threshold)))
    for axis, target in zip(axes[:, 0], targets, strict=True):
        _style_axis(axis)
        axis.broken_barh(
            target.observed_spans_s,
            (-0.72, 0.24),
            facecolors=target.color,
            alpha=0.22,
            linewidth=0,
            label="Observed IQ",
        )
        axis.scatter(
            target.diagnostic_times_s,
            target.diagnostic_robust_z,
            s=20,
            facecolors="none",
            edgecolors=target.color,
            linewidths=0.9,
            alpha=0.72,
            label="Strongest timing hypothesis",
        )
        axis.scatter(
            target.detection_times_s,
            target.detection_robust_z,
            s=52,
            marker="o",
            color=target.color,
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
            label="Qualified PSS-like detection",
        )
        axis.axhline(
            threshold,
            color="#333333",
            linestyle="--",
            linewidth=1.0,
            label=f"Qualification threshold (z={threshold:g})",
        )
        axis.set_ylabel("PSS timing\nrobust z", fontsize=10)
        axis.set_ylim(-0.85, upper + 0.5)
        axis.set_xlim(*time_limits)
        axis.set_title(
            f"{target.label} — {len(target.detection_times_s)} qualified modes",
            loc="left",
            fontsize=11,
        )
    axes[-1, 0].set_xlabel("Time since earliest receiver first sample (s)", fontsize=10)
    axes[0, 0].legend(loc="upper right", ncols=2, fontsize=9)
    figure.suptitle(f"PSS timing detections vs time · {capture_id}", fontsize=14)
    return figure


def _phase_figure(targets: tuple[PlotTarget, ...], *, capture_id: str) -> Figure:
    figure, axes = plt.subplots(
        len(targets),
        1,
        figsize=(12, 3.2 * len(targets) + 1.2),
        sharex=True,
        sharey=True,
        squeeze=False,
        constrained_layout=True,
    )
    time_limits = _time_limits(targets)
    frame_period_us = 1e6 / _FRAME_RATE_HZ
    for axis, target in zip(axes[:, 0], targets, strict=True):
        _style_axis(axis)
        axis.scatter(
            target.window_times_s,
            target.window_phase_us,
            s=7,
            color=target.color,
            alpha=0.28,
            linewidths=0,
            rasterized=True,
            label="Refined frame window",
        )
        axis.scatter(
            target.epoch_times_s,
            target.epoch_phase_us,
            s=48,
            marker="D",
            color=target.color,
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
            label="Folded epoch",
        )
        axis.set_ylabel("Frame phase modulo\n1,333.3 µs (µs)", fontsize=10)
        axis.set_ylim(0.0, frame_period_us)
        axis.set_xlim(*time_limits)
        axis.set_yticks(np.arange(0.0, frame_period_us + 1.0, 200.0))
        axis.set_title(
            f"{target.label} — {len(target.window_times_s):,} detected frame windows",
            loc="left",
            fontsize=11,
        )
    axes[-1, 0].set_xlabel("Time since earliest receiver first sample (s)", fontsize=10)
    axes[0, 0].legend(loc="upper right", ncols=2, fontsize=9)
    figure.suptitle(
        f"Detected frame phase vs time · {capture_id}\n"
        "Phase is receiver-device-axis relative; the vertical axis wraps every Starlink frame",
        fontsize=13,
    )
    return figure


def render_figures(
    document: dict[str, Any],
    *,
    first_sample_utc_ns: dict[str, int],
    output_directory: Path,
    dpi: int,
) -> tuple[Path, Path]:
    if dpi < 72:
        raise ValueError("figure DPI must be at least 72")
    _validate_output_directory(output_directory)
    targets = _plot_targets(document, first_sample_utc_ns=first_sample_utc_ns)
    config = document.get("configuration", {})
    threshold = float(config.get("minimum_epoch_robust_z", 6.0))
    capture_id = str(document["capture_id"])
    output_directory.mkdir(parents=True, exist_ok=True)
    detection_path = output_directory / "pss-detection-vs-time.png"
    phase_path = output_directory / "pss-frame-phase-vs-time.png"

    detection = _detection_figure(targets, capture_id=capture_id, threshold=threshold)
    detection.savefig(detection_path, dpi=dpi, bbox_inches="tight")
    plt.close(detection)
    phase = _phase_figure(targets, capture_id=capture_id)
    phase.savefig(phase_path, dpi=dpi, bbox_inches="tight")
    plt.close(phase)
    return detection_path, phase_path


def main() -> None:
    args = _arguments()
    document = _load(args.input)
    first_sample_utc_ns = _target_start_times_utc_ns(document, bulk_root=args.bulk_root)
    paths = render_figures(
        document,
        first_sample_utc_ns=first_sample_utc_ns,
        output_directory=args.output_directory,
        dpi=args.dpi,
    )
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
