"""Independent full-capture GLRT windows and linear-only receiver diagnostics."""

from __future__ import annotations

import io
import math
from collections.abc import Iterable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import RLock
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam import analyze_pilot_phase_slope
from leo.analysis.starlink import (
    ReceiverFrequencyCalibration,
    StarlinkEdge,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.acquisition import (
    AcquisitionCandidate,
    NumericalStatus,
    acquire_symbolwise,
)
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    fit_huber_linear_dealiased_trajectories,
)
from leo.analysis.starlink.local_doppler import (
    complete_lattice_count,
    frequency_line,
    line_slope_sigma,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
    conditioned_glrt64_score,
    conditioned_glrt64_scores,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    trajectory_observations,
)
from leo.contracts.alternate_cfo_tracks import ResidualHoughSegmentationConfigV2
from leo.contracts.cfo_dealias import (
    CfoDealiasConfigV2,
    HuberLinearRefinementConfigV1,
    SeededAliasEmConfigV1,
)
from leo.contracts.digests import canonical_digest
from leo.pipeline import IqReader

_ZERO_CALIBRATION_SHA256 = "0" * 64
_RENDER_LOCK = RLock()
_GLRT_BATCH_TIE_GUARD = 1e-10
_FRACTIONAL_EPOCH_GRID_OFFSETS = (-2, -1, 0, 1, 2)

_BLUE = "#2678a8"
_ORANGE = "#f28e2b"
_RED = "#c44e52"
_INK = "#1f2933"
_GRAY = "#a7b0b8"
_LIGHT_GRAY = "#d9dee3"
_TRACK_COLORS = (
    "#0072b2",
    "#009e73",
    "#cc79a7",
    "#56b4e9",
    "#6f4e7c",
    "#7f7f7f",
    "#332288",
    "#44aa99",
    "#882255",
    "#117733",
    "#88ccee",
    "#aa4499",
    "#999933",
    "#661100",
    "#6699cc",
    "#000000",
)


@dataclass(frozen=True, slots=True)
class FullCaptureGlrt20msConfig:
    """Bounded independent-window diagnostic settings."""

    enabled: bool = True
    window_ms: int = 20
    stride_ms: int = 10
    margin_gate: float = 0.025
    maximum_workers: int = 4
    line_rms_reference_hz: float = 75.0

    def __post_init__(self) -> None:
        if self.window_ms <= 0 or self.stride_ms <= 0 or self.maximum_workers <= 0:
            raise ValueError("full-capture window, stride, and worker count must be positive")
        if not math.isfinite(self.margin_gate) or not math.isfinite(self.line_rms_reference_hz):
            raise ValueError("full-capture diagnostic thresholds must be finite")
        if self.line_rms_reference_hz <= 0:
            raise ValueError("full-capture line RMS reference must be positive")


@dataclass(frozen=True, slots=True)
class WindowResult:
    probe_index: int
    sample_start: int
    start_time_s: float
    center_time_s: float
    end_time_s: float
    acquisition_status: str
    candidate_count: int
    best_candidate_rank: int | None
    epoch_sample: int | None
    acquired_cfo_hz: float | None
    residual_cfo_hz: float | None
    tracking_cfo_hz: float | None
    glrt_exact_score: float | None
    glrt_control_score: float | None
    glrt_margin: float | None
    passed_margin_gate: bool
    lattice_frame_count: int
    measured_frame_count: int
    robust_line_available: bool
    robust_reference_time_s: float | None
    robust_cfo_at_reference_hz: float | None
    robust_slope_hz_s: float | None
    robust_slope_sigma_hz_s: float | None
    robust_residual_rms_hz: float | None
    robust_median_absolute_residual_hz: float | None
    robust_mad_scale_hz: float | None
    robust_outlier_count: int
    robust_converged: bool | None
    reason: str
    fractional_epoch_status: str = "not_evaluated"
    fractional_epoch_offset_samples: float | None = None
    fractional_epoch_exact_score_grid: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class FullCaptureGlrt20msResult:
    windows: tuple[WindowResult, ...]
    hough_analysis: dict[str, Any]
    constant_doppler_rate: dict[str, Any] | None
    status_note: str


def _acquisition_config(
    probe_samples: int, feedback: TrajectoryFeedbackConfig
) -> SymbolwiseAcquisitionConfig:
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=feedback.cfo_search_min_hz,
        residual_cfo_max_hz=feedback.cfo_search_max_hz,
        coarse_cfo_step_hz=feedback.coarse_cfo_step_hz,
        fine_cfo_radius_hz=feedback.fine_cfo_radius_hz,
        fine_cfo_step_hz=feedback.fine_cfo_step_hz,
        conditioned_cfo_radius_hz=feedback.conditioned_cfo_radius_hz,
        conditioned_cfo_step_hz=feedback.conditioned_cfo_step_hz,
        retained_candidate_count=feedback.retained_candidate_count,
        candidate_epoch_separation_samples=feedback.candidate_epoch_separation_samples,
        candidate_cfo_separation_hz=feedback.candidate_cfo_separation_hz,
        maximum_probe_samples=probe_samples,
    )


def _fit_supported_frame_line(
    times_s: np.ndarray, cfo_hz: np.ndarray
) -> dict[str, float | int | bool | None]:
    fit = frequency_line(times_s, cfo_hz)
    if fit is None:
        return {
            "available": False,
            "reference_time_s": None,
            "cfo_at_reference_hz": None,
            "slope_hz_s": None,
            "slope_sigma_hz_s": None,
            "residual_rms_hz": None,
            "median_absolute_residual_hz": None,
            "mad_scale_hz": None,
            "outlier_count": 0,
            "converged": None,
        }
    predicted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (
        times_s - fit.reference_time_s
    )
    residual = cfo_hz - predicted
    return {
        "available": True,
        "reference_time_s": fit.reference_time_s,
        "cfo_at_reference_hz": fit.intercept_at_reference_hz,
        "slope_hz_s": fit.slope_hz_per_s,
        "slope_sigma_hz_s": line_slope_sigma(times_s, fit),
        "residual_rms_hz": fit.residual_rms_hz,
        "median_absolute_residual_hz": fit.median_absolute_residual_hz,
        "mad_scale_hz": fit.mad_scale_hz,
        "outlier_count": int(np.count_nonzero(np.abs(residual) > 1.345 * fit.mad_scale_hz)),
        "converged": fit.converged,
    }


def _optional_float(value: float | int | bool | None) -> float | None:
    return None if value is None else float(value)


def _winning_candidate_glrt64(
    samples: np.ndarray,
    sample_rate_hz: int,
    candidates: Sequence[AcquisitionCandidate],
    *,
    edge: StarlinkEdge,
    glrt_size: int,
) -> tuple[AcquisitionCandidate, PilotMethodScore]:
    """Batch-rank candidates while publishing the exact scalar winner score."""

    candidate_scores = conditioned_glrt64_scores(
        samples,
        sample_rate_hz,
        epoch_samples=tuple(item.refined_epoch_sample for item in candidates),
        acquired_cfo_hz=tuple(item.absolute_cfo_hz for item in candidates),
        edge=edge,
        glrt_size=glrt_size,
    )
    scored = tuple(zip(candidates, candidate_scores, strict=True))
    maximum_batch_margin = max(item[1].margin for item in scored)
    contenders = tuple(
        item for item in scored if maximum_batch_margin - item[1].margin <= _GLRT_BATCH_TIE_GUARD
    )
    scalar_by_geometry: dict[tuple[int, float], PilotMethodScore] = {}
    scalar_scored: list[tuple[AcquisitionCandidate, PilotMethodScore]] = []
    for candidate, _batch_score in contenders:
        geometry = (candidate.refined_epoch_sample, candidate.absolute_cfo_hz)
        score = scalar_by_geometry.get(geometry)
        if score is None:
            score = conditioned_glrt64_score(
                samples,
                sample_rate_hz,
                epoch_sample=candidate.refined_epoch_sample,
                acquired_cfo_hz=candidate.absolute_cfo_hz,
                edge=edge,
                glrt_size=glrt_size,
            )
            scalar_by_geometry[geometry] = score
        scalar_scored.append((candidate, score))
    return max(scalar_scored, key=lambda item: (item[1].margin, -item[0].rank))


def fractional_log_peak_offset(
    scores: Sequence[float],
    offsets: Sequence[int] = _FRACTIONAL_EPOCH_GRID_OFFSETS,
) -> float | None:
    """Interpolate one bracketed exact-score maximum in log-score space.

    ``None`` is deliberately returned for a boundary maximum or a non-concave
    local surface.  Callers can then retain the integer acquisition epoch as
    provenance without presenting an unsupported fractional measurement.
    """

    values = np.asarray(scores, dtype=float)
    grid = np.asarray(offsets, dtype=float)
    if values.ndim != 1 or grid.ndim != 1 or values.size != grid.size or values.size < 3:
        raise ValueError("fractional GLRT peak requires equal score and offset vectors")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("fractional GLRT scores must be finite and nonnegative")
    steps = np.diff(grid)
    if np.any(steps <= 0.0) or not np.allclose(steps, steps[0], rtol=0.0, atol=1e-12):
        raise ValueError("fractional GLRT offsets must be uniformly increasing")
    index = int(np.argmax(values))
    if index == 0 or index == len(values) - 1:
        return None
    selected = np.log(np.maximum(values[index - 1 : index + 2], np.finfo(float).tiny))
    denominator = float(selected[0] - 2.0 * selected[1] + selected[2])
    if not math.isfinite(denominator) or denominator >= -np.finfo(float).eps:
        return None
    fraction = float(np.clip(0.5 * (selected[0] - selected[2]) / denominator, -0.5, 0.5))
    return float(grid[index] + fraction * steps[0])


def _fractional_glrt_epoch(
    samples: np.ndarray,
    sample_rate_hz: int,
    candidate: AcquisitionCandidate,
    score: PilotMethodScore,
    *,
    edge: StarlinkEdge,
    glrt_size: int,
) -> tuple[str, float | None, tuple[float, ...]]:
    epoch = candidate.refined_epoch_sample
    if epoch + _FRACTIONAL_EPOCH_GRID_OFFSETS[0] < 0:
        return "unavailable", None, ()
    scores = conditioned_glrt64_scores(
        samples,
        sample_rate_hz,
        epoch_samples=tuple(epoch + item for item in _FRACTIONAL_EPOCH_GRID_OFFSETS),
        acquired_cfo_hz=tuple(
            candidate.absolute_cfo_hz for _item in _FRACTIONAL_EPOCH_GRID_OFFSETS
        ),
        edge=edge,
        glrt_size=glrt_size,
    )
    exact = tuple(float(item.exact_score) for item in scores)
    if not math.isclose(exact[2], score.exact_score, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("fractional GLRT center score differs from the selected candidate")
    offset = fractional_log_peak_offset(exact)
    return ("complete", offset, exact) if offset is not None else ("unbracketed", None, exact)


def _analyze_window(
    probe_index: int,
    sample_start: int,
    samples: np.ndarray,
    *,
    sample_rate_hz: int,
    edge: StarlinkEdge,
    acquisition_config: SymbolwiseAcquisitionConfig,
    glrt_size: int,
    margin_gate: float,
    frequency_reference: ReceiverFrequencyCalibration | None = None,
    refine_fractional_epoch: bool = False,
) -> WindowResult:
    calibration = frequency_reference or ReceiverFrequencyCalibration(
        receiver_id="baseband", center_hz=0.0, calibration_sha256=_ZERO_CALIBRATION_SHA256
    )
    acquired = acquire_symbolwise(
        samples,
        sample_rate_hz,
        calibration,
        edge=edge,
        config=acquisition_config,
    )
    start_s = sample_start / sample_rate_hz
    end_s = (sample_start + len(samples)) / sample_rate_hz
    center_s = (start_s + end_s) / 2
    if not acquired.candidates:
        return WindowResult(
            probe_index=probe_index,
            sample_start=sample_start,
            start_time_s=start_s,
            center_time_s=center_s,
            end_time_s=end_s,
            acquisition_status=acquired.status.value,
            candidate_count=0,
            best_candidate_rank=None,
            epoch_sample=None,
            acquired_cfo_hz=None,
            residual_cfo_hz=None,
            tracking_cfo_hz=None,
            glrt_exact_score=None,
            glrt_control_score=None,
            glrt_margin=None,
            passed_margin_gate=False,
            lattice_frame_count=0,
            measured_frame_count=0,
            robust_line_available=False,
            robust_reference_time_s=None,
            robust_cfo_at_reference_hz=None,
            robust_slope_hz_s=None,
            robust_slope_sigma_hz_s=None,
            robust_residual_rms_hz=None,
            robust_median_absolute_residual_hz=None,
            robust_mad_scale_hz=None,
            robust_outlier_count=0,
            robust_converged=None,
            reason=acquired.reason,
        )
    candidate, score = _winning_candidate_glrt64(
        samples,
        sample_rate_hz,
        acquired.candidates,
        edge=edge,
        glrt_size=glrt_size,
    )
    fractional_status = "not_evaluated"
    fractional_offset: float | None = None
    fractional_scores: tuple[float, ...] = ()
    if refine_fractional_epoch and score.margin >= margin_gate:
        fractional_status, fractional_offset, fractional_scores = _fractional_glrt_epoch(
            samples,
            sample_rate_hz,
            candidate,
            score,
            edge=edge,
            glrt_size=glrt_size,
        )
    frame_result = analyze_pilot_phase_slope(
        samples,
        sample_rate_hz,
        epoch_sample=candidate.refined_epoch_sample,
        absolute_cfo_hz=score.tracking_cfo_hz,
        edge=edge,
        maximum_residual_cfo_hz=2_000.0,
    )
    frames = frame_result.frames
    times = np.asarray([item.reference_sample / sample_rate_hz for item in frames], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_hz for item in frames], dtype=float)
    line = _fit_supported_frame_line(times, frequencies)
    lattice_count = complete_lattice_count(
        len(samples), sample_rate_hz, candidate.refined_epoch_sample
    )
    return WindowResult(
        probe_index=probe_index,
        sample_start=sample_start,
        start_time_s=start_s,
        center_time_s=center_s,
        end_time_s=end_s,
        acquisition_status=acquired.status.value,
        candidate_count=len(acquired.candidates),
        best_candidate_rank=candidate.rank,
        epoch_sample=candidate.refined_epoch_sample,
        acquired_cfo_hz=candidate.absolute_cfo_hz,
        residual_cfo_hz=score.residual_cfo_hz,
        tracking_cfo_hz=score.tracking_cfo_hz,
        glrt_exact_score=score.exact_score,
        glrt_control_score=score.control_score,
        glrt_margin=score.margin,
        passed_margin_gate=score.margin >= margin_gate,
        lattice_frame_count=lattice_count,
        measured_frame_count=len(frames),
        robust_line_available=bool(line["available"]),
        robust_reference_time_s=(
            None if line["reference_time_s"] is None else start_s + float(line["reference_time_s"])
        ),
        robust_cfo_at_reference_hz=_optional_float(line["cfo_at_reference_hz"]),
        robust_slope_hz_s=_optional_float(line["slope_hz_s"]),
        robust_slope_sigma_hz_s=_optional_float(line["slope_sigma_hz_s"]),
        robust_residual_rms_hz=_optional_float(line["residual_rms_hz"]),
        robust_median_absolute_residual_hz=_optional_float(line["median_absolute_residual_hz"]),
        robust_mad_scale_hz=_optional_float(line["mad_scale_hz"]),
        robust_outlier_count=int(line["outlier_count"] or 0),
        robust_converged=(None if line["converged"] is None else bool(line["converged"])),
        reason=(
            "Huber degree-one frame-CFO line available"
            if line["available"]
            else f"only {len(frames)} complete frame CFO measurements; need at least 6"
        ),
        fractional_epoch_status=fractional_status,
        fractional_epoch_offset_samples=fractional_offset,
        fractional_epoch_exact_score_grid=fractional_scores,
    )


def _iter_windows(
    reader: IqReader,
    *,
    receiver_id: int,
    window_samples: int,
    stride_samples: int,
) -> Iterable[tuple[int, int, np.ndarray]]:
    receiver_column = reader.receiver_ids.index(receiver_id)
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    next_start = 0
    probe_index = 0
    for block in reader.iter_blocks(block_samples=2**20):
        block_start = block.metadata.session_sample_start
        if block_start != expected_start:
            raise ValueError("full-capture GLRT requires contiguous recorded IQ")
        expected_start += block.metadata.sample_count
        values = (
            block.samples[:, receiver_column, 0].astype(np.float64)
            + 1j * block.samples[:, receiver_column, 1].astype(np.float64)
        ) / 32_768.0
        if not pending.size:
            pending_start = block_start
        elif block_start != pending_start + len(pending):
            raise ValueError("bounded IQ window buffer became discontinuous")
        pending = np.concatenate((pending, values))
        pending_end = pending_start + len(pending)
        while next_start + window_samples <= pending_end:
            offset = next_start - pending_start
            yield (
                probe_index,
                next_start,
                np.ascontiguousarray(pending[offset : offset + window_samples]),
            )
            probe_index += 1
            next_start += stride_samples
        drop = min(max(next_start - pending_start, 0), len(pending))
        if drop:
            pending = pending[drop:]
            pending_start += drop


def _run_parallel(
    windows: Iterable[tuple[int, int, np.ndarray]], function: Any, *, workers: int
) -> tuple[WindowResult, ...]:
    completed: dict[int, WindowResult] = {}
    pending: dict[Future[WindowResult], int] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for probe_index, sample_start, samples in windows:
            pending[executor.submit(function, probe_index, sample_start, samples)] = probe_index
            if len(pending) >= workers * 2:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    index = pending.pop(future)
                    completed[index] = future.result()
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                index = pending.pop(future)
                completed[index] = future.result()
    return tuple(completed[index] for index in sorted(completed))


def _window_winners(
    results: tuple[WindowResult, ...], *, require_margin_pass: bool
) -> tuple[PilotProbeDetection, ...]:
    detections: list[PilotProbeDetection] = []
    for item in results:
        required = (
            item.best_candidate_rank,
            item.epoch_sample,
            item.acquired_cfo_hz,
            item.residual_cfo_hz,
            item.tracking_cfo_hz,
            item.glrt_exact_score,
            item.glrt_control_score,
            item.glrt_margin,
        )
        if (require_margin_pass and not item.passed_margin_gate) or any(
            value is None for value in required
        ):
            continue
        exact_score = item.glrt_exact_score
        control_score = item.glrt_control_score
        margin = item.glrt_margin
        residual_cfo_hz = item.residual_cfo_hz
        tracking_cfo_hz = item.tracking_cfo_hz
        candidate_rank = item.best_candidate_rank
        epoch_sample = item.epoch_sample
        acquired_cfo_hz = item.acquired_cfo_hz
        assert exact_score is not None
        assert control_score is not None
        assert margin is not None
        assert residual_cfo_hz is not None
        assert tracking_cfo_hz is not None
        assert candidate_rank is not None
        assert epoch_sample is not None
        assert acquired_cfo_hz is not None
        score = PilotMethodScore(
            method=PilotMethod.GLRT64,
            exact_score=exact_score,
            control_score=control_score,
            margin=margin,
            residual_cfo_hz=residual_cfo_hz,
            tracking_cfo_hz=tracking_cfo_hz,
        )
        candidate = PilotMethodCandidate(
            rank=candidate_rank,
            local_epoch_sample=epoch_sample,
            acquired_cfo_hz=acquired_cfo_hz,
            scores=(score,),
            qam_accuracy=None,
            qam_evm=None,
        )
        detections.append(
            PilotProbeDetection(
                status=NumericalStatus.COMPLETE,
                sample_start=item.sample_start,
                time_s=item.start_time_s,
                local_epoch_sample=epoch_sample,
                acquired_cfo_hz=acquired_cfo_hz,
                scores=(score,),
                qam_accuracy=None,
                qam_evm=None,
                reason=(
                    "20 ms winner passed the exact-minus-control margin gate"
                    if item.passed_margin_gate
                    else "20 ms winner retained as a conditioned-replay control"
                ),
                source_candidate_count=item.candidate_count,
                truncated_candidate_count=max(item.candidate_count - 1, 0),
                candidates=(candidate,),
            )
        )
    return tuple(detections)


def _threshold_winners(results: tuple[WindowResult, ...]) -> tuple[PilotProbeDetection, ...]:
    return _window_winners(results, require_margin_pass=True)


def _hough_tracks(
    results: tuple[WindowResult, ...],
    *,
    feedback: TrajectoryFeedbackConfig,
    segmentation: ResidualHoughSegmentationConfigV2,
    dealias: CfoDealiasConfigV2,
    seeded_alias_em: SeededAliasEmConfigV1,
    huber_linear: HuberLinearRefinementConfigV1,
) -> dict[str, Any]:
    detections = _threshold_winners(results)
    raw_bank, representatives = fit_residual_hough_pilot_trajectories(
        detections, feedback, segmentation
    )
    raw_observations = trajectory_observations(detections)
    if not raw_bank.trajectories:
        return {
            "input_observation_count": len(detections),
            "segmentation_config": segmentation.model_dump(mode="json"),
            "dealias_config": dealias.model_dump(mode="json"),
            "raw_hough_track_count": 0,
            "truncated_hough_track_count": raw_bank.truncated_trajectory_count,
            "published_track_count": 0,
            "returned_observation_count": 0,
            "tracks": [],
        }
    pilot_digest = canonical_digest(
        {
            "kind": "threshold-passing-20ms-window-winners-v1",
            "observation_ids": tuple(item.observation_id for item in raw_observations),
        }
    )
    raw_bank_digest = canonical_digest(
        {
            "kind": "threshold-winner-residual-hough-bank-v1",
            "config_digest": raw_bank.config_digest,
            "trajectories": tuple(
                (item.trajectory_id, item.observation_ids, item.coefficients_hz)
                for item in raw_bank.trajectories
            ),
        }
    )
    alias_map = build_cfo_alias_map(
        raw_bank,
        representatives,
        pilot_scan_digest=pilot_digest,
        raw_bank_digest=raw_bank_digest,
        config=dealias,
    )
    canonical = fit_huber_linear_dealiased_trajectories(
        raw_observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=dealias,
        seeded_em_config=seeded_alias_em,
        huber_config=huber_linear,
    )
    by_id = {item.observation_id: item for item in canonical.observations}
    tracks = []
    for index, branch in enumerate(
        sorted(canonical.branches, key=lambda item: (item.start_s, item.end_s)), start=1
    ):
        observations = tuple(by_id[item] for item in branch.observation_ids)
        tracks.append(
            {
                "track_label": f"H{index}",
                "start_s": branch.start_s,
                "end_s": branch.end_s,
                "reference_time_s": branch.model.reference_time_s,
                "slope_hz_s": branch.model.coefficients_hz[0],
                "cfo_at_reference_hz": branch.model.coefficients_hz[1],
                "observation_count": len(observations),
                "observations": [
                    {
                        "time_s": item.time_s,
                        "raw_cfo_hz": item.raw_cfo_hz,
                        "alias_index": item.alias_index,
                    }
                    for item in observations
                ],
            }
        )
    return {
        "input_observation_count": len(detections),
        "segmentation_config": segmentation.model_dump(mode="json"),
        "dealias_config": dealias.model_dump(mode="json"),
        "raw_hough_track_count": len(raw_bank.trajectories),
        "truncated_hough_track_count": raw_bank.truncated_trajectory_count,
        "published_track_count": len(tracks),
        "returned_observation_count": canonical.returned_observation_count,
        "tracks": tracks,
    }


def _constant_rate(
    results: tuple[WindowResult, ...], *, line_rms_reference_hz: float
) -> dict[str, Any] | None:
    selected = tuple(
        item
        for item in results
        if item.passed_margin_gate
        and item.robust_line_available
        and item.robust_slope_hz_s is not None
        and abs(item.robust_slope_hz_s) <= 10_000.0
        and item.robust_residual_rms_hz is not None
        and item.robust_residual_rms_hz <= line_rms_reference_hz
    )
    if not selected:
        return None
    rates = np.asarray([item.robust_slope_hz_s for item in selected], dtype=float)
    return {
        "input_filter": (
            "margin passes; within-window line RMS is at or below the display reference; "
            "Doppler rate lies inside +/-10 kHz/s"
        ),
        "point_count": len(selected),
        "start_s": min(item.center_time_s for item in selected),
        "end_s": max(item.center_time_s for item in selected),
        "constant_doppler_rate_hz_s": float(np.median(rates)),
        "median_absolute_deviation_hz_s": float(np.median(np.abs(rates - np.median(rates)))),
    }


def analyze_full_capture_glrt20ms(
    reader: IqReader,
    *,
    receiver_id: int,
    edge: StarlinkEdge,
    config: FullCaptureGlrt20msConfig,
    feedback: TrajectoryFeedbackConfig,
    segmentation: ResidualHoughSegmentationConfigV2,
    dealias: CfoDealiasConfigV2,
    seeded_alias_em: SeededAliasEmConfigV1,
    huber_linear: HuberLinearRefinementConfigV1,
    frequency_reference: ReceiverFrequencyCalibration | None = None,
) -> FullCaptureGlrt20msResult:
    if receiver_id not in reader.receiver_ids:
        raise ValueError("full-capture receiver is absent from IQ input")
    if not config.enabled:
        return FullCaptureGlrt20msResult(
            windows=(),
            hough_analysis={"tracks": [], "published_track_count": 0},
            constant_doppler_rate=None,
            status_note="disabled for this pipeline lane",
        )
    window_samples = round(config.window_ms * reader.sample_rate_hz / 1_000)
    stride_samples = round(config.stride_ms * reader.sample_rate_hz / 1_000)
    if reader.sample_count < window_samples:
        return FullCaptureGlrt20msResult(
            windows=(),
            hough_analysis={"tracks": [], "published_track_count": 0},
            constant_doppler_rate=None,
            status_note="capture is shorter than one complete diagnostic window",
        )
    acquisition = _acquisition_config(window_samples, feedback)

    def analyze(index: int, start: int, values: np.ndarray) -> WindowResult:
        return _analyze_window(
            index,
            start,
            values,
            sample_rate_hz=reader.sample_rate_hz,
            edge=edge,
            acquisition_config=acquisition,
            glrt_size=feedback.glrt_size,
            margin_gate=config.margin_gate,
            frequency_reference=frequency_reference,
        )

    windows = _run_parallel(
        _iter_windows(
            reader,
            receiver_id=receiver_id,
            window_samples=window_samples,
            stride_samples=stride_samples,
        ),
        analyze,
        workers=config.maximum_workers,
    )
    hough = _hough_tracks(
        windows,
        feedback=feedback,
        segmentation=segmentation,
        dealias=dealias,
        seeded_alias_em=seeded_alias_em,
        huber_linear=huber_linear,
    )
    return FullCaptureGlrt20msResult(
        windows=windows,
        hough_analysis=hough,
        constant_doppler_rate=_constant_rate(
            windows, line_rms_reference_hz=config.line_rms_reference_hz
        ),
        status_note="complete",
    )


def _robust_limits(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return (-1.0, 1.0)
    low, high = (
        np.quantile(finite, (0.005, 0.995)) if finite.size >= 20 else (min(finite), max(finite))
    )
    padding = max(1.0, 0.08 * float(high - low))
    return float(low - padding), float(high + padding)


def render_full_capture_glrt20ms_png(
    result: FullCaptureGlrt20msResult,
    *,
    session_id: str,
    path_label: str,
    config: FullCaptureGlrt20msConfig,
) -> bytes:
    rows = result.windows
    with (
        _RENDER_LOCK,
        plt.rc_context({"axes.grid": True, "grid.alpha": 0.22, "font.size": 10}),
    ):
        figure, axes = plt.subplots(
            3,
            2,
            figsize=(18, 12),
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": (1.0, 1.2, 1.2)},
        )
        if not rows:
            for axis in axes.flat:
                axis.text(0.5, 0.5, result.status_note, ha="center")
            figure.suptitle(f"{session_id} · {path_label} · {result.status_note}")
            return _save(figure)
        times = np.asarray([item.center_time_s for item in rows], dtype=float)
        margins = np.asarray(
            [np.nan if item.glrt_margin is None else item.glrt_margin for item in rows]
        )
        cfos = np.asarray(
            [np.nan if item.tracking_cfo_hz is None else item.tracking_cfo_hz for item in rows]
        )
        exact = np.asarray(
            [np.nan if item.glrt_exact_score is None else item.glrt_exact_score for item in rows]
        )
        control = np.asarray(
            [
                np.nan if item.glrt_control_score is None else item.glrt_control_score
                for item in rows
            ]
        )
        slopes = np.asarray(
            [np.nan if item.robust_slope_hz_s is None else item.robust_slope_hz_s for item in rows]
        )
        line_rms = np.asarray(
            [
                np.nan if item.robust_residual_rms_hz is None else item.robust_residual_rms_hz
                for item in rows
            ]
        )
        passed = np.asarray([item.passed_margin_gate for item in rows], dtype=bool)
        line_available = np.asarray([item.robust_line_available for item in rows], dtype=bool)

        detection, components = axes[0]
        cfo_axis, member_axis = axes[1]
        slope_axis, zoom_axis = axes[2]
        detection.scatter(times, margins, s=5, color=_GRAY, alpha=0.55, linewidths=0)
        detection.scatter(times[passed], margins[passed], s=9, color=_BLUE, alpha=0.85)
        detection.axhline(
            config.margin_gate,
            color=_RED,
            linewidth=1.0,
            linestyle="--",
            label=f"detection margin gate {config.margin_gate:.3f}",
        )
        detection.set_ylabel("GLRT-64\nexact − control")
        detection.set_title("A · Independent GLRT detection statistic per 20 ms window")
        detection.legend(loc="upper right", fontsize=9)

        components.scatter(times, exact, s=5, color=_BLUE, alpha=0.55, label="exact Qin pilots")
        components.scatter(
            times,
            control,
            s=5,
            color=_RED,
            alpha=0.45,
            label="17-symbol-rolled control",
        )
        components.set_ylabel("winning-candidate GLRT-64 score")
        components.set_title("B · Exact-pilot score and matched rolled control")
        components.legend(loc="upper right", fontsize=9)

        cfo_axis.scatter(times[~passed], cfos[~passed] / 1e3, s=4, color=_LIGHT_GRAY, alpha=0.4)
        cfo_axis.scatter(
            times[passed],
            cfos[passed] / 1e3,
            s=16,
            marker="x",
            color=_ORANGE,
            linewidths=0.65,
            alpha=0.65,
            label="margin-passing window winner",
        )
        cfo_axis.set_ylabel("best-window CFO (kHz)")
        cfo_axis.set_title("C · One scalar GLRT-64 CFO from every independent window")
        cfo_axis.legend(loc="upper right", fontsize=9)

        hough = result.hough_analysis
        alias_spacing = float(hough.get("dealias_config", {}).get("alias_spacing_hz", 1.0 / 4.4e-6))
        maximum_gap = float(hough.get("dealias_config", {}).get("continuity_gap_s", 1.1))
        for index, track in enumerate(hough.get("tracks", [])):
            color = _TRACK_COLORS[index % len(_TRACK_COLORS)]
            observations = tuple(sorted(track["observations"], key=lambda item: item["time_s"]))
            member_axis.scatter(
                [item["time_s"] for item in observations],
                [item["raw_cfo_hz"] / 1e3 for item in observations],
                s=16,
                marker="x",
                color=_ORANGE,
                linewidths=0.65,
                alpha=0.58,
            )
            labeled = False
            for alias_index in sorted({int(item["alias_index"]) for item in observations}):
                alias_times = np.asarray(
                    [
                        item["time_s"]
                        for item in observations
                        if int(item["alias_index"]) == alias_index
                    ]
                )
                split_indices = np.flatnonzero(np.diff(alias_times) > maximum_gap) + 1
                for run in np.split(alias_times, split_indices):
                    if not run.size:
                        continue
                    line_times = np.asarray([run[0], run[-1]])
                    line_cfo = (
                        float(track["cfo_at_reference_hz"])
                        + float(track["slope_hz_s"])
                        * (line_times - float(track["reference_time_s"]))
                        + alias_index * alias_spacing
                    )
                    member_axis.plot(
                        line_times,
                        line_cfo / 1e3,
                        color=color,
                        linewidth=1.25,
                        label=(
                            f"{track['track_label']} · {float(track['slope_hz_s']) / 1e3:+.2f} "
                            f"kHz/s · n={int(track['observation_count'])}"
                            if not labeled
                            else None
                        ),
                        zorder=3,
                    )
                    labeled = True
        member_axis.set_ylabel("segment-member raw CFO (kHz)")
        member_axis.set_title("D · Margin-pass Hough-segment members in the raw-CFO view")
        member_axis.set_ylim(cfo_axis.get_ylim())
        if hough.get("tracks"):
            member_axis.legend(loc="lower left", fontsize=6.5, ncol=2)

        below = line_available & ~passed
        clean = line_available & passed & (line_rms <= config.line_rms_reference_hz)
        noisy = line_available & passed & ~clean
        for axis in (slope_axis, zoom_axis):
            axis.scatter(times[below], slopes[below] / 1e3, s=4, color=_LIGHT_GRAY, alpha=0.4)
            axis.scatter(
                times[noisy],
                slopes[noisy] / 1e3,
                s=8,
                marker="x",
                color=_ORANGE,
                alpha=0.4,
                linewidths=0.5,
                label=(f"margin passes; line RMS > {config.line_rms_reference_hz:g} Hz"),
            )
            axis.scatter(
                times[clean],
                slopes[clean] / 1e3,
                s=10,
                facecolors="none",
                edgecolors=_BLUE,
                linewidths=0.6,
                label=(f"margin passes; line RMS ≤ {config.line_rms_reference_hz:g} Hz reference"),
            )
            axis.axhline(0.0, color=_INK, linewidth=0.7, alpha=0.7)
        slope_axis.set_ylim(*_robust_limits(slopes[line_available & passed] / 1e3))
        slope_axis.set_ylabel("within-window robust\nCFO slope (kHz/s)")
        slope_axis.set_title("E · Every robust within-window slope; broad diagnostic scale")
        slope_axis.legend(loc="upper right", fontsize=8)

        zoom_axis.set_ylim(-10.0, 10.0)
        zoom_axis.set_ylabel("within-window robust\nCFO slope (kHz/s)")
        zoom_axis.set_title("F · Fixed ±10 kHz/s zoom with robust constant rate")
        constant = result.constant_doppler_rate
        if constant is not None:
            rate = float(constant["constant_doppler_rate_hz_s"])
            zoom_axis.plot(
                [constant["start_s"], constant["end_s"]],
                [rate / 1e3, rate / 1e3],
                color=_INK,
                linewidth=1.25,
                label="robust constant Doppler rate",
            )
            zoom_axis.text(
                0.99,
                0.06,
                f"constant Doppler rate: {rate / 1e3:+.3f} kHz/s (n={constant['point_count']})",
                transform=zoom_axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
                bbox={"facecolor": "white", "edgecolor": _GRAY, "alpha": 0.88},
            )
        segment_constants = tuple(hough.get("segment_constant_rates", ()))
        for index, segment_constant in enumerate(segment_constants):
            rate = float(segment_constant["constant_doppler_rate_hz_s"])
            zoom_axis.plot(
                [segment_constant["start_s"], segment_constant["end_s"]],
                [rate / 1e3, rate / 1e3],
                color=_TRACK_COLORS[index % len(_TRACK_COLORS)],
                linewidth=1.4,
                label=(
                    f"segment {int(segment_constant['segment_index'])} constant rate · "
                    f"n={int(segment_constant['point_count'])}"
                ),
            )
        zoom_axis.legend(loc="upper right", fontsize=8)
        for axis in axes[2]:
            axis.set_xlabel("capture time (s)")
        for axis in axes.flat:
            axis.set_xlim(times[0] - 0.01, times[-1] + 0.01)
        figure.suptitle(
            f"{session_id} · {path_label} · {config.window_ms} ms / "
            f"{config.stride_ms} ms-stride GLRT-64\n"
            "fresh wide search per window; expanded linear Hough/de-alias diagnostic in D; "
            "linear CFO and constant-rate summaries only; no IQ replay",
            fontsize=14,
        )
        return _save(figure)


def _save(figure: Any) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=200, metadata={"Software": "leo-tracker"})
    plt.close(figure)
    return buffer.getvalue()
