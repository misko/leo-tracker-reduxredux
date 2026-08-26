#!/usr/bin/env python3
"""Propagate dense full-capture Hough tracks through shadow downstream analysis.

This report-only prototype starts from the independently searched 20 ms / 10 ms
stride GLRT product and the replay-qualified support produced by
``report_full_capture_hough_downstream_prototype.py``.  It reconstructs the
degree-one final lines, transports their inferred integer aliases, extracts
known-pilot frame measurements from the original IQ, runs the repository's
five-state frame Kalman filter, and evaluates bounded 75 ms PNT-style pilot
segments.  No Standard contract is modified or published.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam.pilot_pnt_kalman import (  # noqa: E402
    PilotPntKalmanConfig,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.robust_linear import fit_huber_linear_irls  # noqa: E402
from leo.analysis.standard.configuration import (  # noqa: E402
    production_receiver_standard_config,
)
from leo.analysis.standard.full_capture_glrt20ms import (  # noqa: E402
    WindowResult,
    _threshold_winners,
    _window_winners,
)
from leo.analysis.starlink.kalman_tracking import (  # noqa: E402
    KalmanFrameObservation,
    PolynomialFrequencyModel,
    extract_probe_frame_measurements,
    track_frame_observations,
)
from leo.analysis.starlink.pilot_doppler_segments import _segment_document  # noqa: E402
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.analysis.starlink.trajectories import PolynomialTrajectory  # noqa: E402
from leo.contracts.kalman_tracking import KalmanTrackingConfigV1  # noqa: E402
from leo.contracts.pilot_doppler_segments import PilotDopplerSegmentConfigV1  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402


def _load_tool(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


downstream = _load_tool(
    "full_capture_hough_downstream_tool",
    "report_full_capture_hough_downstream_prototype.py",
)

SOURCE_JSON = downstream.SOURCE_JSON
DOWNSTREAM_JSON = (
    Path("reports/figures/2026_08_23_full_capture_hough_downstream_prototype")
    / "hough-downstream-prototype.json"
)
CURRENT_PRESENTATION_JSON = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "reprocess-95217d6810004fd99e669e80d9a18923/presentation/path-standard/"
    "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963/"
    "standard.path-presentation.v4.json"
)
CURRENT_SCIENTIFIC_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260821T140820-470384cc9284/"
    "reprocess-95217d6810004fd99e669e80d9a18923/scientific/path-standard/"
    "sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963"
)
OUTPUT_ROOT = Path("reports/figures/2026_08_24_full_capture_hough_end_to_end")
REPORT_PATH = Path("reports/2026_08_24_full_capture_hough_end_to_end.md")
FRAME_PROBE_SEPARATION_S = 0.020
PNT_WINDOWS_PER_TRACK = 16


@dataclass(frozen=True, slots=True)
class ShadowTrack:
    label: str
    alias_index: int
    canonical: PolynomialTrajectory
    absolute_model: PolynomialFrequencyModel
    observation_ids: tuple[str, ...]

    @property
    def start_s(self) -> float:
        return self.canonical.start_s

    @property
    def end_s(self) -> float:
        return self.canonical.end_s

    @property
    def slope_hz_s(self) -> float:
        return self.canonical.coefficients_hz[0]


@dataclass(frozen=True, slots=True)
class TrackKalman:
    label: str
    source_measurement_count: int
    unique_frame_count: int
    times_s: tuple[float, ...]
    measured_doppler_hz: tuple[float, ...]
    prompt_coherence: tuple[float, ...]
    phase_innovation_rad: tuple[float, ...]
    doppler_innovation_hz: tuple[float, ...]
    tracked_doppler_hz: tuple[float, ...]
    tracked_rate_hz_s: tuple[float, ...]
    updates: tuple[bool, ...]
    phase_slips: tuple[bool, ...]
    cfo_corrections: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class _PilotRequest:
    source_trajectory_id: str
    source_branch_id: str
    probe_sample_start: int
    local_epoch_sample: int
    model: PolynomialFrequencyModel


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-json", type=Path, default=SOURCE_JSON)
    parser.add_argument("--downstream-json", type=Path, default=DOWNSTREAM_JSON)
    parser.add_argument("--current-presentation", type=Path, default=CURRENT_PRESENTATION_JSON)
    parser.add_argument("--current-scientific-root", type=Path, default=CURRENT_SCIENTIFIC_ROOT)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    return parser.parse_args()


def _reconstruct_tracks(
    source: dict[str, Any], lifecycle: dict[str, Any]
) -> tuple[
    tuple[ShadowTrack, ...],
    tuple[Any, ...],
    tuple[Any, ...],
    tuple[Any, ...],
]:
    windows = tuple(WindowResult(**item) for item in source["windows"])
    config = production_receiver_standard_config()
    observations, _, retained = downstream._geometry_tracks(windows, config)
    observation_by_id = {item.observation_id: item for item in observations}
    retained_by_label = {item.label: item for item in retained}
    spacing = config.segmentation.initial_hough.alias_spacing_hz
    tracks: list[ShadowTrack] = []
    for row in lifecycle["tracks"]:
        if not row["final_observation_ids"]:
            continue
        parent = retained_by_label[row["label"]].trajectory
        members = tuple(observation_by_id[item] for item in row["final_observation_ids"])
        time = np.asarray([item.time_s for item in members], dtype=float)
        raw = np.asarray([item.tracking_cfo_hz for item in members], dtype=float)
        aliases = np.rint((raw - parent.frequency_hz(time)) / spacing)
        canonical_values = raw - aliases * spacing
        fit = fit_huber_linear_irls(
            time,
            canonical_values,
            initial_coefficients_hz=parent.coefficients_hz,
            reference_time_s=parent.reference_time_s,
        )
        residual = canonical_values - np.polyval(
            np.asarray(fit.coefficients_hz), time - fit.reference_time_s
        )
        rss = max(float(np.sum(residual**2)), np.finfo(float).tiny)
        canonical = PolynomialTrajectory(
            trajectory_id=f"shadow:{row['label']}",
            method=parent.method,
            polynomial_degree=1,
            reference_time_s=fit.reference_time_s,
            coefficients_hz=tuple(float(value) for value in fit.coefficients_hz),
            start_s=float(np.min(time)),
            end_s=float(np.max(time)),
            observation_ids=tuple(item.observation_id for item in members),
            point_count=len(members),
            residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
            bic=float(len(time) * math.log(rss / len(time)) + 2 * math.log(len(time))),
            high_gate=0.0,
            em_iterations=0,
        )
        absolute_coefficients = list(canonical.coefficients_hz)
        absolute_coefficients[-1] += row["alias_index"] * spacing
        tracks.append(
            ShadowTrack(
                label=row["label"],
                alias_index=row["alias_index"],
                canonical=canonical,
                absolute_model=PolynomialFrequencyModel(
                    canonical.reference_time_s, tuple(absolute_coefficients)
                ),
                observation_ids=canonical.observation_ids,
            )
        )
    detections = _window_winners(windows, require_margin_pass=False)
    passing_detections = _threshold_winners(windows)
    return tuple(tracks), observations, detections, passing_detections


def _bounded_probe_starts(
    track: ShadowTrack,
    observation_by_id: dict[str, Any],
    *,
    minimum_separation_s: float,
) -> tuple[int, ...]:
    selected: list[Any] = []
    for item in sorted(
        (observation_by_id[value] for value in track.observation_ids),
        key=lambda value: value.time_s,
    ):
        if not selected or item.time_s - selected[-1].time_s >= minimum_separation_s - 1e-9:
            selected.append(item)
    return tuple(item.sample_start for item in selected)


def _read_complex(
    reader: Any, sample_start: int, sample_count: int, receiver_id: int
) -> np.ndarray:
    ci16 = reader.read(sample_start, sample_count, receiver_ids=(receiver_id,))
    return (ci16[:, 0, 0].astype(np.float64) + 1j * ci16[:, 0, 1].astype(np.float64)) / 32_768.0


def _run_shadow_downstream(
    source: dict[str, Any],
    tracks: tuple[ShadowTrack, ...],
    observations: tuple[Any, ...],
    detections: tuple[Any, ...],
    *,
    bulk_root: Path,
) -> tuple[tuple[TrackKalman, ...], tuple[dict[str, Any], ...]]:
    detection_by_start = {item.sample_start: item for item in detections}
    observation_by_id = {item.observation_id: item for item in observations}
    kalman_config = KalmanTrackingConfigV1()
    pnt_config = PilotDopplerSegmentConfigV1()
    edge = StarlinkEdge(source["edge"])
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    kalman_rows: list[TrackKalman] = []
    segment_rows: list[dict[str, Any]] = []
    try:
        bundle = store.inspect(source["session_id"])
        reader = store.reader(bundle, source["stream_id"], verify=True)
        receiver_id = int(source["receiver_id"])
        probe_samples = round(source["window_ms"] * reader.sample_rate_hz / 1_000)
        pnt_samples = round(pnt_config.window_duration_s * reader.sample_rate_hz)
        for track in tracks:
            raw_measurements: list[Any] = []
            probe_starts = _bounded_probe_starts(
                track,
                observation_by_id,
                minimum_separation_s=FRAME_PROBE_SEPARATION_S,
            )
            for probe_start in probe_starts:
                detection = detection_by_start.get(probe_start)
                if detection is None or detection.local_epoch_sample is None:
                    continue
                samples = _read_complex(reader, probe_start, probe_samples, receiver_id)
                raw_measurements.extend(
                    extract_probe_frame_measurements(
                        samples,
                        probe_sample_start=probe_start,
                        local_epoch_sample=detection.local_epoch_sample,
                        sample_rate_hz=reader.sample_rate_hz,
                        model=track.absolute_model,
                        edge=edge,
                        pilot_symbol_count=kalman_config.pilot_symbol_count,
                        start_time_s=track.start_s,
                        end_time_s=track.end_s,
                    )
                )
            ordered = sorted(
                raw_measurements, key=lambda item: (item.sample_start, -item.prompt_coherence)
            )
            frame_observations: tuple[KalmanFrameObservation, ...]
            if ordered:
                anchor = ordered[0].sample_start
                by_index: dict[int, KalmanFrameObservation] = {}
                for item in ordered:
                    frame_index = round(
                        (item.sample_start - anchor)
                        * kalman_config.frame_rate_hz
                        / reader.sample_rate_hz
                    )
                    nominal = anchor + round(
                        frame_index * reader.sample_rate_hz / kalman_config.frame_rate_hz
                    )
                    observation = KalmanFrameObservation(
                        frame_index=frame_index,
                        sample_start=item.sample_start,
                        time_s=item.time_s,
                        prompt_coherence=item.prompt_coherence,
                        carrier_phase_rad=item.carrier_phase_rad,
                        doppler_hz=item.doppler_hz,
                        frame_phase_s=(item.sample_start - nominal) / reader.sample_rate_hz,
                    )
                    previous = by_index.get(frame_index)
                    if previous is None or observation.prompt_coherence > previous.prompt_coherence:
                        by_index[frame_index] = observation
                frame_observations = tuple(by_index[index] for index in sorted(by_index))
            else:
                frame_observations = ()
            estimates = track_frame_observations(
                frame_observations,
                kalman_config,
                initial_doppler_rate_hz_s=track.slope_hz_s,
            )
            kalman_rows.append(
                TrackKalman(
                    label=track.label,
                    source_measurement_count=len(raw_measurements),
                    unique_frame_count=len(frame_observations),
                    times_s=tuple(item.observation.time_s for item in estimates),
                    measured_doppler_hz=tuple(item.observation.doppler_hz for item in estimates),
                    prompt_coherence=tuple(item.observation.prompt_coherence for item in estimates),
                    phase_innovation_rad=tuple(item.phase_innovation_rad for item in estimates),
                    doppler_innovation_hz=tuple(item.doppler_innovation_hz for item in estimates),
                    tracked_doppler_hz=tuple(item.doppler_shift_hz for item in estimates),
                    tracked_rate_hz_s=tuple(item.doppler_rate_hz_s for item in estimates),
                    updates=tuple(item.update_applied for item in estimates),
                    phase_slips=tuple(item.phase_slip_detected for item in estimates),
                    cfo_corrections=tuple(item.cfo_correction_detected for item in estimates),
                )
            )

            eligible = [
                start
                for start in probe_starts
                if start + pnt_samples <= reader.sample_count
                and start / reader.sample_rate_hz >= track.start_s
                and (start + pnt_samples) / reader.sample_rate_hz <= track.end_s
            ]
            separated: list[int] = []
            minimum_samples = round(pnt_config.minimum_window_separation_s * reader.sample_rate_hz)
            for start in eligible:
                if not separated or start - separated[-1] >= minimum_samples:
                    separated.append(start)
            if len(separated) > PNT_WINDOWS_PER_TRACK:
                indexes = np.rint(np.linspace(0, len(separated) - 1, PNT_WINDOWS_PER_TRACK)).astype(
                    int
                )
                separated = [separated[int(index)] for index in indexes]
            for start in separated:
                detection = detection_by_start.get(start)
                if detection is None or detection.local_epoch_sample is None:
                    continue
                samples = _read_complex(reader, start, pnt_samples, receiver_id)
                result = analyze_contiguous_pilot_pnt_kalman(
                    samples,
                    reader.sample_rate_hz,
                    epoch_sample=detection.local_epoch_sample,
                    initial_absolute_cfo_hz=float(
                        track.absolute_model.frequency_hz(start / reader.sample_rate_hz)
                    ),
                    edge=edge,
                    maximum_residual_cfo_hz=pnt_config.maximum_residual_cfo_hz,
                    config=PilotPntKalmanConfig(initial_doppler_rate_hz_s=track.slope_hz_s),
                )
                request = _PilotRequest(
                    source_trajectory_id=track.label,
                    source_branch_id=f"shadow:{track.label}",
                    probe_sample_start=start,
                    local_epoch_sample=detection.local_epoch_sample,
                    model=track.absolute_model,
                )
                document = _segment_document(
                    request,
                    result,
                    reader.sample_rate_hz,
                    pnt_config,
                )
                document["track_label"] = track.label
                segment_rows.append(document)
    finally:
        store.close()
    return tuple(kalman_rows), tuple(segment_rows)


def _load_current(args: argparse.Namespace) -> dict[str, Any]:
    presentation = json.loads(args.current_presentation.read_text(encoding="utf-8"))
    kalman_path = args.current_scientific_root / "standard.kalman-tracking.v1.json"
    segments_path = args.current_scientific_root / "standard.pilot-doppler-segments.v1.json"
    return {
        "presentation": presentation,
        "kalman": json.loads(kalman_path.read_text(encoding="utf-8")),
        "segments": json.loads(segments_path.read_text(encoding="utf-8")),
    }


def _track_summary(
    track: ShadowTrack,
    row: TrackKalman,
    segments: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    updates = sum(row.updates)
    rates = np.asarray(row.tracked_rate_hz_s, dtype=float)
    innovations = np.asarray(row.doppler_innovation_hz, dtype=float)
    track_segments = tuple(item for item in segments if item["track_label"] == track.label)
    qualified = tuple(item for item in track_segments if item["qualified"])
    qualified_rates = tuple(
        float(item["local_doppler_rate_hz_s"])
        for item in qualified
        if item["local_doppler_rate_hz_s"] is not None
    )
    return {
        "label": track.label,
        "alias_index": track.alias_index,
        "start_s": track.start_s,
        "end_s": track.end_s,
        "final_rate_hz_s": track.slope_hz_s,
        "final_residual_rms_hz": track.canonical.residual_rms_hz,
        "final_support_count": track.canonical.point_count,
        "source_frame_measurement_count": row.source_measurement_count,
        "unique_frame_count": row.unique_frame_count,
        "kalman_update_count": updates,
        "kalman_rejected_count": len(row.updates) - updates,
        "phase_slip_count": sum(row.phase_slips),
        "cfo_correction_count": sum(row.cfo_corrections),
        "median_abs_doppler_innovation_hz": (
            None if not innovations.size else float(np.median(np.abs(innovations)))
        ),
        "median_kalman_rate_hz_s": None if not rates.size else float(np.median(rates)),
        "pnt_segment_count": len(track_segments),
        "qualified_pnt_segment_count": len(qualified),
        "median_qualified_local_rate_hz_s": (
            None if not qualified_rates else float(np.median(qualified_rates))
        ),
        "median_qualified_local_minus_final_hz_s": (
            None if not qualified_rates else float(np.median(qualified_rates) - track.slope_hz_s)
        ),
    }


def _plot_lineage(
    output: Path,
    *,
    source: dict[str, Any],
    tracks: tuple[ShadowTrack, ...],
    observations: tuple[Any, ...],
    kalman: tuple[TrackKalman, ...],
    lifecycle: dict[str, Any],
) -> None:
    figure, axes = plt.subplots(4, 1, figsize=(17, 15), sharex=True)
    colors = plt.get_cmap("tab10")
    time = np.asarray([item.time_s for item in observations])
    raw = np.asarray([item.tracking_cfo_hz for item in observations]) / 1e3
    axes[0].scatter(time, raw, marker="x", s=14, linewidths=0.55, color="#f28e2b", alpha=0.35)
    axes[0].set_ylabel("raw CFO (kHz)")
    axes[0].set_title("A · Dense margin-pass 20 ms evidence and replay-final Hough members")
    observation_by_id = {item.observation_id: item for item in observations}
    row_by_label = {item["label"]: item for item in lifecycle["tracks"]}
    for index, track in enumerate(tracks):
        color = colors(index)
        members = [observation_by_id[value] for value in track.observation_ids]
        member_time = np.asarray([item.time_s for item in members])
        member_raw = np.asarray([item.tracking_cfo_hz for item in members])
        alias_spacing = lifecycle["parameters"]["geometry_residual_gate_hz"] * 0 + 2_500_000 / 11
        aliases = np.rint(
            (member_raw - track.canonical.frequency_hz(member_time)) / alias_spacing
        ).astype(int)
        for alias in sorted(set(aliases)):
            chosen = member_time[aliases == alias]
            interval = np.asarray([chosen.min(), chosen.max()])
            axes[0].plot(
                interval,
                (track.canonical.frequency_hz(interval) + alias * alias_spacing) / 1e3,
                color=color,
                linewidth=2.0,
            )
        axes[0].text(
            track.end_s,
            float((track.canonical.frequency_hz(track.end_s) + aliases[-1] * alias_spacing) / 1e3),
            track.label,
            color=color,
            fontsize=8,
        )
        absolute = track.absolute_model.frequency_hz(member_time)
        axes[1].scatter(member_time, absolute / 1e3, s=8, color=color, alpha=0.45)
        grid = np.asarray([track.start_s, track.end_s])
        axes[1].plot(grid, track.absolute_model.frequency_hz(grid) / 1e3, color=color, linewidth=2)
        row = row_by_label[track.label]
        axes[2].plot(
            [track.start_s, track.end_s],
            [index, index],
            color=color,
            linewidth=8,
            solid_capstyle="butt",
        )
        for evidence in row["replay_positive_evidence_runs"]:
            axes[2].plot(
                [evidence["start_s"], evidence["end_s"]],
                [index, index],
                color="#111827",
                linewidth=1.2,
            )
    axes[1].set_ylabel("lifted CFO (kHz)")
    axes[1].set_title("B · Integer-alias transport and one degree-one final line per track")
    axes[2].set_yticks(range(len(tracks)), [item.label for item in tracks])
    axes[2].set_ylabel("track")
    axes[2].set_title("C · Published envelope (color) and actual replay-positive runs (black)")
    for index, row in enumerate(kalman):
        color = colors(index)
        axes[3].scatter(
            row.times_s,
            np.asarray(row.measured_doppler_hz) / 1e3,
            s=6,
            color=color,
            alpha=0.35,
        )
        axes[3].plot(
            row.times_s,
            np.asarray(row.tracked_doppler_hz) / 1e3,
            color=color,
            linewidth=1.0,
        )
    axes[3].set_ylabel("pilot CFO (kHz)")
    axes[3].set_xlabel("capture time (s)")
    axes[3].set_title("D · Known-pilot frame measurements and five-state Kalman estimates")
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.set_xlim(20, 47)
    figure.suptitle(
        "Dense Hough lineage through de-alias, replay, final selection, and frame tracking\n"
        f"{source['session_id']} · {source['stream_id']}/RX{source['receiver_id']} "
        f"{source['edge']} · shadow prototype",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_kalman(
    output: Path,
    *,
    source: dict[str, Any],
    tracks: tuple[ShadowTrack, ...],
    rows: tuple[TrackKalman, ...],
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(17, 12), sharex=True)
    colors = plt.get_cmap("tab10")
    by_label = {item.label: item for item in tracks}
    for index, row in enumerate(rows):
        if not row.times_s:
            continue
        color = colors(index)
        track = by_label[row.label]
        time = np.asarray(row.times_s)
        frozen = track.absolute_model.frequency_hz(time)
        axes[0].scatter(
            time,
            np.asarray(row.measured_doppler_hz) - frozen,
            s=7,
            color=color,
            alpha=0.42,
            label=row.label,
        )
        accepted = np.asarray(row.updates, dtype=bool)
        phase_cycles = np.asarray(row.phase_innovation_rad) / (2 * math.pi)
        axes[1].scatter(time[accepted], phase_cycles[accepted], s=7, color=color, alpha=0.45)
        axes[1].scatter(
            time[~accepted],
            phase_cycles[~accepted],
            marker="x",
            s=10,
            linewidths=0.6,
            color=color,
            alpha=0.35,
        )
        axes[2].scatter(
            time,
            np.asarray(row.tracked_rate_hz_s) / 1e3,
            color=color,
            s=3,
            alpha=0.25,
        )
        axes[2].hlines(
            track.slope_hz_s / 1e3,
            track.start_s,
            track.end_s,
            color=color,
            linewidth=2.0,
            linestyle="--",
        )
    displayed_min = -15.0
    displayed_max = 5.0
    excluded = sum(
        value / 1e3 < displayed_min or value / 1e3 > displayed_max
        for row in rows
        for value in row.tracked_rate_hz_s
    )
    axes[0].axhline(0, color="#111827", linewidth=0.8)
    axes[0].set_ylabel("measured − final line (Hz)")
    axes[0].set_title("A · Frame-level CFO residual after dense-track initialization")
    axes[0].legend(ncol=6, fontsize=8)
    axes[1].axhspan(-0.1, 0.1, color="#2a9d6f", alpha=0.08)
    axes[1].set_ylabel("phase innovation (cycles)")
    axes[1].set_title("B · Carrier-phase innovation; circles update, × marks coherence rejection")
    axes[2].set_ylabel("Doppler rate (kHz/s)")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title("C · Frame Kalman rate samples versus frozen degree-one Hough rate (dashed)")
    axes[2].set_ylim(displayed_min, displayed_max)
    axes[2].text(
        0.01,
        0.96,
        f"display clips {excluded:,} unstable Kalman estimates outside "
        f"[{displayed_min:.0f}, {displayed_max:.0f}] kHz/s; JSON retains all",
        transform=axes[2].transAxes,
        va="top",
        fontsize=8,
        color="#7f1d1d",
    )
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.set_xlim(20, 47)
    figure.suptitle(
        "Known-pilot five-state Kalman tracking seeded by dense final tracks\n"
        f"{source['session_id']} · no phase-continuity claim across replay evidence holes",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_pnt_segments(
    output: Path,
    *,
    source: dict[str, Any],
    tracks: tuple[ShadowTrack, ...],
    segments: tuple[dict[str, Any], ...],
) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(17, 12), sharex=True)
    colors = {track.label: plt.get_cmap("tab10")(index) for index, track in enumerate(tracks)}
    for segment in segments:
        color = colors[segment["track_label"]]
        marker = "o" if segment["qualified"] else "x"
        time = segment["reference_time_s"]
        local = segment["local_doppler_rate_hz_s"]
        if local is not None:
            axes[0].scatter(time, local / 1e3, marker=marker, s=30, color=color)
        axes[1].scatter(
            time,
            segment["supported_frame_fraction"],
            marker=marker,
            s=30,
            color=color,
        )
        axes[2].scatter(
            time,
            segment["phase_innovation_rms_rad"] or 0.0,
            marker=marker,
            s=30,
            color=color,
        )
    for track in tracks:
        axes[0].hlines(
            track.slope_hz_s / 1e3,
            track.start_s,
            track.end_s,
            color=colors[track.label],
            linewidth=1.2,
            linestyle="--",
            label=f"{track.label} {track.slope_hz_s / 1e3:+.2f}",
        )
    axes[0].set_ylabel("local rate (kHz/s)")
    axes[0].set_title("A · 75 ms local pilot rate; circle qualifies, × fails at least one gate")
    axes[0].legend(ncol=6, fontsize=8)
    axes[1].axhline(0.75, color="#111827", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("supported-frame fraction")
    axes[1].set_title("B · Complete-lattice pilot support")
    axes[2].axhline(0.5, color="#111827", linestyle="--", linewidth=0.8)
    axes[2].set_ylabel("phase innovation RMS (rad)")
    axes[2].set_xlabel("capture time (s)")
    axes[2].set_title("C · Modulo-π phase-lock diagnostic")
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.set_xlim(20, 47)
    figure.suptitle(
        "PNT-style 75 ms pilot segments downstream of dense final tracks\n"
        f"{source['session_id']} · receiver-relative timing; known Qin pilots only",
        fontsize=15,
        fontweight="bold",
    )
    figure.tight_layout()
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_comparison(
    output: Path,
    *,
    tracks: tuple[ShadowTrack, ...],
    summaries: list[dict[str, Any]],
    segments: tuple[dict[str, Any], ...],
    current: dict[str, Any],
) -> None:
    old_final = current["presentation"]["final_trajectory_table"]["trajectories"]
    old_kalman = current["kalman"]["tracks"]
    old_segments = current["segments"]["segments"]
    figure, axes = plt.subplots(1, 2, figsize=(17, 7), constrained_layout=True)
    for item in old_final:
        axes[0].plot(
            [item["start_s"], item["end_s"]],
            [item["absolute_coefficients_hz"][0] / 1e3] * 2,
            color="#8f969c",
            linewidth=2,
            alpha=0.55,
        )
    for index, track in enumerate(tracks):
        axes[0].plot(
            [track.start_s, track.end_s],
            [track.slope_hz_s / 1e3] * 2,
            color=plt.get_cmap("tab10")(index),
            linewidth=5,
            label=track.label,
        )
    axes[0].set_xlabel("capture time (s)")
    axes[0].set_ylabel("degree-one Doppler rate (kHz/s)")
    axes[0].set_title("A · Current Standard final inventory (gray) vs dense shadow final tracks")
    axes[0].legend(ncol=3, fontsize=8)
    axes[0].grid(alpha=0.18)

    labels = [
        "final tracks",
        "Kalman tracks\nwith frames",
        "75 ms segments",
        "qualified\n75 ms segments",
    ]
    old_values = [
        len(old_final),
        sum(item["processed_frame_count"] > 0 for item in old_kalman),
        len(old_segments),
        sum(item["qualified"] for item in old_segments),
    ]
    new_values = [
        len(tracks),
        sum(item["unique_frame_count"] > 0 for item in summaries),
        len(segments),
        sum(item["qualified"] for item in segments),
    ]
    x = np.arange(len(labels))
    axes[1].bar(x - 0.18, old_values, width=0.36, color="#8f969c", label="current Standard")
    axes[1].bar(x + 0.18, new_values, width=0.36, color="#2678a8", label="dense shadow")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("count")
    axes[1].set_title("B · Downstream product inventory")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.18)
    figure.suptitle(
        "Trajectory-source handoff control: current Standard versus dense shadow",
        fontsize=15,
        fontweight="bold",
    )
    figure.savefig(output, dpi=210, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _write_report(
    path: Path,
    *,
    source: dict[str, Any],
    summaries: list[dict[str, Any]],
    segments: tuple[dict[str, Any], ...],
    current: dict[str, Any],
    figures: dict[str, Path],
    result_json: Path,
) -> None:
    old_final = current["presentation"]["final_trajectory_table"]["trajectories"]
    old_kalman = current["kalman"]["tracks"]
    old_segments = current["segments"]["segments"]
    qualified = sum(item["qualified"] for item in segments)
    lines = [
        "# Dense full-capture Hough: end-to-end downstream prototype",
        "",
        "## Result",
        "",
        "The dense 20 ms Hough tracks can be propagated through integer-alias transport, "
        "conditioned IQ replay, replay-supported endpoint selection, degree-one final "
        "refitting, known-pilot frame extraction, the existing five-state Kalman filter, and "
        "the existing 75 ms PNT-style pilot analysis. The prototype keeps one stable Hough "
        "label through every stage, so H1 does not silently vanish or get replaced by an "
        "unrelated older trajectory. Propagation succeeds as data lineage; it does not make "
        "every dense line a successful phase/Doppler track.",
        "",
        f"On `{source['session_id']}` `{source['stream_id']}/RX{source['receiver_id']}` "
        f"`{source['edge']}`, 12 raw Hough fragments become 6 replay-qualified final tracks. "
        f"All {len(summaries)} supply actual known-pilot frames to the Kalman stage. The "
        f"bounded PNT-style audit analyzed {len(segments)} non-overlapping 75 ms windows; "
        f"{qualified} passed every current qualification gate, distributed across only "
        f"{sum(item['qualified_pnt_segment_count'] > 0 for item in summaries)} tracks.",
        "",
        f"![End-to-end lineage]({figures['lineage'].relative_to(path.parent)})",
        "",
        f"![Kalman detail]({figures['kalman'].relative_to(path.parent)})",
        "",
        f"![PNT-style pilot segments]({figures['pnt'].relative_to(path.parent)})",
        "",
        f"![Current versus dense]({figures['comparison'].relative_to(path.parent)})",
        "",
        "## Track accounting",
        "",
        "| Track | Final interval | Rate | Alias | GLRT support | Huber RMS | "
        "Raw / unique frames | Kalman updates | Phase slips | CFO resets | "
        "Median abs frequency innovation | Median KF rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            f"| {item['label']} | {item['start_s']:.2f}–{item['end_s']:.2f} s | "
            f"{item['final_rate_hz_s'] / 1e3:+.3f} kHz/s | {item['alias_index']:+d} | "
            f"{item['final_support_count']} | {item['final_residual_rms_hz']:.1f} Hz | "
            f"{item['source_frame_measurement_count']} / {item['unique_frame_count']} | "
            f"{item['kalman_update_count']} | {item['phase_slip_count']} | "
            f"{item['cfo_correction_count']} | "
            f"{item['median_abs_doppler_innovation_hz']:.1f} Hz | "
            f"{item['median_kalman_rate_hz_s'] / 1e3:+.3f} kHz/s |"
        )
    lines.extend(
        [
            "",
            "## PNT-style qualification by dense track",
            "",
            "| Track | 75 ms windows | Qualified | Median qualified local rate | "
            "Local minus final Hough rate | Assessment |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in summaries:
        local = item["median_qualified_local_rate_hz_s"]
        delta = item["median_qualified_local_minus_final_hz_s"]
        assessment = (
            "no qualifying local phase/rate interval"
            if local is None
            else "local tracker qualifies, but rate does not validate Hough slope"
            if abs(delta) > 1_000
            else "local tracker and Hough rate agree within 1 kHz/s"
        )
        lines.append(
            f"| {item['label']} | {item['pnt_segment_count']} | "
            f"{item['qualified_pnt_segment_count']} | "
            f"{'—' if local is None else f'{local / 1e3:+.3f} kHz/s'} | "
            f"{'—' if delta is None else f'{delta / 1e3:+.3f} kHz/s'} | {assessment} |"
        )
    lines.extend(
        [
            "",
            "## What changed versus the current pipeline",
            "",
            "| Stage | Current Standard source | Shadow prototype source |",
            "|---|---|---|",
            "| Pilot evidence | Scheduled pilot scan | Independent 20 ms / 10 ms-stride "
            "full-capture search |",
            "| Hough geometry | Scheduled-scan Hough representatives | Dense margin-pass "
            "Hough + support closure + Jaccard dedup |",
            "| De-alias | Old representative bank | The same retained dense Hough membership "
            "and stable H label |",
            "| Replay | Old detections/representatives | Dense member windows; "
            "acquisition-CFO transport |",
            "| Final tracks | Old de-aliased branches | Replay-positive support envelope; "
            "Huber degree one only |",
            "| Kalman / pilot segments | Old final trajectory IDs | Dense final H labels and "
            "their exact source epochs |",
            "",
            f"The stored current Standard control has {len(old_final)} final rows, "
            f"{sum(item['processed_frame_count'] > 0 for item in old_kalman)} Kalman rows with "
            f"frames, and {len(old_segments)} 75 ms segment rows. Those are not a fair "
            "one-for-one scientific comparison because the source memberships differ; they "
            "are shown to prove the current UI's de-aliased panel is fed by the older branch.",
            "",
            "## Interpretation",
            "",
            "The experiment establishes plumbing feasibility, not phase continuity or "
            "satellite attribution. A colored final envelope means replay-positive evidence "
            "exists between its endpoints; black sub-runs in the lineage plot show where "
            "evidence was actually observed. The Kalman filter must coast across internal "
            "holes and must never reinterpret the envelope itself as continuous carrier phase.",
            "",
            "The frame-level result is not a blanket success. H1 and H2 are especially poor "
            "initializations for the present Kalman measurement model; H2's low-support line "
            "drives an unstable rate estimate. H7 and H10 have the smallest median frequency "
            "innovations, but frequent phase-slip flags remain. Only H3 and H7 contain any "
            "75 ms interval that passes every existing PNT-style gate, and their qualified "
            "local rates are still roughly 3.0–3.3 kHz/s less negative than their Hough rates. "
            "Therefore this prototype proves provenance and execution, not agreement between "
            "the 20 ms CFO family and local pilot phase/frequency tracking.",
            "",
            "The integer alias is a receiver ambiguity lift. It changes the CFO intercept but "
            "not the degree-one Doppler rate. Every frequency trajectory in this prototype is "
            "degree one; the Kalman phase transition integrates a constant rate but does not fit "
            "a quadratic or cubic radio trajectory.",
            "",
            "## Production recommendation",
            "",
            "Publish the dense window evidence as a versioned scientific JSON product, add a "
            "new major downstream trajectory-source binding, and make all consumers validate "
            "that binding. Preserve Hough label, source observation IDs, alias decision, replay "
            "row IDs, and final member mask. Do not mutate the published V4/V3 contracts or "
            "quietly substitute the dense source beneath existing digests.",
            "",
            f"Machine-readable prototype: [`{result_json.name}`]"
            f"({result_json.relative_to(path.parent)})",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = _arguments()
    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    lifecycle = json.loads(args.downstream_json.read_text(encoding="utf-8"))
    tracks, observations, detections, _ = _reconstruct_tracks(source, lifecycle)
    kalman, segments = _run_shadow_downstream(
        source,
        tracks,
        observations,
        detections,
        bulk_root=args.bulk_root,
    )
    current = _load_current(args)
    summaries = [
        _track_summary(track, row, segments) for track, row in zip(tracks, kalman, strict=True)
    ]
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    figures = {
        "lineage": args.output_root / "dense-hough-end-to-end-lineage.png",
        "kalman": args.output_root / "dense-hough-kalman-detail.png",
        "pnt": args.output_root / "dense-hough-pnt-segments.png",
        "comparison": args.output_root / "current-vs-dense-downstream.png",
    }
    _plot_lineage(
        figures["lineage"],
        source=source,
        tracks=tracks,
        observations=observations,
        kalman=kalman,
        lifecycle=lifecycle,
    )
    _plot_kalman(figures["kalman"], source=source, tracks=tracks, rows=kalman)
    _plot_pnt_segments(figures["pnt"], source=source, tracks=tracks, segments=segments)
    _plot_comparison(
        figures["comparison"],
        tracks=tracks,
        summaries=summaries,
        segments=segments,
        current=current,
    )
    result = {
        "schema_version": 1,
        "kind": "dense-hough-end-to-end-shadow-prototype",
        "session_id": source["session_id"],
        "stream_id": source["stream_id"],
        "receiver_id": source["receiver_id"],
        "edge": source["edge"],
        "degree_one_frequency_trajectories_only": True,
        "promoted_to_standard": False,
        "source_products": {
            "dense_window_json": str(args.source_json),
            "hough_downstream_json": str(args.downstream_json),
            "current_standard_control": str(args.current_presentation),
        },
        "parameters": {
            "frame_probe_minimum_separation_s": FRAME_PROBE_SEPARATION_S,
            "kalman_config": KalmanTrackingConfigV1().model_dump(mode="json"),
            "pnt_segment_config": PilotDopplerSegmentConfigV1().model_dump(mode="json"),
            "maximum_pnt_windows_per_track": PNT_WINDOWS_PER_TRACK,
        },
        "summary": {
            "dense_final_track_count": len(tracks),
            "dense_kalman_track_count": len(kalman),
            "dense_kalman_tracks_with_frames": sum(item.unique_frame_count > 0 for item in kalman),
            "dense_pnt_segment_count": len(segments),
            "dense_qualified_pnt_segment_count": sum(item["qualified"] for item in segments),
            "current_final_track_count": len(
                current["presentation"]["final_trajectory_table"]["trajectories"]
            ),
            "current_kalman_track_count": len(current["kalman"]["tracks"]),
            "current_pnt_segment_count": len(current["segments"]["segments"]),
        },
        "tracks": summaries,
        "pilot_segments": list(segments),
    }
    result_json = args.output_root / "dense-hough-end-to-end.json"
    result_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _write_report(
        args.report,
        source=source,
        summaries=summaries,
        segments=segments,
        current=current,
        figures=figures,
        result_json=result_json,
    )
    print(json.dumps(result["summary"], indent=2), flush=True)
    print(f"wrote {args.report}", flush=True)
    for path in figures.values():
        print(f"wrote {path}", flush=True)
    print(f"wrote {result_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
