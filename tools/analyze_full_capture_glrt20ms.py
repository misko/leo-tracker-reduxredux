#!/usr/bin/env python3
"""Run independent 20 ms GLRT-64 probes and robust frame-CFO lines.

The default case is the previously studied upper-edge signal path in
``cap-20260821T140820-470384cc9284``.  Every 20 ms probe performs a fresh wide
acquisition; no neighboring CFO, trajectory, replay product, or polynomial is
used.  The probe's best GLRT-64 candidate seeds actual-frame Qin-pilot CFO
measurements inside that probe.  A degree-one Huber IRLS fit then estimates the
within-probe frequency slope when at least six complete frames are available.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections.abc import Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam import analyze_pilot_phase_slope
from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.starlink import (
    ReceiverFrequencyCalibration,
    StarlinkEdge,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.acquisition import NumericalStatus, acquire_symbolwise
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    default_linear_cfo_dealias_config,
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
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    trajectory_observations,
)
from leo.contracts.cfo_dealias import (
    HuberLinearRefinementConfigV1,
    SeededAliasEmConfigV1,
)
from leo.contracts.digests import canonical_digest
from leo.storage import PinnedLocalRoot, RecordingStore

SESSION_ID = "cap-20260821T140820-470384cc9284"
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_23_140820_glrt20ms")
ZERO_CALIBRATION_SHA256 = "0" * 64
REPORT_ZOOM_START_S = 25.0
REPORT_ZOOM_END_S = 35.0

# Current production Standard acquisition geometry.  The requested schedule is
# intentionally denser (10 ms stride) than Standard's ordinary dwell schedule.
DEFAULT_CANDIDATES = 10
DEFAULT_EPOCH_SEPARATION_SAMPLES = 5
DEFAULT_CFO_SEPARATION_HZ = 10_000.0
DEFAULT_MARGIN_GATE = 0.025
DEFAULT_GLRT_SIZE = 512
# Existing Standard/scanner local-pilot analyses use 75 Hz as their line-RMS
# reference. Here it is a display diagnostic only, not a qualification verdict.
LINE_RMS_REFERENCE_HZ = 75.0

BLUE = "#2678a8"
ORANGE = "#d88b2f"
RED = "#c44e52"
INK = "#1f2933"
GRAY = "#a7b0b8"
LIGHT_GRAY = "#d9dee3"


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


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--session", default=SESSION_ID)
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=0)
    parser.add_argument("--edge", choices=("lower", "upper"), default="upper")
    parser.add_argument("--window-ms", type=int, default=20)
    parser.add_argument("--stride-ms", type=int, default=10)
    parser.add_argument("--start-s", type=float, default=0.0)
    parser.add_argument("--end-s", type=float)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--margin-gate", type=float, default=DEFAULT_MARGIN_GATE)
    parser.add_argument("--candidate-count", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _acquisition_config(probe_samples: int, candidate_count: int) -> SymbolwiseAcquisitionConfig:
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
        coarse_cfo_step_hz=80_000.0,
        fine_cfo_radius_hz=80_000.0,
        fine_cfo_step_hz=500.0,
        conditioned_cfo_radius_hz=2_000.0,
        conditioned_cfo_step_hz=100.0,
        retained_candidate_count=candidate_count,
        candidate_epoch_separation_samples=DEFAULT_EPOCH_SEPARATION_SAMPLES,
        candidate_cfo_separation_hz=DEFAULT_CFO_SEPARATION_HZ,
        maximum_probe_samples=probe_samples,
    )


def _fit_supported_frame_line(
    times_s: np.ndarray,
    cfo_hz: np.ndarray,
) -> dict[str, float | int | bool | None]:
    """Return robust degree-one metrics without changing point membership."""

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
    outliers = int(np.count_nonzero(np.abs(residual) > 1.345 * fit.mad_scale_hz))
    return {
        "available": True,
        "reference_time_s": fit.reference_time_s,
        "cfo_at_reference_hz": fit.intercept_at_reference_hz,
        "slope_hz_s": fit.slope_hz_per_s,
        "slope_sigma_hz_s": line_slope_sigma(times_s, fit),
        "residual_rms_hz": fit.residual_rms_hz,
        "median_absolute_residual_hz": fit.median_absolute_residual_hz,
        "mad_scale_hz": fit.mad_scale_hz,
        "outlier_count": outliers,
        "converged": fit.converged,
    }


def _analyze_window(
    probe_index: int,
    sample_start: int,
    samples: np.ndarray,
    *,
    sample_rate_hz: int,
    edge: StarlinkEdge,
    acquisition_config: SymbolwiseAcquisitionConfig,
    margin_gate: float,
) -> WindowResult:
    calibration = ReceiverFrequencyCalibration(
        receiver_id="baseband",
        center_hz=0.0,
        calibration_sha256=ZERO_CALIBRATION_SHA256,
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
            probe_index,
            sample_start,
            start_s,
            center_s,
            end_s,
            acquired.status.value,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            0,
            0,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            None,
            acquired.reason,
        )

    scored = tuple(
        (
            candidate,
            conditioned_glrt64_score(
                samples,
                sample_rate_hz,
                epoch_sample=candidate.refined_epoch_sample,
                acquired_cfo_hz=candidate.absolute_cfo_hz,
                edge=edge,
                glrt_size=DEFAULT_GLRT_SIZE,
            ),
        )
        for candidate in acquired.candidates
    )
    candidate, score = max(scored, key=lambda item: (item[1].margin, -item[0].rank))
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
    reason = (
        "Huber degree-one frame-CFO line available"
        if line["available"]
        else f"only {len(frames)} complete frame CFO measurements; need at least 6"
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
            None
            if line["reference_time_s"] is None
            else start_s + float(line["reference_time_s"])
        ),
        robust_cfo_at_reference_hz=_optional_float(line["cfo_at_reference_hz"]),
        robust_slope_hz_s=_optional_float(line["slope_hz_s"]),
        robust_slope_sigma_hz_s=_optional_float(line["slope_sigma_hz_s"]),
        robust_residual_rms_hz=_optional_float(line["residual_rms_hz"]),
        robust_median_absolute_residual_hz=_optional_float(
            line["median_absolute_residual_hz"]
        ),
        robust_mad_scale_hz=_optional_float(line["mad_scale_hz"]),
        robust_outlier_count=int(line["outlier_count"]),
        robust_converged=(None if line["converged"] is None else bool(line["converged"])),
        reason=reason,
    )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _iter_windows(
    reader,
    *,
    receiver_id: int,
    first_sample: int,
    stop_sample: int,
    window_samples: int,
    stride_samples: int,
) -> Iterable[tuple[int, int, np.ndarray]]:
    """Yield overlapping windows during one verified sequential read."""

    receiver_column = reader.receiver_ids.index(receiver_id)
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    next_start = first_sample
    probe_index = 0
    for block in reader.iter_blocks(block_samples=2**20):
        block_start = block.metadata.session_sample_start
        if block_start != expected_start:
            raise ValueError("full-capture GLRT requires contiguous recorded IQ")
        expected_start += block.metadata.sample_count
        block_end = expected_start
        if block_end <= first_sample:
            continue
        local_start = max(first_sample - block_start, 0)
        values = (
            block.samples[local_start:, receiver_column, 0].astype(np.float64)
            + 1j * block.samples[local_start:, receiver_column, 1].astype(np.float64)
        ) / 32_768.0
        values_start = block_start + local_start
        if not pending.size:
            pending_start = values_start
        elif values_start != pending_start + len(pending):
            raise ValueError("bounded IQ window buffer became discontinuous")
        pending = np.concatenate((pending, values))
        pending_end = pending_start + len(pending)
        while next_start + window_samples <= min(pending_end, stop_sample):
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
        if next_start + window_samples > stop_sample:
            return


def _run_bounded_parallel(
    windows: Iterable[tuple[int, int, np.ndarray]],
    function,
    *,
    workers: int,
    progress_every: int,
) -> tuple[WindowResult, ...]:
    completed: dict[int, WindowResult] = {}
    pending: dict[Future[WindowResult], int] = {}
    started = time.monotonic()
    reported = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for probe_index, sample_start, samples in windows:
            pending[executor.submit(function, probe_index, sample_start, samples)] = probe_index
            if len(pending) >= workers * 2:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    index = pending.pop(future)
                    completed[index] = future.result()
                if progress_every and len(completed) - reported >= progress_every:
                    elapsed = time.monotonic() - started
                    print(
                        f"completed {len(completed)} probes in {elapsed:.1f} s "
                        f"({len(completed) / max(elapsed, 1e-9):.2f} probes/s)",
                        flush=True,
                    )
                    reported = len(completed)
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                index = pending.pop(future)
                completed[index] = future.result()
    elapsed = time.monotonic() - started
    print(f"completed {len(completed)} probes in {elapsed:.1f} s", flush=True)
    return tuple(completed[index] for index in sorted(completed))


def _robust_limits(values: np.ndarray) -> tuple[float, float, int]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return (-1.0, 1.0, 0)
    low, high = (
        np.quantile(finite, (0.005, 0.995))
        if finite.size >= 20
        else (min(finite), max(finite))
    )
    if math.isclose(float(low), float(high)):
        padding = max(abs(float(low)) * 0.05, 1.0)
    else:
        padding = 0.08 * float(high - low)
    lower = float(low - padding)
    upper = float(high + padding)
    clipped = int(np.count_nonzero((finite < lower) | (finite > upper)))
    return lower, upper, clipped


def _threshold_winner_detections(
    results: tuple[WindowResult, ...],
) -> tuple[PilotProbeDetection, ...]:
    """Adapt passing window winners to the production Hough input contract."""

    detections: list[PilotProbeDetection] = []
    for item in results:
        if not item.passed_margin_gate:
            continue
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
        if any(value is None for value in required):
            continue
        score = PilotMethodScore(
            method=PilotMethod.GLRT64,
            exact_score=float(item.glrt_exact_score),
            control_score=float(item.glrt_control_score),
            margin=float(item.glrt_margin),
            residual_cfo_hz=float(item.residual_cfo_hz),
            tracking_cfo_hz=float(item.tracking_cfo_hz),
        )
        candidate = PilotMethodCandidate(
            rank=int(item.best_candidate_rank),
            local_epoch_sample=int(item.epoch_sample),
            acquired_cfo_hz=float(item.acquired_cfo_hz),
            scores=(score,),
            qam_accuracy=None,
            qam_evm=None,
        )
        detections.append(
            PilotProbeDetection(
                status=NumericalStatus.COMPLETE,
                sample_start=item.sample_start,
                time_s=item.start_time_s,
                local_epoch_sample=int(item.epoch_sample),
                acquired_cfo_hz=float(item.acquired_cfo_hz),
                scores=(score,),
                qam_accuracy=None,
                qam_evm=None,
                reason="20 ms winner passed the exact-minus-control margin gate",
                source_candidate_count=item.candidate_count,
                truncated_candidate_count=max(item.candidate_count - 1, 0),
                candidates=(candidate,),
            )
        )
    return tuple(detections)


def _hough_dealiased_tracks(results: tuple[WindowResult, ...]) -> dict[str, object]:
    """Run the production linear Hough/de-alias path on passing winners."""

    detections = _threshold_winner_detections(results)
    feedback = TrajectoryFeedbackConfig(
        maximum_scored_candidates_per_probe=DEFAULT_CANDIDATES,
        retained_candidate_count=DEFAULT_CANDIDATES,
        candidate_epoch_separation_samples=DEFAULT_EPOCH_SEPARATION_SAMPLES,
        candidate_cfo_separation_hz=DEFAULT_CFO_SEPARATION_HZ,
    )
    segmentation = default_alternate_cfo_config()
    dealias = default_linear_cfo_dealias_config()
    seeded_em = SeededAliasEmConfigV1()
    huber = HuberLinearRefinementConfigV1()
    raw_bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback,
        segmentation,
    )
    raw_observations = trajectory_observations(detections)
    pilot_scan_digest = canonical_digest(
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
                {
                    "trajectory_id": item.trajectory_id,
                    "observation_ids": item.observation_ids,
                    "coefficients_hz": item.coefficients_hz,
                }
                for item in raw_bank.trajectories
            ),
        }
    )
    alias_map = build_cfo_alias_map(
        raw_bank,
        representatives,
        pilot_scan_digest=pilot_scan_digest,
        raw_bank_digest=raw_bank_digest,
        config=dealias,
    )
    canonical = fit_huber_linear_dealiased_trajectories(
        raw_observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=dealias,
        seeded_em_config=seeded_em,
        huber_config=huber,
    )
    observation_by_id = {item.observation_id: item for item in canonical.observations}
    tracks: list[dict[str, object]] = []
    ordered_branches = sorted(canonical.branches, key=lambda item: (item.start_s, item.end_s))
    for track_index, branch in enumerate(ordered_branches, start=1):
        observations = tuple(observation_by_id[item] for item in branch.observation_ids)
        tracks.append(
            {
                "track_label": f"H{track_index}",
                "branch_id": branch.branch_id,
                "component_id": branch.component_id,
                "seed_trajectory_id": branch.seed_trajectory_id,
                "start_s": branch.start_s,
                "end_s": branch.end_s,
                "observation_count": len(observations),
                "reference_time_s": branch.model.reference_time_s,
                "slope_hz_s": branch.model.coefficients_hz[0],
                "cfo_at_reference_hz": branch.model.coefficients_hz[1],
                "residual_rms_hz": branch.model.residual_rms_hz,
                "observed_alias_indices": branch.observed_alias_indices,
                "observations": [
                    {
                        "time_s": item.time_s,
                        "raw_cfo_hz": item.raw_cfo_hz,
                        "dealiased_cfo_hz": item.component_cfo_hz,
                        "alias_index": item.alias_index,
                    }
                    for item in observations
                ],
            }
        )
    return {
        "input_filter": (
            "one independently acquired winning GLRT64 candidate from every window whose "
            "exact-minus-control margin passes the configured threshold"
        ),
        "input_time_convention": "20 ms window start time",
        "input_observation_count": len(detections),
        "frequency_trajectory_orders": [1],
        "algorithm_stages": [
            "residual Hough segmentation",
            "CFO alias-map construction",
            "seeded integer-alias EM",
            "MAD-scaled Huber degree-one refinement",
        ],
        "segmentation_config": segmentation.model_dump(mode="json"),
        "dealias_config": dealias.model_dump(mode="json"),
        "seeded_alias_em_config": seeded_em.model_dump(mode="json"),
        "huber_linear_config": huber.model_dump(mode="json"),
        "raw_hough_track_count": len(raw_bank.trajectories),
        "truncated_hough_track_count": raw_bank.truncated_trajectory_count,
        "alias_component_count": len(alias_map.components),
        "status": canonical.status.value,
        "published_track_count": len(tracks),
        "returned_observation_count": canonical.returned_observation_count,
        "tracks": tracks,
    }


def _robust_slope_trend(results: tuple[WindowResult, ...]) -> dict[str, object] | None:
    """Fit one robust degree-one trend through the clean, visible slope band."""

    selected = tuple(
        item
        for item in results
        if item.passed_margin_gate
        and item.robust_line_available
        and item.robust_slope_hz_s is not None
        and abs(item.robust_slope_hz_s) <= 10_000.0
        and item.robust_residual_rms_hz is not None
        and item.robust_residual_rms_hz <= LINE_RMS_REFERENCE_HZ
    )
    if len(selected) < 6:
        return None
    times = np.asarray([item.center_time_s for item in selected], dtype=float)
    rates = np.asarray([item.robust_slope_hz_s for item in selected], dtype=float)
    fit = frequency_line(times, rates)
    if fit is None:
        return None
    return {
        "input_filter": (
            "margin passes; within-window line RMS <= 75 Hz; Doppler rate lies inside "
            "the displayed +/-10 kHz/s band"
        ),
        "point_count": len(selected),
        "start_s": float(np.min(times)),
        "end_s": float(np.max(times)),
        "reference_time_s": fit.reference_time_s,
        "doppler_rate_at_reference_hz_s": fit.intercept_at_reference_hz,
        "doppler_rate_change_hz_s2": fit.slope_hz_per_s,
        "residual_rms_hz_s": fit.residual_rms_hz,
        "median_absolute_residual_hz_s": fit.median_absolute_residual_hz,
        "converged": fit.converged,
    }


def _plot(
    results: tuple[WindowResult, ...],
    *,
    session_id: str,
    path_label: str,
    margin_gate: float,
    output_path: Path,
    hough_analysis: dict[str, object] | None = None,
    slope_trend: dict[str, object] | None = None,
    display_start_s: float | None = None,
    display_end_s: float | None = None,
) -> None:
    times = np.asarray([item.center_time_s for item in results], dtype=float)
    margins = np.asarray(
        [np.nan if item.glrt_margin is None else item.glrt_margin for item in results], dtype=float
    )
    cfos = np.asarray(
        [np.nan if item.tracking_cfo_hz is None else item.tracking_cfo_hz for item in results],
        dtype=float,
    )
    exact_scores = np.asarray(
        [np.nan if item.glrt_exact_score is None else item.glrt_exact_score for item in results],
        dtype=float,
    )
    control_scores = np.asarray(
        [
            np.nan if item.glrt_control_score is None else item.glrt_control_score
            for item in results
        ],
        dtype=float,
    )
    slopes = np.asarray(
        [np.nan if item.robust_slope_hz_s is None else item.robust_slope_hz_s for item in results],
        dtype=float,
    )
    line_rms = np.asarray(
        [
            np.nan if item.robust_residual_rms_hz is None else item.robust_residual_rms_hz
            for item in results
        ],
        dtype=float,
    )
    passed = np.asarray([item.passed_margin_gate for item in results], dtype=bool)
    line_available = np.asarray([item.robust_line_available for item in results], dtype=bool)

    with plt.rc_context({"axes.grid": True, "grid.alpha": 0.22, "font.size": 10}):
        figure, axes = plt.subplots(
            3,
            2,
            figsize=(18, 12),
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": (1.0, 1.2, 1.2)},
        )
        detection = axes[0, 0]
        components = axes[0, 1]
        cfo_axis = axes[1, 0]
        cfo_pass_axis = axes[1, 1]
        slope_axis = axes[2, 0]
        slope_zoom_axis = axes[2, 1]
        detection.scatter(times, margins, s=5, color=GRAY, alpha=0.55, linewidths=0)
        detection.scatter(times[passed], margins[passed], s=9, color=BLUE, alpha=0.85, linewidths=0)
        detection.axhline(
            margin_gate,
            color=RED,
            linewidth=1.0,
            linestyle="--",
            label=f"detection margin gate {margin_gate:.3f}",
        )
        detection.set_ylabel("GLRT-64\nexact − control")
        detection.set_title("A · Independent GLRT detection statistic per 20 ms window")
        detection.legend(loc="upper right", fontsize=9)

        components.scatter(
            times,
            exact_scores,
            s=5,
            color=BLUE,
            alpha=0.55,
            linewidths=0,
            label="exact Qin pilots",
        )
        components.scatter(
            times,
            control_scores,
            s=5,
            color=RED,
            alpha=0.45,
            linewidths=0,
            label="17-symbol-rolled control",
        )
        components.set_ylabel("winning-candidate GLRT-64 score")
        components.set_title("B · Exact-pilot score and matched rolled control")
        components.legend(loc="upper right", fontsize=9)

        cfo_axis.scatter(times[~passed], cfos[~passed] / 1e3, s=4, color=LIGHT_GRAY, alpha=0.45)
        cfo_axis.scatter(
            times[passed],
            cfos[passed] / 1e3,
            s=9,
            facecolors="none",
            edgecolors=ORANGE,
            linewidths=0.55,
            label="best candidate in windows passing the margin gate",
        )
        cfo_axis.set_ylabel("best-window CFO (kHz)")
        cfo_axis.set_title("C · One scalar GLRT-64 CFO from every independent window")
        cfo_axis.legend(loc="upper right", fontsize=9)

        all_tracks = () if hough_analysis is None else tuple(hough_analysis["tracks"])
        tracks = tuple(
            track
            for track in all_tracks
            if (display_start_s is None or float(track["end_s"]) >= display_start_s)
            and (display_end_s is None or float(track["start_s"]) <= display_end_s)
        )
        colors = plt.get_cmap("tab10").colors
        dealias_config = {} if hough_analysis is None else hough_analysis["dealias_config"]
        alias_spacing_hz = float(dealias_config.get("alias_spacing_hz", 1.0 / 4.4e-6))
        maximum_gap_s = float(dealias_config.get("continuity_gap_s", 1.1))
        for track_index, track in enumerate(tracks):
            track_color = colors[track_index % len(colors)]
            observations = tuple(
                sorted(
                    track["observations"],
                    key=lambda item: (item["time_s"], item["alias_index"]),
                )
            )
            track_times = np.asarray([item["time_s"] for item in observations], dtype=float)
            track_cfos = np.asarray(
                [item["raw_cfo_hz"] for item in observations], dtype=float
            )
            cfo_pass_axis.scatter(
                track_times,
                track_cfos / 1e3,
                s=7,
                color=track_color,
                alpha=0.38,
                linewidths=0,
            )
            labeled = False
            for alias_index in sorted({int(item["alias_index"]) for item in observations}):
                alias_times = np.asarray(
                    [
                        item["time_s"]
                        for item in observations
                        if int(item["alias_index"]) == alias_index
                    ],
                    dtype=float,
                )
                split_indices = np.flatnonzero(np.diff(alias_times) > maximum_gap_s) + 1
                for run in np.split(alias_times, split_indices):
                    if not run.size:
                        continue
                    line_times = np.asarray([run[0], run[-1]], dtype=float)
                    line_cfos = (
                        float(track["cfo_at_reference_hz"])
                        + float(track["slope_hz_s"])
                        * (line_times - float(track["reference_time_s"]))
                        + alias_index * alias_spacing_hz
                    )
                    cfo_pass_axis.plot(
                        line_times,
                        line_cfos / 1e3,
                        color=track_color,
                        linewidth=1.35,
                        label=(
                            f"{track['track_label']} {track['start_s']:.2f}–"
                            f"{track['end_s']:.2f} s: "
                            f"{track['slope_hz_s'] / 1e3:+.2f} kHz/s"
                            if not labeled
                            else None
                        ),
                    )
                    labeled = True
        if not tracks:
            cfo_pass_axis.text(
                0.5,
                0.5,
                "no Hough segment met the production support gates",
                transform=cfo_pass_axis.transAxes,
                ha="center",
                va="center",
                color=INK,
            )
        cfo_pass_axis.set_ylabel("segment-member raw CFO (kHz)")
        cfo_pass_axis.set_title(
            "D · Margin-pass Hough-segment members in the same raw-CFO view"
        )
        if tracks:
            cfo_pass_axis.legend(loc="lower left", fontsize=6.8, ncol=2)
        cfo_pass_axis.set_ylim(cfo_axis.get_ylim())

        below = line_available & ~passed
        detected_line = line_available & passed
        reference_residual = detected_line & (line_rms <= LINE_RMS_REFERENCE_HZ)
        high_residual = detected_line & ~reference_residual

        def scatter_slopes(axis) -> None:
            axis.scatter(times[below], slopes[below] / 1e3, s=4, color=LIGHT_GRAY, alpha=0.4)
            axis.scatter(
                times[high_residual],
                slopes[high_residual] / 1e3,
                s=8,
                marker="x",
                color=ORANGE,
                alpha=0.4,
                linewidths=0.5,
                label="margin passes; line RMS > 75 Hz",
            )
            axis.scatter(
                times[reference_residual],
                slopes[reference_residual] / 1e3,
                s=10,
                facecolors="none",
                edgecolors=BLUE,
                linewidths=0.6,
                label="margin passes; line RMS ≤ 75 Hz reference",
            )
            axis.axhline(0.0, color=INK, linewidth=0.7, alpha=0.7)

        scatter_slopes(slope_axis)
        scatter_slopes(slope_zoom_axis)
        display_values = slopes[detected_line] / 1e3
        if np.count_nonzero(np.isfinite(display_values)) < 20:
            display_values = slopes[line_available] / 1e3
        lower, upper, _ = _robust_limits(display_values)
        detected_slopes = slopes[detected_line] / 1e3
        clipped = int(np.count_nonzero((detected_slopes < lower) | (detected_slopes > upper)))
        slope_axis.set_ylim(lower, upper)
        slope_axis.set_ylabel("within-window robust\nCFO slope (kHz/s)")
        slope_axis.set_title("E · Every robust within-window slope; broad diagnostic scale")
        if clipped:
            slope_axis.text(
                0.005,
                0.98,
                f"display clips {clipped} extreme margin-passing fits; JSON/CSV retain all",
                transform=slope_axis.transAxes,
                va="top",
                fontsize=8,
                color=INK,
            )
        slope_axis.legend(loc="upper right", fontsize=9)

        slope_zoom_axis.set_ylim(-10.0, 10.0)
        zoom_clipped = int(np.count_nonzero(np.abs(detected_slopes) > 10.0))
        slope_zoom_axis.set_ylabel("within-window robust\nCFO slope (kHz/s)")
        slope_zoom_axis.set_title("F · Fixed ±10 kHz/s zoom with robust degree-one trend")
        if slope_trend is not None:
            trend_times = np.asarray(
                [slope_trend["start_s"], slope_trend["end_s"]], dtype=float
            )
            trend_rates = float(slope_trend["doppler_rate_at_reference_hz_s"]) + float(
                slope_trend["doppler_rate_change_hz_s2"]
            ) * (trend_times - float(slope_trend["reference_time_s"]))
            slope_zoom_axis.plot(
                trend_times,
                trend_rates / 1e3,
                color=INK,
                linewidth=1.25,
                label="Huber d1 trend through clean visible rates",
            )
            annotation_time_s = float(slope_trend["reference_time_s"])
            if display_start_s is not None and display_end_s is not None:
                annotation_time_s = (display_start_s + display_end_s) / 2.0
            annotation_rate_hz_s = float(slope_trend["doppler_rate_at_reference_hz_s"]) + float(
                slope_trend["doppler_rate_change_hz_s2"]
            ) * (annotation_time_s - float(slope_trend["reference_time_s"]))
            slope_zoom_axis.text(
                0.99,
                0.06,
                (
                    f"robust Doppler rate at {annotation_time_s:.2f} s: "
                    f"{annotation_rate_hz_s / 1e3:+.3f} kHz/s\n"
                    "rate change: "
                    f"{slope_trend['doppler_rate_change_hz_s2']:+.1f} Hz/s² "
                    f"(n={slope_trend['point_count']})"
                ),
                transform=slope_zoom_axis.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
                color=INK,
                bbox={"facecolor": "white", "edgecolor": GRAY, "alpha": 0.88},
            )
        if zoom_clipped:
            slope_zoom_axis.text(
                0.005,
                0.98,
                f"{zoom_clipped} margin-passing slopes lie outside ±10 kHz/s",
                transform=slope_zoom_axis.transAxes,
                va="top",
                fontsize=8,
                color=INK,
            )
        slope_zoom_axis.legend(loc="upper right", fontsize=9)
        slope_axis.set_xlabel("capture time (s)")
        slope_zoom_axis.set_xlabel("capture time (s)")
        x_start = times[0] - 0.01 if display_start_s is None else display_start_s
        x_end = times[-1] + 0.01 if display_end_s is None else display_end_s
        if not math.isfinite(x_start) or not math.isfinite(x_end) or x_end <= x_start:
            raise ValueError("plot display interval must be finite and increasing")
        for axis in axes.flat:
            axis.set_xlim(x_start, x_end)
        view_note = (
            ""
            if display_start_s is None and display_end_s is None
            else f" · {x_start:g}–{x_end:g} s zoom"
        )
        figure.suptitle(
            f"{session_id} · {path_label} · 20 ms / 10 ms-stride GLRT-64{view_note}\n"
            "fresh wide search per window; production Hough/de-alias diagnostic in D; "
            "degree-one fits only; no IQ replay",
            fontsize=14,
        )
        figure.savefig(output_path, dpi=200, metadata={"Software": "leo-tracker"})
        plt.close(figure)


def _write_csv(path: Path, results: tuple[WindowResult, ...]) -> None:
    rows = [asdict(item) for item in results]
    if not rows:
        raise ValueError("cannot write an empty result table")
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _summary(results: tuple[WindowResult, ...]) -> dict[str, object]:
    passed = tuple(item for item in results if item.passed_margin_gate)
    fit = tuple(item for item in results if item.robust_line_available)
    passed_fit = tuple(item for item in passed if item.robust_line_available)
    reference_residual = tuple(
        item
        for item in passed_fit
        if item.robust_residual_rms_hz is not None
        and item.robust_residual_rms_hz <= LINE_RMS_REFERENCE_HZ
    )
    return {
        "window_count": len(results),
        "margin_pass_count": len(passed),
        "margin_pass_fraction": len(passed) / len(results),
        "robust_line_count": len(fit),
        "robust_line_fraction": len(fit) / len(results),
        "margin_pass_with_robust_line_count": len(passed_fit),
        "margin_pass_with_robust_line_fraction": len(passed_fit) / max(len(passed), 1),
        "margin_pass_with_line_rms_le_75_hz_count": len(reference_residual),
        "maximum_glrt_margin": max(
            item.glrt_margin for item in results if item.glrt_margin is not None
        ),
    }


def main() -> int:
    args = _arguments()
    if args.window_ms <= 0 or args.stride_ms <= 0:
        raise ValueError("window and stride must be positive")
    if args.workers <= 0 or args.candidate_count <= 0:
        raise ValueError("worker and candidate counts must be positive")
    if not math.isfinite(args.start_s) or args.start_s < 0:
        raise ValueError("start time must be finite and nonnegative")
    if args.end_s is not None and (
        not math.isfinite(args.end_s) or args.end_s <= args.start_s
    ):
        raise ValueError("end time must be finite and greater than start")

    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    try:
        bundle = store.inspect(args.session)
        reader = store.reader(bundle, args.stream, verify=True)
        if args.receiver not in reader.receiver_ids:
            raise ValueError(f"receiver {args.receiver} is absent from {args.stream}")
        sample_rate_hz = reader.sample_rate_hz
        capture_end_s = reader.sample_count / sample_rate_hz
        end_s = capture_end_s if args.end_s is None else min(args.end_s, capture_end_s)
        window_samples = round(args.window_ms * sample_rate_hz / 1_000)
        stride_samples = round(args.stride_ms * sample_rate_hz / 1_000)
        first_sample = round(args.start_s * sample_rate_hz)
        stop_sample = round(end_s * sample_rate_hz)
        if first_sample + window_samples > stop_sample:
            raise ValueError("selected interval contains no complete analysis window")
        acquisition = _acquisition_config(window_samples, args.candidate_count)
        edge = StarlinkEdge(args.edge)
        function = lambda index, start, values: _analyze_window(  # noqa: E731
            index,
            start,
            values,
            sample_rate_hz=sample_rate_hz,
            edge=edge,
            acquisition_config=acquisition,
            margin_gate=args.margin_gate,
        )
        results = _run_bounded_parallel(
            _iter_windows(
                reader,
                receiver_id=args.receiver,
                first_sample=first_sample,
                stop_sample=stop_sample,
                window_samples=window_samples,
                stride_samples=stride_samples,
            ),
            function,
            workers=args.workers,
            progress_every=args.progress_every,
        )
    finally:
        store.close()

    args.output_root.mkdir(parents=True, exist_ok=True)
    stem = f"{args.session}-{args.stream}-rx{args.receiver}-{args.edge}-glrt20ms"
    png_path = args.output_root / f"{stem}.png"
    zoom_png_path = args.output_root / f"{stem}-zoom-25-35s.png"
    json_path = args.output_root / f"{stem}.json"
    csv_path = args.output_root / f"{stem}.csv"
    hough_analysis = _hough_dealiased_tracks(results)
    slope_trend = _robust_slope_trend(results)
    _plot(
        results,
        session_id=args.session,
        path_label=f"{args.stream}/RX{args.receiver} {args.edge}",
        margin_gate=args.margin_gate,
        output_path=png_path,
        hough_analysis=hough_analysis,
        slope_trend=slope_trend,
    )
    _plot(
        results,
        session_id=args.session,
        path_label=f"{args.stream}/RX{args.receiver} {args.edge}",
        margin_gate=args.margin_gate,
        output_path=zoom_png_path,
        hough_analysis=hough_analysis,
        slope_trend=slope_trend,
        display_start_s=REPORT_ZOOM_START_S,
        display_end_s=REPORT_ZOOM_END_S,
    )
    _write_csv(csv_path, results)
    summary = _summary(results)
    summary.update(
        {
            "hough_dealiased_track_count": hough_analysis["published_track_count"],
            "hough_dealiased_observation_count": hough_analysis[
                "returned_observation_count"
            ],
            "robust_slope_trend_point_count": (
                0 if slope_trend is None else slope_trend["point_count"]
            ),
        }
    )
    document = {
        "schema_version": 2,
        "kind": "full-capture-glrt20ms-linear-hough-dealias-audit",
        "session_id": args.session,
        "recording_uri": bundle.uri,
        "recording_manifest_sha256": bundle.manifest_sha256,
        "stream_id": args.stream,
        "receiver_id": args.receiver,
        "edge": args.edge,
        "sample_rate_hz": sample_rate_hz,
        "capture_sample_count": reader.sample_count,
        "capture_duration_s": capture_end_s,
        "analyzed_start_s": args.start_s,
        "analyzed_end_s": end_s,
        "window_ms": args.window_ms,
        "stride_ms": args.stride_ms,
        "glrt_margin_gate": args.margin_gate,
        "glrt_size": DEFAULT_GLRT_SIZE,
        "line_rms_display_reference_hz": LINE_RMS_REFERENCE_HZ,
        "line_rms_display_reference_is_qualification": False,
        "frequency_trajectory_orders": [1],
        "neighboring_window_state_used": False,
        "trajectory_used_for_window_measurements": False,
        "trajectory_used_for_panel_d_diagnostic": True,
        "replay_used": False,
        "overlapping_windows_are_statistically_independent": False,
        "overlap_note": (
            "Each search is algorithmically independent, but adjacent windows share 10 ms of "
            "recorded samples and therefore are statistically correlated."
        ),
        "cfo_note": (
            "tracking_cfo_hz is the single scalar GLRT-64 CFO for the best candidate in a "
            "20 ms window. Panel D alone passes margin-qualified winners through the "
            "production residual-Hough, alias-map, seeded-alias-EM, and Huber degree-one "
            "path, then displays only retained segment observations and models lifted back "
            "into raw-CFO coordinates. robust_slope_hz_s is a separate Huber degree-one fit "
            "to every complete actual-frame pilot CFO measurement inside that window. Lines "
            "below the GLRT margin gate are noise diagnostics, not signal measurements."
        ),
        "acquisition_config": asdict(acquisition),
        "hough_dealias_analysis": hough_analysis,
        "robust_slope_trend": slope_trend,
        "figure_files": {
            "full_capture": png_path.name,
            "zoom_25_35_s": zoom_png_path.name,
        },
        "summary": summary,
        "windows": [asdict(item) for item in results],
    }
    json_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    print(png_path)
    print(zoom_png_path)
    print(json_path)
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
