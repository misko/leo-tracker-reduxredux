#!/usr/bin/env python3
"""Render measured-data figures for the frame-local edge-pilot phase report.

The default invocation is pinned to the report's read-only dwell and frozen
Standard artifacts.  Candidate selection is completed from persisted GLRT64
results before raw IQ is opened.  The tool then reads one digest-verified IQ
interval, reruns the Research phase-slope estimator, and emits PNG figures plus
per-window/per-frame JSON evidence.  It never decodes payload or writes to the
recording or analysis corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PIL import Image

from leo.analysis.qam import PilotPhaseSlopeFrame, analyze_pilot_phase_slope
from leo.analysis.qam.pilot import _complete_frame_starts, _KnownPilotDemodulator
from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge, qin_edge_pilot_symbols
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
ANALYSIS_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
BRANCH_PREFIX = "sha256:5852a936"
DEFAULT_ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/" + ANALYSIS_SCOPE
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_22_edge_pilot_phase_slope")
BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
RED = "#c44e52"
INK = "#193549"
GRAY = "#728694"


@dataclass(frozen=True, slots=True)
class FrozenTrajectory:
    coefficients_hz: tuple[float, ...]
    reference_time_s: float
    branch_id: str
    trajectory_id: str

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        values = np.polyval(self.coefficients_hz, np.asarray(time_s) - self.reference_time_s)
        return float(values) if np.ndim(values) == 0 else values


@dataclass(frozen=True, slots=True)
class SelectedWindow:
    index: int
    detection_time_s: float
    probe_sample_start: int
    aligned_sample_start: int
    candidate_rank: int
    local_epoch_sample: int
    acquired_cfo_hz: float
    glrt64_cfo_hz: float
    glrt64_margin: float
    selection_model_error_hz: float


@dataclass(frozen=True, slots=True)
class FrameDetail:
    window_index: int
    frame_index: int
    reference_time_s: float
    residual_cfo_hz: float
    absolute_cfo_hz: float
    model_cfo_hz: float
    error_vs_model_hz: float
    frequency_uncertainty_hz: float
    phase_at_reference_rad: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    phase_residual_rms_rad: float


@dataclass(frozen=True, slots=True)
class WindowDetail:
    selected: SelectedWindow
    reference_time_s: float
    phase_slope_cfo_hz: float
    glrt64_cfo_hz: float
    model_cfo_hz: float
    phase_error_vs_model_hz: float
    glrt64_error_vs_model_hz: float
    frames: tuple[FrameDetail, ...]
    phase_display_rad: np.ndarray = field(repr=False)
    phase_residual_rad: np.ndarray = field(repr=False)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-root", type=Path, default=DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--session-id", default=SESSION_ID)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--edge", choices=("lower", "upper"), default="upper")
    parser.add_argument("--start-s", type=float, default=33.7)
    parser.add_argument("--end-s", type=float, default=37.7)
    parser.add_argument("--minimum-glrt64-margin", type=float, default=0.05)
    parser.add_argument("--maximum-model-error-hz", type=float, default=2_500.0)
    parser.add_argument("--accepted-stride", type=int, default=8)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _trajectory(document: dict[str, Any], branch_prefix: str = BRANCH_PREFIX) -> FrozenTrajectory:
    matches = [
        item
        for item in document["trajectories"]
        if str(item["branch_id"]).startswith(branch_prefix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one frozen trajectory for {branch_prefix}, found {len(matches)}"
        )
    item = matches[0]
    return FrozenTrajectory(
        tuple(float(value) for value in item["absolute_coefficients_hz"]),
        float(item["reference_time_s"]),
        str(item["branch_id"]),
        str(item["trajectory_id"]),
    )


def _glrt64_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def _select_windows(
    scan: dict[str, Any],
    trajectory: FrozenTrajectory,
    *,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
    accepted_stride: int,
) -> tuple[SelectedWindow, ...]:
    if accepted_stride <= 0:
        raise ValueError("accepted stride must be positive")
    accepted: list[SelectedWindow] = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s <= end_s:
            continue
        model_hz = float(trajectory.frequency_hz(time_s))
        eligible: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for candidate in detection["candidates"]:
            score = _glrt64_score(candidate)
            if float(score["margin"]) < minimum_margin:
                continue
            error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
            eligible.append((error_hz, candidate, score))
        if not eligible:
            continue
        error_hz, candidate, score = min(eligible, key=lambda item: item[0])
        if error_hz > maximum_model_error_hz:
            continue
        epoch = int(candidate["local_epoch_sample"])
        accepted.append(
            SelectedWindow(
                index=len(accepted),
                detection_time_s=time_s,
                probe_sample_start=int(detection["sample_start"]),
                aligned_sample_start=int(detection["sample_start"]) + epoch,
                candidate_rank=int(candidate["rank"]),
                local_epoch_sample=epoch,
                acquired_cfo_hz=float(candidate["acquired_cfo_hz"]),
                glrt64_cfo_hz=float(score["tracking_cfo_hz"]),
                glrt64_margin=float(score["margin"]),
                selection_model_error_hz=error_hz,
            )
        )
    selected = accepted[::accepted_stride]
    return tuple(
        SelectedWindow(
            index=index,
            detection_time_s=item.detection_time_s,
            probe_sample_start=item.probe_sample_start,
            aligned_sample_start=item.aligned_sample_start,
            candidate_rank=item.candidate_rank,
            local_epoch_sample=item.local_epoch_sample,
            acquired_cfo_hz=item.acquired_cfo_hz,
            glrt64_cfo_hz=item.glrt64_cfo_hz,
            glrt64_margin=item.glrt64_margin,
            selection_model_error_hz=item.selection_model_error_hz,
        )
        for index, item in enumerate(selected)
    )


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15)


def _phase_arrays(
    pilots: np.ndarray,
    expected: np.ndarray,
    frames: tuple[PilotPhaseSlopeFrame, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Return display phase and circular residual for every frame/symbol.

    The display phase is coherently combined only after estimating one channel
    vector per frame.  Circular residuals are lifted onto the branch nearest
    the fitted slope, avoiding false 2-pi steps from low-weight symbols.  The
    intercept is restored from the estimator's relative diagnostic phase; it
    is never unwrapped between frames.
    """

    if pilots.shape != (len(frames), 300, 8):
        raise ValueError("pilot cube does not match frame results")
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    displays = []
    residuals = []
    for pilot, frame in zip(pilots, frames, strict=True):
        matched = pilot * np.conj(expected)
        rotation = np.exp(-2j * np.pi * frame.residual_cfo_hz * times_s)
        channel = np.mean(matched * rotation[:, None], axis=0)
        combined = np.sum(matched * np.conj(channel)[None, :], axis=1)
        weights = np.abs(combined)
        fitted_slope = 2 * np.pi * frame.residual_cfo_hz * times_s
        weight_sum = float(np.sum(weights))
        residual_phase = np.angle(combined * rotation)
        phase_center = (
            float(np.angle(np.sum(weights * np.exp(1j * residual_phase))))
            if weight_sum > 0
            else 0.0
        )
        fit = fitted_slope + frame.phase_at_reference_rad
        residual = np.angle(np.exp(1j * (residual_phase - phase_center)))
        display = fit + residual
        displays.append(display)
        residuals.append(residual)
    return np.asarray(displays), np.asarray(residuals)


def _analyze_windows(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    probe_samples: int,
    edge: StarlinkEdge,
    selected: tuple[SelectedWindow, ...],
    trajectory: FrozenTrajectory,
) -> tuple[WindowDetail, ...]:
    expected = qin_edge_pilot_symbols(edge)
    details = []
    for item in selected:
        relative = item.aligned_sample_start - raw_sample_start
        samples = np.ascontiguousarray(iq[relative : relative + probe_samples])
        if len(samples) != probe_samples:
            raise ValueError(f"window {item.index} lies outside the verified IQ interval")
        result = analyze_pilot_phase_slope(
            samples,
            sample_rate_hz,
            epoch_sample=0,
            absolute_cfo_hz=item.glrt64_cfo_hz,
            edge=edge,
        )
        if result.aggregate_absolute_cfo_hz is None or not result.frames:
            raise ValueError(f"phase-slope estimator returned no result for window {item.index}")
        starts = _complete_frame_starts(len(samples), sample_rate_hz, 0)
        demodulator = _KnownPilotDemodulator(samples, sample_rate_hz, edge, item.glrt64_cfo_hz)
        pilots = np.asarray([demodulator.frame(start) for start in starts])
        display, residual = _phase_arrays(pilots, expected, result.frames)
        supported_reference = np.asarray(
            [frame.reference_sample for frame in result.frames if frame.coherence_margin > 0],
            dtype=float,
        )
        if not supported_reference.size:
            supported_reference = np.asarray(
                [frame.reference_sample for frame in result.frames], dtype=float
            )
        reference_time_s = (
            item.aligned_sample_start + float(np.median(supported_reference))
        ) / sample_rate_hz
        model_hz = float(trajectory.frequency_hz(reference_time_s))
        frame_details = []
        for frame in result.frames:
            frame_time_s = (item.aligned_sample_start + frame.reference_sample) / sample_rate_hz
            frame_model_hz = float(trajectory.frequency_hz(frame_time_s))
            frame_details.append(
                FrameDetail(
                    window_index=item.index,
                    frame_index=frame.frame_index,
                    reference_time_s=frame_time_s,
                    residual_cfo_hz=frame.residual_cfo_hz,
                    absolute_cfo_hz=frame.absolute_cfo_hz,
                    model_cfo_hz=frame_model_hz,
                    error_vs_model_hz=frame.absolute_cfo_hz - frame_model_hz,
                    frequency_uncertainty_hz=frame.frequency_uncertainty_hz,
                    phase_at_reference_rad=frame.phase_at_reference_rad,
                    exact_coherence=frame.exact_coherence,
                    control_coherence=frame.control_coherence,
                    coherence_margin=frame.coherence_margin,
                    phase_residual_rms_rad=frame.phase_residual_rms_rad,
                )
            )
        details.append(
            WindowDetail(
                selected=item,
                reference_time_s=reference_time_s,
                phase_slope_cfo_hz=result.aggregate_absolute_cfo_hz,
                glrt64_cfo_hz=item.glrt64_cfo_hz,
                model_cfo_hz=model_hz,
                phase_error_vs_model_hz=result.aggregate_absolute_cfo_hz - model_hz,
                glrt64_error_vs_model_hz=item.glrt64_cfo_hz - model_hz,
                frames=tuple(frame_details),
                phase_display_rad=display,
                phase_residual_rad=residual,
            )
        )
    return tuple(details)


def _style() -> dict[str, Any]:
    return {
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.edgecolor": "#9eb0bb",
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "text.color": INK,
        "grid.color": "#cbd7dd",
        "grid.alpha": 0.35,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#fbfcfd",
    }


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=190,
        bbox_inches="tight",
        metadata={"Software": "leo-tracker", "Creation Time": None},
    )
    plt.close(figure)


def _quantize_png(path: Path) -> None:
    """Bound the high-entropy waterfall size without changing its pixel geometry."""

    with Image.open(path) as source:
        palette = source.convert("RGB").quantize(
            colors=256,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        palette.save(path, optimize=True)


def _waterfall(
    iq: np.ndarray, sample_rate_hz: float, start_time_s: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nfft = 4_096
    usable = len(iq) // nfft * nfft
    if usable < nfft:
        raise ValueError("IQ context is too short for waterfall")
    blocks = iq[:usable].reshape(-1, nfft)
    window = np.hanning(nfft)
    spectra = np.fft.fftshift(np.fft.fft(blocks * window, axis=1), axes=1)
    power = 10 * np.log10(np.maximum(np.abs(spectra) ** 2 / np.sum(window**2), 1e-20))
    times_s = start_time_s + (np.arange(len(blocks)) + 0.5) * nfft / sample_rate_hz
    frequencies_hz = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / sample_rate_hz))
    return times_s, frequencies_hz, power


def _plot_raw_context(
    iq: np.ndarray,
    *,
    sample_rate_hz: float,
    raw_sample_start: int,
    trajectory: FrozenTrajectory,
    details: tuple[WindowDetail, ...],
    path: Path,
) -> None:
    times_s, frequencies_hz, power = _waterfall(
        iq, sample_rate_hz, raw_sample_start / sample_rate_hz
    )
    lower, upper = np.quantile(power, (0.10, 0.997))
    dense = np.linspace(times_s[0], times_s[-1], 800)
    model = np.asarray(trajectory.frequency_hz(dense))
    window_times = np.asarray([item.reference_time_s for item in details])
    glrt = np.asarray([item.glrt64_cfo_hz for item in details])
    phase = np.asarray([item.phase_slope_cfo_hz for item in details])
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 1, figsize=(15, 8.4), sharex=True, constrained_layout=True)
        image = axes[0].imshow(
            power.T,
            origin="lower",
            aspect="auto",
            extent=(times_s[0], times_s[-1], frequencies_hz[0] / 1e3, frequencies_hz[-1] / 1e3),
            cmap="magma",
            vmin=float(lower),
            vmax=float(upper),
            rasterized=True,
        )
        axes[0].plot(dense, model / 1e3, color="#63f2dd", linewidth=1.2, label="frozen trajectory")
        axes[0].scatter(
            window_times,
            np.full(len(window_times), frequencies_hz[-1] / 1e3 - 30),
            marker="v",
            s=22,
            color="white",
            edgecolor=INK,
            linewidth=0.35,
            label="16 selected windows",
        )
        axes[0].set_ylabel("baseband frequency (kHz)")
        axes[0].set_title(
            "A · Raw RX0 IQ spectrogram across the full 2.5 MHz capture band",
            loc="left",
            fontweight="bold",
        )
        axes[0].legend(loc="upper right")
        zoom_low = float(np.min(model) - 45_000)
        zoom_high = float(np.max(model) + 45_000)
        keep = (frequencies_hz >= zoom_low) & (frequencies_hz <= zoom_high)
        axes[1].imshow(
            power[:, keep].T,
            origin="lower",
            aspect="auto",
            extent=(
                times_s[0],
                times_s[-1],
                frequencies_hz[keep][0] / 1e3,
                frequencies_hz[keep][-1] / 1e3,
            ),
            cmap="magma",
            vmin=float(lower),
            vmax=float(upper),
            rasterized=True,
        )
        axes[1].plot(dense, model / 1e3, color="#63f2dd", linewidth=1.3, label="frozen trajectory")
        axes[1].scatter(window_times, glrt / 1e3, s=24, color=GREEN, marker="s", label="GLRT64")
        axes[1].scatter(
            window_times,
            phase / 1e3,
            s=34,
            facecolor="white",
            edgecolor=BLUE,
            linewidth=1.1,
            label="phase-slope aggregate",
        )
        for time_s in window_times:
            axes[1].axvline(time_s, color="white", linewidth=0.45, alpha=0.20)
        axes[1].set_xlabel("capture time (s)")
        axes[1].set_ylabel("baseband frequency (kHz)")
        axes[1].set_title(
            "B · Same raw spectrum, zoomed around the tracked carrier",
            loc="left",
            fontweight="bold",
        )
        axes[1].legend(loc="upper right", ncol=3)
        colorbar = figure.colorbar(image, ax=axes, fraction=0.018, pad=0.012)
        colorbar.set_label("FFT-bin power (dBFS-relative)")
        figure.suptitle(
            "Measured IQ context · cap-20260821T140820-470384cc9284 · stream-0/RX0",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_anchor_phase(detail: WindowDetail, path: Path) -> None:
    times_ms = (
        (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
        - np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    ) * 1e3
    chosen = np.linspace(0, len(detail.frames) - 1, 4, dtype=int)
    with plt.rc_context(_style()):
        figure = plt.figure(figsize=(15, 10.2), constrained_layout=True)
        grid = figure.add_gridspec(3, 2, height_ratios=(1.05, 1, 1))
        axis = figure.add_subplot(grid[0, :])
        frame_times_ms = (
            np.asarray(
                [
                    frame.reference_time_s - detail.selected.detection_time_s
                    for frame in detail.frames
                ]
            )
            * 1e3
        )
        phases = np.asarray([frame.phase_at_reference_rad for frame in detail.frames])
        axis.scatter(frame_times_ms, phases, s=50, color=BLUE, edgecolor="white", linewidth=0.6)
        axis.axhline(-np.pi, color=GRAY, linewidth=0.7, linestyle=":")
        axis.axhline(np.pi, color=GRAY, linewidth=0.7, linestyle=":")
        axis.set_ylim(-3.45, 3.45)
        axis.set_yticks((-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi), ("-π", "-π/2", "0", "π/2", "π"))
        axis.set_xlabel("time after nominal 33.700 s probe start (ms)")
        axis.set_ylabel("diagnostic reference phase (rad)")
        axis.set_title(
            "A · Every frame has its own wrapped phase; points are deliberately not connected",
            loc="left",
            fontweight="bold",
        )
        axis.grid(True)
        for plot_index, frame_index in enumerate(chosen):
            frame = detail.frames[frame_index]
            subaxis = figure.add_subplot(grid[1 + plot_index // 2, plot_index % 2])
            observed = detail.phase_display_rad[frame_index]
            fit = frame.phase_at_reference_rad + 2 * np.pi * frame.residual_cfo_hz * times_ms / 1e3
            subaxis.scatter(
                times_ms[::3],
                observed[::3],
                s=8,
                color=BLUE,
                alpha=0.42,
                linewidths=0,
                label="circular phase lifted around fit",
            )
            subaxis.plot(times_ms, fit, color=AMBER, linewidth=1.7, label="fitted phase slope")
            subaxis.set_title(
                f"Frame {frame_index:02d} · residual CFO {frame.residual_cfo_hz:+.1f} Hz · "
                f"RMS {frame.phase_residual_rms_rad:.2f} rad",
                loc="left",
            )
            subaxis.set_xlabel("time within frame, centered (ms)")
            subaxis.set_ylabel("locally lifted phase (rad)")
            subaxis.grid(True)
            if plot_index == 0:
                subaxis.legend(loc="best")
        figure.suptitle(
            "Anchor window: arbitrary frame phase, consistent within-frame slope\n"
            "Measured Qin pilot phase after exact wipeoff and frame-local circular lifting",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _representative_frame(detail: WindowDetail) -> int:
    supported = [frame.frame_index for frame in detail.frames if frame.coherence_margin > 0]
    candidates = supported or [frame.frame_index for frame in detail.frames]
    return min(
        candidates,
        key=lambda index: abs(detail.frames[index].reference_time_s - detail.reference_time_s),
    )


def _plot_window_phase_gallery(details: tuple[WindowDetail, ...], path: Path) -> None:
    if len(details) != 16:
        raise ValueError("the report gallery requires the preregistered 16-window selection")
    times_ms = (
        (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
        - np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    ) * 1e3
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(
            4, 4, figsize=(16, 12), sharex=True, sharey=True, constrained_layout=True
        )
        for axis, detail in zip(axes.flat, details, strict=True):
            index = _representative_frame(detail)
            frame = detail.frames[index]
            phase = detail.phase_display_rad[index] - frame.phase_at_reference_rad
            fit = 2 * np.pi * frame.residual_cfo_hz * times_ms / 1e3
            axis.scatter(times_ms[::3], phase[::3], s=5, color=BLUE, alpha=0.38, linewidths=0)
            axis.plot(times_ms, fit, color=AMBER, linewidth=1.25)
            axis.axhline(0, color=GRAY, linewidth=0.55)
            axis.set_title(
                f"{detail.selected.detection_time_s:.3f} s · Δf {frame.residual_cfo_hz:+.0f} Hz\n"
                f"margin {frame.coherence_margin:+.3f} · "
                f"RMS {frame.phase_residual_rms_rad:.2f} rad",
                loc="left",
                fontsize=9.4,
            )
            axis.grid(True)
        for axis in axes[-1, :]:
            axis.set_xlabel("centered frame time (ms)")
        for axis in axes[:, 0]:
            axis.set_ylabel("phase minus intercept (rad)")
        figure.suptitle(
            "One measured frame from every selected 20 ms window\n"
            "Blue: circular pilot phase lifted around fit · amber: independent fitted slope",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_window_alignment(
    details: tuple[WindowDetail, ...], trajectory: FrozenTrajectory, path: Path
) -> None:
    times = np.asarray([item.reference_time_s for item in details])
    phase = np.asarray([item.phase_slope_cfo_hz for item in details])
    glrt = np.asarray([item.glrt64_cfo_hz for item in details])
    model = np.asarray([item.model_cfo_hz for item in details])
    frame_times = np.asarray([frame.reference_time_s for item in details for frame in item.frames])
    frame_cfo = np.asarray([frame.absolute_cfo_hz for item in details for frame in item.frames])
    dense = np.linspace(times[0], times[-1], 600)
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(3, 1, figsize=(15, 10.5), sharex=True, constrained_layout=True)
        axes[0].scatter(
            frame_times,
            frame_cfo / 1e3,
            s=9,
            color=BLUE,
            alpha=0.22,
            linewidths=0,
            label="240 frame-local estimates",
        )
        axes[0].plot(
            dense,
            np.asarray(trajectory.frequency_hz(dense)) / 1e3,
            color=INK,
            linewidth=1.6,
            label="frozen model",
        )
        axes[0].scatter(times, glrt / 1e3, s=30, color=GREEN, marker="s", label="GLRT64/window")
        axes[0].scatter(
            times,
            phase / 1e3,
            s=48,
            facecolor="white",
            edgecolor=BLUE,
            linewidth=1.2,
            label="phase median/window",
        )
        axes[0].set_ylabel("absolute CFO (kHz)")
        axes[0].set_title(
            "A · Every frame and window follows the same four-second carrier trend",
            loc="left",
            fontweight="bold",
        )
        axes[0].legend(loc="upper right", ncol=2)
        axes[0].grid(True)
        axes[1].axhline(0, color=INK, linewidth=0.8)
        axes[1].plot(times, phase - model, color=BLUE, linewidth=1.1, alpha=0.8)
        axes[1].scatter(times, phase - model, s=40, color=BLUE, label="phase aggregate − model")
        axes[1].plot(times, glrt - model, color=GREEN, linewidth=1.0, alpha=0.75)
        axes[1].scatter(times, glrt - model, s=30, color=GREEN, marker="s", label="GLRT64 − model")
        axes[1].set_ylabel("window residual (Hz)")
        axes[1].set_title(
            "B · Window-level residuals: phase adds local refinement, not a uniform accuracy win",
            loc="left",
            fontweight="bold",
        )
        axes[1].legend(loc="best", ncol=2)
        axes[1].grid(True)
        positions = times
        residual_groups = [
            np.asarray([frame.error_vs_model_hz for frame in item.frames]) for item in details
        ]
        widths = np.full(len(times), 0.055)
        boxes = axes[2].boxplot(
            residual_groups,
            positions=positions,
            widths=widths,
            manage_ticks=False,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": INK, "linewidth": 1.1},
            whiskerprops={"color": GRAY},
            capprops={"color": GRAY},
        )
        for patch in boxes["boxes"]:
            patch.set_facecolor("#b9d9ea")
            patch.set_edgecolor(BLUE)
            patch.set_alpha(0.75)
        axes[2].axhline(0, color=INK, linewidth=0.8)
        axes[2].scatter(
            times, phase - model, s=32, color=AMBER, zorder=4, label="supported-frame median"
        )
        axes[2].set_xlabel("capture time (s)")
        axes[2].set_ylabel("per-frame residual (Hz)")
        axes[2].set_title(
            "C · Each box is one 15-frame window; amber is the control-supported aggregate",
            loc="left",
            fontweight="bold",
        )
        axes[2].legend(loc="best")
        axes[2].grid(True)
        figure.suptitle(
            "Window-by-window CFO alignment against the frozen trajectory",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _ecdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ordered = np.sort(values)
    return ordered, np.arange(1, len(ordered) + 1) / len(ordered)


def _plot_residual_diagnostics(details: tuple[WindowDetail, ...], path: Path) -> None:
    phase_error = np.asarray([item.phase_error_vs_model_hz for item in details])
    glrt_error = np.asarray([item.glrt64_error_vs_model_hz for item in details])
    frames = tuple(frame for item in details for frame in item.frames)
    exact = np.asarray([frame.exact_coherence for frame in frames])
    control = np.asarray([frame.control_coherence for frame in frames])
    residual = np.concatenate([item.phase_residual_rad for item in details], axis=0)
    times_ms = (
        (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
        - np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    ) * 1e3
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 11), constrained_layout=True)
        for values, color, label in (
            (phase_error, BLUE, "phase aggregate − model"),
            (glrt_error, GREEN, "GLRT64 − model"),
        ):
            x, y = _ecdf(values)
            median = float(np.median(values))
            mad = float(np.median(np.abs(values - median)))
            axes[0, 0].step(
                x, y, where="post", color=color, linewidth=2, label=f"{label} (MAD {mad:.0f} Hz)"
            )
        axes[0, 0].axvline(0, color=INK, linewidth=0.8)
        axes[0, 0].set_xlabel("window residual vs frozen model (Hz)")
        axes[0, 0].set_ylabel("empirical cumulative fraction")
        axes[0, 0].set_title("A · Window residual distributions", loc="left", fontweight="bold")
        axes[0, 0].legend(loc="best")
        axes[0, 0].grid(True)
        bounds = np.asarray([phase_error, glrt_error])
        low = float(np.min(bounds) - 80)
        high = float(np.max(bounds) + 80)
        axes[0, 1].plot(
            [low, high],
            [low, high],
            color=INK,
            linewidth=0.8,
            linestyle="--",
            label="no refinement",
        )
        scatter = axes[0, 1].scatter(
            glrt_error,
            phase_error,
            c=[item.reference_time_s for item in details],
            cmap="viridis",
            s=58,
            edgecolor="white",
            linewidth=0.55,
        )
        axes[0, 1].axhline(0, color=GRAY, linewidth=0.6)
        axes[0, 1].axvline(0, color=GRAY, linewidth=0.6)
        axes[0, 1].set_xlim(low, high)
        axes[0, 1].set_ylim(low, high)
        axes[0, 1].set_aspect("equal", adjustable="box")
        axes[0, 1].set_xlabel("GLRT64 residual (Hz)")
        axes[0, 1].set_ylabel("phase aggregate residual (Hz)")
        axes[0, 1].set_title(
            "B · What the phase refinement changes in each window", loc="left", fontweight="bold"
        )
        axes[0, 1].legend(loc="upper left")
        figure.colorbar(scatter, ax=axes[0, 1], label="capture time (s)", fraction=0.046)
        positive = exact > control
        axes[1, 0].scatter(
            control[positive],
            exact[positive],
            s=14,
            color=BLUE,
            alpha=0.45,
            linewidths=0,
            label=f"exact wins ({np.count_nonzero(positive)})",
        )
        axes[1, 0].scatter(
            control[~positive],
            exact[~positive],
            s=34,
            color=RED,
            marker="x",
            label=f"control wins/ties ({np.count_nonzero(~positive)})",
        )
        ceiling = float(max(np.max(exact), np.max(control)) * 1.05)
        axes[1, 0].plot([0, ceiling], [0, ceiling], color=INK, linewidth=0.9, linestyle="--")
        axes[1, 0].set_xlim(0, ceiling)
        axes[1, 0].set_ylim(0, ceiling)
        axes[1, 0].set_aspect("equal", adjustable="box")
        axes[1, 0].set_xlabel("rolled-control coherence")
        axes[1, 0].set_ylabel("exact Qin coherence")
        axes[1, 0].set_title(
            "C · 237/240 frames lie above the exact=control line", loc="left", fontweight="bold"
        )
        axes[1, 0].legend(loc="lower right")
        axes[1, 0].grid(True)
        image = axes[1, 1].imshow(
            residual,
            origin="upper",
            aspect="auto",
            extent=(times_ms[0], times_ms[-1], len(frames), 0),
            cmap="coolwarm",
            vmin=-np.pi,
            vmax=np.pi,
            interpolation="nearest",
            rasterized=True,
        )
        for boundary in range(15, len(frames), 15):
            axes[1, 1].axhline(boundary, color="black", linewidth=0.35, alpha=0.35)
        axes[1, 1].set_xlabel("centered time within frame (ms)")
        axes[1, 1].set_ylabel("frame row (16 windows x 15 frames)")
        axes[1, 1].set_title(
            "D · Circular phase after removing each independently fitted slope",
            loc="left",
            fontweight="bold",
        )
        figure.colorbar(image, ax=axes[1, 1], label="phase residual (rad)", fraction=0.046)
        figure.suptitle(
            "Residual and negative-control diagnostics from measured pilot data",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _serializable_frame(frame: FrameDetail) -> dict[str, Any]:
    return {name: getattr(frame, name) for name in frame.__dataclass_fields__}


def _serializable_window(item: WindowDetail) -> dict[str, Any]:
    selected = {name: getattr(item.selected, name) for name in item.selected.__dataclass_fields__}
    return {
        "selection": selected,
        "reference_time_s": item.reference_time_s,
        "phase_slope_cfo_hz": item.phase_slope_cfo_hz,
        "glrt64_cfo_hz": item.glrt64_cfo_hz,
        "model_cfo_hz": item.model_cfo_hz,
        "phase_error_vs_model_hz": item.phase_error_vs_model_hz,
        "glrt64_error_vs_model_hz": item.glrt64_error_vs_model_hz,
        "frames": [_serializable_frame(frame) for frame in item.frames],
    }


def _write_evidence(
    path: Path,
    *,
    args: argparse.Namespace,
    trajectory: FrozenTrajectory,
    accepted_count: int,
    details: tuple[WindowDetail, ...],
    figures: tuple[Path, ...],
) -> None:
    frames = tuple(frame for item in details for frame in item.frames)
    phase_error = np.asarray([item.phase_error_vs_model_hz for item in details])
    glrt_error = np.asarray([item.glrt64_error_vs_model_hz for item in details])
    phase_median = float(np.median(phase_error))
    glrt_median = float(np.median(glrt_error))
    document = {
        "schema_version": 1,
        "algorithm": "edge-pilot-phase-slope-report-figures-v1",
        "candidate_only": True,
        "payload_decoded": False,
        "input": {
            "session_id": args.session_id,
            "stream_id": args.stream,
            "receiver_id": args.receiver,
            "edge": args.edge,
            "analysis_scope": ANALYSIS_SCOPE,
            "trajectory_id": trajectory.trajectory_id,
            "trajectory_branch_id": trajectory.branch_id,
        },
        "selection": {
            "start_s": args.start_s,
            "end_s": args.end_s,
            "minimum_glrt64_margin": args.minimum_glrt64_margin,
            "maximum_model_error_hz": args.maximum_model_error_hz,
            "accepted_stride": args.accepted_stride,
            "accepted_before_stride": accepted_count,
            "selected_window_count": len(details),
        },
        "summary": {
            "complete_frame_count": len(frames),
            "positive_coherence_margin_frame_count": sum(
                frame.coherence_margin > 0 for frame in frames
            ),
            "phase_error_vs_model_hz": {
                "median": phase_median,
                "mad": float(np.median(np.abs(phase_error - phase_median))),
                "rms": float(np.sqrt(np.mean(phase_error**2))),
            },
            "glrt64_error_vs_model_hz": {
                "median": glrt_median,
                "mad": float(np.median(np.abs(glrt_error - glrt_median))),
                "rms": float(np.sqrt(np.mean(glrt_error**2))),
            },
        },
        "windows": [_serializable_window(item) for item in details],
        "figures": [
            {"path": item.name, "sha256": _sha256(item), "bytes": item.stat().st_size}
            for item in figures
        ],
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _arguments()
    if (
        not math.isfinite(args.start_s)
        or not math.isfinite(args.end_s)
        or args.end_s <= args.start_s
    ):
        raise ValueError("report interval must be finite and increasing")
    scan = _load_json(args.analysis_root / "standard.pilot-scan.v3.json")
    trajectory = _trajectory(
        _load_json(args.analysis_root / "standard.final-trajectory-bank.v2.json")
    )
    all_accepted = _select_windows(
        scan,
        trajectory,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
        accepted_stride=1,
    )
    selected = all_accepted[:: args.accepted_stride]
    selected = tuple(
        SelectedWindow(
            index=index,
            detection_time_s=item.detection_time_s,
            probe_sample_start=item.probe_sample_start,
            aligned_sample_start=item.aligned_sample_start,
            candidate_rank=item.candidate_rank,
            local_epoch_sample=item.local_epoch_sample,
            acquired_cfo_hz=item.acquired_cfo_hz,
            glrt64_cfo_hz=item.glrt64_cfo_hz,
            glrt64_margin=item.glrt64_margin,
            selection_model_error_hz=item.selection_model_error_hz,
        )
        for index, item in enumerate(selected)
    )
    if not selected:
        raise ValueError("selection produced no report windows")
    probe_samples = int(scan["probe_samples"])
    context_start_s = min(args.start_s - 0.05, selected[0].aligned_sample_start / 2_500_000)
    context_end_s = max(
        args.end_s + 0.05,
        (selected[-1].aligned_sample_start + probe_samples) / 2_500_000,
    )
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(args.session_id)
        reader = store.reader(bundle, args.stream, verify=True)
        sample_rate_hz = reader.sample_rate_hz
        if sample_rate_hz != 2_500_000:
            raise ValueError(f"report expects 2.5 MS/s, found {sample_rate_hz}")
        raw_start = round(context_start_s * sample_rate_hz)
        raw_stop = round(context_end_s * sample_rate_hz)
        raw = reader.read(
            raw_start,
            raw_stop - raw_start,
            receiver_ids=(args.receiver,),
        )
        iq = _complex_receiver(raw)
    finally:
        if store is not None:
            store.close()
    details = _analyze_windows(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        probe_samples=probe_samples,
        edge=StarlinkEdge(args.edge),
        selected=selected,
        trajectory=trajectory,
    )
    output = args.output_root
    figures = (
        output / "raw-iq-context.png",
        output / "anchor-phase-evolution.png",
        output / "window-phase-gallery.png",
        output / "window-alignment.png",
        output / "residual-diagnostics.png",
    )
    _plot_raw_context(
        iq,
        sample_rate_hz=sample_rate_hz,
        raw_sample_start=raw_start,
        trajectory=trajectory,
        details=details,
        path=figures[0],
    )
    _quantize_png(figures[0])
    _plot_anchor_phase(details[0], figures[1])
    _plot_window_phase_gallery(details, figures[2])
    _plot_window_alignment(details, trajectory, figures[3])
    _plot_residual_diagnostics(details, figures[4])
    _write_evidence(
        output / "detailed-results.json",
        args=args,
        trajectory=trajectory,
        accepted_count=len(all_accepted),
        details=details,
        figures=figures,
    )
    print(
        f"rendered {len(figures)} measured-data figures from {len(details)} windows and "
        f"{sum(len(item.frames) for item in details)} frames"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
