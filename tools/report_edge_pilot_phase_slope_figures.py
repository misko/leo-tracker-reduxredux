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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image

from leo.analysis.qam import (
    PilotPhaseDopplerTrackingConfig,
    PilotPhaseSlopeFrame,
    analyze_locked_pilot_phase_doppler_tracking,
    analyze_pilot_phase_doppler_tracking,
    analyze_pilot_phase_slope,
)
from leo.analysis.qam.pilot import (
    _complete_frame_starts,
    _fit_phase_slope_frame,
    _KnownPilotDemodulator,
)
from leo.analysis.starlink import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
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

    def doppler_rate_hz_s(self, time_s: float | np.ndarray) -> float | np.ndarray:
        values = np.polyval(
            np.polyder(np.asarray(self.coefficients_hz)),
            np.asarray(time_s) - self.reference_time_s,
        )
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
    tracked_phase_rad: float | None
    tracked_absolute_cfo_hz: float | None
    tracked_doppler_rate_hz_s: float | None
    tracked_frequency_sigma_hz: float | None
    tracked_rate_sigma_hz_s: float | None
    phase_measurement_rad: float | None
    phase_innovation_rad: float | None
    channel_similarity: float | None
    phase_segment_id: int | None
    phase_update_applied: bool
    frequency_update_applied: bool
    phase_reset_detected: bool


@dataclass(frozen=True, slots=True)
class WindowDetail:
    selected: SelectedWindow
    reference_time_s: float
    phase_slope_cfo_hz: float
    glrt64_cfo_hz: float
    model_cfo_hz: float
    phase_error_vs_model_hz: float
    glrt64_error_vs_model_hz: float
    phase_tracking_cfo_hz: float
    phase_tracking_error_vs_model_hz: float
    phase_tracking_reset_count: int
    phase_tracking_update_count: int
    frames: tuple[FrameDetail, ...]
    phase_display_rad: np.ndarray = field(repr=False)
    phase_residual_rad: np.ndarray = field(repr=False)


@dataclass(frozen=True, slots=True)
class DenseTrackingFrame:
    frame_start_sample: int
    reference_time_s: float
    source_window_index: int
    glrt64_cfo_hz: float
    model_cfo_hz: float
    absolute_cfo_measurement_hz: float
    tracked_absolute_cfo_hz: float
    tracked_doppler_rate_hz_s: float
    model_doppler_rate_hz_s: float
    residual_cfo_measurement_hz: float
    frequency_uncertainty_hz: float
    tracked_frequency_sigma_hz: float
    tracked_rate_sigma_hz_s: float
    phase_measurement_rad: float
    tracked_phase_rad: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    phase_innovation_rad: float
    channel_similarity: float
    phase_segment_id: int
    phase_update_applied: bool
    frequency_update_applied: bool
    phase_reset_detected: bool


@dataclass(frozen=True, slots=True)
class DenseTrackingDetail:
    source_window_count: int
    requested_frame_count: int
    phase_segment_count: int
    phase_reset_count: int
    phase_update_count: int
    frequency_update_count: int
    processing_elapsed_s: float
    frames: tuple[DenseTrackingFrame, ...]


@dataclass(frozen=True, slots=True)
class PhaseLockInterval:
    start_time_s: float
    end_time_s: float
    observed_span_s: float
    frame_count: int
    start_interval_s: float | None
    crosses_sampling_gap: bool | None
    median_exact_coherence: float
    median_coherence_margin: float
    median_frequency_uncertainty_hz: float
    raw_stack_efficiency: float | None
    tracked_stack_efficiency: float | None
    self_aligned_stack_efficiency: float | None


@dataclass(frozen=True, slots=True)
class OfflinePhaseContinuityFrame:
    frame_start_sample: int
    reference_time_s: float
    retained_by_dense_pass: bool
    model_cfo_hz: float
    measured_cfo_hz: float
    frequency_fit_cfo_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float
    within_frame_phase_residual_rms_rad: float
    fractional_delay_samples: float
    timing_corrected_channel_similarity: float
    phase_measurement_rad: float
    cubic_batch_phase_residual_rad: float
    flexible_batch_phase_residual_rad: float
    pi_ambiguity_batch_phase_residual_rad: float
    pi_ambiguity_state: int
    adjacent_phase_innovation_rad: float | None
    phase_implied_frequency_error_hz: float | None
    pi_corrected_phase_implied_frequency_error_hz: float | None


@dataclass(frozen=True, slots=True)
class OfflinePhaseContinuityDetail:
    start_s: float
    end_s: float
    inferred_frame_count: int
    retained_frame_count: int
    newly_evaluated_frame_count: int
    quality_frame_count: int
    frequency_fit_rms_hz: float
    median_frequency_uncertainty_hz: float
    median_within_frame_phase_residual_rms_rad: float
    median_abs_fractional_delay_samples: float
    median_timing_corrected_channel_similarity: float
    adjacent_phase_innovation_rms_rad: float
    median_abs_phase_implied_frequency_error_hz: float
    cubic_batch_phase_residual_rms_rad: float
    flexible_batch_phase_residual_rms_rad: float
    pi_ambiguity_batch_phase_residual_rms_rad: float
    pi_centered_adjacent_phase_innovation_rms_rad: float
    pi_ambiguity_frequency_correction_hz: float
    pi_ambiguity_state_transition_count: int
    even_to_odd_heldout_phase_residual_rms_rad: float
    even_to_odd_heldout_stack_efficiency: float
    odd_to_even_heldout_phase_residual_rms_rad: float
    odd_to_even_heldout_stack_efficiency: float
    heldout_pi_state_agreement: float
    raw_stack_efficiency: float
    frequency_only_stack_efficiency: float
    cubic_batch_stack_efficiency: float
    flexible_batch_stack_efficiency: float
    pi_ambiguity_batch_stack_efficiency: float
    per_frame_nuisance_stack_efficiency: float
    causal_evaluated_frame_count: int
    causal_phase_update_count: int
    causal_phase_reset_count: int
    causal_longest_strict_run_frames: int
    frames: tuple[OfflinePhaseContinuityFrame, ...]


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
        tracking = analyze_pilot_phase_doppler_tracking(
            samples,
            sample_rate_hz,
            epoch_sample=0,
            absolute_cfo_hz=item.glrt64_cfo_hz,
            edge=edge,
        )
        if result.aggregate_absolute_cfo_hz is None or not result.frames:
            raise ValueError(f"phase-slope estimator returned no result for window {item.index}")
        if not tracking.frames:
            raise ValueError(f"phase/Doppler tracker returned no result for window {item.index}")
        tracked_by_index = {frame.frame_index: frame for frame in tracking.frames}
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
            tracked = tracked_by_index.get(frame.frame_index)
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
                    tracked_phase_rad=(tracked.tracked_phase_rad if tracked else None),
                    tracked_absolute_cfo_hz=(tracked.tracked_absolute_cfo_hz if tracked else None),
                    tracked_doppler_rate_hz_s=(
                        tracked.tracked_doppler_rate_hz_s if tracked else None
                    ),
                    tracked_frequency_sigma_hz=(tracked.frequency_sigma_hz if tracked else None),
                    tracked_rate_sigma_hz_s=(tracked.doppler_rate_sigma_hz_s if tracked else None),
                    phase_measurement_rad=(tracked.phase_measurement_rad if tracked else None),
                    phase_innovation_rad=(tracked.phase_innovation_rad if tracked else None),
                    channel_similarity=(tracked.channel_similarity if tracked else None),
                    phase_segment_id=(tracked.phase_segment_id if tracked else None),
                    phase_update_applied=(tracked.phase_update_applied if tracked else False),
                    frequency_update_applied=(
                        tracked.frequency_update_applied if tracked else False
                    ),
                    phase_reset_detected=(tracked.phase_reset_detected if tracked else False),
                )
            )
        supported_tracking = [
            frame.tracked_absolute_cfo_hz
            for frame in frame_details
            if frame.frequency_update_applied and frame.tracked_absolute_cfo_hz is not None
        ]
        if not supported_tracking:
            supported_tracking = [
                frame.tracked_absolute_cfo_hz
                for frame in frame_details
                if frame.tracked_absolute_cfo_hz is not None
            ]
        if not supported_tracking:
            raise ValueError(
                f"phase/Doppler tracker has no comparable frames in window {item.index}"
            )
        tracking_cfo_hz = float(np.median(supported_tracking))
        details.append(
            WindowDetail(
                selected=item,
                reference_time_s=reference_time_s,
                phase_slope_cfo_hz=result.aggregate_absolute_cfo_hz,
                glrt64_cfo_hz=item.glrt64_cfo_hz,
                model_cfo_hz=model_hz,
                phase_error_vs_model_hz=result.aggregate_absolute_cfo_hz - model_hz,
                glrt64_error_vs_model_hz=item.glrt64_cfo_hz - model_hz,
                phase_tracking_cfo_hz=tracking_cfo_hz,
                phase_tracking_error_vs_model_hz=tracking_cfo_hz - model_hz,
                phase_tracking_reset_count=tracking.phase_reset_count,
                phase_tracking_update_count=tracking.phase_update_count,
                frames=tuple(frame_details),
                phase_display_rad=display,
                phase_residual_rad=residual,
            )
        )
    return tuple(details)


def _analyze_dense_locked_frames(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    probe_samples: int,
    edge: StarlinkEdge,
    locked_windows: tuple[SelectedWindow, ...],
    trajectory: FrozenTrajectory,
    tracking_config: PilotPhaseDopplerTrackingConfig | None = None,
) -> DenseTrackingDetail:
    """Carry one carrier state through every frame exposed by existing pilot locks."""

    local_starts = _complete_frame_starts(probe_samples, sample_rate_hz, 0)
    source_by_start: dict[int, SelectedWindow] = {}
    for window in locked_windows:
        relative_window = window.aligned_sample_start - raw_sample_start
        for local_start in local_starts:
            frame_start = relative_window + local_start
            previous = source_by_start.get(frame_start)
            if previous is None or window.glrt64_margin > previous.glrt64_margin:
                source_by_start[frame_start] = window
    starts = tuple(sorted(source_by_start))
    started = time.perf_counter()
    result = analyze_locked_pilot_phase_doppler_tracking(
        iq,
        sample_rate_hz,
        frame_starts=starts,
        initial_absolute_cfo_hz=locked_windows[0].glrt64_cfo_hz,
        edge=edge,
        config=tracking_config,
    )
    processing_elapsed_s = time.perf_counter() - started
    if not result.frames:
        raise ValueError("dense locked-frame phase/Doppler tracker returned no frames")
    frames = []
    for frame in result.frames:
        time_s = (raw_sample_start + frame.reference_sample) / sample_rate_hz
        source = source_by_start[frame.frame_start_sample]
        frames.append(
            DenseTrackingFrame(
                frame_start_sample=frame.frame_start_sample,
                reference_time_s=time_s,
                source_window_index=source.index,
                glrt64_cfo_hz=source.glrt64_cfo_hz,
                model_cfo_hz=float(trajectory.frequency_hz(time_s)),
                absolute_cfo_measurement_hz=frame.absolute_cfo_measurement_hz,
                tracked_absolute_cfo_hz=frame.tracked_absolute_cfo_hz,
                tracked_doppler_rate_hz_s=frame.tracked_doppler_rate_hz_s,
                model_doppler_rate_hz_s=float(trajectory.doppler_rate_hz_s(time_s)),
                residual_cfo_measurement_hz=frame.residual_cfo_measurement_hz,
                frequency_uncertainty_hz=frame.frequency_uncertainty_hz,
                tracked_frequency_sigma_hz=frame.frequency_sigma_hz,
                tracked_rate_sigma_hz_s=frame.doppler_rate_sigma_hz_s,
                phase_measurement_rad=frame.phase_measurement_rad,
                tracked_phase_rad=frame.tracked_phase_rad,
                exact_coherence=frame.exact_coherence,
                control_coherence=frame.control_coherence,
                coherence_margin=frame.coherence_margin,
                phase_innovation_rad=frame.phase_innovation_rad,
                channel_similarity=frame.channel_similarity,
                phase_segment_id=frame.phase_segment_id,
                phase_update_applied=frame.phase_update_applied,
                frequency_update_applied=frame.frequency_update_applied,
                phase_reset_detected=frame.phase_reset_detected,
            )
        )
    return DenseTrackingDetail(
        len(locked_windows),
        len(starts),
        result.phase_segment_count,
        result.phase_reset_count,
        result.phase_update_count,
        result.frequency_update_count,
        processing_elapsed_s,
        tuple(frames),
    )


def _robust_polynomial_coefficients(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    *,
    degree: int,
) -> tuple[np.ndarray, float]:
    """Return increasing-order Huber-IRLS coefficients on a scaled abscissa."""

    values = np.asarray(x, dtype=float)
    observations = np.asarray(y, dtype=float)
    base_weights = np.asarray(weights, dtype=float)
    if not (values.ndim == observations.ndim == base_weights.ndim == 1):
        raise ValueError("robust polynomial inputs must be one dimensional")
    if not (len(values) == len(observations) == len(base_weights)):
        raise ValueError("robust polynomial input lengths differ")
    if degree < 0 or np.count_nonzero(base_weights > 0) <= degree:
        raise ValueError("insufficient positive-weight observations for polynomial degree")
    scale = max(float(np.max(np.abs(values))), np.finfo(float).eps)
    design = np.column_stack([(values / scale) ** order for order in range(degree + 1)])
    fit_weights = np.maximum(base_weights, 0.0)
    coefficients = np.zeros(degree + 1)
    for _ in range(12):
        root = np.sqrt(fit_weights)
        coefficients = np.linalg.lstsq(
            design * root[:, None],
            observations * root,
            rcond=None,
        )[0]
        residual = observations - design @ coefficients
        supported = residual[base_weights > 0]
        center = float(np.median(supported))
        robust_scale = 1.4826 * float(np.median(np.abs(supported - center))) + 1e-9
        huber = np.minimum(
            1.0,
            1.5 * robust_scale / np.maximum(np.abs(residual - center), 1e-12),
        )
        fit_weights = np.maximum(base_weights, 0.0) * huber
    return coefficients, scale


def _evaluate_scaled_polynomial(
    x: np.ndarray,
    coefficients: np.ndarray,
    scale: float,
) -> np.ndarray:
    normalized = np.asarray(x, dtype=float) / scale
    return np.polynomial.polynomial.polyval(normalized, coefficients)


def _fit_wrapped_polynomial(
    x: np.ndarray,
    angles_rad: np.ndarray,
    weights: np.ndarray,
    *,
    degree: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit a noncausal smooth phase curve while resolving integer cycle branches."""

    angles = np.asarray(angles_rad, dtype=float)
    lifted = np.unwrap(angles)
    model = np.zeros_like(angles)
    for _ in range(12):
        coefficients, scale = _robust_polynomial_coefficients(
            x,
            lifted,
            weights,
            degree=degree,
        )
        model = _evaluate_scaled_polynomial(x, coefficients, scale)
        lifted = model + np.angle(np.exp(1j * (angles - model)))
    residual = np.angle(np.exp(1j * (angles - model)))
    return model, residual


def _separate_channel_delay_and_phase(
    channel_vectors: np.ndarray,
    weights: np.ndarray,
    *,
    sample_rate_hz: float,
    edge: StarlinkEdge,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Separate a scalar carrier phase from a fractional-delay channel ramp.

    A nuisance carrier phase and a nuisance fractional-sample delay are estimated
    independently for every frame.  They are used only to expose the phase
    observable; treating the nuisance phase as a correction is the per-frame
    oracle ceiling, not evidence of cross-frame lock.
    """

    vectors = np.asarray(channel_vectors, dtype=np.complex128)
    frame_weights = np.asarray(weights, dtype=float)
    if vectors.ndim != 2 or vectors.shape[1] != 8:
        raise ValueError("channel vectors must have shape (frames, 8)")
    if frame_weights.shape != (len(vectors),):
        raise ValueError("channel-vector weights do not match frame count")
    delay_grid = np.linspace(-0.75, 0.75, 301)
    frequencies_hz = edge_frequencies_hz(edge)
    ramps = np.exp(-2j * np.pi * delay_grid[:, None] * frequencies_hz[None, :] / sample_rate_hz)
    channel = vectors[int(np.argmax(frame_weights))].copy()
    channel /= max(float(np.linalg.norm(channel)), np.finfo(float).tiny)
    delays = np.zeros(len(vectors))
    phases = np.zeros(len(vectors))
    similarities = np.zeros(len(vectors))
    corrected = vectors.copy()
    for _ in range(24):
        aligned = []
        for index, vector in enumerate(vectors):
            candidates = ramps * vector[None, :]
            projections = candidates @ np.conj(channel)
            best = int(np.argmax(np.abs(projections)))
            corrected[index] = candidates[best]
            delays[index] = delay_grid[best]
            phases[index] = float(np.angle(projections[best]))
            similarities[index] = float(abs(projections[best]))
            aligned.append(corrected[index] * np.exp(-1j * phases[index]))
        channel = np.sum(frame_weights[:, None] * np.asarray(aligned), axis=0)
        channel /= max(float(np.linalg.norm(channel)), np.finfo(float).tiny)
    return delays, phases, similarities, corrected


def _weighted_stack_efficiency(vectors: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(vectors, dtype=np.complex128)
    frame_weights = np.asarray(weights, dtype=float)
    total = float(np.sum(frame_weights))
    if values.ndim != 2 or frame_weights.shape != (len(values),) or total <= 0:
        raise ValueError("weighted stack requires positive matching frame weights")
    return float(np.linalg.norm(np.sum(frame_weights[:, None] * values, axis=0)) / total)


def _heldout_pi_phase_validation(
    pilot_cube: np.ndarray,
    *,
    expected: np.ndarray,
    control: np.ndarray,
    symbol_times_s: np.ndarray,
    reference_times_s: np.ndarray,
    center_cfo_hz: float,
    sample_rate_hz: float,
    edge: StarlinkEdge,
) -> tuple[float, float, float, float, float]:
    """Fit each interleaved pilot half and predict the disjoint other half."""

    centered_times_s = reference_times_s - float(np.mean(reference_times_s))

    def extract(
        selector: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        fits = tuple(
            _fit_phase_slope_frame(
                pilots[selector] * np.conj(expected[selector]),
                pilots[selector] * np.conj(control[selector]),
                symbol_times_s[selector],
                maximum_residual_cfo_hz=2_000.0,
            )
            for pilots in pilot_cube
        )
        frequency_hz = center_cfo_hz + np.asarray([fit.residual_cfo_hz for fit in fits])
        uncertainty_hz = np.asarray([fit.frequency_uncertainty_hz for fit in fits])
        exact = np.asarray([fit.exact_coherence for fit in fits])
        margin = exact - np.asarray([fit.control_coherence for fit in fits])
        quality = (exact >= 0.02) & (margin >= 0)
        channels = np.asarray(
            [
                fit.channel_vector
                / max(float(np.linalg.norm(fit.channel_vector)), np.finfo(float).tiny)
                for fit in fits
            ]
        )
        weights = np.where(quality, exact, 0.0)
        _delay, phase, _similarity, corrected = _separate_channel_delay_and_phase(
            channels,
            weights,
            sample_rate_hz=sample_rate_hz,
            edge=edge,
        )
        return frequency_hz, uncertainty_hz, exact, quality, phase, corrected

    even = extract(np.arange(0, 300, 2))
    odd = extract(np.arange(1, 300, 2))

    def validate(
        train: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
        test: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    ) -> tuple[float, float, float]:
        frequency_hz, uncertainty_hz, exact, quality, phase, _corrected = train
        _test_frequency, _test_uncertainty, test_exact, test_quality, test_phase, test_corrected = (
            test
        )
        frequency_weights = np.where(
            quality,
            exact / np.maximum(uncertainty_hz, 5.0) ** 2,
            0.0,
        )
        coefficients, scale = _robust_polynomial_coefficients(
            centered_times_s,
            frequency_hz,
            frequency_weights,
            degree=2,
        )
        c0, c1, c2 = coefficients
        normalized_time = centered_times_s / scale
        integrated_phase = (
            2
            * np.pi
            * scale
            * (
                (c0 - center_cfo_hz) * normalized_time
                + 0.5 * c1 * normalized_time**2
                + (c2 / 3) * normalized_time**3
            )
        )
        train_after_frequency = np.angle(np.exp(1j * (phase - integrated_phase)))
        doubled_model, _doubled_residual = _fit_wrapped_polynomial(
            centered_times_s,
            np.angle(np.exp(2j * train_after_frequency)),
            np.where(quality, exact, 0.0),
            degree=3,
        )
        pi_model = 0.5 * doubled_model
        state = np.rint((train_after_frequency - pi_model) / np.pi).astype(int)
        predicted_phase = integrated_phase + pi_model + np.pi * state
        test_weights = np.where(test_quality, test_exact, 0.0)
        test_delta = np.angle(np.exp(1j * (test_phase - predicted_phase)))
        global_offset = float(np.angle(np.sum(test_weights * np.exp(1j * test_delta))))
        heldout_residual = np.angle(np.exp(1j * (test_delta - global_offset)))
        heldout_rms = float(np.sqrt(np.mean(heldout_residual[test_quality] ** 2)))
        heldout_efficiency = _weighted_stack_efficiency(
            test_corrected * np.exp(-1j * (predicted_phase + global_offset))[:, None],
            test_weights,
        )

        test_after_model = np.angle(np.exp(1j * (test_phase - integrated_phase - pi_model)))
        test_pi_offset = 0.5 * float(np.angle(np.sum(test_weights * np.exp(2j * test_after_model))))
        test_state = np.mod(
            np.rint((test_after_model - test_pi_offset) / np.pi).astype(int),
            2,
        )
        train_state = np.mod(state, 2)
        state_agreement = max(
            float(np.mean(test_state == train_state)),
            float(np.mean((1 - test_state) == train_state)),
        )
        return heldout_rms, heldout_efficiency, state_agreement

    even_to_odd = validate(even, odd)
    odd_to_even = validate(odd, even)
    return (
        even_to_odd[0],
        even_to_odd[1],
        odd_to_even[0],
        odd_to_even[1],
        min(even_to_odd[2], odd_to_even[2]),
    )


def _offline_phase_continuity_audit(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    trajectory: FrozenTrajectory,
    dense_tracking: DenseTrackingDetail,
    start_s: float = 34.73,
    end_s: float = 34.81,
) -> OfflinePhaseContinuityDetail:
    """Run an optimistic noncausal phase audit on a complete inferred frame lattice."""

    retained = tuple(
        frame for frame in dense_tracking.frames if start_s <= frame.reference_time_s < end_s
    )
    if not retained:
        raise ValueError("offline phase interval contains no retained frame anchor")
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    anchor = retained[0]
    first_step = math.ceil((start_s - anchor.reference_time_s) * 750 - 1e-9)
    last_step = math.floor((end_s - anchor.reference_time_s) * 750 - 1e-9)
    steps = np.arange(first_step, last_step + 1)
    starts = np.rint(anchor.frame_start_sample + steps * sample_rate_hz / 750).astype(int)
    reference_times_s = (
        raw_sample_start + starts + reference_offset_s * sample_rate_hz
    ) / sample_rate_hz
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if starts[0] < 0 or starts[-1] + frame_content > len(iq):
        raise ValueError("offline phase lattice exceeds verified IQ interval")

    retained_starts = np.asarray([frame.frame_start_sample for frame in retained], dtype=int)
    retained_match = np.asarray(
        [np.min(np.abs(retained_starts - start)) <= 1 for start in starts],
        dtype=bool,
    )
    center_time_s = float(np.mean(reference_times_s))
    center_cfo_hz = float(trajectory.frequency_hz(center_time_s))
    expected = qin_edge_pilot_symbols(edge)
    control = qin_edge_pilot_symbols(edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    symbol_times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    symbol_times_s -= np.mean(symbol_times_s)
    demodulator = _KnownPilotDemodulator(iq, sample_rate_hz, edge, center_cfo_hz)
    fits = []
    pilot_frames = []
    for start in starts:
        pilots = demodulator.frame(int(start))
        pilot_frames.append(pilots)
        fits.append(
            _fit_phase_slope_frame(
                pilots * np.conj(expected),
                pilots * np.conj(control),
                symbol_times_s,
                maximum_residual_cfo_hz=2_000.0,
            )
        )
    heldout_validation = _heldout_pi_phase_validation(
        np.asarray(pilot_frames),
        expected=expected,
        control=control,
        symbol_times_s=symbol_times_s,
        reference_times_s=reference_times_s,
        center_cfo_hz=center_cfo_hz,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
    )
    exact = np.asarray([fit.exact_coherence for fit in fits])
    control_values = np.asarray([fit.control_coherence for fit in fits])
    margins = exact - control_values
    uncertainty_hz = np.asarray([fit.frequency_uncertainty_hz for fit in fits])
    measured_cfo_hz = center_cfo_hz + np.asarray([fit.residual_cfo_hz for fit in fits])
    quality = (
        (exact >= 0.02)
        & (margins >= 0)
        & np.isfinite(measured_cfo_hz)
        & np.isfinite(uncertainty_hz)
    )
    if np.count_nonzero(quality) < 10:
        raise ValueError("offline phase interval has insufficient supported pilot frames")
    channels = np.asarray(
        [
            np.asarray(fit.channel_vector)
            / max(float(np.linalg.norm(fit.channel_vector)), np.finfo(float).tiny)
            for fit in fits
        ]
    )
    centered_times_s = reference_times_s - center_time_s
    frequency_weights = np.where(
        quality,
        exact / np.maximum(uncertainty_hz, 5.0) ** 2,
        0.0,
    )
    frequency_coefficients, frequency_scale = _robust_polynomial_coefficients(
        centered_times_s,
        measured_cfo_hz,
        frequency_weights,
        degree=2,
    )
    frequency_fit_hz = _evaluate_scaled_polynomial(
        centered_times_s,
        frequency_coefficients,
        frequency_scale,
    )
    c0, c1, c2 = frequency_coefficients
    normalized_time = centered_times_s / frequency_scale
    integrated_frequency_phase_rad = (
        2
        * np.pi
        * frequency_scale
        * (
            (c0 - center_cfo_hz) * normalized_time
            + 0.5 * c1 * normalized_time**2
            + (c2 / 3) * normalized_time**3
        )
    )

    phase_weights = np.where(quality, exact, 0.0)
    delays, phase_measurements, similarities, delay_corrected = _separate_channel_delay_and_phase(
        channels,
        phase_weights,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
    )
    phase_after_frequency_rad = np.angle(
        np.exp(1j * (phase_measurements - integrated_frequency_phase_rad))
    )
    cubic_model, cubic_residual = _fit_wrapped_polynomial(
        centered_times_s,
        phase_after_frequency_rad,
        phase_weights,
        degree=3,
    )
    flexible_model, flexible_residual = _fit_wrapped_polynomial(
        centered_times_s,
        phase_after_frequency_rad,
        phase_weights,
        degree=8,
    )
    doubled_model, doubled_residual = _fit_wrapped_polynomial(
        centered_times_s,
        np.angle(np.exp(2j * phase_after_frequency_rad)),
        phase_weights,
        degree=3,
    )
    pi_ambiguity_model = 0.5 * doubled_model
    pi_ambiguity_residual = 0.5 * doubled_residual
    pi_ambiguity_state = np.rint((phase_after_frequency_rad - pi_ambiguity_model) / np.pi).astype(
        int
    )
    pi_ambiguity_state_bits = np.mod(pi_ambiguity_state, 2)
    cubic_phase = integrated_frequency_phase_rad + cubic_model
    flexible_phase = integrated_frequency_phase_rad + flexible_model
    pi_ambiguity_phase = (
        integrated_frequency_phase_rad + pi_ambiguity_model + np.pi * pi_ambiguity_state
    )

    adjacent_innovations = np.full(len(starts), np.nan)
    implied_frequency_error_hz = np.full(len(starts), np.nan)
    pi_corrected_frequency_error_hz = np.full(len(starts), np.nan)
    pair_quality = np.zeros(len(starts), dtype=bool)
    for index in range(1, len(starts)):
        observed = float(np.angle(np.vdot(delay_corrected[index - 1], delay_corrected[index])))
        predicted = float(
            integrated_frequency_phase_rad[index] - integrated_frequency_phase_rad[index - 1]
        )
        innovation = float(np.angle(np.exp(1j * (observed - predicted))))
        dt_s = reference_times_s[index] - reference_times_s[index - 1]
        adjacent_innovations[index] = innovation
        implied_frequency_error_hz[index] = innovation / (2 * np.pi * dt_s)
        pair_quality[index] = bool(quality[index - 1] and quality[index])

    supported_pairs = pair_quality & np.isfinite(adjacent_innovations)
    pair_weights = np.minimum(phase_weights[:-1], phase_weights[1:])
    supported_pair_weights = pair_weights[supported_pairs[1:]]
    supported_innovations = adjacent_innovations[supported_pairs]
    pi_innovation_center = 0.5 * float(
        np.angle(np.sum(supported_pair_weights * np.exp(2j * supported_innovations)))
    )
    pi_centered_innovations = 0.5 * np.angle(
        np.exp(2j * (adjacent_innovations - pi_innovation_center))
    )
    for index in range(1, len(starts)):
        dt_s = reference_times_s[index] - reference_times_s[index - 1]
        pi_corrected_frequency_error_hz[index] = pi_centered_innovations[index] / (2 * np.pi * dt_s)

    cubic_corrected = delay_corrected * np.exp(-1j * cubic_phase)[:, None]
    flexible_corrected = delay_corrected * np.exp(-1j * flexible_phase)[:, None]
    pi_ambiguity_corrected = delay_corrected * np.exp(-1j * pi_ambiguity_phase)[:, None]
    oracle_corrected = delay_corrected * np.exp(-1j * phase_measurements)[:, None]
    causal_frames = tuple(
        frame for frame in dense_tracking.frames if start_s <= frame.reference_time_s < end_s
    )
    causal_runs = _strict_phase_update_runs(causal_frames)
    frame_details = []
    model_cfo_hz = np.asarray(trajectory.frequency_hz(reference_times_s))
    for index, start in enumerate(starts):
        frame_details.append(
            OfflinePhaseContinuityFrame(
                frame_start_sample=int(start),
                reference_time_s=float(reference_times_s[index]),
                retained_by_dense_pass=bool(retained_match[index]),
                model_cfo_hz=float(model_cfo_hz[index]),
                measured_cfo_hz=float(measured_cfo_hz[index]),
                frequency_fit_cfo_hz=float(frequency_fit_hz[index]),
                frequency_uncertainty_hz=float(uncertainty_hz[index]),
                exact_coherence=float(exact[index]),
                control_coherence=float(control_values[index]),
                coherence_margin=float(margins[index]),
                within_frame_phase_residual_rms_rad=float(fits[index].phase_residual_rms_rad),
                fractional_delay_samples=float(delays[index]),
                timing_corrected_channel_similarity=float(similarities[index]),
                phase_measurement_rad=float(phase_measurements[index]),
                cubic_batch_phase_residual_rad=float(cubic_residual[index]),
                flexible_batch_phase_residual_rad=float(flexible_residual[index]),
                pi_ambiguity_batch_phase_residual_rad=float(pi_ambiguity_residual[index]),
                pi_ambiguity_state=int(pi_ambiguity_state_bits[index]),
                adjacent_phase_innovation_rad=(
                    float(adjacent_innovations[index]) if index else None
                ),
                phase_implied_frequency_error_hz=(
                    float(implied_frequency_error_hz[index]) if index else None
                ),
                pi_corrected_phase_implied_frequency_error_hz=(
                    float(pi_corrected_frequency_error_hz[index]) if index else None
                ),
            )
        )
    return OfflinePhaseContinuityDetail(
        start_s=start_s,
        end_s=end_s,
        inferred_frame_count=len(starts),
        retained_frame_count=int(np.count_nonzero(retained_match)),
        newly_evaluated_frame_count=int(np.count_nonzero(~retained_match)),
        quality_frame_count=int(np.count_nonzero(quality)),
        frequency_fit_rms_hz=float(
            np.sqrt(np.mean((measured_cfo_hz[quality] - frequency_fit_hz[quality]) ** 2))
        ),
        median_frequency_uncertainty_hz=float(np.median(uncertainty_hz[quality])),
        median_within_frame_phase_residual_rms_rad=float(
            np.median([fits[index].phase_residual_rms_rad for index in np.flatnonzero(quality)])
        ),
        median_abs_fractional_delay_samples=float(np.median(np.abs(delays[quality]))),
        median_timing_corrected_channel_similarity=float(np.median(similarities[quality])),
        adjacent_phase_innovation_rms_rad=float(
            np.sqrt(np.mean(adjacent_innovations[supported_pairs] ** 2))
        ),
        median_abs_phase_implied_frequency_error_hz=float(
            np.median(np.abs(implied_frequency_error_hz[supported_pairs]))
        ),
        cubic_batch_phase_residual_rms_rad=float(np.sqrt(np.mean(cubic_residual[quality] ** 2))),
        flexible_batch_phase_residual_rms_rad=float(
            np.sqrt(np.mean(flexible_residual[quality] ** 2))
        ),
        pi_ambiguity_batch_phase_residual_rms_rad=float(
            np.sqrt(np.mean(pi_ambiguity_residual[quality] ** 2))
        ),
        pi_centered_adjacent_phase_innovation_rms_rad=float(
            np.sqrt(np.mean(pi_centered_innovations[supported_pairs] ** 2))
        ),
        pi_ambiguity_frequency_correction_hz=float(
            pi_innovation_center / (2 * np.pi * np.median(np.diff(reference_times_s)))
        ),
        pi_ambiguity_state_transition_count=int(np.count_nonzero(np.diff(pi_ambiguity_state_bits))),
        even_to_odd_heldout_phase_residual_rms_rad=heldout_validation[0],
        even_to_odd_heldout_stack_efficiency=heldout_validation[1],
        odd_to_even_heldout_phase_residual_rms_rad=heldout_validation[2],
        odd_to_even_heldout_stack_efficiency=heldout_validation[3],
        heldout_pi_state_agreement=heldout_validation[4],
        raw_stack_efficiency=_weighted_stack_efficiency(channels, phase_weights),
        frequency_only_stack_efficiency=_weighted_stack_efficiency(
            delay_corrected * np.exp(-1j * integrated_frequency_phase_rad)[:, None],
            phase_weights,
        ),
        cubic_batch_stack_efficiency=_weighted_stack_efficiency(
            cubic_corrected,
            phase_weights,
        ),
        flexible_batch_stack_efficiency=_weighted_stack_efficiency(
            flexible_corrected,
            phase_weights,
        ),
        pi_ambiguity_batch_stack_efficiency=_weighted_stack_efficiency(
            pi_ambiguity_corrected,
            phase_weights,
        ),
        per_frame_nuisance_stack_efficiency=_weighted_stack_efficiency(
            oracle_corrected,
            phase_weights,
        ),
        causal_evaluated_frame_count=len(causal_frames),
        causal_phase_update_count=sum(frame.phase_update_applied for frame in causal_frames),
        causal_phase_reset_count=sum(frame.phase_reset_detected for frame in causal_frames),
        causal_longest_strict_run_frames=max((len(run) for run in causal_runs), default=0),
        frames=tuple(frame_details),
    )


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


def _plot_phase_doppler_tracking(
    details: tuple[WindowDetail, ...], trajectory: FrozenTrajectory, path: Path
) -> None:
    pairs = tuple(
        (item, frame)
        for item in details
        for frame in item.frames
        if frame.tracked_absolute_cfo_hz is not None
        and frame.tracked_doppler_rate_hz_s is not None
        and frame.tracked_rate_sigma_hz_s is not None
        and frame.phase_innovation_rad is not None
    )
    frames = tuple(frame for _, frame in pairs)
    times = np.asarray([frame.reference_time_s for frame in frames])
    measured = np.asarray([frame.absolute_cfo_hz for frame in frames])
    tracked = np.asarray([float(frame.tracked_absolute_cfo_hz) for frame in frames])
    model = np.asarray([frame.model_cfo_hz for frame in frames])
    glrt = np.asarray([item.glrt64_cfo_hz for item, _ in pairs])
    rate = np.asarray([float(frame.tracked_doppler_rate_hz_s) for frame in frames])
    model_rate = np.asarray(trajectory.doppler_rate_hz_s(times))
    phase_innovation = np.asarray([float(frame.phase_innovation_rad) for frame in frames])
    phase_updates = np.asarray([frame.phase_update_applied for frame in frames])
    resets = np.asarray([frame.phase_reset_detected for frame in frames])
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.5), constrained_layout=True)
        axes[0, 0].axhline(0, color=INK, linewidth=0.8)
        axes[0, 0].scatter(
            times,
            measured - model,
            s=13,
            color=BLUE,
            alpha=0.32,
            linewidths=0,
            label="independent frame slope",
        )
        axes[0, 0].plot(
            times,
            tracked - model,
            color=AMBER,
            linewidth=1.15,
            label="phase + Doppler Kalman state",
        )
        axes[0, 0].set_xlabel("capture time (s)")
        axes[0, 0].set_ylabel("CFO residual vs frozen model (Hz)")
        axes[0, 0].set_title(
            "A · Pilot-only state tracking within each 20 ms window",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend(loc="best")
        axes[0, 0].grid(True)

        for values, color, label in (
            (measured - model, BLUE, "independent frame slope"),
            (tracked - model, AMBER, "phase + Doppler tracker"),
            (glrt - model, GREEN, "GLRT64 held over window"),
        ):
            x, y = _ecdf(np.abs(values))
            axes[0, 1].step(
                x,
                y,
                where="post",
                color=color,
                linewidth=1.8,
                label=f"{label} · RMS {np.sqrt(np.mean(values**2)):.0f} Hz",
            )
        axes[0, 1].set_xlabel("absolute CFO residual vs frozen model (Hz)")
        axes[0, 1].set_ylabel("empirical cumulative fraction")
        axes[0, 1].set_title("B · Like-for-like per-frame error", loc="left", fontweight="bold")
        axes[0, 1].legend(loc="best")
        axes[0, 1].grid(True)

        axes[1, 0].plot(times, model_rate, color=INK, linewidth=1.4, label="frozen-model rate")
        axes[1, 0].plot(times, rate, color=AMBER, linewidth=1.1, label="tracked rate")
        axes[1, 0].fill_between(
            times,
            rate - np.asarray([float(frame.tracked_rate_sigma_hz_s) for frame in frames]),
            rate + np.asarray([float(frame.tracked_rate_sigma_hz_s) for frame in frames]),
            color=AMBER,
            alpha=0.15,
            linewidth=0,
            label="tracker ±1σ",
        )
        axes[1, 0].set_xlabel("capture time (s)")
        axes[1, 0].set_ylabel("Doppler/CFO rate (Hz/s)")
        axes[1, 0].set_title(
            "C · Rate is estimated as a state, not a post-hoc line fit",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(loc="best")
        axes[1, 0].grid(True)

        axes[1, 1].axhline(0, color=INK, linewidth=0.7)
        axes[1, 1].scatter(
            times[phase_updates],
            phase_innovation[phase_updates],
            s=16,
            color=BLUE,
            alpha=0.55,
            linewidths=0,
            label=f"accepted phase updates ({np.count_nonzero(phase_updates)})",
        )
        axes[1, 1].scatter(
            times[~phase_updates],
            phase_innovation[~phase_updates],
            s=25,
            color=GRAY,
            marker="x",
            label=f"rejected/coasted ({np.count_nonzero(~phase_updates)})",
        )
        axes[1, 1].scatter(
            times[resets],
            phase_innovation[resets],
            s=75,
            facecolor="none",
            edgecolor=RED,
            linewidth=1.4,
            label=f"declared phase resets ({np.count_nonzero(resets)})",
        )
        axes[1, 1].axhline(1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 1].axhline(-1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 1].set_ylim(-math.pi, math.pi)
        axes[1, 1].set_xlabel("capture time (s)")
        axes[1, 1].set_ylabel("wrapped phase innovation (rad)")
        axes[1, 1].set_title(
            "D · Phase is connected only while the pilot channel remains coherent",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(loc="best")
        axes[1, 1].grid(True)
        figure.suptitle(
            "PNT-like carrier tracking from the known Qin edge pilots",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_dense_phase_doppler_tracking(detail: DenseTrackingDetail, path: Path) -> None:
    frames = detail.frames
    times = np.asarray([frame.reference_time_s for frame in frames])
    measured = np.asarray([frame.absolute_cfo_measurement_hz for frame in frames])
    tracked = np.asarray([frame.tracked_absolute_cfo_hz for frame in frames])
    model = np.asarray([frame.model_cfo_hz for frame in frames])
    glrt = np.asarray([frame.glrt64_cfo_hz for frame in frames])
    rate = np.asarray([frame.tracked_doppler_rate_hz_s for frame in frames])
    model_rate = np.asarray([frame.model_doppler_rate_hz_s for frame in frames])
    phase_innovation = np.asarray([frame.phase_innovation_rad for frame in frames])
    phase_updates = np.asarray([frame.phase_update_applied for frame in frames])
    frequency_updates = np.asarray([frame.frequency_update_applied for frame in frames])
    resets = np.asarray([frame.phase_reset_detected for frame in frames])
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.5), constrained_layout=True)
        axes[0, 0].axhline(0, color=INK, linewidth=0.8)
        axes[0, 0].scatter(
            times[frequency_updates],
            (measured - model)[frequency_updates],
            s=9,
            color=BLUE,
            alpha=0.28,
            linewidths=0,
            label=f"accepted independent pilot frames ({np.count_nonzero(frequency_updates)})",
        )
        axes[0, 0].scatter(
            times[~frequency_updates],
            (measured - model)[~frequency_updates],
            s=10,
            color=GRAY,
            alpha=0.16,
            linewidths=0,
            label=f"rejected/coasted frames ({np.count_nonzero(~frequency_updates)})",
        )
        axes[0, 0].scatter(
            times[frequency_updates],
            (tracked - model)[frequency_updates],
            s=7,
            color=AMBER,
            alpha=0.48,
            linewidths=0,
            label="tracked CFO on accepted frames",
        )
        axes[0, 0].set_xlabel("capture time (s)")
        axes[0, 0].set_ylabel("CFO residual vs frozen model (Hz)")
        axes[0, 0].set_title(
            f"A · Dense pass: {detail.source_window_count} timing locks, "
            f"{detail.requested_frame_count} pilot frames",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend(loc="best", fontsize=8.5)
        axes[0, 0].grid(True)

        for values, color, label in (
            (measured - model, BLUE, "independent pilot frame"),
            (tracked - model, AMBER, "phase + Doppler tracker"),
            (glrt - model, GREEN, "source-window GLRT64"),
        ):
            selected = values[frequency_updates]
            x, y = _ecdf(np.abs(selected))
            axes[0, 1].step(
                x,
                y,
                where="post",
                color=color,
                linewidth=1.8,
                label=f"{label} · RMS {np.sqrt(np.mean(selected**2)):.0f} Hz",
            )
        axes[0, 1].set_xlabel("absolute CFO residual on accepted updates (Hz)")
        axes[0, 1].set_ylabel("empirical cumulative fraction")
        axes[0, 1].set_title(
            "B · Like-for-like dense frequency comparison",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].legend(loc="best", fontsize=8.5)
        axes[0, 1].grid(True)

        axes[1, 0].plot(times, model_rate, color=INK, linewidth=1.4, label="frozen-model rate")
        axes[1, 0].scatter(
            times[frequency_updates],
            rate[frequency_updates],
            s=8,
            color=AMBER,
            alpha=0.5,
            linewidths=0,
            label="tracked rate on accepted frames",
        )
        axes[1, 0].set_xlabel("capture time (s)")
        axes[1, 0].set_ylabel("Doppler/CFO rate (Hz/s)")
        axes[1, 0].set_title(
            "C · Carrier-rate state across independently timed pilot bursts",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(loc="best")
        axes[1, 0].grid(True)

        axes[1, 1].axhline(0, color=INK, linewidth=0.7)
        axes[1, 1].scatter(
            times[phase_updates],
            phase_innovation[phase_updates],
            s=10,
            color=BLUE,
            alpha=0.48,
            linewidths=0,
            label=f"accepted phase updates ({np.count_nonzero(phase_updates)})",
        )
        axes[1, 1].scatter(
            times[~phase_updates],
            phase_innovation[~phase_updates],
            s=13,
            color=GRAY,
            marker="x",
            alpha=0.45,
            label=f"rejected/coasted ({np.count_nonzero(~phase_updates)})",
        )
        axes[1, 1].scatter(
            times[resets],
            phase_innovation[resets],
            s=44,
            facecolor="none",
            edgecolor=RED,
            linewidth=1.0,
            label=f"declared phase resets ({np.count_nonzero(resets)})",
        )
        axes[1, 1].axhline(1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 1].axhline(-1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 1].set_ylim(-math.pi, math.pi)
        axes[1, 1].set_xlabel("capture time (s)")
        axes[1, 1].set_ylabel("wrapped phase innovation (rad)")
        axes[1, 1].set_title(
            f"D · {detail.phase_segment_count} coherent-phase segments; resets are explicit",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(loc="best", fontsize=8.5)
        axes[1, 1].grid(True)
        figure.suptitle(
            "Dense PNT-like carrier tracking from existing Qin edge-pilot locks",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _phase_update_runs(
    frames: tuple[DenseTrackingFrame, ...],
) -> tuple[tuple[DenseTrackingFrame, ...], ...]:
    runs: list[tuple[DenseTrackingFrame, ...]] = []
    current: list[DenseTrackingFrame] = []
    for frame in frames:
        if frame.phase_update_applied:
            current.append(frame)
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _frequency_update_runs(
    frames: tuple[DenseTrackingFrame, ...],
) -> tuple[tuple[DenseTrackingFrame, ...], ...]:
    runs: list[tuple[DenseTrackingFrame, ...]] = []
    current: list[DenseTrackingFrame] = []
    for frame in frames:
        if frame.frequency_update_applied:
            current.append(frame)
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _strict_phase_update_runs(
    frames: tuple[DenseTrackingFrame, ...],
) -> tuple[tuple[DenseTrackingFrame, ...], ...]:
    runs: list[tuple[DenseTrackingFrame, ...]] = []
    current: list[DenseTrackingFrame] = []
    for frame in frames:
        gap = bool(current and frame.reference_time_s - current[-1].reference_time_s > 1.5 / 750)
        if frame.phase_update_applied and not gap:
            current.append(frame)
        elif frame.phase_update_applied:
            runs.append(tuple(current))
            current = [frame]
        elif current:
            runs.append(tuple(current))
            current = []
    if current:
        runs.append(tuple(current))
    return tuple(runs)


def _phase_segments(
    frames: tuple[DenseTrackingFrame, ...],
) -> tuple[tuple[DenseTrackingFrame, ...], ...]:
    segments: list[tuple[DenseTrackingFrame, ...]] = []
    current: list[DenseTrackingFrame] = []
    current_id: int | None = None
    for frame in frames:
        if current_id is None or frame.phase_segment_id == current_id:
            current.append(frame)
            current_id = frame.phase_segment_id
            continue
        segments.append(tuple(current))
        current = [frame]
        current_id = frame.phase_segment_id
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _coherent_stack_efficiency(channels: np.ndarray) -> float:
    """Return normalized coherent power after stacking channel vectors."""

    values = np.asarray(channels, dtype=np.complex128)
    if values.ndim != 2 or not values.shape[0] or not values.shape[1]:
        raise ValueError("channels must be a nonempty two-dimensional array")
    energy = float(np.sum(np.abs(values) ** 2))
    return float(np.sum(np.abs(np.sum(values, axis=0)) ** 2) / max(values.shape[0] * energy, 1e-20))


def _analyze_phase_lock_intervals(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    detail: DenseTrackingDetail,
) -> tuple[PhaseLockInterval, ...]:
    frames = detail.frames
    runs = _phase_update_runs(frames)
    position = {id(frame): index for index, frame in enumerate(frames)}
    expected = qin_edge_pilot_symbols(edge)
    control = qin_edge_pilot_symbols(edge, symbol_roll=CONTROL_SYMBOL_ROLL)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    centered_times_s = times_s - np.mean(times_s)
    raw_start_time_s = raw_sample_start / sample_rate_hz
    previous_start_s: float | None = None
    previous_start_position: int | None = None
    intervals: list[PhaseLockInterval] = []

    for run in runs:
        start_s = run[0].reference_time_s
        end_s = run[-1].reference_time_s
        start_position = position[id(run[0])]
        start_interval_s = None if previous_start_s is None else start_s - previous_start_s
        crosses_sampling_gap: bool | None = None
        if previous_start_position is not None:
            between = frames[previous_start_position : start_position + 1]
            gaps_s = np.diff([frame.reference_time_s for frame in between])
            crosses_sampling_gap = bool(np.any(gaps_s > 1.5 / 750))

        raw_efficiency: float | None = None
        tracked_efficiency: float | None = None
        self_aligned_efficiency: float | None = None
        if len(run) >= 2:
            channels = []
            tracked_channels = []
            for frame in run:
                frame_position = position[id(frame)]
                if frame_position == 0:
                    predicted_phase_rad = 0.0
                    predicted_frequency_hz = frame.glrt64_cfo_hz
                else:
                    previous = frames[frame_position - 1]
                    dt_s = frame.reference_time_s - previous.reference_time_s
                    predicted_phase_rad = (
                        previous.tracked_phase_rad
                        + 2 * math.pi * previous.tracked_absolute_cfo_hz * dt_s
                        + math.pi * previous.tracked_doppler_rate_hz_s * dt_s**2
                    )
                    predicted_frequency_hz = (
                        previous.tracked_absolute_cfo_hz + previous.tracked_doppler_rate_hz_s * dt_s
                    )
                demodulator = _KnownPilotDemodulator(
                    iq,
                    sample_rate_hz,
                    edge,
                    predicted_frequency_hz,
                )
                pilots = demodulator.frame(frame.frame_start_sample)
                exact = pilots * np.conj(expected)
                rolled = pilots * np.conj(control)
                fit = _fit_phase_slope_frame(
                    exact,
                    rolled,
                    centered_times_s,
                    maximum_residual_cfo_hz=2_000.0,
                )
                channel = np.asarray(fit.channel_vector)
                norm = float(np.linalg.norm(channel))
                if norm <= np.finfo(float).tiny:
                    continue
                channel = channel / norm
                local_time_s = frame.reference_time_s - raw_start_time_s
                gauge = math.remainder(
                    2 * math.pi * predicted_frequency_hz * local_time_s - predicted_phase_rad,
                    2 * math.pi,
                )
                channels.append(channel)
                tracked_channels.append(channel * np.exp(1j * gauge))
            if len(channels) >= 2:
                channel_array = np.asarray(channels)
                tracked_array = np.asarray(tracked_channels)
                reference = channel_array[0]
                independent_phase = np.angle(channel_array @ np.conj(reference))
                self_aligned = channel_array * np.exp(-1j * independent_phase)[:, None]
                raw_efficiency = _coherent_stack_efficiency(channel_array)
                tracked_efficiency = _coherent_stack_efficiency(tracked_array)
                self_aligned_efficiency = _coherent_stack_efficiency(self_aligned)

        intervals.append(
            PhaseLockInterval(
                start_time_s=start_s,
                end_time_s=end_s,
                observed_span_s=end_s - start_s,
                frame_count=len(run),
                start_interval_s=start_interval_s,
                crosses_sampling_gap=crosses_sampling_gap,
                median_exact_coherence=float(np.median([frame.exact_coherence for frame in run])),
                median_coherence_margin=float(np.median([frame.coherence_margin for frame in run])),
                median_frequency_uncertainty_hz=float(
                    np.median([frame.frequency_uncertainty_hz for frame in run])
                ),
                raw_stack_efficiency=raw_efficiency,
                tracked_stack_efficiency=tracked_efficiency,
                self_aligned_stack_efficiency=self_aligned_efficiency,
            )
        )
        previous_start_s = start_s
        previous_start_position = start_position
    return tuple(intervals)


def _plot_dense_sampling_geometry(detail: DenseTrackingDetail, path: Path) -> None:
    frames = detail.frames
    times = np.asarray([frame.reference_time_s for frame in frames])
    frequency = np.asarray([frame.frequency_update_applied for frame in frames])
    phase = np.asarray([frame.phase_update_applied for frame in frames])
    resets = np.asarray([frame.phase_reset_detected for frame in frames])
    gaps_ms = np.diff(times) * 1e3
    grouped: dict[int, list[DenseTrackingFrame]] = {}
    for frame in frames:
        grouped.setdefault(frame.source_window_index, []).append(frame)
    windows = tuple(grouped[index] for index in sorted(grouped))
    window_times = np.asarray(
        [np.mean([frame.reference_time_s for frame in group]) for group in windows]
    )
    frequency_counts = np.asarray(
        [sum(frame.frequency_update_applied for frame in group) for group in windows]
    )
    phase_counts = np.asarray(
        [sum(frame.phase_update_applied for frame in group) for group in windows]
    )
    reset_counts = np.asarray(
        [sum(frame.phase_reset_detected for frame in group) for group in windows]
    )

    with plt.rc_context(_style()):
        figure = plt.figure(figsize=(15, 8.7), constrained_layout=True)
        grid = figure.add_gridspec(2, 2, height_ratios=(1.0, 1.1))
        timeline = figure.add_subplot(grid[0, :])
        for y, selected, color, label in (
            (0, np.ones(len(frames), dtype=bool), GRAY, f"requested frames ({len(frames)})"),
            (1, frequency, GREEN, f"frequency updates ({np.count_nonzero(frequency)})"),
            (2, phase, BLUE, f"phase updates ({np.count_nonzero(phase)})"),
            (3, resets, RED, f"phase resets ({np.count_nonzero(resets)})"),
        ):
            timeline.scatter(
                times[selected],
                np.full(np.count_nonzero(selected), y),
                marker="|",
                s=38,
                color=color,
                alpha=0.68,
                linewidths=0.8,
                label=label,
            )
        timeline.set_yticks((0, 1, 2, 3), ("requested", "frequency", "phase", "reset"))
        timeline.set_ylim(-0.6, 3.6)
        timeline.set_xlabel("capture time (s)")
        timeline.set_title(
            "A · Frames occur in 125 acquisition-timed bursts; blank intervals were not evaluated",
            loc="left",
            fontweight="bold",
        )
        timeline.legend(loc="upper center", ncol=4, fontsize=8.8)
        timeline.grid(True, axis="x")

        gap_axis = figure.add_subplot(grid[1, 0])
        ordered_gaps = np.sort(gaps_ms)
        gap_axis.step(
            ordered_gaps,
            np.arange(1, len(ordered_gaps) + 1) / len(ordered_gaps),
            where="post",
            color=INK,
            linewidth=1.7,
        )
        gap_axis.axvline(
            1_000 / 750,
            color=BLUE,
            linewidth=1.2,
            linestyle="--",
            label="750 Hz frame spacing",
        )
        gap_axis.set_xscale("log")
        gap_axis.set_xlabel("gap between evaluated frame references (ms, log scale)")
        gap_axis.set_ylabel("empirical cumulative fraction")
        gap_axis.set_title(
            "B · Most evaluated frames are adjacent inside a burst; larger gaps remain",
            loc="left",
            fontweight="bold",
        )
        gap_axis.legend(loc="lower right")
        gap_axis.grid(True)

        count_axis = figure.add_subplot(grid[1, 1])
        count_axis.plot(
            window_times,
            frequency_counts,
            color=GREEN,
            linewidth=0.8,
            alpha=0.55,
        )
        count_axis.scatter(
            window_times,
            frequency_counts,
            s=18,
            color=GREEN,
            label="frequency updates/window",
        )
        count_axis.scatter(
            window_times,
            phase_counts,
            s=18,
            color=BLUE,
            label="phase updates/window",
        )
        count_axis.scatter(
            window_times,
            reset_counts,
            s=23,
            color=RED,
            marker="x",
            label="resets/window",
        )
        count_axis.set_ylim(-0.6, max(15.5, float(np.max(frequency_counts)) + 0.5))
        count_axis.set_xlabel("capture time (s)")
        count_axis.set_ylabel("count in one 15-frame window")
        count_axis.set_title(
            "C · Pilot structure is common; usable phase continuity is intermittent",
            loc="left",
            fontweight="bold",
        )
        count_axis.legend(loc="best", fontsize=8.8)
        count_axis.grid(True)
        figure.suptitle(
            "Dense-pass sampling geometry and accepted observations",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_phase_coherence_detail(detail: DenseTrackingDetail, path: Path) -> None:
    frames = detail.frames
    segments = _phase_segments(frames)
    runs = _phase_update_runs(frames)
    longest = max(runs, key=len)
    spans_ms = np.asarray(
        [(segment[-1].reference_time_s - segment[0].reference_time_s) * 1e3 for segment in segments]
    )
    updates = np.asarray(
        [sum(frame.phase_update_applied for frame in segment) for segment in segments]
    )
    frame_index = {id(frame): index for index, frame in enumerate(frames)}
    first = frame_index[id(longest[0])]
    last = frame_index[id(longest[-1])]
    context = frames[max(0, first - 3) : min(len(frames), last + 4)]
    reference = longest[0].reference_time_s
    context_time_ms = np.asarray([(frame.reference_time_s - reference) * 1e3 for frame in context])
    accepted = np.asarray([frame.phase_update_applied for frame in context])
    innovation = np.asarray([frame.phase_innovation_rad for frame in context])
    measured_error = np.asarray(
        [frame.absolute_cfo_measurement_hz - frame.model_cfo_hz for frame in context]
    )
    tracked_error = np.asarray(
        [frame.tracked_absolute_cfo_hz - frame.model_cfo_hz for frame in context]
    )
    glrt_error = np.asarray([frame.glrt64_cfo_hz - frame.model_cfo_hz for frame in context])

    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.2), constrained_layout=True)
        scatter = axes[0, 0].scatter(
            spans_ms,
            updates,
            c=np.arange(len(segments)),
            cmap="viridis",
            s=22,
            alpha=0.62,
            linewidths=0,
        )
        strongest = int(np.argmax(updates))
        axes[0, 0].scatter(
            [spans_ms[strongest]],
            [updates[strongest]],
            s=95,
            facecolor="none",
            edgecolor=RED,
            linewidth=1.5,
            label="most accepted updates",
        )
        axes[0, 0].set_xlabel("phase-segment span (ms)")
        axes[0, 0].set_ylabel("accepted phase updates in segment")
        axes[0, 0].set_title(
            "A · Most reset-delimited segments contain no accepted phase update",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend(loc="upper right")
        axes[0, 0].grid(True)
        figure.colorbar(scatter, ax=axes[0, 0], label="segment order", fraction=0.046)

        counts = np.bincount(updates)
        axes[0, 1].bar(np.arange(len(counts)), counts, color=BLUE, alpha=0.72, width=0.8)
        axes[0, 1].axvline(
            len(longest),
            color=RED,
            linewidth=1.2,
            linestyle="--",
            label=f"longest consecutive run: {len(longest)}",
        )
        axes[0, 1].axvline(
            int(np.max(updates)),
            color=GREEN,
            linewidth=1.2,
            linestyle=":",
            label=f"maximum updates in one segment: {int(np.max(updates))}",
        )
        axes[0, 1].set_yscale("log")
        axes[0, 1].set_xlabel("accepted phase updates in one reset-delimited segment")
        axes[0, 1].set_ylabel("segment count (log scale)")
        axes[0, 1].set_title(
            f"B · {detail.phase_segment_count} segments; median accepted count is zero",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].legend(loc="upper right")
        axes[0, 1].grid(True, axis="y")

        axes[1, 0].scatter(
            context_time_ms[accepted],
            innovation[accepted],
            s=34,
            color=BLUE,
            label="accepted phase innovation",
        )
        axes[1, 0].scatter(
            context_time_ms[~accepted],
            innovation[~accepted],
            s=40,
            color=RED,
            marker="x",
            label="neighboring rejected/reset frame",
        )
        axes[1, 0].axhline(0, color=INK, linewidth=0.75)
        axes[1, 0].axhline(1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 0].axhline(-1.2, color=RED, linewidth=0.75, linestyle=":")
        axes[1, 0].set_ylim(-math.pi, math.pi)
        axes[1, 0].set_xlabel("time from first accepted frame in run (ms)")
        axes[1, 0].set_ylabel("wrapped phase innovation (rad)")
        axes[1, 0].set_title(
            f"C · Strongest consecutive run: {len(longest)} observed frames",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(loc="best", fontsize=8.8)
        axes[1, 0].grid(True)

        axes[1, 1].axhline(0, color=INK, linewidth=0.75)
        axes[1, 1].plot(
            context_time_ms,
            measured_error,
            color=BLUE,
            marker="o",
            markersize=3.5,
            linewidth=1.0,
            label="independent pilot frame",
        )
        axes[1, 1].plot(
            context_time_ms,
            tracked_error,
            color=AMBER,
            marker="o",
            markersize=3.5,
            linewidth=1.2,
            label="phase + Doppler state",
        )
        axes[1, 1].plot(
            context_time_ms,
            glrt_error,
            color=GREEN,
            linewidth=1.0,
            label="source GLRT64",
        )
        axes[1, 1].set_xlabel("time from first accepted frame in run (ms)")
        axes[1, 1].set_ylabel("CFO residual vs frozen model (Hz)")
        axes[1, 1].set_title(
            "D · Even the strongest phase run does not remove common CFO bias",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(loc="best", fontsize=8.8)
        axes[1, 1].grid(True)
        figure.suptitle(
            "Phase-coherence segments and strongest-run detail",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_phase_lock_timing_distribution(
    intervals: tuple[PhaseLockInterval, ...],
    path: Path,
) -> None:
    starts = np.asarray([item.start_time_s for item in intervals])
    spans_ms = np.asarray([item.observed_span_s * 1e3 for item in intervals])
    lengths = np.asarray([item.frame_count for item in intervals])
    exact = np.asarray([item.median_exact_coherence for item in intervals])
    gaps_ms = np.asarray(
        [item.start_interval_s * 1e3 for item in intervals if item.start_interval_s is not None]
    )
    crosses = np.asarray(
        [item.crosses_sampling_gap for item in intervals if item.start_interval_s is not None],
        dtype=bool,
    )
    within_periods = gaps_ms[~crosses] * 0.75
    rounded_periods = np.rint(within_periods).astype(int)
    maximum_period = min(30, int(np.max(rounded_periods)))
    period_counts = np.bincount(rounded_periods, minlength=maximum_period + 1)

    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.2), constrained_layout=True)
        scatter = axes[0, 0].scatter(
            starts,
            spans_ms,
            c=exact,
            cmap="viridis",
            s=16 + 7 * lengths,
            alpha=0.72,
            linewidths=0,
        )
        axes[0, 0].set_xlabel("phase-lock run start time (s)")
        axes[0, 0].set_ylabel("observed run span (ms)")
        axes[0, 0].set_title(
            "A · Lock runs are short and distributed throughout the observed dwell",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].grid(True)
        figure.colorbar(
            scatter,
            ax=axes[0, 0],
            label="median exact-pilot coherence",
            fraction=0.046,
        )

        unique_lengths, counts = np.unique(lengths, return_counts=True)
        axes[0, 1].bar(unique_lengths, counts, color=BLUE, alpha=0.75, width=0.8)
        axes[0, 1].set_yscale("log")
        axes[0, 1].set_xticks(np.arange(1, int(np.max(lengths)) + 1))
        axes[0, 1].set_xlabel("consecutive accepted evaluated frames")
        axes[0, 1].set_ylabel("run count (log scale)")
        axes[0, 1].set_title(
            f"B · {np.count_nonzero(lengths == 1)} of {len(intervals)} runs are singletons",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].grid(True, axis="y")

        axes[1, 0].bar(
            np.arange(1, maximum_period + 1),
            period_counts[1 : maximum_period + 1],
            color=GREEN,
            alpha=0.75,
            width=0.8,
        )
        axes[1, 0].axvline(
            2,
            color=RED,
            linestyle="--",
            linewidth=1.1,
            label="one rejected frame between runs",
        )
        axes[1, 0].set_xlabel("run-start interval (nominal 750 Hz frame periods)")
        axes[1, 0].set_ylabel("interval count")
        axes[1, 0].set_title(
            "C · Within sampled stretches, apparent cadence is quantized by evaluation",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(loc="upper right")
        axes[1, 0].grid(True, axis="y")

        for selected, color, label in (
            (~crosses, BLUE, "within continuously evaluated stretch"),
            (crosses, RED, "crosses a frame-evaluation gap"),
        ):
            values = np.sort(gaps_ms[selected])
            axes[1, 1].step(
                values,
                np.arange(1, len(values) + 1) / len(values),
                where="post",
                color=color,
                linewidth=1.6,
                label=f"{label} ({len(values)})",
            )
        axes[1, 1].set_xscale("log")
        axes[1, 1].set_xlabel("time between observed run starts (ms, log scale)")
        axes[1, 1].set_ylabel("empirical cumulative fraction")
        axes[1, 1].set_title(
            "D · Acquisition gaps censor the physical unlock/relock process",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(loc="lower right", fontsize=8.8)
        axes[1, 1].grid(True)
        figure.suptitle(
            "Observed coherent-phase lock timing and cadence",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_phase_lock_quality_correction(
    intervals: tuple[PhaseLockInterval, ...],
    path: Path,
) -> None:
    usable = tuple(item for item in intervals if item.raw_stack_efficiency is not None)
    lengths = np.asarray([item.frame_count for item in usable])
    spans_ms = np.asarray([item.observed_span_s * 1e3 for item in usable])
    exact = np.asarray([item.median_exact_coherence for item in usable])
    raw = np.asarray([float(item.raw_stack_efficiency) for item in usable])
    tracked = np.asarray([float(item.tracked_stack_efficiency) for item in usable])
    aligned = np.asarray([float(item.self_aligned_stack_efficiency) for item in usable])
    raw_gain_db = 10 * np.log10(np.maximum(lengths * raw, 1e-20))
    tracked_gain_db = 10 * np.log10(np.maximum(lengths * tracked, 1e-20))
    aligned_gain_db = 10 * np.log10(np.maximum(lengths * aligned, 1e-20))

    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.2), constrained_layout=True)
        scatter = axes[0, 0].scatter(
            exact,
            spans_ms,
            c=lengths,
            cmap="viridis",
            s=30,
            alpha=0.72,
            linewidths=0,
        )
        axes[0, 0].set_xlabel("median exact-pilot coherence in interval")
        axes[0, 0].set_ylabel("observed phase-lock span (ms)")
        axes[0, 0].set_title(
            "A · Duration remains variable after exposing probe quality",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].grid(True)
        figure.colorbar(scatter, ax=axes[0, 0], label="accepted frames", fraction=0.046)

        limits = (
            min(float(np.min(raw)), float(np.min(tracked))),
            max(float(np.max(raw)), float(np.max(tracked))),
        )
        axes[0, 1].plot(limits, limits, color=INK, linestyle="--", linewidth=0.9)
        comparison = axes[0, 1].scatter(
            raw,
            tracked,
            c=exact,
            cmap="viridis",
            s=24 + 5 * lengths,
            alpha=0.72,
            linewidths=0,
        )
        axes[0, 1].set_xlim(limits)
        axes[0, 1].set_ylim(limits)
        axes[0, 1].set_xlabel("uncorrected channel-stack efficiency")
        axes[0, 1].set_ylabel("causal tracker-phase-corrected efficiency")
        axes[0, 1].set_title(
            "B · Points above the diagonal benefit from causal phase derotation",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].grid(True)
        figure.colorbar(
            comparison,
            ax=axes[0, 1],
            label="median exact-pilot coherence",
            fraction=0.046,
        )

        axes[1, 0].boxplot(
            (raw_gain_db, tracked_gain_db, aligned_gain_db),
            tick_labels=("uncorrected", "causal tracker", "self-aligned ceiling"),
            showfliers=True,
        )
        axes[1, 0].axhline(0, color=INK, linewidth=0.8)
        axes[1, 0].set_ylabel("effective coherent combining gain vs one frame (dB)")
        axes[1, 0].set_title(
            f"C · Combining comparison over {len(usable)} multi-frame lock runs",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].grid(True, axis="y")

        improvement_db = tracked_gain_db - raw_gain_db
        axes[1, 1].axhline(0, color=INK, linewidth=0.8)
        axes[1, 1].scatter(
            exact,
            improvement_db,
            c=lengths,
            cmap="viridis",
            s=26,
            alpha=0.72,
            linewidths=0,
        )
        axes[1, 1].set_xlabel("median exact-pilot coherence in interval")
        axes[1, 1].set_ylabel("causal correction minus uncorrected gain (dB)")
        axes[1, 1].set_title(
            "D · Correction gain is evaluated against interval signal quality",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].grid(True)
        figure.suptitle(
            "Phase correction and coherent probe combination inside accepted runs",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_frequency_run_phase_zooms(detail: DenseTrackingDetail, path: Path) -> None:
    frequency_runs = _frequency_update_runs(detail.frames)
    selected_ids = (2, 3, 5, 9, 20, 31)
    selected = tuple(frequency_runs[index - 1] for index in selected_ids)

    with plt.rc_context(_style()):
        figure, axes = plt.subplots(3, 2, figsize=(15, 13.5), constrained_layout=True)
        for axis, run_id, run in zip(axes.flat, selected_ids, selected, strict=True):
            times = np.asarray([frame.reference_time_s for frame in run])
            measured = np.asarray(
                [frame.absolute_cfo_measurement_hz - frame.model_cfo_hz for frame in run]
            )
            tracked = np.asarray(
                [frame.tracked_absolute_cfo_hz - frame.model_cfo_hz for frame in run]
            )
            phase = np.asarray([frame.phase_update_applied for frame in run])
            resets = np.asarray([frame.phase_reset_detected for frame in run])
            gaps = np.diff(times) > 1.5 / 750
            phase_runs = _strict_phase_update_runs(run)
            longest = max(phase_runs, key=len) if phase_runs else ()
            longest_span_ms = (
                (longest[-1].reference_time_s - longest[0].reference_time_s) * 1e3
                if longest
                else 0.0
            )
            phase_fraction = float(np.mean(phase))
            coverage = len(longest) / len(run) if longest else 0.0
            if phase_fraction >= 0.8 and coverage >= 0.75 and not np.any(gaps):
                classification = "PHASE LOCKED"
                title_color = GREEN
            elif len(longest) >= 5:
                classification = "LOCAL LOCKS / FRAGMENTED"
                title_color = AMBER
            else:
                classification = "NOT PHASE LOCKED"
                title_color = RED

            half_frame_s = 0.5 / 750
            for phase_run in phase_runs:
                if len(phase_run) >= 2:
                    axis.axvspan(
                        phase_run[0].reference_time_s - half_frame_s,
                        phase_run[-1].reference_time_s + half_frame_s,
                        color=GREEN,
                        alpha=0.11,
                        linewidth=0,
                    )
            for index in np.flatnonzero(gaps):
                axis.axvspan(
                    times[index] + half_frame_s,
                    times[index + 1] - half_frame_s,
                    color=GRAY,
                    alpha=0.14,
                    linewidth=0,
                    hatch="//",
                )

            segments = np.split(np.arange(len(run)), np.flatnonzero(gaps) + 1)
            for segment in segments:
                axis.plot(
                    times[segment],
                    tracked[segment],
                    color=AMBER,
                    linewidth=1.25,
                    alpha=0.85,
                )
            axis.scatter(
                times,
                measured,
                s=18,
                color=BLUE,
                alpha=0.56,
                linewidths=0,
            )
            axis.scatter(
                times,
                tracked,
                s=16,
                color=AMBER,
                alpha=0.9,
                linewidths=0,
            )
            axis.scatter(
                times[phase],
                tracked[phase],
                s=42,
                facecolor="none",
                edgecolor=GREEN,
                linewidth=1.2,
            )
            axis.scatter(
                times[~phase],
                tracked[~phase],
                s=30,
                color=RED,
                marker="x",
                linewidth=1.0,
            )
            axis.scatter(
                times[resets],
                tracked[resets],
                s=74,
                facecolor="none",
                edgecolor=RED,
                linewidth=1.25,
            )
            axis.axhline(0, color=INK, linewidth=0.7)
            span_ms = (times[-1] - times[0]) * 1e3
            axis.set_title(
                f"Run {run_id} · {classification} · frequency span {span_ms:.1f} ms",
                loc="left",
                color=title_color,
                fontweight="bold",
            )
            axis.text(
                0.015,
                0.965,
                f"phase {np.count_nonzero(phase)}/{len(run)} · "
                f"longest strict run {len(longest)} frames / {longest_span_ms:.1f} ms · "
                f"resets {np.count_nonzero(resets)}",
                transform=axis.transAxes,
                ha="left",
                va="top",
                fontsize=8.5,
                color=INK,
            )
            axis.set_xlabel("capture time (s)")
            axis.set_ylabel("CFO residual vs frozen model (Hz)")
            axis.grid(True)

        legend = (
            Line2D([], [], color=BLUE, marker="o", linestyle="none", label="independent CFO"),
            Line2D([], [], color=AMBER, linewidth=1.3, label="tracked CFO"),
            Line2D(
                [],
                [],
                color=GREEN,
                marker="o",
                markerfacecolor="none",
                linestyle="none",
                label="phase update accepted",
            ),
            Line2D([], [], color=RED, marker="x", linestyle="none", label="phase rejected"),
            Line2D(
                [],
                [],
                color=RED,
                marker="o",
                markerfacecolor="none",
                linestyle="none",
                markersize=9,
                label="phase reset",
            ),
            Patch(facecolor=GREEN, alpha=0.11, label="strict multi-frame phase lock"),
            Patch(
                facecolor=GRAY,
                alpha=0.14,
                hatch="//",
                label="not evaluated: no retained timing lock",
            ),
        )
        figure.legend(
            handles=legend,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.018),
            ncol=4,
            fontsize=8.8,
        )
        figure.suptitle(
            "Six frequency-run zooms: smooth CFO does not imply continuous carrier phase",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_phase_threshold_zooms(
    threshold_details: tuple[tuple[str, PilotPhaseDopplerTrackingConfig, DenseTrackingDetail], ...],
    path: Path,
) -> None:
    intervals = ((34.08, 34.18), (34.73, 34.81))
    current = threshold_details[1][2]

    with plt.rc_context(_style()):
        figure, axes = plt.subplots(4, 2, figsize=(15, 14.5), constrained_layout=True)
        for column, (start_s, end_s) in enumerate(intervals):
            current_frames = tuple(
                frame for frame in current.frames if start_s <= frame.reference_time_s <= end_s
            )
            times = np.asarray([frame.reference_time_s for frame in current_frames])
            measured = np.asarray(
                [frame.absolute_cfo_measurement_hz - frame.model_cfo_hz for frame in current_frames]
            )
            tracked = np.asarray(
                [frame.tracked_absolute_cfo_hz - frame.model_cfo_hz for frame in current_frames]
            )
            frequency = np.asarray([frame.frequency_update_applied for frame in current_frames])
            phase = np.asarray([frame.phase_update_applied for frame in current_frames])
            gaps = np.diff(times) > 1.5 / 750
            cfo_axis = axes[0, column]
            for index in np.flatnonzero(gaps):
                cfo_axis.axvspan(
                    times[index] + 0.5 / 750,
                    times[index + 1] - 0.5 / 750,
                    color=GRAY,
                    alpha=0.14,
                    linewidth=0,
                    hatch="//",
                )
            segments = np.split(np.arange(len(current_frames)), np.flatnonzero(gaps) + 1)
            for segment in segments:
                selected = segment[frequency[segment]]
                if len(selected):
                    cfo_axis.plot(
                        times[selected],
                        tracked[selected],
                        color=AMBER,
                        linewidth=1.25,
                    )
            cfo_axis.scatter(
                times[frequency],
                measured[frequency],
                s=18,
                color=BLUE,
                alpha=0.55,
                linewidths=0,
            )
            cfo_axis.scatter(
                times[~frequency],
                measured[~frequency],
                s=20,
                color=GRAY,
                marker="x",
                alpha=0.45,
            )
            cfo_axis.scatter(
                times[phase],
                tracked[phase],
                s=40,
                facecolor="none",
                edgecolor=GREEN,
                linewidth=1.2,
            )
            cfo_axis.scatter(
                times[~phase & frequency],
                tracked[~phase & frequency],
                s=28,
                color=RED,
                marker="x",
                linewidth=1.0,
            )
            cfo_axis.axhline(0, color=INK, linewidth=0.7)
            cfo_axis.set_title(
                f"{start_s:.2f}-{end_s:.2f} s · CFO view with phase status",
                loc="left",
                fontweight="bold",
            )
            cfo_axis.set_ylabel("CFO residual vs model (Hz)")
            cfo_axis.set_xlabel("capture time (s)")
            cfo_axis.grid(True)

            for row, (label, config, detail) in enumerate(threshold_details, start=1):
                interval_frames = tuple(
                    frame for frame in detail.frames if start_s <= frame.reference_time_s <= end_s
                )
                interval_times = np.asarray([frame.reference_time_s for frame in interval_frames])
                innovation = np.asarray([frame.phase_innovation_rad for frame in interval_frames])
                accepted = np.asarray([frame.phase_update_applied for frame in interval_frames])
                resets = np.asarray([frame.phase_reset_detected for frame in interval_frames])
                interval_gaps = np.diff(interval_times) > 1.5 / 750
                phase_runs = _strict_phase_update_runs(interval_frames)
                longest = max(phase_runs, key=len) if phase_runs else ()
                longest_span_ms = (
                    (longest[-1].reference_time_s - longest[0].reference_time_s) * 1e3
                    if longest
                    else 0.0
                )
                phase_axis = axes[row, column]
                for index in np.flatnonzero(interval_gaps):
                    phase_axis.axvspan(
                        interval_times[index] + 0.5 / 750,
                        interval_times[index + 1] - 0.5 / 750,
                        color=GRAY,
                        alpha=0.14,
                        linewidth=0,
                        hatch="//",
                    )
                phase_axis.scatter(
                    interval_times[accepted],
                    innovation[accepted],
                    s=23,
                    color=GREEN,
                    linewidths=0,
                )
                phase_axis.scatter(
                    interval_times[~accepted],
                    innovation[~accepted],
                    s=25,
                    color=GRAY,
                    marker="x",
                    alpha=0.65,
                )
                phase_axis.scatter(
                    interval_times[resets],
                    innovation[resets],
                    s=55,
                    facecolor="none",
                    edgecolor=RED,
                    linewidth=1.15,
                )
                phase_axis.axhline(0, color=INK, linewidth=0.7)
                phase_axis.axhline(
                    config.phase_innovation_gate_rad,
                    color=RED,
                    linestyle=":",
                    linewidth=0.8,
                )
                phase_axis.axhline(
                    -config.phase_innovation_gate_rad,
                    color=RED,
                    linestyle=":",
                    linewidth=0.8,
                )
                phase_axis.set_ylim(-math.pi, math.pi)
                phase_axis.set_title(
                    f"{label}: |innovation| <= {config.phase_innovation_gate_rad:.1f} rad, "
                    f"similarity >= {config.minimum_channel_similarity:.2f} · "
                    f"accepted {np.count_nonzero(accepted)}/{len(interval_frames)} · "
                    f"longest {len(longest)} frames/{longest_span_ms:.1f} ms",
                    loc="left",
                    fontweight="bold",
                    fontsize=9.5,
                )
                phase_axis.set_ylabel("wrapped phase innovation (rad)")
                phase_axis.set_xlabel("capture time (s)")
                phase_axis.grid(True)

        legend = (
            Line2D([], [], color=BLUE, marker="o", linestyle="none", label="independent CFO"),
            Line2D([], [], color=AMBER, linewidth=1.3, label="tracked CFO"),
            Line2D([], [], color=GREEN, marker="o", linestyle="none", label="phase accepted"),
            Line2D([], [], color=GRAY, marker="x", linestyle="none", label="phase rejected"),
            Line2D(
                [],
                [],
                color=RED,
                marker="o",
                markerfacecolor="none",
                linestyle="none",
                markersize=9,
                label="phase reset",
            ),
            Patch(
                facecolor=GRAY,
                alpha=0.14,
                hatch="//",
                label="not evaluated: no retained timing lock",
            ),
        )
        figure.legend(
            handles=legend,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.012),
            ncol=3,
            fontsize=8.8,
        )
        figure.suptitle(
            "Two requested zooms with causal phase-lock threshold sensitivity",
            fontsize=15,
            fontweight="bold",
        )
        _save(figure, path)


def _plot_offline_phase_continuity_audit(
    detail: OfflinePhaseContinuityDetail,
    path: Path,
) -> None:
    with plt.rc_context(_style()):
        figure, axes = plt.subplots(2, 2, figsize=(13.2, 8.7), constrained_layout=True)
        frames = detail.frames
        times = np.asarray([frame.reference_time_s for frame in frames])
        retained = np.asarray(
            [frame.retained_by_dense_pass for frame in frames],
            dtype=bool,
        )
        model = np.asarray([frame.model_cfo_hz for frame in frames])
        measured = np.asarray([frame.measured_cfo_hz for frame in frames])
        fitted = np.asarray([frame.frequency_fit_cfo_hz for frame in frames])

        axis = axes[0, 0]
        axis.scatter(
            times[retained],
            (measured - model)[retained],
            s=28,
            color=BLUE,
            label=f"retained timing epochs ({np.count_nonzero(retained)})",
            zorder=3,
        )
        axis.scatter(
            times[~retained],
            (measured - model)[~retained],
            s=42,
            marker="D",
            facecolors="none",
            edgecolors=AMBER,
            linewidths=1.3,
            label=f"inferred lattice epochs ({np.count_nonzero(~retained)})",
            zorder=4,
        )
        axis.plot(times, fitted - model, color=INK, linewidth=1.5, label="robust CFO fit")
        axis.axhline(0, color=INK, linewidth=0.8)
        axis.set_title("A · The omitted frames contain equally strong CFO measurements")
        axis.set_ylabel("CFO residual vs frozen model (Hz)")
        axis.legend(fontsize=8, loc="upper left")
        axis.grid(True)

        axis = axes[0, 1]
        cubic = np.asarray([frame.cubic_batch_phase_residual_rad for frame in frames])
        pi_ambiguity = np.asarray([frame.pi_ambiguity_batch_phase_residual_rad for frame in frames])
        axis.scatter(times, cubic, s=24, color=GRAY, alpha=0.65, label="ordinary cubic")
        axis.scatter(
            times,
            pi_ambiguity,
            s=28,
            color=GREEN,
            label="cubic with binary π state",
        )
        axis.axhline(0, color=INK, linewidth=0.8)
        axis.axhline(1.2, color=RED, linestyle=":", linewidth=1)
        axis.axhline(-1.2, color=RED, linestyle=":", linewidth=1)
        axis.set_ylim(-math.pi, math.pi)
        axis.set_title("B · A binary π state exposes a smooth phase trajectory")
        axis.set_ylabel("wrapped residual phase (rad)")
        axis.legend(fontsize=8, loc="upper left")
        axis.grid(True)

        axis = axes[1, 0]
        implied = np.asarray(
            [
                np.nan
                if frame.phase_implied_frequency_error_hz is None
                else frame.phase_implied_frequency_error_hz
                for frame in frames
            ]
        )
        pi_corrected = np.asarray(
            [
                np.nan
                if frame.pi_corrected_phase_implied_frequency_error_hz is None
                else frame.pi_corrected_phase_implied_frequency_error_hz
                for frame in frames
            ]
        )
        typical_uncertainty = detail.median_frequency_uncertainty_hz
        axis.axhspan(
            -typical_uncertainty,
            typical_uncertainty,
            color=GREEN,
            alpha=0.16,
            label=f"median frame-slope uncertainty ±{typical_uncertainty:.0f} Hz",
        )
        axis.scatter(
            times[1:],
            implied[1:],
            s=24,
            color=RED,
            alpha=0.45,
            label="ordinary phase",
        )
        axis.scatter(
            times[1:],
            pi_corrected[1:],
            s=26,
            color=GREEN,
            label="after π state + common bias",
        )
        axis.axhline(0, color=INK, linewidth=0.8)
        axis.set_title("C · The apparent CFO contradiction is mostly a π ambiguity")
        axis.set_xlabel("capture time (s)")
        axis.set_ylabel("phase-implied CFO error (Hz)")
        axis.legend(fontsize=8, loc="upper left")
        axis.grid(True)

        axis = axes[1, 1]
        labels = (
            "raw\nchannel",
            "integrated\nCFO",
            "ordinary\ncubic",
            "held-out\nbinary π",
            "per-frame\nnuisance*",
        )
        values = (
            detail.raw_stack_efficiency,
            detail.frequency_only_stack_efficiency,
            detail.cubic_batch_stack_efficiency,
            min(
                detail.even_to_odd_heldout_stack_efficiency,
                detail.odd_to_even_heldout_stack_efficiency,
            ),
            detail.per_frame_nuisance_stack_efficiency,
        )
        colors = (GRAY, BLUE, AMBER, GREEN, GREEN)
        bars = axis.bar(labels, values, color=colors, width=0.68)
        axis.bar_label(bars, labels=[f"{value:.2f}" for value in values], padding=3, fontsize=9)
        axis.axhline(1, color=INK, linewidth=0.8)
        axis.set_ylim(0, 1.08)
        axis.set_title("D · The binary-state batch nearly reaches the oracle ceiling")
        axis.set_ylabel("coherent stack efficiency")
        axis.grid(True, axis="y")
        axis.text(
            0.02,
            0.03,
            "*diagnostic ceiling, not a cross-frame phase lock",
            transform=axis.transAxes,
            fontsize=8,
            color=INK,
        )

        axes[0, 0].set_xlim(detail.start_s, detail.end_s)
        axes[0, 1].set_xlim(detail.start_s, detail.end_s)
        axes[1, 0].set_xlim(detail.start_s, detail.end_s)
        figure.suptitle(
            "Offline audit of the visually smooth 34.73–34.81 s frequency run",
            fontsize=15,
            fontweight="bold",
        )
        worst_heldout_rms = max(
            detail.even_to_odd_heldout_phase_residual_rms_rad,
            detail.odd_to_even_heldout_phase_residual_rms_rad,
        )
        figure.text(
            0.5,
            -0.012,
            (
                f"All {detail.quality_frame_count}/{detail.inferred_frame_count} inferred frames "
                f"pass pilot quality; timing-corrected channel similarity median "
                f"{detail.median_timing_corrected_channel_similarity:.3f}.  "
                f"π-aware batch residual RMS "
                f"{detail.pi_ambiguity_batch_phase_residual_rms_rad:.3f} rad; "
                f"worst held-out RMS {worst_heldout_rms:.3f} rad."
            ),
            ha="center",
            fontsize=9,
            color=INK,
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
        "phase_tracking_cfo_hz": item.phase_tracking_cfo_hz,
        "phase_tracking_error_vs_model_hz": item.phase_tracking_error_vs_model_hz,
        "phase_tracking_reset_count": item.phase_tracking_reset_count,
        "phase_tracking_update_count": item.phase_tracking_update_count,
        "frames": [_serializable_frame(frame) for frame in item.frames],
    }


def _serializable_dense_tracking(detail: DenseTrackingDetail) -> dict[str, Any]:
    frames = detail.frames
    update_mask = np.asarray([frame.frequency_update_applied for frame in frames])
    model = np.asarray([frame.model_cfo_hz for frame in frames])
    measured_error = np.asarray([frame.absolute_cfo_measurement_hz for frame in frames]) - model
    tracked_error = np.asarray([frame.tracked_absolute_cfo_hz for frame in frames]) - model
    glrt_error = np.asarray([frame.glrt64_cfo_hz for frame in frames]) - model
    rate_error = np.asarray([frame.tracked_doppler_rate_hz_s for frame in frames]) - np.asarray(
        [frame.model_doppler_rate_hz_s for frame in frames]
    )
    consecutive = 0
    longest = 0
    run_start_s = 0.0
    longest_span_s = 0.0
    for frame in frames:
        if frame.phase_update_applied:
            if consecutive == 0:
                run_start_s = frame.reference_time_s
            consecutive += 1
            longest_span_s = max(longest_span_s, frame.reference_time_s - run_start_s)
        else:
            consecutive = 0
        longest = max(longest, consecutive)
    segment_spans = []
    segment_updates = []
    for segment_id in sorted({frame.phase_segment_id for frame in frames}):
        members = [frame for frame in frames if frame.phase_segment_id == segment_id]
        segment_spans.append(members[-1].reference_time_s - members[0].reference_time_s)
        segment_updates.append(sum(frame.phase_update_applied for frame in members))
    return {
        "source_window_count": detail.source_window_count,
        "requested_frame_count": detail.requested_frame_count,
        "returned_frame_count": len(frames),
        "frequency_update_count": detail.frequency_update_count,
        "processing_elapsed_s": detail.processing_elapsed_s,
        "processing_ms_per_requested_frame": (
            1_000 * detail.processing_elapsed_s / detail.requested_frame_count
        ),
        "phase_update_count": detail.phase_update_count,
        "phase_reset_count": detail.phase_reset_count,
        "phase_segment_count": detail.phase_segment_count,
        "quality_frame_count": sum(
            frame.exact_coherence >= 0.02 and frame.coherence_margin >= 0 for frame in frames
        ),
        "longest_consecutive_phase_update_run_frames": longest,
        "longest_consecutive_phase_update_span_s": longest_span_s,
        "maximum_phase_segment_span_s": max(segment_spans),
        "maximum_phase_updates_in_one_segment": max(segment_updates),
        "median_phase_updates_per_segment": float(np.median(segment_updates)),
        "accepted_phase_innovation_abs_rad": _error_summary(
            np.abs(
                np.asarray(
                    [frame.phase_innovation_rad for frame in frames if frame.phase_update_applied]
                )
            )
        ),
        "accepted_update_comparison": {
            "independent_pilot_frame_error_hz": _error_summary(measured_error[update_mask]),
            "phase_doppler_tracking_error_hz": _error_summary(tracked_error[update_mask]),
            "source_glrt64_error_hz": _error_summary(glrt_error[update_mask]),
            "tracked_doppler_rate_error_hz_s": _error_summary(rate_error[update_mask]),
        },
        "frames": [
            {name: getattr(frame, name) for name in frame.__dataclass_fields__} for frame in frames
        ],
    }


def _serializable_phase_lock_intervals(
    intervals: tuple[PhaseLockInterval, ...],
) -> dict[str, Any]:
    usable = tuple(item for item in intervals if item.raw_stack_efficiency is not None)
    lengths = np.asarray([item.frame_count for item in usable])
    raw = np.asarray([float(item.raw_stack_efficiency) for item in usable])
    tracked = np.asarray([float(item.tracked_stack_efficiency) for item in usable])
    aligned = np.asarray([float(item.self_aligned_stack_efficiency) for item in usable])
    raw_gain_db = 10 * np.log10(np.maximum(lengths * raw, 1e-20))
    tracked_gain_db = 10 * np.log10(np.maximum(lengths * tracked, 1e-20))
    aligned_gain_db = 10 * np.log10(np.maximum(lengths * aligned, 1e-20))
    start_intervals = tuple(item for item in intervals if item.start_interval_s is not None)
    within_intervals = tuple(
        item for item in start_intervals if not bool(item.crosses_sampling_gap)
    )
    within_periods = np.rint(
        np.asarray([float(item.start_interval_s) for item in within_intervals]) * 750
    ).astype(int)
    exact_coherence = np.asarray([item.median_exact_coherence for item in intervals])
    frame_counts = np.asarray([item.frame_count for item in intervals], dtype=float)
    spans_ms = np.asarray([item.observed_span_s * 1e3 for item in intervals])
    return {
        "observed_run_count": len(intervals),
        "singleton_run_count": sum(item.frame_count == 1 for item in intervals),
        "multi_frame_run_count": len(usable),
        "start_interval_count": len(start_intervals),
        "start_intervals_crossing_sampling_gap": sum(
            bool(item.crosses_sampling_gap) for item in start_intervals
        ),
        "start_intervals_within_sampled_stretch": sum(
            not bool(item.crosses_sampling_gap) for item in start_intervals
        ),
        "within_sampled_stretch_start_interval_periods": {
            "two_frame_period_count": int(np.count_nonzero(within_periods == 2)),
            "two_frame_period_fraction": float(np.mean(within_periods == 2)),
            "three_frame_period_count": int(np.count_nonzero(within_periods == 3)),
            "three_frame_period_fraction": float(np.mean(within_periods == 3)),
        },
        "probe_quality_association": {
            "exact_coherence_vs_frame_count_pearson_r": float(
                np.corrcoef(exact_coherence, frame_counts)[0, 1]
            ),
            "exact_coherence_vs_observed_span_pearson_r": float(
                np.corrcoef(exact_coherence, spans_ms)[0, 1]
            ),
        },
        "observed_span_ms": _error_summary(
            np.asarray([item.observed_span_s * 1e3 for item in intervals])
        ),
        "frame_count": _error_summary(
            np.asarray([item.frame_count for item in intervals], dtype=float)
        ),
        "multi_frame_stack_efficiency": {
            "uncorrected": _error_summary(raw),
            "causal_tracker_phase_corrected": _error_summary(tracked),
            "self_aligned_ceiling": _error_summary(aligned),
        },
        "multi_frame_effective_combining_gain_db": {
            "uncorrected": _error_summary(raw_gain_db),
            "causal_tracker_phase_corrected": _error_summary(tracked_gain_db),
            "self_aligned_ceiling": _error_summary(aligned_gain_db),
            "causal_tracker_minus_uncorrected": _error_summary(tracked_gain_db - raw_gain_db),
            "fraction_improved_by_causal_tracker_phase": float(np.mean(tracked > raw)),
        },
        "intervals": [
            {name: getattr(item, name) for name in item.__dataclass_fields__} for item in intervals
        ],
    }


def _serializable_threshold_sensitivity(
    threshold_details: tuple[tuple[str, PilotPhaseDopplerTrackingConfig, DenseTrackingDetail], ...],
) -> dict[str, Any]:
    intervals = ((34.08, 34.18), (34.73, 34.81))
    configurations = []
    for label, config, detail in threshold_details:
        interval_results = []
        for start_s, end_s in intervals:
            frames = tuple(
                frame for frame in detail.frames if start_s <= frame.reference_time_s <= end_s
            )
            runs = _strict_phase_update_runs(frames)
            longest = max(runs, key=len) if runs else ()
            interval_results.append(
                {
                    "start_s": start_s,
                    "end_s": end_s,
                    "evaluated_frame_count": len(frames),
                    "phase_update_count": sum(frame.phase_update_applied for frame in frames),
                    "phase_reset_count": sum(frame.phase_reset_detected for frame in frames),
                    "longest_strict_phase_run_frames": len(longest),
                    "longest_strict_phase_run_span_s": (
                        longest[-1].reference_time_s - longest[0].reference_time_s
                        if longest
                        else 0.0
                    ),
                }
            )
        configurations.append(
            {
                "label": label,
                "minimum_channel_similarity": config.minimum_channel_similarity,
                "phase_innovation_gate_rad": config.phase_innovation_gate_rad,
                "maximum_phase_coast_s": config.maximum_phase_coast_s,
                "phase_reset_after_failures": config.phase_reset_after_failures,
                "global_phase_update_count": detail.phase_update_count,
                "global_phase_reset_count": detail.phase_reset_count,
                "intervals": interval_results,
            }
        )
    return {"configurations": configurations}


def _serializable_offline_phase_continuity(
    detail: OfflinePhaseContinuityDetail,
) -> dict[str, Any]:
    return {
        name: (
            [
                {
                    frame_name: getattr(frame, frame_name)
                    for frame_name in frame.__dataclass_fields__
                }
                for frame in detail.frames
            ]
            if name == "frames"
            else getattr(detail, name)
        )
        for name in detail.__dataclass_fields__
    }


def _error_summary(values: np.ndarray) -> dict[str, float]:
    median = float(np.median(values))
    return {
        "median": median,
        "mad": float(np.median(np.abs(values - median))),
        "rms": float(np.sqrt(np.mean(values**2))),
    }


def _write_evidence(
    path: Path,
    *,
    args: argparse.Namespace,
    trajectory: FrozenTrajectory,
    accepted_count: int,
    details: tuple[WindowDetail, ...],
    dense_tracking: DenseTrackingDetail,
    phase_lock_intervals: tuple[PhaseLockInterval, ...],
    threshold_details: tuple[tuple[str, PilotPhaseDopplerTrackingConfig, DenseTrackingDetail], ...],
    offline_phase_continuity: OfflinePhaseContinuityDetail,
    figures: tuple[Path, ...],
) -> None:
    frames = tuple(frame for item in details for frame in item.frames)
    tracked_pairs = tuple(
        (item, frame)
        for item in details
        for frame in item.frames
        if frame.tracked_absolute_cfo_hz is not None and frame.tracked_doppler_rate_hz_s is not None
    )
    tracked_frames = tuple(frame for _, frame in tracked_pairs)
    phase_error = np.asarray([item.phase_error_vs_model_hz for item in details])
    glrt_error = np.asarray([item.glrt64_error_vs_model_hz for item in details])
    phase_median = float(np.median(phase_error))
    glrt_median = float(np.median(glrt_error))
    tracked_model = np.asarray([frame.model_cfo_hz for frame in tracked_frames])
    frame_slope_error = (
        np.asarray([frame.absolute_cfo_hz for frame in tracked_frames]) - tracked_model
    )
    tracked_error = (
        np.asarray([float(frame.tracked_absolute_cfo_hz) for frame in tracked_frames])
        - tracked_model
    )
    repeated_glrt = np.asarray([item.glrt64_cfo_hz for item, _ in tracked_pairs])
    repeated_glrt_error = repeated_glrt - tracked_model
    frame_times = np.asarray([frame.reference_time_s for frame in tracked_frames])
    tracked_rate_error = np.asarray(
        [float(frame.tracked_doppler_rate_hz_s) for frame in tracked_frames]
    ) - np.asarray(trajectory.doppler_rate_hz_s(frame_times))
    document = {
        "schema_version": 2,
        "algorithm": "edge-pilot-phase-slope-and-tracking-report-v2",
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
            "per_frame_comparison": {
                "independent_phase_slope_error_hz": _error_summary(frame_slope_error),
                "phase_doppler_tracking_error_hz": _error_summary(tracked_error),
                "glrt64_held_over_window_error_hz": _error_summary(repeated_glrt_error),
                "tracked_doppler_rate_error_hz_s": _error_summary(tracked_rate_error),
            },
            "tracking": {
                "comparable_frame_count": len(tracked_frames),
                "phase_update_count": sum(frame.phase_update_applied for frame in tracked_frames),
                "frequency_update_count": sum(
                    frame.frequency_update_applied for frame in tracked_frames
                ),
                "phase_reset_count": sum(frame.phase_reset_detected for frame in tracked_frames),
                "phase_segment_count": sum(1 + item.phase_tracking_reset_count for item in details),
            },
        },
        "windows": [_serializable_window(item) for item in details],
        "dense_tracking": _serializable_dense_tracking(dense_tracking),
        "phase_lock_intervals": _serializable_phase_lock_intervals(phase_lock_intervals),
        "phase_threshold_sensitivity": _serializable_threshold_sensitivity(threshold_details),
        "offline_phase_continuity": _serializable_offline_phase_continuity(
            offline_phase_continuity
        ),
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
    dense_tracking = _analyze_dense_locked_frames(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        probe_samples=probe_samples,
        edge=StarlinkEdge(args.edge),
        locked_windows=all_accepted,
        trajectory=trajectory,
    )
    strict_config = PilotPhaseDopplerTrackingConfig(
        minimum_channel_similarity=0.80,
        phase_innovation_gate_rad=0.60,
    )
    current_config = PilotPhaseDopplerTrackingConfig()
    lenient_config = PilotPhaseDopplerTrackingConfig(
        minimum_channel_similarity=0.50,
        phase_innovation_gate_rad=2.00,
    )
    threshold_details = (
        (
            "Strict",
            strict_config,
            _analyze_dense_locked_frames(
                iq,
                raw_sample_start=raw_start,
                sample_rate_hz=sample_rate_hz,
                probe_samples=probe_samples,
                edge=StarlinkEdge(args.edge),
                locked_windows=all_accepted,
                trajectory=trajectory,
                tracking_config=strict_config,
            ),
        ),
        ("Current", current_config, dense_tracking),
        (
            "Lenient",
            lenient_config,
            _analyze_dense_locked_frames(
                iq,
                raw_sample_start=raw_start,
                sample_rate_hz=sample_rate_hz,
                probe_samples=probe_samples,
                edge=StarlinkEdge(args.edge),
                locked_windows=all_accepted,
                trajectory=trajectory,
                tracking_config=lenient_config,
            ),
        ),
    )
    phase_lock_intervals = _analyze_phase_lock_intervals(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        edge=StarlinkEdge(args.edge),
        detail=dense_tracking,
    )
    offline_phase_continuity = _offline_phase_continuity_audit(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        edge=StarlinkEdge(args.edge),
        trajectory=trajectory,
        dense_tracking=dense_tracking,
    )
    output = args.output_root
    figures = (
        output / "raw-iq-context.png",
        output / "anchor-phase-evolution.png",
        output / "window-phase-gallery.png",
        output / "window-alignment.png",
        output / "residual-diagnostics.png",
        output / "phase-doppler-tracking.png",
        output / "dense-sampling-geometry.png",
        output / "phase-coherence-detail.png",
        output / "phase-lock-timing-distribution.png",
        output / "phase-lock-quality-correction.png",
        output / "frequency-run-phase-zoom-six.png",
        output / "phase-threshold-zoom-two.png",
        output / "offline-phase-continuity-audit.png",
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
    _plot_dense_phase_doppler_tracking(dense_tracking, figures[5])
    _plot_dense_sampling_geometry(dense_tracking, figures[6])
    _plot_phase_coherence_detail(dense_tracking, figures[7])
    _plot_phase_lock_timing_distribution(phase_lock_intervals, figures[8])
    _plot_phase_lock_quality_correction(phase_lock_intervals, figures[9])
    _plot_frequency_run_phase_zooms(dense_tracking, figures[10])
    _plot_phase_threshold_zooms(threshold_details, figures[11])
    _plot_offline_phase_continuity_audit(offline_phase_continuity, figures[12])
    _write_evidence(
        output / "detailed-results.json",
        args=args,
        trajectory=trajectory,
        accepted_count=len(all_accepted),
        details=details,
        dense_tracking=dense_tracking,
        phase_lock_intervals=phase_lock_intervals,
        threshold_details=threshold_details,
        offline_phase_continuity=offline_phase_continuity,
        figures=figures,
    )
    print(
        f"rendered {len(figures)} measured-data figures from {len(details)} windows and "
        f"{sum(len(item.frames) for item in details)} sparse frames plus "
        f"{len(dense_tracking.frames)} dense locked frames"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
