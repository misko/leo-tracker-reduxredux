#!/usr/bin/env python3
"""Test whether sub-second pilot-CFO jumps move with analysis windows.

The default experiment is pinned to the four-second worked interval in the
piecewise pilot Doppler-rate report.  It reads digest-verified raw IQ once,
reruns the frame-local known-pilot estimator on four shifted 20 ms grids, and
then returns to fixed 100 ms IQ intervals around the strongest apparent
between-window jumps.  The long-window control follows both neighboring timing
lattices through the same samples and tests a smooth line against a frequency
step.  Recording and analysis roots are read-only.
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
import matplotlib.pyplot as plt

from leo.analysis.qam import analyze_pilot_phase_slope
from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.local_doppler import (
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
)
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
ANALYSIS_SCOPE = "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
BRANCH_PREFIX = "sha256:5852a936"
DEFAULT_ANALYSIS_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "capture-438ad263e01048ef82f660975ec55a08/scientific/path-standard/"
    + ANALYSIS_SCOPE
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_470384_shifted_pilot_grid")
GRID_OFFSETS_MS = (0.0, 5.0, 10.0, 12.5)
BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
RED = "#c44e52"
PURPLE = "#7f62a6"
INK = "#193549"
GRAY = "#728694"


@dataclass(frozen=True, slots=True)
class FrozenTrajectory:
    coefficients_hz: tuple[float, ...]
    reference_time_s: float
    trajectory_id: str
    branch_id: str

    def frequency_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = np.polyval(self.coefficients_hz, np.asarray(time_s) - self.reference_time_s)
        return float(value) if np.ndim(value) == 0 else value


@dataclass(frozen=True, slots=True)
class SourceWindow:
    index: int
    detection_time_s: float
    probe_sample_start: int
    local_epoch_sample: int
    glrt64_cfo_hz: float
    glrt64_margin: float
    candidate_rank: int

    @property
    def aligned_sample_start(self) -> int:
        return self.probe_sample_start + self.local_epoch_sample


@dataclass(frozen=True, slots=True)
class FrameMeasurement:
    source_index: int
    frame_start_sample: int
    reference_time_s: float
    absolute_cfo_hz: float
    frequency_uncertainty_hz: float
    exact_coherence: float
    control_coherence: float
    coherence_margin: float


@dataclass(frozen=True, slots=True)
class WindowFit:
    source_index: int
    grid_offset_ms: float
    start_time_s: float
    reference_time_s: float
    supported_frame_count: int
    complete_frame_count: int
    supported_frame_fraction: float
    maximum_supported_gap_s: float | None
    median_exact_coherence: float | None
    median_coherence_margin: float | None
    cfo_at_reference_hz: float
    frozen_cfo_at_reference_hz: float
    carrier_bias_at_reference_hz: float
    local_rate_hz_s: float
    local_rate_sigma_hz_s: float | None
    line_rms_hz: float
    held_out_rms_hz: float | None
    direct_quality_qualified: bool
    direct_quality_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PairStep:
    right_source_index: int
    left_source_index: int
    grid_offset_ms: float
    midpoint_time_s: float
    center_separation_s: float
    inferred_step_hz: float
    conditional_sigma_hz: float


@dataclass(frozen=True, slots=True)
class WeightedLine:
    reference_time_s: float
    intercept_hz: float
    slope_hz_s: float
    chi_square: float
    intercept_variance_hz2: float
    intercept_slope_covariance_hz2_s: float
    slope_variance_hz2_s2: float

    def value_hz(self, time_s: float | np.ndarray) -> float | np.ndarray:
        value = self.intercept_hz + self.slope_hz_s * (
            np.asarray(time_s) - self.reference_time_s
        )
        return float(value) if np.ndim(value) == 0 else value

    def prediction_sigma_hz(self, time_s: float) -> float:
        offset_s = time_s - self.reference_time_s
        variance = (
            self.intercept_variance_hz2
            + 2 * offset_s * self.intercept_slope_covariance_hz2_s
            + offset_s**2 * self.slope_variance_hz2_s2
        )
        return math.sqrt(max(variance, 0.0))


@dataclass(frozen=True, slots=True)
class StepModel:
    frame_count: int
    smooth_bic: float
    scanned_step_bic: float
    scanned_delta_bic: float
    scanned_step_time_s: float
    scanned_step_hz: float
    scanned_step_sigma_hz: float
    scanned_near_best_start_s: float
    scanned_near_best_end_s: float
    fixed_step_bic: float
    fixed_delta_bic: float
    fixed_step_time_s: float
    fixed_step_hz: float
    fixed_step_sigma_hz: float


@dataclass(frozen=True, slots=True)
class LatticeAudit:
    source_index: int
    role: str
    timing_offset_from_other_us: float
    frame_count: int
    first_supported_reference_time_s: float
    last_supported_reference_time_s: float
    median_exact_coherence: float
    median_coherence_margin: float
    smooth_line: WeightedLine
    robust_line_rms_hz: float
    cfo_at_nominal_boundary_hz: float
    cfo_at_nominal_boundary_sigma_hz: float
    alternate_seed_cfo_at_boundary_hz: float
    alternate_seed_difference_hz: float
    step_model: StepModel
    frames: tuple[FrameMeasurement, ...]


@dataclass(frozen=True, slots=True)
class BoundaryAudit:
    rank: int
    nominal_boundary_time_s: float
    pair_step_hz: float
    pair_step_conditional_sigma_hz: float
    previous: LatticeAudit | None
    current: LatticeAudit | None
    boundary_mode_separation_hz: float | None
    boundary_mode_separation_sigma_hz: float | None
    separation_minus_pair_step_hz: float | None
    handoff_bracket_start_s: float | None
    handoff_bracket_end_s: float | None
    handoff_bracket_width_ms: float | None
    handoff_midpoint_minus_nominal_ms: float | None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-root", type=Path, default=DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--session-id", default=SESSION_ID)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--control-receiver", type=int, default=1)
    parser.add_argument("--edge", choices=("lower", "upper"), default="upper")
    parser.add_argument("--start-s", type=float, default=33.7)
    parser.add_argument("--end-s", type=float, default=37.7)
    parser.add_argument("--minimum-glrt64-margin", type=float, default=0.05)
    parser.add_argument("--maximum-model-error-hz", type=float, default=2_500.0)
    parser.add_argument("--boundary-count", type=int, default=12)
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
    return digest.hexdigest()


def _trajectory(document: dict[str, Any]) -> FrozenTrajectory:
    matches = [
        item
        for item in document["trajectories"]
        if str(item["branch_id"]).startswith(BRANCH_PREFIX)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one target branch, found {len(matches)}")
    item = matches[0]
    return FrozenTrajectory(
        coefficients_hz=tuple(float(value) for value in item["absolute_coefficients_hz"]),
        reference_time_s=float(item["reference_time_s"]),
        trajectory_id=str(item["trajectory_id"]),
        branch_id=str(item["branch_id"]),
    )


def _glrt64(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def _source_windows(
    scan: dict[str, Any],
    trajectory: FrozenTrajectory,
    *,
    start_s: float,
    end_s: float,
    minimum_margin: float,
    maximum_model_error_hz: float,
) -> tuple[SourceWindow, ...]:
    selected: list[SourceWindow] = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s <= end_s:
            continue
        model_hz = float(trajectory.frequency_hz(time_s))
        eligible = []
        for candidate in detection["candidates"]:
            score = _glrt64(candidate)
            if float(score["margin"]) < minimum_margin:
                continue
            error_hz = abs(float(score["tracking_cfo_hz"]) - model_hz)
            eligible.append((error_hz, int(candidate["rank"]), candidate, score))
        if not eligible:
            continue
        error_hz, _rank, candidate, score = min(eligible, key=lambda item: (item[0], item[1]))
        if error_hz > maximum_model_error_hz:
            continue
        selected.append(
            SourceWindow(
                index=len(selected),
                detection_time_s=time_s,
                probe_sample_start=int(detection["sample_start"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                glrt64_cfo_hz=float(score["tracking_cfo_hz"]),
                glrt64_margin=float(score["margin"]),
                candidate_rank=int(candidate["rank"]),
            )
        )
    return tuple(selected)


def _complex_receiver(values: np.ndarray, receiver_position: int = 0) -> np.ndarray:
    if values.ndim != 3 or values.shape[2] != 2:
        raise ValueError("CI16 data must have shape (samples, receivers, 2)")
    if not 0 <= receiver_position < values.shape[1]:
        raise ValueError("receiver position lies outside CI16 data")
    return (
        values[:, receiver_position, 0].astype(np.float64)
        + 1j * values[:, receiver_position, 1].astype(np.float64)
    ) / (2**15)


def _epoch_for_shifted_start(
    source: SourceWindow,
    requested_start_sample: int,
    sample_rate_hz: float,
) -> int:
    """Return the first source-lattice frame at or after a new window start."""

    period_samples = sample_rate_hz / 750.0
    source_epoch = source.aligned_sample_start
    step = math.ceil((requested_start_sample - source_epoch) / period_samples - 1e-12)
    absolute_epoch = source_epoch + round(step * period_samples)
    relative_epoch = absolute_epoch - requested_start_sample
    if relative_epoch < 0:
        raise ValueError("shifted lattice epoch precedes requested window")
    return relative_epoch


def _quality_frames(
    result: Any,
    *,
    source_index: int,
    absolute_window_start: int,
    sample_rate_hz: float,
) -> tuple[FrameMeasurement, ...]:
    return tuple(
        FrameMeasurement(
            source_index=source_index,
            frame_start_sample=absolute_window_start + int(frame.frame_start_sample),
            reference_time_s=(absolute_window_start + float(frame.reference_sample))
            / sample_rate_hz,
            absolute_cfo_hz=float(frame.absolute_cfo_hz),
            frequency_uncertainty_hz=float(frame.frequency_uncertainty_hz),
            exact_coherence=float(frame.exact_coherence),
            control_coherence=float(frame.control_coherence),
            coherence_margin=float(frame.coherence_margin),
        )
        for frame in result.frames
        if frame.exact_coherence >= 0.02
        and frame.coherence_margin >= 0.0
        and math.isfinite(frame.absolute_cfo_hz)
        and math.isfinite(frame.frequency_uncertainty_hz)
    )


def _fit_window(
    frames: tuple[FrameMeasurement, ...],
    *,
    source_index: int,
    grid_offset_ms: float,
    start_time_s: float,
    complete_frame_count: int,
    trajectory: FrozenTrajectory,
) -> WindowFit | None:
    times = np.asarray([frame.reference_time_s for frame in frames], dtype=float)
    frequencies = np.asarray([frame.absolute_cfo_hz for frame in frames], dtype=float)
    fit = frequency_line(times, frequencies)
    if fit is None:
        return None
    held_out = interleaved_held_out_rms(times, frequencies)
    gaps = np.diff(times)
    maximum_gap = float(np.max(gaps)) if gaps.size else None
    fraction = len(frames) / complete_frame_count if complete_frame_count else 0.0
    failures = []
    if fraction < 0.75:
        failures.append("supported frame coverage below 75%")
    if maximum_gap is None or maximum_gap > 0.0041:
        failures.append("supported frame gap exceeds 4.1 ms")
    if fit.residual_rms_hz > 75.0:
        failures.append("frequency-line RMS exceeds 75 Hz")
    if held_out is None or held_out > 100.0:
        failures.append("interleaved held-out RMS exceeds 100 Hz")
    reference_time_s = fit.reference_time_s
    frozen_hz = float(trajectory.frequency_hz(reference_time_s))
    return WindowFit(
        source_index=source_index,
        grid_offset_ms=grid_offset_ms,
        start_time_s=start_time_s,
        reference_time_s=reference_time_s,
        supported_frame_count=len(frames),
        complete_frame_count=complete_frame_count,
        supported_frame_fraction=fraction,
        maximum_supported_gap_s=maximum_gap,
        median_exact_coherence=(
            float(np.median([frame.exact_coherence for frame in frames])) if frames else None
        ),
        median_coherence_margin=(
            float(np.median([frame.coherence_margin for frame in frames])) if frames else None
        ),
        cfo_at_reference_hz=fit.intercept_at_reference_hz,
        frozen_cfo_at_reference_hz=frozen_hz,
        carrier_bias_at_reference_hz=fit.intercept_at_reference_hz - frozen_hz,
        local_rate_hz_s=fit.slope_hz_per_s,
        local_rate_sigma_hz_s=line_slope_sigma(times, fit),
        line_rms_hz=fit.residual_rms_hz,
        held_out_rms_hz=held_out,
        direct_quality_qualified=not failures,
        direct_quality_failures=tuple(failures),
    )


def _pair_steps(
    fits: tuple[WindowFit, ...],
    *,
    maximum_center_separation_s: float = 0.150,
) -> tuple[PairStep, ...]:
    by_source = {item.source_index: item for item in fits if item.direct_quality_qualified}
    output = []
    for right_index in sorted(by_source):
        left_index = right_index - 1
        if left_index not in by_source:
            continue
        left = by_source[left_index]
        right = by_source[right_index]
        separation_s = right.reference_time_s - left.reference_time_s
        if not 0 < separation_s <= maximum_center_separation_s + 1e-12:
            continue
        midpoint_s = 0.5 * (left.reference_time_s + right.reference_time_s)
        left_hz = left.cfo_at_reference_hz + left.local_rate_hz_s * (
            midpoint_s - left.reference_time_s
        )
        right_hz = right.cfo_at_reference_hz + right.local_rate_hz_s * (
            midpoint_s - right.reference_time_s
        )
        conditional_sigma = math.sqrt(
            left.line_rms_hz**2 / left.supported_frame_count
            + right.line_rms_hz**2 / right.supported_frame_count
        )
        output.append(
            PairStep(
                right_source_index=right_index,
                left_source_index=left_index,
                grid_offset_ms=right.grid_offset_ms,
                midpoint_time_s=midpoint_s,
                center_separation_s=separation_s,
                inferred_step_hz=right_hz - left_hz,
                conditional_sigma_hz=conditional_sigma,
            )
        )
    return tuple(output)


def _weighted_fit(
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
    uncertainties_hz: np.ndarray,
    *,
    step_index: int | None = None,
) -> tuple[np.ndarray, float, np.ndarray, float]:
    reference_time_s = float(np.mean(times_s))
    centered = times_s - reference_time_s
    columns = [np.ones(len(times_s)), centered]
    if step_index is not None:
        columns.append((np.arange(len(times_s)) >= step_index).astype(float))
    design = np.column_stack(columns)
    weights = 1.0 / np.maximum(uncertainties_hz, 5.0) ** 2
    information = design.T @ (weights[:, None] * design)
    covariance = np.linalg.inv(information)
    coefficients = covariance @ (design.T @ (weights * frequencies_hz))
    residuals = frequencies_hz - design @ coefficients
    chi_square = float(np.sum(weights * residuals**2))
    return coefficients, chi_square, covariance, reference_time_s


def _weighted_line(frames: tuple[FrameMeasurement, ...]) -> WeightedLine:
    times = np.asarray([item.reference_time_s for item in frames], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in frames], dtype=float)
    uncertainties = np.asarray([item.frequency_uncertainty_hz for item in frames], dtype=float)
    coefficients, chi_square, covariance, reference_time_s = _weighted_fit(
        times, frequencies, uncertainties
    )
    return WeightedLine(
        reference_time_s=reference_time_s,
        intercept_hz=float(coefficients[0]),
        slope_hz_s=float(coefficients[1]),
        chi_square=chi_square,
        intercept_variance_hz2=float(covariance[0, 0]),
        intercept_slope_covariance_hz2_s=float(covariance[0, 1]),
        slope_variance_hz2_s2=float(covariance[1, 1]),
    )


def _step_candidate(
    times: np.ndarray,
    frequencies: np.ndarray,
    uncertainties: np.ndarray,
    step_index: int,
    *,
    parameter_count: int,
) -> tuple[float, float, float, float]:
    coefficients, chi_square, covariance, _reference = _weighted_fit(
        times, frequencies, uncertainties, step_index=step_index
    )
    step_time_s = 0.5 * (times[step_index - 1] + times[step_index])
    bic = chi_square + parameter_count * math.log(len(times))
    return bic, float(step_time_s), float(coefficients[2]), float(math.sqrt(covariance[2, 2]))


def _best_step_model(
    frames: tuple[FrameMeasurement, ...],
    *,
    nominal_boundary_time_s: float,
    minimum_side_frames: int = 10,
) -> StepModel:
    if len(frames) < 2 * minimum_side_frames:
        raise ValueError("step audit needs enough supported frames on both sides")
    times = np.asarray([item.reference_time_s for item in frames], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in frames], dtype=float)
    uncertainties = np.asarray([item.frequency_uncertainty_hz for item in frames], dtype=float)
    _coefficients, smooth_chi, _covariance, _reference = _weighted_fit(
        times, frequencies, uncertainties
    )
    smooth_bic = smooth_chi + 2 * math.log(len(times))
    candidates = [
        _step_candidate(
            times,
            frequencies,
            uncertainties,
            index,
            parameter_count=4,
        )
        for index in range(minimum_side_frames, len(times) - minimum_side_frames + 1)
    ]
    best = min(candidates, key=lambda item: item[0])
    near_best = [item for item in candidates if item[0] <= best[0] + 2.0]
    fixed_index = int(np.searchsorted(times, nominal_boundary_time_s))
    fixed_index = min(max(fixed_index, minimum_side_frames), len(times) - minimum_side_frames)
    fixed = _step_candidate(
        times,
        frequencies,
        uncertainties,
        fixed_index,
        parameter_count=3,
    )
    return StepModel(
        frame_count=len(frames),
        smooth_bic=smooth_bic,
        scanned_step_bic=best[0],
        scanned_delta_bic=smooth_bic - best[0],
        scanned_step_time_s=best[1],
        scanned_step_hz=best[2],
        scanned_step_sigma_hz=best[3],
        scanned_near_best_start_s=min(item[1] for item in near_best),
        scanned_near_best_end_s=max(item[1] for item in near_best),
        fixed_step_bic=fixed[0],
        fixed_delta_bic=smooth_bic - fixed[0],
        fixed_step_time_s=fixed[1],
        fixed_step_hz=fixed[2],
        fixed_step_sigma_hz=fixed[3],
    )


def _grid_analysis(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    probe_samples: int,
    edge: StarlinkEdge,
    source_windows: tuple[SourceWindow, ...],
    trajectory: FrozenTrajectory,
    offset_ms: float,
) -> tuple[tuple[WindowFit, ...], tuple[FrameMeasurement, ...]]:
    shift_samples = round(offset_ms * sample_rate_hz / 1_000.0)
    fits: list[WindowFit] = []
    all_frames: list[FrameMeasurement] = []
    for source in source_windows:
        absolute_start = source.probe_sample_start + shift_samples
        relative_start = absolute_start - raw_sample_start
        samples = np.ascontiguousarray(iq[relative_start : relative_start + probe_samples])
        if len(samples) != probe_samples:
            raise ValueError("shifted probe lies outside verified IQ interval")
        epoch = _epoch_for_shifted_start(source, absolute_start, sample_rate_hz)
        result = analyze_pilot_phase_slope(
            samples,
            sample_rate_hz,
            epoch_sample=epoch,
            absolute_cfo_hz=source.glrt64_cfo_hz,
            edge=edge,
        )
        frames = _quality_frames(
            result,
            source_index=source.index,
            absolute_window_start=absolute_start,
            sample_rate_hz=sample_rate_hz,
        )
        fit = _fit_window(
            frames,
            source_index=source.index,
            grid_offset_ms=offset_ms,
            start_time_s=absolute_start / sample_rate_hz,
            complete_frame_count=len(result.frames),
            trajectory=trajectory,
        )
        if fit is not None:
            fits.append(fit)
        all_frames.extend(frames)
    return tuple(fits), tuple(all_frames)


def _analyze_lattice(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    source: SourceWindow,
    other: SourceWindow,
    role: str,
    nominal_boundary_time_s: float,
    interval_s: float = 0.100,
) -> LatticeAudit | None:
    absolute_start = round((nominal_boundary_time_s - interval_s / 2) * sample_rate_hz)
    sample_count = round(interval_s * sample_rate_hz)
    relative_start = absolute_start - raw_sample_start
    samples = np.ascontiguousarray(iq[relative_start : relative_start + sample_count])
    epoch = _epoch_for_shifted_start(source, absolute_start, sample_rate_hz)

    def analyze(seed_cfo_hz: float) -> tuple[FrameMeasurement, ...]:
        result = analyze_pilot_phase_slope(
            samples,
            sample_rate_hz,
            epoch_sample=epoch,
            absolute_cfo_hz=seed_cfo_hz,
            edge=edge,
        )
        return _quality_frames(
            result,
            source_index=source.index,
            absolute_window_start=absolute_start,
            sample_rate_hz=sample_rate_hz,
        )

    frames = analyze(source.glrt64_cfo_hz)
    if len(frames) < 20:
        return None
    alternate_frames = analyze(other.glrt64_cfo_hz)
    if len(alternate_frames) < 20:
        return None
    line = _weighted_line(frames)
    alternate_line = _weighted_line(alternate_frames)
    times = np.asarray([item.reference_time_s for item in frames], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in frames], dtype=float)
    robust = frequency_line(times, frequencies)
    if robust is None:
        return None
    cfo_at_boundary = float(line.value_hz(nominal_boundary_time_s))
    alternate_at_boundary = float(alternate_line.value_hz(nominal_boundary_time_s))
    prediction_sigma = line.prediction_sigma_hz(nominal_boundary_time_s)
    period_samples = sample_rate_hz / 750.0
    timing_offset_samples = (
        (source.aligned_sample_start - other.aligned_sample_start + period_samples / 2)
        % period_samples
    ) - period_samples / 2
    return LatticeAudit(
        source_index=source.index,
        role=role,
        timing_offset_from_other_us=float(timing_offset_samples / sample_rate_hz * 1e6),
        frame_count=len(frames),
        first_supported_reference_time_s=frames[0].reference_time_s,
        last_supported_reference_time_s=frames[-1].reference_time_s,
        median_exact_coherence=float(np.median([item.exact_coherence for item in frames])),
        median_coherence_margin=float(np.median([item.coherence_margin for item in frames])),
        smooth_line=line,
        robust_line_rms_hz=robust.residual_rms_hz,
        cfo_at_nominal_boundary_hz=cfo_at_boundary,
        cfo_at_nominal_boundary_sigma_hz=prediction_sigma,
        alternate_seed_cfo_at_boundary_hz=alternate_at_boundary,
        alternate_seed_difference_hz=alternate_at_boundary - cfo_at_boundary,
        step_model=_best_step_model(frames, nominal_boundary_time_s=nominal_boundary_time_s),
        frames=frames,
    )


def _boundary_audits(
    iq: np.ndarray,
    *,
    raw_sample_start: int,
    sample_rate_hz: float,
    edge: StarlinkEdge,
    source_windows: tuple[SourceWindow, ...],
    base_steps: tuple[PairStep, ...],
    boundary_count: int,
) -> tuple[BoundaryAudit, ...]:
    strongest = sorted(base_steps, key=lambda item: abs(item.inferred_step_hz), reverse=True)[
        :boundary_count
    ]
    output = []
    for rank, pair in enumerate(strongest, start=1):
        previous_source = source_windows[pair.left_source_index]
        current_source = source_windows[pair.right_source_index]
        nominal_time_s = current_source.detection_time_s
        previous = _analyze_lattice(
            iq,
            raw_sample_start=raw_sample_start,
            sample_rate_hz=sample_rate_hz,
            edge=edge,
            source=previous_source,
            other=current_source,
            role="previous",
            nominal_boundary_time_s=nominal_time_s,
        )
        current = _analyze_lattice(
            iq,
            raw_sample_start=raw_sample_start,
            sample_rate_hz=sample_rate_hz,
            edge=edge,
            source=current_source,
            other=previous_source,
            role="current",
            nominal_boundary_time_s=nominal_time_s,
        )
        separation = None
        separation_sigma = None
        mismatch = None
        bracket_start = None
        bracket_end = None
        bracket_width_ms = None
        bracket_midpoint_error_ms = None
        if previous is not None and current is not None:
            separation = (
                current.cfo_at_nominal_boundary_hz - previous.cfo_at_nominal_boundary_hz
            )
            separation_sigma = math.sqrt(
                previous.cfo_at_nominal_boundary_sigma_hz**2
                + current.cfo_at_nominal_boundary_sigma_hz**2
            )
            mismatch = separation - pair.inferred_step_hz
            bracket_start = previous.last_supported_reference_time_s
            bracket_end = current.first_supported_reference_time_s
            bracket_width_ms = (bracket_end - bracket_start) * 1_000
            bracket_midpoint_error_ms = (
                0.5 * (bracket_start + bracket_end) - nominal_time_s
            ) * 1_000
        output.append(
            BoundaryAudit(
                rank=rank,
                nominal_boundary_time_s=nominal_time_s,
                pair_step_hz=pair.inferred_step_hz,
                pair_step_conditional_sigma_hz=pair.conditional_sigma_hz,
                previous=previous,
                current=current,
                boundary_mode_separation_hz=separation,
                boundary_mode_separation_sigma_hz=separation_sigma,
                separation_minus_pair_step_hz=mismatch,
                handoff_bracket_start_s=bracket_start,
                handoff_bracket_end_s=bracket_end,
                handoff_bracket_width_ms=bracket_width_ms,
                handoff_midpoint_minus_nominal_ms=bracket_midpoint_error_ms,
            )
        )
    return tuple(output)


def _grid_summary(
    fits: tuple[WindowFit, ...], pairs: tuple[PairStep, ...]
) -> dict[str, Any]:
    qualified = [item for item in fits if item.direct_quality_qualified]
    slopes = np.asarray([item.local_rate_hz_s for item in qualified], dtype=float)
    slope_sigmas = np.asarray(
        [item.local_rate_sigma_hz_s for item in qualified if item.local_rate_sigma_hz_s is not None]
    )
    line_rms = np.asarray([item.line_rms_hz for item in qualified], dtype=float)
    uncertainty = np.asarray(
        [
            frame
            for item in qualified
            for frame in (item.line_rms_hz / math.sqrt(item.supported_frame_count),)
        ],
        dtype=float,
    )
    steps = np.asarray([item.inferred_step_hz for item in pairs], dtype=float)
    median_slope = float(np.median(slopes)) if len(slopes) else None
    return {
        "analyzed_window_count": len(fits),
        "direct_quality_qualified_window_count": len(qualified),
        "median_local_rate_hz_s": median_slope,
        "local_rate_p10_hz_s": float(np.percentile(slopes, 10)) if len(slopes) else None,
        "local_rate_p90_hz_s": float(np.percentile(slopes, 90)) if len(slopes) else None,
        "median_conditional_slope_sigma_hz_s": (
            float(np.median(slope_sigmas)) if len(slope_sigmas) else None
        ),
        "median_line_rms_hz": float(np.median(line_rms)) if len(line_rms) else None,
        "median_conditional_cfo_mean_sigma_hz": (
            float(np.median(uncertainty)) if len(uncertainty) else None
        ),
        "qualified_adjacent_pair_count": len(pairs),
        "median_pair_step_hz": float(np.median(steps)) if len(steps) else None,
        "pair_step_p90_absolute_hz": (
            float(np.percentile(np.abs(steps), 90)) if len(steps) else None
        ),
        "pair_step_over_100_hz_count": int(np.count_nonzero(np.abs(steps) > 100.0)),
    }


def _same_frame_summary(
    base_frames: tuple[FrameMeasurement, ...],
    shifted_frames: tuple[FrameMeasurement, ...],
) -> dict[str, Any]:
    base = {
        (item.source_index, item.frame_start_sample): item.absolute_cfo_hz
        for item in base_frames
    }
    shifted = {
        (item.source_index, item.frame_start_sample): item.absolute_cfo_hz
        for item in shifted_frames
    }
    keys = sorted(set(base) & set(shifted))
    differences = np.asarray([shifted[key] - base[key] for key in keys], dtype=float)
    return {
        "matched_frame_count": len(keys),
        "cfo_difference_rms_hz": float(np.sqrt(np.mean(differences**2))),
        "cfo_difference_max_absolute_hz": float(np.max(np.abs(differences))),
    }


def _frame_summary(frames: tuple[FrameMeasurement, ...]) -> dict[str, Any]:
    uncertainties = np.asarray(
        [item.frequency_uncertainty_hz for item in frames], dtype=float
    )
    return {
        "supported_frame_count": len(frames),
        "median_reported_frequency_uncertainty_hz": (
            float(np.median(uncertainties)) if len(uncertainties) else None
        ),
        "frequency_uncertainty_p90_hz": (
            float(np.percentile(uncertainties, 90)) if len(uncertainties) else None
        ),
    }


def _pair_stability_summary(
    base_pairs: tuple[PairStep, ...], shifted_pairs: tuple[PairStep, ...]
) -> dict[str, Any]:
    base = {item.right_source_index: item.inferred_step_hz for item in base_pairs}
    shifted = {item.right_source_index: item.inferred_step_hz for item in shifted_pairs}
    indexes = sorted(set(base) & set(shifted))
    x = np.asarray([base[index] for index in indexes], dtype=float)
    y = np.asarray([shifted[index] for index in indexes], dtype=float)
    difference = y - x
    return {
        "matched_pair_count": len(indexes),
        "pearson_correlation": float(np.corrcoef(x, y)[0, 1]),
        "step_difference_rms_hz": float(np.sqrt(np.mean(difference**2))),
        "step_difference_median_absolute_hz": float(np.median(np.abs(difference))),
    }


def _boundary_summary(audits: tuple[BoundaryAudit, ...]) -> dict[str, Any]:
    complete: list[tuple[BoundaryAudit, LatticeAudit, LatticeAudit]] = []
    for item in audits:
        if item.previous is not None and item.current is not None:
            complete.append((item, item.previous, item.current))
    lattice_results = [
        lattice
        for item in audits
        for lattice in (item.previous, item.current)
        if lattice is not None
    ]
    pair = np.asarray([item.pair_step_hz for item, _previous, _current in complete], dtype=float)
    separation = np.asarray(
        [float(item.boundary_mode_separation_hz) for item, _previous, _current in complete],
        dtype=float,
    )
    mismatch = separation - pair
    bracket_widths_ms = np.asarray(
        [float(item.handoff_bracket_width_ms) for item, _previous, _current in complete],
        dtype=float,
    )
    timing_offsets_us = np.asarray(
        [abs(previous.timing_offset_from_other_us) for _item, previous, _current in complete],
        dtype=float,
    )
    midpoint_errors_ms = np.asarray(
        [
            float(item.handoff_midpoint_minus_nominal_ms)
            for item, _previous, _current in complete
        ],
        dtype=float,
    )
    return {
        "requested_boundary_count": len(audits),
        "both_lattices_qualified_count": len(complete),
        "qualified_lattice_count": len(lattice_results),
        "lattice_with_positive_scanned_step_delta_bic_count": sum(
            item.step_model.scanned_delta_bic > 0 for item in lattice_results
        ),
        "lattice_with_strong_scanned_step_delta_bic_count": sum(
            item.step_model.scanned_delta_bic >= 6 for item in lattice_results
        ),
        "largest_scanned_step_delta_bic": max(
            (item.step_model.scanned_delta_bic for item in lattice_results), default=None
        ),
        "largest_fixed_boundary_step_delta_bic": max(
            (item.step_model.fixed_delta_bic for item in lattice_results), default=None
        ),
        "pair_vs_boundary_mode_separation_correlation": (
            float(np.corrcoef(pair, separation)[0, 1]) if len(complete) >= 3 else None
        ),
        "separation_minus_pair_rms_hz": (
            float(np.sqrt(np.mean(mismatch**2))) if len(complete) else None
        ),
        "handoff_bracket_width_median_ms": (
            float(np.median(bracket_widths_ms)) if len(complete) else None
        ),
        "handoff_bracket_width_min_ms": (
            float(np.min(bracket_widths_ms)) if len(complete) else None
        ),
        "handoff_bracket_width_max_ms": (
            float(np.max(bracket_widths_ms)) if len(complete) else None
        ),
        "handoff_midpoint_minus_nominal_rms_ms": (
            float(np.sqrt(np.mean(midpoint_errors_ms**2))) if len(complete) else None
        ),
        "median_absolute_timing_lattice_offset_us": (
            float(np.median(timing_offsets_us)) if len(complete) else None
        ),
        "median_absolute_alternate_seed_difference_hz": float(
            np.median([abs(item.alternate_seed_difference_hz) for item in lattice_results])
        ),
        "maximum_absolute_alternate_seed_difference_hz": max(
            (abs(item.alternate_seed_difference_hz) for item in lattice_results), default=None
        ),
    }


def _strong_pair_cadence(
    pairs: tuple[PairStep, ...], *, minimum_absolute_step_hz: float = 100.0
) -> dict[str, Any]:
    selected = sorted(
        (item for item in pairs if abs(item.inferred_step_hz) > minimum_absolute_step_hz),
        key=lambda item: item.midpoint_time_s,
    )
    spacings_ms = np.diff([item.midpoint_time_s for item in selected]) * 1_000
    return {
        "minimum_absolute_step_hz": minimum_absolute_step_hz,
        "event_count": len(selected),
        "inter_event_interval_count": len(spacings_ms),
        "inter_event_median_ms": (
            float(np.median(spacings_ms)) if len(spacings_ms) else None
        ),
        "inter_event_p25_ms": (
            float(np.percentile(spacings_ms, 25)) if len(spacings_ms) else None
        ),
        "inter_event_p75_ms": (
            float(np.percentile(spacings_ms, 75)) if len(spacings_ms) else None
        ),
        "inter_event_minimum_ms": float(np.min(spacings_ms)) if len(spacings_ms) else None,
        "inter_event_maximum_ms": float(np.max(spacings_ms)) if len(spacings_ms) else None,
        "note": (
            "Intervals above the upper quartile can contain missed or unqualified events; "
            "this is a thresholded observed cadence, not a scheduler-period estimate"
        ),
    }


def _plot(
    path: Path,
    *,
    trajectory: FrozenTrajectory,
    grid_fits: dict[float, tuple[WindowFit, ...]],
    grid_pairs: dict[float, tuple[PairStep, ...]],
    boundaries: tuple[BoundaryAudit, ...],
) -> None:
    colors = {0.0: BLUE, 5.0: GREEN, 10.0: AMBER, 12.5: PURPLE}
    with plt.rc_context(
        {
            "font.size": 9.5,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "legend.frameon": False,
        }
    ):
        figure, axes = plt.subplots(2, 2, figsize=(15, 10.5))
        for offset, fits in grid_fits.items():
            qualified = [item for item in fits if item.direct_quality_qualified]
            axes[0, 0].scatter(
                [item.reference_time_s for item in qualified],
                [item.carrier_bias_at_reference_hz for item in qualified],
                s=15,
                alpha=0.72,
                color=colors[offset],
                label=f"+{offset:g} ms",
            )
        axes[0, 0].set_title("A. Shifted 20 ms fits preserve the same carrier modes")
        axes[0, 0].set_ylabel("CFO minus frozen trajectory (Hz)")
        axes[0, 0].legend(ncol=2)

        base_pairs = {item.right_source_index: item for item in grid_pairs[0.0]}
        for offset in GRID_OFFSETS_MS[1:]:
            shifted = {item.right_source_index: item for item in grid_pairs[offset]}
            indexes = sorted(set(base_pairs) & set(shifted))
            axes[0, 1].scatter(
                [base_pairs[index].inferred_step_hz for index in indexes],
                [shifted[index].inferred_step_hz for index in indexes],
                s=20,
                alpha=0.65,
                color=colors[offset],
                label=f"+{offset:g} ms",
            )
        limits = (-1_400, 500)
        axes[0, 1].plot(limits, limits, color=GRAY, linestyle="--", linewidth=1)
        axes[0, 1].set_xlim(limits)
        axes[0, 1].set_ylim(limits)
        axes[0, 1].set_title("B. Apparent pair offsets survive grid shifts")
        axes[0, 1].set_xlabel("Base-grid inferred offset (Hz)")
        axes[0, 1].set_ylabel("Shifted-grid inferred offset (Hz)")
        axes[0, 1].legend()

        complete: list[tuple[BoundaryAudit, LatticeAudit, LatticeAudit]] = []
        for item in boundaries:
            if item.previous is not None and item.current is not None:
                complete.append((item, item.previous, item.current))
        ranks = np.arange(len(complete))
        axes[1, 0].bar(
            ranks - 0.18,
            [abs(item.pair_step_hz) for item, _previous, _current in complete],
            width=0.36,
            color=RED,
            alpha=0.78,
            label="between selected 20 ms fits",
        )
        axes[1, 0].bar(
            ranks + 0.18,
            [
                max(
                    abs(previous.step_model.scanned_step_hz),
                    abs(current.step_model.scanned_step_hz),
                )
                for _item, previous, current in complete
            ],
            width=0.36,
            color=BLUE,
            alpha=0.78,
            label="largest modeled step within either burst",
        )
        axes[1, 0].set_xticks(
            ranks,
            [
                f"{item.nominal_boundary_time_s:.3f}"
                for item, _previous, _current in complete
            ],
            rotation=35,
            ha="right",
        )
        axes[1, 0].set_title("C. Kilohertz offsets occur between timing-lattice bursts")
        axes[1, 0].set_ylabel("Absolute frequency change (Hz)")
        axes[1, 0].set_xlabel("Nominal boundary time (s)")
        axes[1, 0].legend()

        strongest = next((item for item in boundaries if item.previous and item.current), None)
        if strongest is None:
            raise ValueError("no complete boundary audit is available to plot")
        previous = strongest.previous
        current = strongest.current
        assert previous is not None
        assert current is not None
        for lattice, color, label in (
            (previous, BLUE, "previous timing lattice"),
            (current, RED, "current timing lattice"),
        ):
            times = np.asarray([item.reference_time_s for item in lattice.frames])
            residual = np.asarray([item.absolute_cfo_hz for item in lattice.frames]) - np.asarray(
                trajectory.frequency_hz(times)
            )
            axes[1, 1].scatter(times, residual, s=17, alpha=0.75, color=color, label=label)
            model_times = np.linspace(times.min(), times.max(), 100)
            model_residual = np.asarray(lattice.smooth_line.value_hz(model_times)) - np.asarray(
                trajectory.frequency_hz(model_times)
            )
            axes[1, 1].plot(model_times, model_residual, color=color, linewidth=1.4)
        axes[1, 1].axvline(
            strongest.nominal_boundary_time_s, color=INK, linestyle="--", linewidth=1
        )
        assert strongest.handoff_bracket_start_s is not None
        assert strongest.handoff_bracket_end_s is not None
        handoff_midpoint_s = 0.5 * (
            strongest.handoff_bracket_start_s + strongest.handoff_bracket_end_s
        )
        axes[1, 1].axvline(
            handoff_midpoint_s,
            color=GREEN,
            linestyle=":",
            linewidth=1.5,
            label="raw-IQ handoff bracket midpoint",
        )
        axes[1, 1].set_title(
            f"D. Adjacent smooth bursts hand off near "
            f"{strongest.nominal_boundary_time_s:.3f} s"
        )
        axes[1, 1].set_xlabel("Capture time (s)")
        axes[1, 1].set_ylabel("CFO minus frozen trajectory (Hz)")
        axes[1, 1].legend()
        figure.tight_layout()
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(
            path,
            dpi=190,
            bbox_inches="tight",
            metadata={"Software": "leo-tracker", "Creation Time": None},
        )
        plt.close(figure)


def _jsonable_lattice(item: LatticeAudit | None) -> dict[str, Any] | None:
    if item is None:
        return None
    value = asdict(item)
    return value


def main() -> int:
    args = _arguments()
    if args.boundary_count < 1:
        raise ValueError("boundary count must be positive")
    scan_path = args.analysis_root / "standard.pilot-scan.v3.json"
    bank_path = args.analysis_root / "standard.final-trajectory-bank.v2.json"
    scan = _load_json(scan_path)
    trajectory = _trajectory(_load_json(bank_path))
    sources = _source_windows(
        scan,
        trajectory,
        start_s=args.start_s,
        end_s=args.end_s,
        minimum_margin=args.minimum_glrt64_margin,
        maximum_model_error_hz=args.maximum_model_error_hz,
    )
    if not sources:
        raise ValueError("no source windows passed the frozen selection")
    sample_rate_hz = 2_500_000.0
    raw_start = round((args.start_s - 0.100) * sample_rate_hz)
    raw_stop = round((args.end_s + 0.150) * sample_rate_hz)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
        bundle = store.inspect(args.session_id)
        reader = store.reader(bundle, args.stream, verify=True)
        if float(reader.sample_rate_hz) != sample_rate_hz:
            raise ValueError(f"experiment expects 2.5 MS/s, found {reader.sample_rate_hz}")
        receiver_ids = tuple(dict.fromkeys((args.receiver, args.control_receiver)))
        raw = reader.read(raw_start, raw_stop - raw_start, receiver_ids=receiver_ids)
        iq = _complex_receiver(raw, receiver_ids.index(args.receiver))
        control_iq = _complex_receiver(raw, receiver_ids.index(args.control_receiver))
        manifest_digest = bundle.manifest_sha256
    finally:
        if store is not None:
            store.close()

    edge = StarlinkEdge(args.edge)
    grid_fits = {}
    grid_frames = {}
    grid_pairs = {}
    for offset in GRID_OFFSETS_MS:
        fits, frames = _grid_analysis(
            iq,
            raw_sample_start=raw_start,
            sample_rate_hz=sample_rate_hz,
            probe_samples=int(scan["probe_samples"]),
            edge=edge,
            source_windows=sources,
            trajectory=trajectory,
            offset_ms=offset,
        )
        grid_fits[offset] = fits
        grid_frames[offset] = frames
        grid_pairs[offset] = _pair_steps(fits)

    control_fits, control_frames = _grid_analysis(
        control_iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        probe_samples=int(scan["probe_samples"]),
        edge=edge,
        source_windows=sources,
        trajectory=trajectory,
        offset_ms=0.0,
    )
    control_pairs = _pair_steps(control_fits)

    boundaries = _boundary_audits(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
        source_windows=sources,
        base_steps=grid_pairs[0.0],
        boundary_count=args.boundary_count,
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    figure_path = args.output_root / "shifted-grid-boundary-audit.png"
    _plot(
        figure_path,
        trajectory=trajectory,
        grid_fits=grid_fits,
        grid_pairs=grid_pairs,
        boundaries=boundaries,
    )
    document = {
        "schema": "research.shifted-pilot-grid-experiment.v1",
        "session_id": args.session_id,
        "stream_id": args.stream,
        "receiver_id": args.receiver,
        "control_receiver_id": args.control_receiver,
        "edge": edge.value,
        "interval_s": [args.start_s, args.end_s],
        "recording_manifest_digest": manifest_digest,
        "analysis_scope": ANALYSIS_SCOPE,
        "pilot_scan_sha256": _sha256(scan_path),
        "final_trajectory_bank_sha256": _sha256(bank_path),
        "measurement_implementation_sha256": _sha256(
            Path(__file__).parents[1] / "src/leo/analysis/qam/pilot.py"
        ),
        "local_fit_implementation_sha256": _sha256(
            Path(__file__).parents[1] / "src/leo/analysis/starlink/local_doppler.py"
        ),
        "trajectory_id": trajectory.trajectory_id,
        "branch_id": trajectory.branch_id,
        "trajectory_coefficients_hz": list(trajectory.coefficients_hz),
        "trajectory_reference_time_s": trajectory.reference_time_s,
        "source_window_count": len(sources),
        "probe_duration_ms": float(scan["probe_samples"]) / sample_rate_hz * 1_000,
        "grid_offsets_ms": list(GRID_OFFSETS_MS),
        "direct_quality_gate": {
            "minimum_exact_coherence": 0.02,
            "minimum_coherence_margin": 0.0,
            "minimum_supported_frame_fraction": 0.75,
            "maximum_supported_frame_gap_s": 0.0041,
            "maximum_frequency_line_rms_hz": 75.0,
            "maximum_interleaved_held_out_rms_hz": 100.0,
            "phase_lock_gate_applied": False,
            "reason": (
                "20 ms probes contain only about 15 frames, below the production "
                "20-frame phase-lock minimum; this control tests the direct CFO observable"
            ),
        },
        "grid_summaries": {
            f"{offset:g}": _grid_summary(grid_fits[offset], grid_pairs[offset])
            for offset in GRID_OFFSETS_MS
        },
        "grid_frame_summaries": {
            f"{offset:g}": _frame_summary(grid_frames[offset])
            for offset in GRID_OFFSETS_MS
        },
        "same_absolute_frame_reproducibility": {
            f"base_to_{offset:g}_ms": _same_frame_summary(
                grid_frames[0.0], grid_frames[offset]
            )
            for offset in GRID_OFFSETS_MS[1:]
        },
        "pair_step_stability": {
            f"base_to_{offset:g}_ms": _pair_stability_summary(
                grid_pairs[0.0], grid_pairs[offset]
            )
            for offset in GRID_OFFSETS_MS[1:]
        },
        "strong_pair_cadence": _strong_pair_cadence(grid_pairs[0.0]),
        "control_receiver_summary": {
            **_grid_summary(control_fits, control_pairs),
            **_frame_summary(control_frames),
            "interpretation": (
                "A zero or sparse qualified count makes this a sensitivity null, not an "
                "independent confirmation or refutation of the receiver-0 transitions"
            ),
        },
        "boundary_summary": _boundary_summary(boundaries),
        "source_windows": [asdict(item) for item in sources],
        "grid_window_fits": {
            f"{offset:g}": [asdict(item) for item in grid_fits[offset]]
            for offset in GRID_OFFSETS_MS
        },
        "grid_pair_steps": {
            f"{offset:g}": [asdict(item) for item in grid_pairs[offset]]
            for offset in GRID_OFFSETS_MS
        },
        "boundary_audits": [
            {
                "rank": item.rank,
                "nominal_boundary_time_s": item.nominal_boundary_time_s,
                "pair_step_hz": item.pair_step_hz,
                "pair_step_conditional_sigma_hz": item.pair_step_conditional_sigma_hz,
                "previous": _jsonable_lattice(item.previous),
                "current": _jsonable_lattice(item.current),
                "boundary_mode_separation_hz": item.boundary_mode_separation_hz,
                "boundary_mode_separation_sigma_hz": (
                    item.boundary_mode_separation_sigma_hz
                ),
                "separation_minus_pair_step_hz": item.separation_minus_pair_step_hz,
                "handoff_bracket_start_s": item.handoff_bracket_start_s,
                "handoff_bracket_end_s": item.handoff_bracket_end_s,
                "handoff_bracket_width_ms": item.handoff_bracket_width_ms,
                "handoff_midpoint_minus_nominal_ms": (
                    item.handoff_midpoint_minus_nominal_ms
                ),
            }
            for item in boundaries
        ],
        "figure": {
            "path": figure_path.name,
            "sha256": _sha256(figure_path),
            "bytes": figure_path.stat().st_size,
        },
        "candidate_only": True,
        "known_pilots_only": True,
        "payload_decoded": False,
        "satellite_identity_resolved": False,
    }
    output_path = args.output_root / "shifted-grid-boundary-audit.json"
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output_path)
    print(json.dumps(document["grid_summaries"], indent=2, sort_keys=True))
    print(json.dumps(document["same_absolute_frame_reproducibility"], indent=2, sort_keys=True))
    print(json.dumps(document["pair_step_stability"], indent=2, sort_keys=True))
    print(json.dumps(document["boundary_summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
