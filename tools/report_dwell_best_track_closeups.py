#!/usr/bin/env python3
"""Render close-up and A-like CFO evidence for a dwell's best pilot tracks.

The script ranks sealed Standard products, then exactly replays only the two
selected 75 ms close-ups plus every bounded window on the best track from
immutable recording IQ.  The output is reporting evidence; it does not alter
any persisted Standard contract or recording.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfig,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.starlink.kalman_tracking import (
    PolynomialFrequencyModel,
    raw_candidate_sources,
)
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4, FinalTrajectoryBankV3
from leo.contracts.kalman_tracking import KalmanTrajectoryTrackV1, StandardKalmanTrackingV1
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentV1,
    StandardPilotDopplerSegmentsV1,
)
from leo.contracts.states import StarlinkEdge
from leo.storage.store import RecordingStore

INK = "#17394d"
BLUE = "#277da1"
AMBER = "#d48806"
GREEN = "#2a9d55"
GRAY = "#9aa7b2"
RED = "#c94c4c"


@dataclass(frozen=True, slots=True)
class PathIdentity:
    label: str
    stream_id: str
    receiver_id: int


@dataclass(frozen=True, slots=True)
class Candidate:
    scope_digest: str
    path: PathIdentity
    product_dir: Path
    kalman: StandardKalmanTrackingV1
    bank: FinalTrajectoryBankV3
    segments: StandardPilotDopplerSegmentsV1
    track: KalmanTrajectoryTrackV1
    qualified_segments: tuple[PilotDopplerSegmentV1, ...]

    @property
    def path_label(self) -> str:
        return self.path.label

    @property
    def track_score(self) -> tuple[float | str, ...]:
        held_out = min(
            item.held_out_frequency_rms_hz
            for item in self.qualified_segments
            if item.held_out_frequency_rms_hz is not None
        )
        return (
            -len(self.qualified_segments),
            -sum(item.frequency_update_count for item in self.qualified_segments),
            held_out,
            -self.track.measurement_update_count,
            self.scope_digest,
            self.track.source_trajectory_id,
        )

    @property
    def best_segment(self) -> PilotDopplerSegmentV1:
        def score(item: PilotDopplerSegmentV1) -> tuple[float | int, ...]:
            return (
                -item.supported_frame_fraction,
                -item.frequency_update_count,
                item.held_out_frequency_rms_hz or math.inf,
                item.frequency_line_rms_hz or math.inf,
                item.local_doppler_rate_sigma_hz_s or math.inf,
                item.segment_index,
            )

        return min(self.qualified_segments, key=score)


def _read_contract(path: Path, model: type[Any]) -> Any:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _path_identities(session_id: str, api_base: str | None) -> dict[str, PathIdentity]:
    if not api_base:
        return {}
    url = f"{api_base.rstrip('/')}/api/v2/recordings/{session_id}/standard-subjects"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError):
        return {}
    identities: dict[str, PathIdentity] = {}
    for row in payload.get("rows", []):
        for receiver in row.get("receiver_paths", []):
            scope = receiver.get("scope") or {}
            digest = receiver.get("scope_digest")
            if not digest or digest in identities:
                continue
            stream_id = scope.get("stream_id", "unknown stream")
            identities[digest] = PathIdentity(
                label=(
                    f"{receiver.get('radio_label', receiver.get('radio_id', 'radio'))} "
                    f"{receiver.get('receiver_label', 'RX?')} · {stream_id}"
                ),
                stream_id=stream_id,
                receiver_id=int(receiver["receiver_id"]),
            )
    return identities


def _load_candidates(
    session_id: str,
    analysis_root: Path,
    identities: dict[str, PathIdentity],
) -> list[Candidate]:
    candidates: list[Candidate] = []
    pattern = f"{session_id}/capture-*/scientific/path-standard/sha256:*"
    for product_dir in sorted(analysis_root.glob(pattern)):
        required = {
            "kalman": product_dir / "standard.kalman-tracking.v1.json",
            "bank": product_dir / "standard.final-trajectory-bank.v3.json",
            "segments": product_dir / "standard.pilot-doppler-segments.v1.json",
        }
        if not all(path.is_file() for path in required.values()):
            continue
        kalman = _read_contract(required["kalman"], StandardKalmanTrackingV1)
        bank = _read_contract(required["bank"], FinalTrajectoryBankV3)
        segments = _read_contract(required["segments"], StandardPilotDopplerSegmentsV1)
        if segments.kalman_tracking_digest != kalman.content_digest:
            raise ValueError(f"Kalman/segment digest mismatch in {product_dir}")
        if segments.final_trajectory_bank_digest != bank.content_digest:
            raise ValueError(f"trajectory/segment digest mismatch in {product_dir}")
        scope_digest = product_dir.name.removeprefix("sha256:")
        identity = identities.get(scope_digest)
        if identity is None:
            continue
        qualified_by_track: dict[str, list[PilotDopplerSegmentV1]] = {}
        for segment in segments.segments:
            if segment.qualified:
                qualified_by_track.setdefault(segment.source_trajectory_id, []).append(segment)
        for track in kalman.tracks:
            qualified = tuple(qualified_by_track.get(track.source_trajectory_id, ()))
            if not qualified:
                continue
            candidates.append(
                Candidate(
                    scope_digest=scope_digest,
                    path=identity,
                    product_dir=product_dir,
                    kalman=kalman,
                    bank=bank,
                    segments=segments,
                    track=track,
                    qualified_segments=qualified,
                )
            )
    return sorted(candidates, key=lambda item: item.track_score)


def _model(candidate: Candidate) -> PolynomialFrequencyModel:
    trajectory = next(
        item
        for item in candidate.bank.trajectories
        if item.trajectory_id == candidate.track.source_trajectory_id
    )
    return PolynomialFrequencyModel(
        trajectory.reference_time_s,
        tuple(trajectory.absolute_coefficients_hz),
    )


def _stream_edge(tags: tuple[str, ...], stream_id: str) -> StarlinkEdge:
    prefix = f"tuning:{stream_id}:"
    matches = [tag for tag in tags if tag.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"recording must identify exactly one tuning tag for {stream_id}")
    return StarlinkEdge(matches[0].rsplit(":", 1)[-1])


def _replay_segment(
    candidate: Candidate,
    store: RecordingStore,
    bundle: Any,
    segment: PilotDopplerSegmentV1 | None = None,
) -> PilotPntKalmanResult:
    """Reproduce the exact local tracker input behind one persisted segment."""

    segment = segment or candidate.best_segment
    scan_document = json.loads(
        (candidate.product_dir / "standard.pilot-scan.v3.json").read_text(encoding="utf-8")
    )
    detections = _pilot_detections(scan_document)
    raw_sources = raw_candidate_sources(detections)
    canonical_bank = _read_contract(
        candidate.product_dir / "standard.dealiased-trajectory-bank.v4.json",
        DealiasedTrajectoryBankV4,
    )
    canonical_by_id = {item.observation_id: item for item in canonical_bank.observations}
    trajectory = next(
        item
        for item in candidate.bank.trajectories
        if item.trajectory_id == candidate.track.source_trajectory_id
    )
    timing_source = None
    for observation_id in trajectory.observation_ids:
        canonical = canonical_by_id.get(observation_id)
        if canonical is None:
            continue
        for source_id in canonical.source_observation_ids:
            source = raw_sources.get(source_id)
            if (
                source is not None
                and source.detection_sample_start == segment.source_probe_sample_start
            ):
                timing_source = source
                break
        if timing_source is not None:
            break
    if timing_source is None:
        raise ValueError(f"could not resolve raw timing source for segment {segment.segment_index}")

    reader = store.reader(bundle, candidate.path.stream_id, verify=True)
    sample_count = round(candidate.segments.config.window_duration_s * reader.sample_rate_hz)
    ci16 = reader.read(
        segment.source_probe_sample_start,
        sample_count,
        receiver_ids=(candidate.path.receiver_id,),
    )
    samples = (ci16[:, 0, 0].astype(np.float64) + 1j * ci16[:, 0, 1].astype(np.float64)) / 32_768.0
    model = _model(candidate)
    result = analyze_contiguous_pilot_pnt_kalman(
        samples,
        reader.sample_rate_hz,
        epoch_sample=timing_source.local_epoch_sample,
        initial_absolute_cfo_hz=float(model.frequency_hz(segment.start_time_s)),
        edge=_stream_edge(bundle.manifest.tags, candidate.path.stream_id),
        maximum_residual_cfo_hz=candidate.segments.config.maximum_residual_cfo_hz,
        config=PilotPntKalmanConfig(),
    )
    if (
        result.supported_frame_count != segment.supported_frame_count
        or result.frequency_update_count != segment.frequency_update_count
        or result.phase_update_count != segment.phase_update_count
        or not result.frames
        or not math.isclose(
            result.frames[-1].tracked_doppler_rate_hz_s,
            segment.kalman_doppler_rate_hz_s,
            rel_tol=0,
            abs_tol=1e-6,
        )
    ):
        raise ValueError(f"raw replay does not reproduce sealed segment {segment.segment_index}")
    return result


def _track_segments(candidate: Candidate) -> tuple[PilotDopplerSegmentV1, ...]:
    return tuple(
        sorted(
            (
                item
                for item in candidate.segments.segments
                if item.source_trajectory_id == candidate.track.source_trajectory_id
            ),
            key=lambda item: (item.start_time_s, item.segment_index),
        )
    )


def _render_a_like(
    candidate: Candidate,
    replayed: list[tuple[PilotDopplerSegmentV1, PilotPntKalmanResult]],
    *,
    session_id: str,
    output_path: Path,
    frame_csv_path: Path,
) -> dict[str, Any]:
    """Render an A-like dense view from exact per-frame raw-IQ replays."""

    model = _model(candidate)
    figure = Figure(figsize=(16.0, 7.8), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    axis = figure.subplots(1, 1)
    accepted_count = 0
    rejected_count = 0
    frame_count = 0
    plotted_values: list[float] = [0.0]
    rows: list[dict[str, Any]] = []
    qualified_span_labeled = False
    unqualified_span_labeled = False
    for window_index, (segment, result) in enumerate(replayed):
        frames = result.frames
        if not frames:
            continue
        relative_times = np.asarray([item.time_s for item in frames], dtype=float)
        times = segment.start_time_s + relative_times
        measured = np.asarray([item.absolute_cfo_measurement_hz for item in frames], dtype=float)
        tracked = np.asarray([item.tracked_absolute_cfo_hz for item in frames], dtype=float)
        frozen = model.frequency_hz(times)
        measured_residual = measured - frozen
        tracked_residual = tracked - frozen
        supported = np.asarray([item.measurement_supported for item in frames], dtype=bool)
        accepted_count += int(np.count_nonzero(supported))
        rejected_count += int(np.count_nonzero(~supported))
        frame_count += len(frames)
        plotted_values.extend(measured_residual[np.isfinite(measured_residual)].tolist())
        plotted_values.extend(tracked_residual[np.isfinite(tracked_residual)].tolist())

        span_label = None
        if segment.qualified and not qualified_span_labeled:
            span_label = "qualified 75 ms segment"
            qualified_span_labeled = True
        elif not segment.qualified and not unqualified_span_labeled:
            span_label = "unqualified 75 ms segment"
            unqualified_span_labeled = True
        axis.axvspan(
            segment.start_time_s,
            segment.end_time_s,
            color=GREEN if segment.qualified else GRAY,
            alpha=0.065 if segment.qualified else 0.045,
            linewidth=0,
            label=span_label,
        )
        axis.scatter(
            times[~supported],
            measured_residual[~supported],
            color=GRAY,
            marker="x",
            s=17,
            alpha=0.30,
            linewidths=0.8,
            label="rejected/coasted frame" if window_index == 0 else None,
            zorder=2,
        )
        axis.scatter(
            times[supported],
            measured_residual[supported],
            color=BLUE,
            s=18,
            alpha=0.58,
            linewidths=0,
            label="accepted raw pilot-frame CFO" if window_index == 0 else None,
            zorder=3,
        )
        axis.plot(
            times,
            tracked_residual,
            color=AMBER,
            linewidth=1.55,
            alpha=0.92,
            label="local phase + Doppler tracker" if window_index == 0 else None,
            zorder=4,
        )
        if segment.local_cfo_at_reference_hz is not None:
            local = segment.local_cfo_at_reference_hz + segment.local_doppler_rate_hz_s * (
                times - segment.reference_time_s
            )
            axis.plot(
                times,
                local - frozen,
                color=GREEN,
                linewidth=1.1,
                alpha=0.90 if segment.qualified else 0.35,
                linestyle="--",
                label="direct segment CFO line" if window_index == 0 else None,
                zorder=5,
            )
        for item, time_s, measured_value, tracked_value, model_value in zip(
            frames, times, measured, tracked, frozen, strict=True
        ):
            rows.append(
                {
                    "segment_index": segment.segment_index,
                    "segment_qualified": segment.qualified,
                    "frame_index": item.frame_index,
                    "capture_time_s": float(time_s),
                    "measurement_supported": item.measurement_supported,
                    "absolute_cfo_measurement_hz": float(measured_value),
                    "tracked_absolute_cfo_hz": float(tracked_value),
                    "frozen_model_cfo_hz": float(model_value),
                    "measurement_residual_hz": float(measured_value - model_value),
                    "tracked_residual_hz": float(tracked_value - model_value),
                    "tracked_doppler_rate_hz_s": item.tracked_doppler_rate_hz_s,
                    "phase_innovation_modulo_pi_rad": item.phase_innovation_modulo_pi_rad,
                    "phase_update_applied": item.phase_update_applied,
                    "frequency_update_applied": item.frequency_update_applied,
                }
            )

    values = np.asarray(plotted_values, dtype=float)
    lower, upper = _robust_limits(values, minimum_span=800.0)
    axis.set_ylim(lower, upper)
    if replayed:
        axis.set_xlim(replayed[0][0].start_time_s, replayed[-1][0].end_time_s)
    axis.axhline(0, color=INK, linewidth=1.15, label="frozen trajectory")
    axis.set_xlabel("capture time (s)")
    axis.set_ylabel("CFO residual vs frozen trajectory (Hz)")
    axis.set_title(
        f"A-like · {len(replayed)} complete 75 ms windows, {frame_count} pilot-frame epochs\n"
        f"{candidate.path_label} · accepted {accepted_count}, rejected/coasted {rejected_count}",
        loc="left",
        fontweight="bold",
    )
    axis.grid(alpha=0.22)
    handles, labels = axis.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=True))
    axis.legend(unique.values(), unique.keys(), fontsize=8.5, loc="best")
    figure.suptitle(
        "Dense per-frame pilot carrier tracking from the current Standard segment analysis\n"
        f"{session_id}",
        fontsize=15.5,
        fontweight="bold",
    )
    canvas.print_png(output_path)

    with frame_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]) if rows else [],
            lineterminator="\n",
        )
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    return {
        "scope_digest": candidate.scope_digest,
        "path_label": candidate.path_label,
        "source_trajectory_id": candidate.track.source_trajectory_id,
        "segment_count": len(replayed),
        "qualified_segment_count": sum(item.qualified for item, _ in replayed),
        "frame_count": frame_count,
        "accepted_frame_count": accepted_count,
        "rejected_or_coasted_frame_count": rejected_count,
        "nominal_frame_period_ms": 1_000 / 750,
        "frame_csv": str(frame_csv_path),
        "segments": [
            {
                "segment_index": item.segment_index,
                "start_time_s": item.start_time_s,
                "end_time_s": item.end_time_s,
                "qualified": item.qualified,
                "supported_frame_count": item.supported_frame_count,
                "lattice_frame_count": item.lattice_frame_count,
                "local_doppler_rate_hz_s": item.local_doppler_rate_hz_s,
                "kalman_doppler_rate_hz_s": item.kalman_doppler_rate_hz_s,
                "frozen_doppler_rate_hz_s": item.frozen_doppler_rate_hz_s,
                "qualification_failures": list(item.qualification_failures),
            }
            for item, _ in replayed
        ],
    }


def _robust_limits(values: np.ndarray, minimum_span: float) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return (-minimum_span / 2, minimum_span / 2)
    lower, upper = np.quantile(finite, (0.01, 0.99))
    center = float((lower + upper) / 2)
    span = max(minimum_span, float(upper - lower) * 1.2)
    return center - span / 2, center + span / 2


def _plot_candidate(
    cfo_axis: Any,
    rate_axis: Any,
    candidate: Candidate,
    local_result: PilotPntKalmanResult,
    *,
    rank: int,
) -> dict[str, Any]:
    segment = candidate.best_segment
    model = _model(candidate)
    frames = local_result.frames
    if not frames:
        raise ValueError(f"selected segment {segment.segment_index} replay returned no frames")
    relative_times = np.asarray([item.time_s for item in frames], dtype=float)
    times = segment.start_time_s + relative_times
    relative_ms = relative_times * 1_000
    supported = np.asarray([item.measurement_supported for item in frames], dtype=bool)
    measured = np.asarray([item.absolute_cfo_measurement_hz for item in frames], dtype=float)
    tracked = np.asarray([item.tracked_absolute_cfo_hz for item in frames], dtype=float)
    tracked_rate = np.asarray([item.tracked_doppler_rate_hz_s for item in frames], dtype=float)
    tracked_rate_sigma = np.asarray([item.doppler_rate_sigma_hz_s for item in frames], dtype=float)
    frozen = model.frequency_hz(times)
    frozen_rate = model.doppler_rate_hz_s(times)
    measured_residual = measured - frozen
    tracked_residual = tracked - frozen
    local = segment.local_cfo_at_reference_hz + segment.local_doppler_rate_hz_s * (
        times - segment.reference_time_s
    )
    local_residual = local - frozen

    detail_values = np.concatenate(
        (measured_residual[supported], tracked_residual, local_residual, np.asarray([0.0]))
    )
    cfo_lower, cfo_upper = _robust_limits(detail_values, minimum_span=300.0)
    rejected_in_detail = (
        (~supported) & (measured_residual >= cfo_lower) & (measured_residual <= cfo_upper)
    )
    if np.any(rejected_in_detail):
        cfo_axis.scatter(
            relative_ms[rejected_in_detail],
            measured_residual[rejected_in_detail],
            marker="x",
            color=GRAY,
            s=28,
            alpha=0.55,
            label=f"exact/control-gate rejects ({np.count_nonzero(~supported)})",
            zorder=2,
        )
    cfo_axis.scatter(
        relative_ms[supported],
        measured_residual[supported],
        color=BLUE,
        s=30,
        alpha=0.72,
        linewidths=0,
        label=f"raw supported pilot CFO ({np.count_nonzero(supported)})",
        zorder=3,
    )
    cfo_axis.plot(
        relative_ms,
        tracked_residual,
        color=AMBER,
        linewidth=1.8,
        label="local five-state Kalman CFO",
        zorder=4,
    )
    cfo_axis.plot(
        relative_ms,
        local_residual,
        color=GREEN,
        linewidth=2.4,
        label="direct 75 ms CFO line",
        zorder=5,
    )
    cfo_axis.axhline(0, color=INK, linewidth=1.2, label="frozen trajectory")
    cfo_axis.set_ylim(cfo_lower, cfo_upper)
    cfo_axis.set_xlim(0, (segment.end_time_s - segment.start_time_s) * 1_000)
    cfo_axis.set_xlabel("time within selected segment (ms)")
    cfo_axis.set_ylabel("CFO residual vs frozen trajectory (Hz)")
    cfo_axis.set_title(
        f"A{rank} · raw supported CFO and fitted structure\n"
        f"{candidate.path_label} · {segment.start_time_s:.3f}–{segment.end_time_s:.3f} s",
        loc="left",
        fontweight="bold",
    )

    accepted_x = relative_ms[supported]
    accepted_rate = tracked_rate[supported] / 1_000
    accepted_sigma = tracked_rate_sigma[supported] / 1_000
    bootstrap_frames = [item for item in frames if item.doppler_rate_bootstrapped]
    if bootstrap_frames:
        bootstrap_ms = bootstrap_frames[0].time_s * 1_000
        rate_axis.axvspan(
            0,
            bootstrap_ms,
            color=GRAY,
            alpha=0.10,
            label="rate bootstrap interval",
        )
        rate_axis.axvline(bootstrap_ms, color=GRAY, linewidth=1.0, linestyle="--")
    rate_axis.plot(
        accepted_x,
        accepted_rate,
        color=AMBER,
        linewidth=1.5,
        marker="o",
        markersize=3.5,
        alpha=0.86,
        label="local five-state Kalman rate",
    )
    rate_axis.fill_between(
        accepted_x,
        accepted_rate - accepted_sigma,
        accepted_rate + accepted_sigma,
        color=AMBER,
        alpha=0.08,
    )
    local_rate = segment.local_doppler_rate_hz_s / 1_000
    local_sigma = segment.local_doppler_rate_sigma_hz_s / 1_000
    rate_axis.axhspan(
        local_rate - local_sigma,
        local_rate + local_sigma,
        color=GREEN,
        alpha=0.12,
    )
    rate_axis.axhline(
        local_rate,
        color=GREEN,
        linewidth=2.4,
        label=f"direct local slope: {local_rate:+.3f} ± {local_sigma:.3f} kHz/s",
    )
    rate_axis.plot(
        relative_ms,
        frozen_rate / 1_000,
        color=INK,
        linewidth=1.5,
        label=f"frozen trajectory: {segment.frozen_doppler_rate_hz_s / 1_000:+.3f} kHz/s",
    )
    rate_references = np.concatenate(
        (
            accepted_rate,
            np.asarray(
                [
                    local_rate - local_sigma,
                    local_rate + local_sigma,
                    segment.frozen_doppler_rate_hz_s / 1_000,
                    segment.kalman_doppler_rate_hz_s / 1_000,
                ]
            ),
        )
    )
    rate_axis.set_ylim(*_robust_limits(rate_references, minimum_span=3.0))
    rate_axis.set_xlim(0, (segment.end_time_s - segment.start_time_s) * 1_000)
    rate_axis.set_xlabel("time within selected segment (ms)")
    rate_axis.set_ylabel("receiver-relative CFO/Doppler rate (kHz/s)")
    rate_axis.set_title(
        f"C{rank} · rate implied by the same 75 ms evidence\n"
        f"coverage {segment.supported_frame_fraction:.1%} · line/held-out RMS "
        f"{segment.frequency_line_rms_hz:.1f}/{segment.held_out_frequency_rms_hz:.1f} Hz "
        f"· phase RMS {segment.phase_innovation_rms_rad:.2f} rad",
        loc="left",
        fontweight="bold",
    )
    for axis in (cfo_axis, rate_axis):
        axis.grid(alpha=0.22)
        handles, labels = axis.get_legend_handles_labels()
        unique = dict(zip(labels, handles, strict=True))
        axis.legend(unique.values(), unique.keys(), fontsize=8.2, loc="best")

    return {
        "rank": rank,
        "scope_digest": candidate.scope_digest,
        "path_label": candidate.path_label,
        "source_trajectory_id": candidate.track.source_trajectory_id,
        "qualified_segment_count_for_track": len(candidate.qualified_segments),
        "track_measurement_update_count": candidate.track.measurement_update_count,
        "selected_segment_index": segment.segment_index,
        "selected_start_time_s": segment.start_time_s,
        "selected_end_time_s": segment.end_time_s,
        "selected_duration_ms": 1_000 * (segment.end_time_s - segment.start_time_s),
        "raw_replay_frame_count": len(frames),
        "raw_replay_supported_frame_count": int(np.count_nonzero(supported)),
        "raw_replay_frequency_update_count": local_result.frequency_update_count,
        "raw_replay_phase_update_count": local_result.phase_update_count,
        "raw_replay_phase_lock_qualified": local_result.phase_lock_qualified,
        "raw_replay_rate_bootstrap_frame_index": local_result.rate_bootstrap_frame_index,
        "cfo_detail_range_hz": [cfo_lower, cfo_upper],
        "supported_frame_fraction": segment.supported_frame_fraction,
        "frequency_line_rms_hz": segment.frequency_line_rms_hz,
        "held_out_frequency_rms_hz": segment.held_out_frequency_rms_hz,
        "phase_innovation_rms_rad": segment.phase_innovation_rms_rad,
        "local_doppler_rate_hz_s": segment.local_doppler_rate_hz_s,
        "local_doppler_rate_sigma_hz_s": segment.local_doppler_rate_sigma_hz_s,
        "kalman_doppler_rate_hz_s": segment.kalman_doppler_rate_hz_s,
        "frozen_doppler_rate_hz_s": segment.frozen_doppler_rate_hz_s,
        "kalman_tracking_digest": candidate.kalman.content_digest,
        "final_trajectory_bank_digest": candidate.bank.content_digest,
        "pilot_doppler_segments_digest": candidate.segments.content_digest,
        "product_directory": str(candidate.product_dir),
    }


def _render_one(
    candidate: Candidate,
    local_result: PilotPntKalmanResult,
    *,
    session_id: str,
    rank: int,
    output_path: Path,
) -> dict[str, Any]:
    figure = Figure(figsize=(15.5, 6.6), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    cfo_axis, rate_axis = figure.subplots(1, 2)
    evidence = _plot_candidate(cfo_axis, rate_axis, candidate, local_result, rank=rank)
    figure.suptitle(
        f"Qualified 75 ms pilot-CFO close-up · rank {rank}\n{session_id}",
        fontsize=15,
        fontweight="bold",
    )
    canvas.print_png(output_path)
    return evidence


def _render_combined(
    selected: list[tuple[Candidate, PilotPntKalmanResult]],
    *,
    session_id: str,
    output_path: Path,
) -> None:
    figure = Figure(figsize=(15.5, 11.8), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    axes = figure.subplots(len(selected), 2, squeeze=False)
    for index, (candidate, local_result) in enumerate(selected):
        _plot_candidate(axes[index, 0], axes[index, 1], candidate, local_result, rank=index + 1)
    figure.suptitle(
        "Best two qualified pilot tracks: 75 ms CFO structure\n"
        f"{session_id} · ranked across every receiver path",
        fontsize=16,
        fontweight="bold",
    )
    canvas.print_png(output_path)


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id")
    parser.add_argument(
        "--analysis-root",
        type=Path,
        default=Path("/srv/bulk/leo/analysis"),
    )
    parser.add_argument("--recording-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--track-count", type=int, default=2)
    args = parser.parse_args()
    if args.track_count < 1:
        parser.error("--track-count must be positive")

    identities = _path_identities(args.session_id, args.api_base)
    candidates = _load_candidates(args.session_id, args.analysis_root, identities)
    if len(candidates) < args.track_count:
        raise SystemExit(
            f"only {len(candidates)} trajectories have qualified local segments; "
            f"cannot select {args.track_count}"
        )
    store = RecordingStore.open_read_only(args.recording_root)
    bundle = store.inspect(args.session_id)
    selected = [
        (candidate, _replay_segment(candidate, store, bundle))
        for candidate in candidates[: args.track_count]
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evidence = [
        _render_one(
            candidate,
            local_result,
            session_id=args.session_id,
            rank=index,
            output_path=args.output_dir / f"best-track-{index}-cfo-closeup.png",
        )
        for index, (candidate, local_result) in enumerate(selected, start=1)
    ]
    _render_combined(
        selected,
        session_id=args.session_id,
        output_path=args.output_dir / "best-two-track-cfo-closeups.png",
    )
    a_like_candidate = candidates[0]
    a_like_replayed = [
        (segment, _replay_segment(a_like_candidate, store, bundle, segment))
        for segment in _track_segments(a_like_candidate)
    ]
    a_like_evidence = _render_a_like(
        a_like_candidate,
        a_like_replayed,
        session_id=args.session_id,
        output_path=args.output_dir / "a-like-dense-carrier-tracking.png",
        frame_csv_path=args.output_dir / "a-like-dense-carrier-tracking.frames.csv",
    )
    payload = {
        "schema_version": 1,
        "session_id": args.session_id,
        "selection_policy": (
            "rank tracks by qualified-window count, accepted updates in qualified windows, "
            "best held-out RMS, then total accepted updates; choose each track's segment by "
            "coverage, accepted updates, held-out RMS, line RMS, and rate uncertainty"
        ),
        "candidate_qualified_track_count": len(candidates),
        "selected": evidence,
        "a_like": a_like_evidence,
        "raw_iq_replay_window_count": len(selected) + len(a_like_replayed),
        "raw_iq_replay_input_duration_s": sum(
            candidate.best_segment.end_time_s - candidate.best_segment.start_time_s
            for candidate, _ in selected
        )
        + sum(segment.end_time_s - segment.start_time_s for segment, _ in a_like_replayed),
        "report_elapsed_s": time.perf_counter() - started,
    }
    (args.output_dir / "best-two-track-cfo-closeups.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
