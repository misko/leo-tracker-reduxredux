#!/usr/bin/env python3
"""Render the multiscale pilot-CFO ladder for the 470384 worked example.

The default analysis is pinned to the upper edge of stream-0/RX0 in
``cap-20260821T140820-470384cc9284`` from 33.7 through 37.7 seconds.  It
reselects the documented GLRT windows, digest-verifies the existing recording,
and re-reads bounded 70 ms IQ intervals so that 16, 20, 50, and 70 ms local
frequency-line fits are supported by actual pilot-frame measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam.pilot_pnt_kalman import (  # noqa: E402
    PilotPntKalmanConfig,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.starlink.local_doppler import frequency_line  # noqa: E402
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

SESSION_ID = "cap-20260821T140820-470384cc9284"
ANALYSIS_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
BRANCH_PREFIX = "sha256:5852a936"
TRAJECTORY_ID = "sha256:f751bbe5a13af4ba0481e6d434fc5a373c5a95a64c55aa0df8b80a86963ca601"
DEFAULT_ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/" + ANALYSIS_SCOPE
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_multiscale_cfo")
DEFAULT_REPORT_PATH = Path("reports/2026_08_23_470384_multiscale_cfo.md")
DEFAULT_DENSE_EVIDENCE = Path(
    "reports/figures/2026_08_22_edge_pilot_phase_slope/detailed-results.json"
)
WINDOW_DURATION_S = 0.070
ZOOM_DURATION_S = 0.500
ROLLING_BASELINES_S = (0.016, 0.020, 0.050, 0.070)
MAXIMUM_ROLLING_FRAME_GAP_S = 0.0041
MAXIMUM_DISPLAY_RATE_HZ_S = 15_000.0

BLUE = "#2f83b7"
AMBER = "#d9881f"
GREEN = "#4e9a68"
PURPLE = "#8a6bb8"
INK = "#193549"
GRAY = "#8796a3"


@dataclass(frozen=True, slots=True)
class FrozenTrajectory:
    coefficients_hz: tuple[float, ...]
    reference_time_s: float
    branch_id: str
    trajectory_id: str

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = np.polyval(self.coefficients_hz, np.asarray(time_s) - self.reference_time_s)
        return float(value) if np.ndim(value) == 0 else value

    def doppler_rate_hz_s(self, time_s: float | np.ndarray) -> float | np.ndarray:
        derivative = np.polyder(np.asarray(self.coefficients_hz, dtype=float))
        value = np.polyval(derivative, np.asarray(time_s) - self.reference_time_s)
        return float(value) if np.ndim(value) == 0 else value


@dataclass(frozen=True, slots=True)
class SourceWindow:
    index: int
    accepted_index: int
    detection_time_s: float
    probe_sample_start: int
    local_epoch_sample: int
    candidate_rank: int
    glrt64_cfo_hz: float
    glrt64_margin: float
    selection_model_error_hz: float


@dataclass(frozen=True, slots=True)
class TrackingInterval:
    source: SourceWindow
    start_time_s: float
    end_time_s: float
    result: PilotPntKalmanResult


@dataclass(frozen=True, slots=True)
class RollingFrequencyEstimate:
    time_s: float
    fitted_cfo_hz: float
    doppler_rate_hz_s: float
    support_span_s: float
    supported_frame_count: int
    fit_rms_hz: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-root", type=Path, default=DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--dense-evidence", type=Path, default=DEFAULT_DENSE_EVIDENCE)
    parser.add_argument("--session-id", default=SESSION_ID)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--edge", choices=("lower", "upper"), default="upper")
    parser.add_argument("--start-s", type=float, default=33.7)
    parser.add_argument("--end-s", type=float, default=37.7)
    parser.add_argument("--minimum-glrt64-margin", type=float, default=0.05)
    parser.add_argument("--maximum-model-error-hz", type=float, default=2_500.0)
    parser.add_argument("--accepted-stride", type=int, default=8)
    parser.add_argument("--window-duration-s", type=float, default=WINDOW_DURATION_S)
    parser.add_argument("--zoom-duration-s", type=float, default=ZOOM_DURATION_S)
    parser.add_argument("--maximum-residual-cfo-hz", type=float, default=15_000.0)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def trajectory_from_bank(document: dict[str, Any]) -> FrozenTrajectory:
    matches = [
        item
        for item in document["trajectories"]
        if str(item["branch_id"]).startswith(BRANCH_PREFIX)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one target trajectory, found {len(matches)}")
    item = matches[0]
    if str(item["trajectory_id"]) != TRAJECTORY_ID:
        raise ValueError("target branch resolved to an unexpected trajectory")
    return FrozenTrajectory(
        coefficients_hz=tuple(float(value) for value in item["absolute_coefficients_hz"]),
        reference_time_s=float(item["reference_time_s"]),
        branch_id=str(item["branch_id"]),
        trajectory_id=str(item["trajectory_id"]),
    )


def _glrt64_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def select_source_windows(
    scan: dict[str, Any],
    trajectory: FrozenTrajectory,
    *,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
    accepted_stride: int,
) -> tuple[SourceWindow, ...]:
    """Reproduce the worked-example selection before taking a fixed stride."""

    if accepted_stride <= 0:
        raise ValueError("accepted stride must be positive")
    accepted: list[SourceWindow] = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s <= end_s:
            continue
        model_hz = float(trajectory.frequency_hz(time_s))
        eligible: list[tuple[float, int, dict[str, Any], dict[str, Any]]] = []
        for candidate in detection["candidates"]:
            score = _glrt64_score(candidate)
            if float(score["margin"]) < minimum_margin:
                continue
            error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
            eligible.append((error_hz, int(candidate["rank"]), candidate, score))
        if not eligible:
            continue
        error_hz, _rank, candidate, score = min(eligible, key=lambda item: (item[0], item[1]))
        if error_hz > maximum_model_error_hz:
            continue
        accepted.append(
            SourceWindow(
                index=-1,
                accepted_index=len(accepted),
                detection_time_s=time_s,
                probe_sample_start=int(detection["sample_start"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                candidate_rank=int(candidate["rank"]),
                glrt64_cfo_hz=float(score["tracking_cfo_hz"]),
                glrt64_margin=float(score["margin"]),
                selection_model_error_hz=float(error_hz),
            )
        )
    return tuple(
        SourceWindow(
            index=index,
            accepted_index=item.accepted_index,
            detection_time_s=item.detection_time_s,
            probe_sample_start=item.probe_sample_start,
            local_epoch_sample=item.local_epoch_sample,
            candidate_rank=item.candidate_rank,
            glrt64_cfo_hz=item.glrt64_cfo_hz,
            glrt64_margin=item.glrt64_margin,
            selection_model_error_hz=item.selection_model_error_hz,
        )
        for index, item in enumerate(accepted[::accepted_stride])
    )


def _complex_receiver(raw: np.ndarray) -> np.ndarray:
    values = np.asarray(raw)
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("IQ read did not return one CI16 receiver column")
    return np.ascontiguousarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / 32_768.0
    )


def analyze_windows(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    windows: tuple[SourceWindow, ...],
    trajectory: FrozenTrajectory,
    edge: StarlinkEdge,
    window_duration_s: float,
    maximum_residual_cfo_hz: float,
) -> tuple[TrackingInterval, ...]:
    sample_count = round(window_duration_s * sample_rate_hz)
    intervals = []
    for source in windows:
        relative_start = source.probe_sample_start - raw_sample_start
        samples = np.ascontiguousarray(iq[relative_start : relative_start + sample_count])
        if len(samples) != sample_count:
            raise ValueError("70 ms source window lies outside the verified IQ read")
        start_time_s = source.probe_sample_start / sample_rate_hz
        result = analyze_contiguous_pilot_pnt_kalman(
            samples,
            sample_rate_hz,
            epoch_sample=source.local_epoch_sample,
            initial_absolute_cfo_hz=float(trajectory.frequency_hz(start_time_s)),
            edge=edge,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
            config=PilotPntKalmanConfig(),
        )
        intervals.append(
            TrackingInterval(
                source=source,
                start_time_s=start_time_s,
                end_time_s=start_time_s + window_duration_s,
                result=result,
            )
        )
    return tuple(intervals)


def rolling_frequency_estimates(
    interval: TrackingInterval,
    baseline_s: float,
) -> tuple[RollingFrequencyEstimate, ...]:
    """Fit a causal local CFO line without bridging unsupported pilot frames."""

    if not math.isfinite(baseline_s) or baseline_s <= 0:
        raise ValueError("rolling CFO baseline must be finite and positive")
    supported = [
        frame
        for frame in interval.result.frames
        if frame.measurement_supported
        and math.isfinite(frame.time_s)
        and math.isfinite(frame.absolute_cfo_measurement_hz)
    ]
    minimum_count = max(3, math.ceil(0.75 * baseline_s * FRAME_RATE_HZ))
    minimum_span_s = max(2 / FRAME_RATE_HZ, 0.70 * baseline_s)
    output = []
    for right, frame in enumerate(supported):
        left = right
        while left > 0 and supported[left - 1].time_s >= frame.time_s - baseline_s - 1e-12:
            left -= 1
        selected = supported[left : right + 1]
        if len(selected) < minimum_count:
            continue
        times = np.asarray([item.time_s for item in selected], dtype=float)
        if times[-1] - times[0] < minimum_span_s:
            continue
        if np.max(np.diff(times)) > MAXIMUM_ROLLING_FRAME_GAP_S:
            continue
        frequencies = np.asarray(
            [item.absolute_cfo_measurement_hz for item in selected], dtype=float
        )
        fit = frequency_line(times, frequencies)
        if fit is None:
            continue
        fitted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (
            frame.time_s - fit.reference_time_s
        )
        output.append(
            RollingFrequencyEstimate(
                time_s=interval.start_time_s + frame.time_s,
                fitted_cfo_hz=float(fitted),
                doppler_rate_hz_s=float(fit.slope_hz_per_s),
                support_span_s=float(times[-1] - times[0]),
                supported_frame_count=len(selected),
                fit_rms_hz=float(fit.residual_rms_hz),
            )
        )
    return tuple(output)


def select_strongest_zoom(
    intervals: tuple[TrackingInterval, ...],
    *,
    start_s: float,
    end_s: float,
    duration_s: float,
) -> tuple[float, float]:
    """Select the 0.5 s range with the most direct-quality frame support."""

    if duration_s <= 0 or duration_s > end_s - start_s:
        raise ValueError("zoom duration must be positive and fit inside the report interval")
    frame_times = [
        interval.start_time_s + frame.time_s
        for interval in intervals
        for frame in interval.result.frames
    ]
    candidates = {start_s, end_s - duration_s}
    for time_s in frame_times:
        candidates.add(min(max(time_s, start_s), end_s - duration_s))
        candidates.add(min(max(time_s - duration_s, start_s), end_s - duration_s))
    best: tuple[tuple[float, ...], float] | None = None
    for candidate in sorted(candidates):
        stop = candidate + duration_s
        frames = [
            frame
            for interval in intervals
            for frame in interval.result.frames
            if candidate <= interval.start_time_s + frame.time_s <= stop
        ]
        supported = [item for item in frames if item.measurement_supported]
        score = (
            float(len(supported)),
            float(sum(item.phase_update_applied for item in supported)),
            float(sum(max(item.coherence_margin, 0.0) for item in supported)),
            -candidate,
        )
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is None or best[0][0] == 0:
        raise ValueError("no supported pilot frames are available for the zoom")
    return best[1], best[1] + duration_s


def _frame_arrays(
    interval: TrackingInterval,
    trajectory: FrozenTrajectory,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    frames = interval.result.frames
    times = np.asarray([interval.start_time_s + frame.time_s for frame in frames])
    frozen = np.asarray(trajectory.frequency_hz(times), dtype=float)
    measured = np.asarray([frame.absolute_cfo_measurement_hz for frame in frames]) - frozen
    tracked = np.asarray([frame.tracked_absolute_cfo_hz for frame in frames]) - frozen
    supported = np.asarray([frame.measurement_supported for frame in frames], dtype=bool)
    return times, measured, tracked, supported


def render_multiscale_cfo(
    path: Path,
    intervals: tuple[TrackingInterval, ...],
    trajectory: FrozenTrajectory,
    *,
    x_limits_s: tuple[float, float],
    title: str,
    highlighted_zoom_s: tuple[float, float] | None = None,
) -> None:
    """Render frame, local-fit, and frozen-trajectory scales on one x axis."""

    line_styles = {0.020: ":", 0.050: "--", 0.070: "-"}
    line_colors = {0.020: GREEN, 0.050: AMBER, 0.070: PURPLE}
    figure, axes = plt.subplots(4, 1, figsize=(15, 13), sharex=True)
    frame_axis, bootstrap_axis, local_axis, rate_axis = axes
    supported_residuals: list[float] = []
    rejected_label_used = False
    measured_label_used = False
    bootstrap_label_used = False
    kalman_label_used = False
    baseline_labels_used: set[float] = set()
    rate_labels_used: set[float] = set()
    for interval in intervals:
        times, measured_residual, tracked_residual, supported = _frame_arrays(interval, trajectory)
        finite = np.isfinite(measured_residual)
        accepted = supported & finite
        rejected = ~supported & finite
        supported_residuals.extend(float(value) for value in measured_residual[accepted])
        if np.any(rejected):
            frame_axis.scatter(
                times[rejected],
                measured_residual[rejected],
                s=8,
                color=GRAY,
                alpha=0.22,
                linewidths=0,
                label="rejected/coasted pilot frame" if not rejected_label_used else None,
                zorder=1,
            )
            rejected_label_used = True
        if np.any(accepted):
            frame_axis.scatter(
                times[accepted],
                measured_residual[accepted],
                s=11,
                color=BLUE,
                alpha=0.72,
                linewidths=0,
                label="accepted 1.333 ms frame CFO" if not measured_label_used else None,
                zorder=2,
            )
            measured_label_used = True

        bootstrap = rolling_frequency_estimates(interval, 0.016)
        if bootstrap:
            bootstrap_times = np.asarray([item.time_s for item in bootstrap])
            bootstrap_residual = np.asarray(
                [item.fitted_cfo_hz - trajectory.frequency_hz(item.time_s) for item in bootstrap]
            )
            bootstrap_axis.plot(
                bootstrap_times,
                bootstrap_residual,
                color=BLUE,
                linewidth=1.55,
                alpha=0.94,
                label="16 ms local frequency line" if not bootstrap_label_used else None,
                zorder=3,
            )
            bootstrap_label_used = True
        tracked_supported = np.where(supported, tracked_residual, np.nan)
        bootstrap_axis.plot(
            times,
            tracked_supported,
            color=AMBER,
            linewidth=1.0,
            linestyle="--",
            alpha=0.62,
            label="five-state phase+frequency KF" if not kalman_label_used else None,
            zorder=2,
        )
        kalman_label_used = True

        for baseline_s in (0.020, 0.050, 0.070):
            estimates = rolling_frequency_estimates(interval, baseline_s)
            if not estimates:
                continue
            estimate_times = np.asarray([item.time_s for item in estimates])
            estimate_residual = np.asarray(
                [item.fitted_cfo_hz - trajectory.frequency_hz(item.time_s) for item in estimates]
            )
            label = None
            if baseline_s not in baseline_labels_used:
                label = f"{baseline_s * 1_000:.0f} ms local frequency line"
                baseline_labels_used.add(baseline_s)
            local_axis.plot(
                estimate_times,
                estimate_residual,
                color=line_colors[baseline_s],
                linestyle=line_styles[baseline_s],
                linewidth=1.75 if baseline_s == 0.070 else 1.25,
                alpha=0.92 if baseline_s == 0.070 else 0.76,
                label=label,
                zorder=2 + int(baseline_s == 0.070),
            )

        for baseline_s in ROLLING_BASELINES_S:
            estimates = [
                item
                for item in rolling_frequency_estimates(interval, baseline_s)
                if abs(item.doppler_rate_hz_s) <= MAXIMUM_DISPLAY_RATE_HZ_S
            ]
            if not estimates:
                continue
            label = None
            if baseline_s not in rate_labels_used:
                label = f"{baseline_s * 1_000:.0f} ms local slope"
                rate_labels_used.add(baseline_s)
            rate_axis.plot(
                [item.time_s for item in estimates],
                [item.doppler_rate_hz_s / 1_000 for item in estimates],
                color=BLUE if baseline_s == 0.016 else line_colors[baseline_s],
                linestyle="-." if baseline_s == 0.016 else line_styles[baseline_s],
                linewidth=1.5 if baseline_s == 0.070 else 1.0,
                alpha=0.88 if baseline_s == 0.070 else 0.62,
                label=label,
            )

    model_times = np.linspace(x_limits_s[0], x_limits_s[1], 800)
    rate_axis.plot(
        model_times,
        np.asarray(trajectory.doppler_rate_hz_s(model_times)) / 1_000,
        color=INK,
        linewidth=2.4,
        label="multi-second cubic GLRT derivative",
        zorder=5,
    )
    panel_titles = (
        "A · One independent known-pilot CFO per complete 1.333 ms frame",
        "B · 16 ms local frequency line and causal phase+frequency Kalman state",
        "C · Rolling fitted CFO at 20, 50, and 70 ms support",
        "D · Slope of each fitted CFO versus the multi-second GLRT trajectory",
    )
    for axis, panel_title in zip(axes, panel_titles, strict=True):
        axis.axhline(0, color=INK, linewidth=0.9, alpha=0.72, zorder=0)
        axis.grid(alpha=0.18)
        axis.set_title(panel_title, loc="left", fontsize=11)
        axis.set_xlim(*x_limits_s)
        if highlighted_zoom_s is not None:
            axis.axvspan(
                highlighted_zoom_s[0],
                highlighted_zoom_s[1],
                color="#e6b85c",
                alpha=0.11,
                linewidth=0,
                zorder=0,
            )
    for axis in axes[:3]:
        axis.set_ylabel("CFO − frozen GLRT fit (Hz)")
    if supported_residuals:
        lower, upper = np.percentile(np.asarray(supported_residuals), (0.5, 99.5))
        padding = max(40.0, 0.12 * max(upper - lower, 1.0))
        for axis in axes[:3]:
            axis.set_ylim(lower - padding, upper + padding)
    rate_axis.set_ylabel("fitted CFO slope (kHz/s)")
    rate_axis.set_ylim(-15, 15)
    rate_axis.set_xlabel("capture time (s)")
    frame_axis.legend(loc="best", fontsize=8, ncols=2)
    bootstrap_axis.legend(loc="best", fontsize=8, ncols=2)
    local_axis.legend(loc="best", fontsize=8, ncols=3)
    rate_axis.legend(loc="best", fontsize=7.5, ncols=3)
    figure.suptitle(title, fontsize=16)
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def dense_frames_from_document(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Validate and return the original all-lock dense frame-CFO evidence."""

    expected = {
        "session_id": SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "edge": "upper",
        "trajectory_id": TRAJECTORY_ID,
    }
    actual = document.get("input", {})
    mismatches = [
        key for key, expected_value in expected.items() if actual.get(key) != expected_value
    ]
    if mismatches:
        raise ValueError("dense evidence has an unexpected " + ", ".join(mismatches))
    dense = document.get("dense_tracking")
    if not isinstance(dense, dict) or not isinstance(dense.get("frames"), list):
        raise ValueError("dense evidence does not contain frame rows")
    frames = tuple(dense["frames"])
    if len(frames) != int(dense.get("returned_frame_count", -1)):
        raise ValueError("dense evidence frame count disagrees with its summary")
    times = [float(item["reference_time_s"]) for item in frames]
    if times != sorted(times):
        raise ValueError("dense frame evidence is not time ordered")
    return frames


def _dense_frame_summary(
    frames: tuple[dict[str, Any], ...],
    *,
    limits_s: tuple[float, float],
) -> dict[str, int]:
    selected = [
        item for item in frames if limits_s[0] <= float(item["reference_time_s"]) <= limits_s[1]
    ]
    return {
        "frame_count": len(selected),
        "frequency_update_count": sum(bool(item["frequency_update_applied"]) for item in selected),
        "phase_update_count": sum(bool(item["phase_update_applied"]) for item in selected),
        "phase_reset_count": sum(bool(item["phase_reset_detected"]) for item in selected),
    }


def render_all_frame_cfo(
    path: Path,
    frames: tuple[dict[str, Any], ...],
    *,
    full_limits_s: tuple[float, float],
    zoom_limits_s: tuple[float, float],
    source_window_count: int,
) -> None:
    """Plot every original 1.333 ms frame-CFO measurement without subsampling."""

    figure, axes = plt.subplots(2, 1, figsize=(15, 10), constrained_layout=True)
    panels = (
        (
            axes[0],
            full_limits_s,
            9,
            f"A · Complete {full_limits_s[0]:.3f}–{full_limits_s[1]:.3f} s dense-frame record",
        ),
        (axes[1], zoom_limits_s, 15, "B · Same 0.5 s region, without stride subsampling"),
    )
    for axis, limits_s, marker_size, title in panels:
        selected = [
            item for item in frames if limits_s[0] <= float(item["reference_time_s"]) <= limits_s[1]
        ]
        times = np.asarray([item["reference_time_s"] for item in selected], dtype=float)
        residual = np.asarray(
            [item["absolute_cfo_measurement_hz"] - item["model_cfo_hz"] for item in selected],
            dtype=float,
        )
        accepted = np.asarray([item["frequency_update_applied"] for item in selected], dtype=bool)
        finite = np.isfinite(residual)
        rejected = ~accepted & finite
        accepted &= finite
        axis.scatter(
            times[rejected],
            residual[rejected],
            s=marker_size,
            color=GRAY,
            alpha=0.20,
            linewidths=0,
            label=f"measured, not used for CFO update ({np.count_nonzero(rejected)})",
            zorder=1,
        )
        axis.scatter(
            times[accepted],
            residual[accepted],
            s=marker_size + 2,
            color=BLUE,
            alpha=0.76,
            linewidths=0,
            label=f"accepted frame-CFO update ({np.count_nonzero(accepted)})",
            zorder=2,
        )
        axis.axhline(0, color=INK, linewidth=1.0, alpha=0.82, zorder=0)
        axis.set_xlim(*limits_s)
        if np.any(finite):
            lower = float(np.min(residual[finite]))
            upper = float(np.max(residual[finite]))
            padding = max(50.0, 0.06 * max(upper - lower, 1.0))
            axis.set_ylim(lower - padding, upper + padding)
        axis.set_title(title, loc="left", fontsize=12)
        axis.set_ylabel("frame CFO − frozen GLRT fit (Hz)")
        axis.set_xlabel("capture time (s)")
        axis.grid(alpha=0.18)
        axis.legend(loc="best", fontsize=8.5, ncols=2)
    figure.suptitle(
        f"All 1.333 ms known-pilot frame CFOs · {source_window_count} timing locks · "
        f"{len(frames)} frames",
        fontsize=16,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _rolling_rows(
    intervals: tuple[TrackingInterval, ...],
    trajectory: FrozenTrajectory,
) -> list[dict[str, Any]]:
    rows = []
    for interval in intervals:
        for baseline_s in ROLLING_BASELINES_S:
            for estimate in rolling_frequency_estimates(interval, baseline_s):
                rows.append(
                    {
                        "source_window_index": interval.source.index,
                        "baseline_s": baseline_s,
                        **asdict(estimate),
                        "frozen_glrt_rate_hz_s": float(
                            trajectory.doppler_rate_hz_s(estimate.time_s)
                        ),
                        "local_minus_frozen_rate_hz_s": float(
                            estimate.doppler_rate_hz_s
                            - trajectory.doppler_rate_hz_s(estimate.time_s)
                        ),
                    }
                )
    return rows


def _baseline_summary(
    rows: list[dict[str, Any]],
    baseline_s: float,
    *,
    time_limits_s: tuple[float, float] | None = None,
) -> dict[str, Any]:
    selected = [item for item in rows if item["baseline_s"] == baseline_s]
    if time_limits_s is not None:
        selected = [
            item for item in selected if time_limits_s[0] <= item["time_s"] <= time_limits_s[1]
        ]
    if not selected:
        return {"baseline_s": baseline_s, "estimate_count": 0}
    rates = np.asarray([item["doppler_rate_hz_s"] for item in selected], dtype=float)
    differences = np.asarray(
        [item["local_minus_frozen_rate_hz_s"] for item in selected], dtype=float
    )
    rms = np.asarray([item["fit_rms_hz"] for item in selected], dtype=float)
    return {
        "baseline_s": baseline_s,
        "estimate_count": len(selected),
        "median_rate_hz_s": float(np.median(rates)),
        "p10_rate_hz_s": float(np.percentile(rates, 10)),
        "p90_rate_hz_s": float(np.percentile(rates, 90)),
        "median_local_minus_frozen_rate_hz_s": float(np.median(differences)),
        "median_fit_rms_hz": float(np.median(rms)),
    }


def _frame_rows(
    intervals: tuple[TrackingInterval, ...],
    trajectory: FrozenTrajectory,
) -> list[dict[str, Any]]:
    rows = []
    for interval in intervals:
        for frame in interval.result.frames:
            time_s = interval.start_time_s + frame.time_s
            model_hz = float(trajectory.frequency_hz(time_s))
            rows.append(
                {
                    "source_window_index": interval.source.index,
                    "frame_index": frame.frame_index,
                    "reference_time_s": time_s,
                    "measurement_supported": frame.measurement_supported,
                    "phase_update_applied": frame.phase_update_applied,
                    "frequency_update_applied": frame.frequency_update_applied,
                    "absolute_cfo_measurement_hz": frame.absolute_cfo_measurement_hz,
                    "tracked_absolute_cfo_hz": frame.tracked_absolute_cfo_hz,
                    "tracked_doppler_rate_hz_s": frame.tracked_doppler_rate_hz_s,
                    "model_cfo_hz": model_hz,
                    "model_doppler_rate_hz_s": float(trajectory.doppler_rate_hz_s(time_s)),
                    "frequency_uncertainty_hz": frame.frequency_sigma_hz,
                    "exact_coherence": frame.exact_coherence,
                    "control_coherence": frame.control_coherence,
                    "coherence_margin": frame.coherence_margin,
                }
            )
    return rows


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---:" if index else "---" for index in range(len(headers))) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def write_report(
    path: Path,
    *,
    trajectory: FrozenTrajectory,
    start_s: float,
    end_s: float,
    zoom_start_s: float,
    zoom_end_s: float,
    intervals: tuple[TrackingInterval, ...],
    accepted_before_stride: int,
    accepted_stride: int,
    baseline_summary: list[dict[str, Any]],
    zoom_baseline_summary: list[dict[str, Any]],
    dense_figure: Path,
    dense_summary: dict[str, int],
    dense_zoom_summary: dict[str, int],
    full_figure: Path,
    zoom_figure: Path,
    result_path: Path,
) -> None:
    model_start = float(trajectory.doppler_rate_hz_s(start_s))
    model_end = float(trajectory.doppler_rate_hz_s(end_s))
    supported = sum(interval.result.supported_frame_count for interval in intervals)
    phase_updates = sum(interval.result.phase_update_count for interval in intervals)
    rows = []
    for full, zoom in zip(baseline_summary, zoom_baseline_summary, strict=True):
        rows.append(
            (
                f"{full['baseline_s'] * 1_000:.0f}",
                str(full["estimate_count"]),
                f"{full.get('median_rate_hz_s', math.nan) / 1_000:+.3f}",
                f"{full.get('p10_rate_hz_s', math.nan) / 1_000:+.3f}",
                f"{full.get('p90_rate_hz_s', math.nan) / 1_000:+.3f}",
                f"{full.get('median_local_minus_frozen_rate_hz_s', math.nan) / 1_000:+.3f}",
                f"{full.get('median_fit_rms_hz', math.nan):.1f}",
                f"{zoom.get('median_rate_hz_s', math.nan) / 1_000:+.3f}",
            )
        )
    parent = path.parent
    lines = [
        "# Multiscale pilot-CFO tracking in the 470384 worked example",
        "",
        "Date: 2026-08-23",
        "",
        f"Capture: `{SESSION_ID}`",
        "Path: `stream-0`, receiver 0, upper edge",
        f"Interval: {start_s:.3f}–{end_s:.3f} s",
        "",
        "## Result",
        "",
        (
            f"The same resolution ladder is now reproduced for the original worked "
            f"example. It contains {supported} accepted 1.333 ms pilot-frame CFO "
            f"measurements and {phase_updates} applied modulo-pi phase updates across "
            f"{len(intervals)} digest-verified 70 ms raw-IQ windows, selected at stride "
            f"{accepted_stride} from {accepted_before_stride} qualifying timing locks."
        ),
        "",
        (
            f"The frozen multi-second GLRT product is cubic, so it has no single rate: "
            f"its derivative changes from {model_start / 1_000:+.3f} kHz/s at "
            f"{start_s:.1f} s to {model_end / 1_000:+.3f} kHz/s at {end_s:.1f} s. "
            "Panel D therefore plots the derivative curve rather than a horizontal line."
        ),
        "",
        "## Every 1.333 ms frame-CFO measurement",
        "",
        f"![All dense frame CFOs]({dense_figure.relative_to(parent)})",
        "",
        (
            f"*Figure 1. The upper panel includes all {dense_summary['frame_count']} frame-local "
            f"CFO measurements exposed by all {accepted_before_stride} timing locks; "
            f"{dense_summary['frequency_update_count']} were accepted for tracker updates. "
            f"The lower panel contains {dense_zoom_summary['frame_count']} frames in the same "
            f"{zoom_start_s:.3f}–{zoom_end_s:.3f} s zoom, including "
            f"{dense_zoom_summary['frequency_update_count']} accepted CFO updates. There is no "
            "stride subsampling in this figure.*"
        ),
        "",
        "## Sparse multiscale 33.7–37.7 s interval",
        "",
        f"![Full worked-example multiscale CFO]({full_figure.relative_to(parent)})",
        "",
        (
            "*Figure 2. All four levels share capture time. Panels A–C use CFO minus "
            "the frozen cubic trajectory, which removes the arbitrary constant receiver/"
            "LNB offset but preserves slope and carrier-mode changes. Blank regions were "
            "not re-read and are not interpolated. Unlike Figure 1, this scale comparison "
            f"uses the stride-{accepted_stride} set of longer 70 ms rereads.*"
        ),
        "",
        "## Strongest 0.5 s region",
        "",
        f"![Strongest 500 ms worked-example zoom]({zoom_figure.relative_to(parent)})",
        "",
        (
            f"*Figure 3. The direct-quality support maximum is {zoom_start_s:.3f}–"
            f"{zoom_end_s:.3f} s. Each rolling curve is fitted only inside one verified "
            "70 ms source interval and never bridges a rejected-frame gap above 4.1 ms.*"
        ),
        "",
        "## Scale comparison",
        "",
    ]
    lines.extend(
        _markdown_table(
            (
                "Support (ms)",
                "Full estimates",
                "Median rate (kHz/s)",
                "P10",
                "P90",
                "Median local−GLRT (kHz/s)",
                "Median line RMS (Hz)",
                "Zoom median rate (kHz/s)",
            ),
            rows,
        )
    )
    lines.extend(
        [
            "",
            "The 1.333 ms level is a frequency measurement, not a rate measurement. "
            "A Doppler-rate estimate appears only after fitting multiple frame CFOs "
            "over 16–70 ms. Those rolling samples overlap heavily and are descriptive, "
            "not independent trials.",
            "",
            "The orange curve in panel B is the causal five-state phase+frequency Kalman "
            "state. Phase tracking improves continuity and ambiguity handling, while the "
            "blue/green/purple local slopes in panels C–D are fitted directly to accepted "
            "frame-CFO measurements. Their agreement or disagreement can therefore be "
            "inspected without treating the Kalman rate as independent evidence.",
            "",
            "This remains receiver-relative, candidate-only evidence. It does not resolve "
            "an absolute transmitter frequency, an LNB offset, a satellite identity, or "
            "which part of the short-scale carrier motion is geometric Doppler.",
            "",
            "## Machine-readable evidence",
            "",
            f"- [Full result JSON]({result_path.relative_to(parent)})",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    if not math.isfinite(args.start_s) or not math.isfinite(args.end_s):
        raise ValueError("report interval must be finite")
    if args.end_s <= args.start_s:
        raise ValueError("report interval must be increasing")
    if args.window_duration_s < max(ROLLING_BASELINES_S):
        raise ValueError("raw window is shorter than the longest requested fit")

    scan_path = args.analysis_root / "standard.pilot-scan.v3.json"
    bank_path = args.analysis_root / "standard.final-trajectory-bank.v2.json"
    scan = _load_json(scan_path)
    trajectory = trajectory_from_bank(_load_json(bank_path))
    dense_document = _load_json(args.dense_evidence)
    dense_frames = dense_frames_from_document(dense_document)
    all_accepted = select_source_windows(
        scan,
        trajectory,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
        accepted_stride=1,
    )
    windows = select_source_windows(
        scan,
        trajectory,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
        accepted_stride=args.accepted_stride,
    )
    if not windows:
        raise ValueError("selection produced no source windows")

    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
        bundle = store.inspect(args.session_id)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError(f"receiver {args.receiver} is absent from {args.stream}")
        sample_rate_hz = float(reader.sample_rate_hz)
        raw_start = min(item.probe_sample_start for item in windows)
        raw_stop = max(item.probe_sample_start for item in windows) + round(
            args.window_duration_s * sample_rate_hz
        )
        raw = reader.read(
            raw_start,
            raw_stop - raw_start,
            receiver_ids=(args.receiver,),
        )
        recording_manifest_digest = bundle.manifest_sha256
    finally:
        if store is not None:
            store.close()
    intervals = analyze_windows(
        _complex_receiver(raw),
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        windows=windows,
        trajectory=trajectory,
        edge=StarlinkEdge(args.edge),
        window_duration_s=args.window_duration_s,
        maximum_residual_cfo_hz=args.maximum_residual_cfo_hz,
    )
    zoom_start_s, zoom_end_s = select_strongest_zoom(
        intervals,
        start_s=args.start_s,
        end_s=args.end_s,
        duration_s=args.zoom_duration_s,
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    full_figure = args.output_root / "multiscale-cfo-33p7-37p7.png"
    zoom_figure = args.output_root / "multiscale-cfo-500ms-zoom.png"
    dense_figure = args.output_root / "all-1p333ms-frame-cfos.png"
    result_path = args.output_root / "multiscale-cfo-results.json"
    dense_full_limits_s = (
        float(dense_frames[0]["reference_time_s"]),
        float(dense_frames[-1]["reference_time_s"]),
    )
    dense_summary = _dense_frame_summary(
        dense_frames,
        limits_s=dense_full_limits_s,
    )
    dense_zoom_summary = _dense_frame_summary(
        dense_frames,
        limits_s=(zoom_start_s, zoom_end_s),
    )
    render_all_frame_cfo(
        dense_figure,
        dense_frames,
        full_limits_s=dense_full_limits_s,
        zoom_limits_s=(zoom_start_s, zoom_end_s),
        source_window_count=int(dense_document["dense_tracking"]["source_window_count"]),
    )
    render_multiscale_cfo(
        full_figure,
        intervals,
        trajectory,
        x_limits_s=(args.start_s, args.end_s),
        highlighted_zoom_s=(zoom_start_s, zoom_end_s),
        title=(
            "Original worked example · pilot-CFO tracking resolution ladder\n"
            "stream-0/RX0 upper · verified 70 ms source windows only"
        ),
    )
    render_multiscale_cfo(
        zoom_figure,
        intervals,
        trajectory,
        x_limits_s=(zoom_start_s, zoom_end_s),
        title="Original worked example · strongest 0.500 s audited-signal zoom",
    )

    rolling_rows = _rolling_rows(intervals, trajectory)
    baseline_summary = [
        _baseline_summary(rolling_rows, baseline_s) for baseline_s in ROLLING_BASELINES_S
    ]
    zoom_baseline_summary = [
        _baseline_summary(
            rolling_rows,
            baseline_s,
            time_limits_s=(zoom_start_s, zoom_end_s),
        )
        for baseline_s in ROLLING_BASELINES_S
    ]
    frame_rows = _frame_rows(intervals, trajectory)
    result = {
        "schema": "research.470384-multiscale-pilot-cfo.v1",
        "algorithm": "bounded-70ms-pilot-frame-cfo-rolling-lines-v1",
        "session_id": args.session_id,
        "stream_id": args.stream,
        "receiver_id": args.receiver,
        "edge": args.edge,
        "analysis_scope": ANALYSIS_SCOPE,
        "recording_manifest_digest": recording_manifest_digest,
        "source_products": {
            "pilot_scan": {"path": str(scan_path), "sha256": _sha256(scan_path)},
            "final_trajectory_bank": {"path": str(bank_path), "sha256": _sha256(bank_path)},
            "dense_frame_evidence": {
                "path": str(args.dense_evidence),
                "sha256": _sha256(args.dense_evidence),
            },
        },
        "trajectory": {
            **asdict(trajectory),
            "polynomial_degree": len(trajectory.coefficients_hz) - 1,
            "rate_at_start_hz_s": float(trajectory.doppler_rate_hz_s(args.start_s)),
            "rate_at_end_hz_s": float(trajectory.doppler_rate_hz_s(args.end_s)),
        },
        "selection": {
            "start_s": args.start_s,
            "end_s": args.end_s,
            "minimum_glrt64_margin": args.minimum_glrt64_margin,
            "maximum_model_error_hz": args.maximum_model_error_hz,
            "accepted_stride": args.accepted_stride,
            "accepted_before_stride": len(all_accepted),
            "selected_window_count": len(windows),
            "source_windows": [asdict(item) for item in windows],
        },
        "tracking": {
            "frame_rate_hz": FRAME_RATE_HZ,
            "raw_window_duration_s": args.window_duration_s,
            "requested_frame_count": sum(len(item.result.frames) for item in intervals),
            "supported_frame_count": sum(item.result.supported_frame_count for item in intervals),
            "phase_update_count": sum(item.result.phase_update_count for item in intervals),
            "frequency_update_count": sum(item.result.frequency_update_count for item in intervals),
            "rolling_fit_baselines_s": list(ROLLING_BASELINES_S),
            "maximum_supported_frame_gap_s": MAXIMUM_ROLLING_FRAME_GAP_S,
            "rolling_fits_are_overlapping_descriptive_estimates": True,
            "unsampled_gaps_are_not_interpolated": True,
        },
        "zoom": {
            "start_s": zoom_start_s,
            "end_s": zoom_end_s,
            "duration_s": args.zoom_duration_s,
            "selection": "maximum supported frames, then phase updates and coherence margin",
            "supported_frame_count": sum(
                item["measurement_supported"]
                and zoom_start_s <= item["reference_time_s"] <= zoom_end_s
                for item in frame_rows
            ),
        },
        "dense_frame_visualization": {
            "source_window_count": int(dense_document["dense_tracking"]["source_window_count"]),
            "full": dense_summary,
            "zoom": dense_zoom_summary,
            "all_finite_frame_cfo_measurements_are_rendered": True,
            "stride_subsampled": False,
            "cfo_ordinate": "frame-local CFO minus matched frozen cubic GLRT CFO",
        },
        "baseline_summary": baseline_summary,
        "zoom_baseline_summary": zoom_baseline_summary,
        "frames": frame_rows,
        "rolling_fits": rolling_rows,
        "candidate_only": True,
        "known_pilots_only": True,
        "satellite_identity_resolved": False,
        "absolute_carrier_frequency_resolved": False,
        "figures": [
            {"path": str(dense_figure), "sha256": _sha256(dense_figure)},
            {"path": str(full_figure), "sha256": _sha256(full_figure)},
            {"path": str(zoom_figure), "sha256": _sha256(zoom_figure)},
        ],
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(
        args.report_path,
        trajectory=trajectory,
        start_s=args.start_s,
        end_s=args.end_s,
        zoom_start_s=zoom_start_s,
        zoom_end_s=zoom_end_s,
        intervals=intervals,
        accepted_before_stride=len(all_accepted),
        accepted_stride=args.accepted_stride,
        baseline_summary=baseline_summary,
        zoom_baseline_summary=zoom_baseline_summary,
        dense_figure=dense_figure,
        dense_summary=dense_summary,
        dense_zoom_summary=dense_zoom_summary,
        full_figure=full_figure,
        zoom_figure=zoom_figure,
        result_path=result_path,
    )
    print(result_path)
    print(dense_figure)
    print(full_figure)
    print(zoom_figure)
    print(args.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
