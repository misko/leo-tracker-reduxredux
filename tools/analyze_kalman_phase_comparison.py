#!/usr/bin/env python3
"""Replay the frame Kalman stage and compare it with a sealed Standard path.

The recording store is opened read-only and every consumed IQ shard is digest
verified.  The tool reuses the sealed pilot scan and final trajectory products;
it does not publish a run, update the catalog, or claim Starlink attribution.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.standard.analyzers import _pilot_detections
from leo.analysis.standard.runner import ReceiverStandardConfig, SingleReceiverIqReader
from leo.analysis.starlink.kalman_tracking import (
    PolynomialFrequencyModel,
    build_standard_kalman_tracking,
)
from leo.analysis.starlink.templates import StarlinkEdge
from leo.contracts.cfo_dealias import DealiasedTrajectoryBankV4, FinalTrajectoryBankV3
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.kalman_tracking import KalmanFrameEstimateV1, StandardKalmanTrackingV1
from leo.storage import RecordingStore

DEFAULT_SESSION = "cap-20260822T143411-4e2a0c111a30"
DEFAULT_RUN = "reprocess-a3fc4c77b1234b58ab5f7292b23db161"
DEFAULT_SCOPE = "sha256:d7412c34fc4f03bbe33b2818b87aa0e902893daf9be899e9e01585a404122ba0"
DEFAULT_OUTPUT = Path("reports/figures/2026_08_22_kalman_phase_tracking")
FRAME_PERIOD_S = 1 / 750
FRAME_BUNCH_GAP_S = 0.0021


@dataclass(frozen=True, slots=True)
class FrameBunch:
    track_index: int
    frames: tuple[KalmanFrameEstimateV1, ...]
    updated: tuple[KalmanFrameEstimateV1, ...]
    start_s: float
    end_s: float
    filtered_center_s: float
    measured_center_s: float
    filtered_median_absolute_deviation_s: float
    carrier_phase_innovation_resultant: float
    carrier_phase_innovation_center_rad: float


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument("--scope-key", default=DEFAULT_SCOPE)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--stream", default="stream-0")
    parser.add_argument("--receiver", type=int, default=1)
    parser.add_argument("--edge", choices=("lower", "upper"), default="lower")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _median(values: list[float]) -> float | None:
    return None if not values else float(statistics.median(values))


def _rms(values: list[float]) -> float | None:
    if not values:
        return None
    return float(math.sqrt(sum(value * value for value in values) / len(values)))


def _resultant_length(values: list[float]) -> float | None:
    return None if not values else float(abs(np.mean(np.exp(1j * np.asarray(values)))))


def _wrap_frame_phase_s(value: float) -> float:
    return (value + FRAME_PERIOD_S / 2) % FRAME_PERIOD_S - FRAME_PERIOD_S / 2


def _frame_phase_center_s(values: list[float]) -> float:
    angles = 2 * math.pi * np.asarray(values) / FRAME_PERIOD_S
    center = np.mean(np.exp(1j * angles))
    return float(math.atan2(center.imag, center.real) * FRAME_PERIOD_S / (2 * math.pi))


def _frame_bunches(product: StandardKalmanTrackingV1) -> list[FrameBunch]:
    result: list[FrameBunch] = []
    for track_index, track in enumerate(product.tracks, start=1):
        grouped: list[list[KalmanFrameEstimateV1]] = []
        current: list[KalmanFrameEstimateV1] = []
        for frame in track.frames:
            if current and frame.time_s - current[-1].time_s > FRAME_BUNCH_GAP_S:
                grouped.append(current)
                current = []
            current.append(frame)
        if current:
            grouped.append(current)
        for group in grouped:
            updated = tuple(frame for frame in group if frame.update_applied)
            if not updated:
                continue
            filtered = [frame.frame_phase_s for frame in updated]
            measured = [frame.measurement_frame_phase_s for frame in updated]
            filtered_center = _frame_phase_center_s(filtered)
            carrier_phase = [frame.phase_innovation_rad for frame in updated]
            carrier_center = np.mean(np.exp(1j * np.asarray(carrier_phase)))
            result.append(
                FrameBunch(
                    track_index=track_index,
                    frames=tuple(group),
                    updated=updated,
                    start_s=group[0].time_s,
                    end_s=group[-1].time_s,
                    filtered_center_s=filtered_center,
                    measured_center_s=_frame_phase_center_s(measured),
                    filtered_median_absolute_deviation_s=float(
                        statistics.median(
                            abs(_wrap_frame_phase_s(value - filtered_center)) for value in filtered
                        )
                    ),
                    carrier_phase_innovation_resultant=float(abs(carrier_center)),
                    carrier_phase_innovation_center_rad=float(
                        math.atan2(carrier_center.imag, carrier_center.real)
                    ),
                )
            )
    return result


def _frame_bunch_analysis(
    product: StandardKalmanTrackingV1,
) -> tuple[dict[str, Any], list[FrameBunch]]:
    bunches = _frame_bunches(product)
    by_track: dict[int, list[FrameBunch]] = {}
    for bunch in bunches:
        by_track.setdefault(bunch.track_index, []).append(bunch)

    transitions_us: list[float] = []
    cadences_ms: list[float] = []
    event_intervals_ms: dict[float, list[float]] = {100.0: [], 250.0: [], 500.0: []}
    for track_bunches in by_track.values():
        transitions = [
            abs(_wrap_frame_phase_s(right.filtered_center_s - left.filtered_center_s)) * 1e6
            for left, right in zip(track_bunches, track_bunches[1:], strict=False)
        ]
        transitions_us.extend(transitions)
        cadences_ms.extend(
            (right.start_s - left.start_s) * 1e3
            for left, right in zip(track_bunches, track_bunches[1:], strict=False)
        )
        for threshold_us, intervals in event_intervals_ms.items():
            event_times = [
                track_bunches[index + 1].start_s
                for index, transition in enumerate(transitions)
                if transition > threshold_us
            ]
            intervals.extend(
                (right - left) * 1e3
                for left, right in zip(event_times, event_times[1:], strict=False)
            )

    filtered_centers = [bunch.filtered_center_s for bunch in bunches]
    measured_centers = [bunch.measured_center_s for bunch in bunches]
    filtered_angles = [2 * math.pi * value / FRAME_PERIOD_S for value in filtered_centers]
    measured_angles = [2 * math.pi * value / FRAME_PERIOD_S for value in measured_centers]
    carrier_centers = [bunch.carrier_phase_innovation_center_rad for bunch in bunches]
    switches = {}
    for threshold_us in (100.0, 250.0, 500.0):
        count = sum(value > threshold_us for value in transitions_us)
        intervals = event_intervals_ms[threshold_us]
        switches[f"greater_than_{int(threshold_us)}_us"] = {
            "count": count,
            "fraction_of_adjacent_bunch_transitions": count / len(transitions_us),
            "median_inter_event_interval_ms": _median(intervals),
        }
    analysis = {
        "nominal_frame_rate_hz": 750.0,
        "nominal_frame_period_us": FRAME_PERIOD_S * 1e6,
        "probe_duration_ms": 20.0,
        "probe_offsets_ms": [0.0, 25.0],
        "bunch_gap_threshold_ms": FRAME_BUNCH_GAP_S * 1e3,
        "bunch_count": len(bunches),
        "adjacent_bunch_transition_count": len(transitions_us),
        "median_frames_per_bunch": _median([float(len(bunch.frames)) for bunch in bunches]),
        "median_bunch_duration_ms": _median(
            [(bunch.end_s - bunch.start_s) * 1e3 for bunch in bunches]
        ),
        "median_bunch_cadence_ms": _median(cadences_ms),
        "median_within_bunch_frame_phase_deviation_us": _median(
            [bunch.filtered_median_absolute_deviation_s * 1e6 for bunch in bunches]
        ),
        "filtered_bunch_center_resultant_length": _resultant_length(filtered_angles),
        "measured_bunch_center_resultant_length": _resultant_length(measured_angles),
        "median_wrapped_adjacent_bunch_change_us": _median(transitions_us),
        "carrier_phase_innovation_within_bunch_resultant_median": _median(
            [bunch.carrier_phase_innovation_resultant for bunch in bunches]
        ),
        "carrier_phase_innovation_bunch_center_resultant_length": _resultant_length(
            carrier_centers
        ),
        "switches": switches,
        "interpretation": (
            "one bunch is the nominal 750 Hz frame lattice projected from one independently "
            "acquired 20 ms probe epoch; tight within-bunch timing is not independent "
            "per-frame timing acquisition"
        ),
    }
    return analysis, bunches


def _track_metrics(
    product: StandardKalmanTrackingV1,
    final_bank: FinalTrajectoryBankV3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    final_by_id = {item.trajectory_id: item for item in final_bank.trajectories}
    per_track: list[dict[str, Any]] = []
    updated_phase: list[float] = []
    updated_doppler_innovation: list[float] = []
    filtered_cfo_delta: list[float] = []
    filtered_rate_delta: list[float] = []
    frame_phase_us: list[float] = []

    for track in product.tracks:
        source = final_by_id[track.source_trajectory_id]
        model = PolynomialFrequencyModel(
            source.reference_time_s,
            tuple(source.absolute_coefficients_hz),
        )
        updated = [frame for frame in track.frames if frame.update_applied]
        phase = [frame.phase_innovation_rad for frame in updated]
        doppler_innovation = [frame.doppler_innovation_hz for frame in updated]
        cfo_delta = [
            frame.doppler_shift_hz - float(model.frequency_hz(frame.time_s)) for frame in updated
        ]
        rate_delta = [
            frame.doppler_rate_hz_s - float(model.doppler_rate_hz_s(frame.time_s))
            for frame in updated
        ]
        timing = [frame.frame_phase_s * 1e6 for frame in updated]
        updated_phase.extend(phase)
        updated_doppler_innovation.extend(doppler_innovation)
        filtered_cfo_delta.extend(cfo_delta)
        filtered_rate_delta.extend(rate_delta)
        frame_phase_us.extend(timing)
        per_track.append(
            {
                "source_trajectory_id": track.source_trajectory_id,
                "source_branch_id": track.source_branch_id,
                "start_s": source.start_s,
                "end_s": source.end_s,
                "current_polynomial_coefficients_hz": list(source.absolute_coefficients_hz),
                "source_frame_count": track.source_frame_count,
                "processed_frame_count": track.processed_frame_count,
                "returned_frame_count": track.returned_frame_count,
                "measurement_update_count": track.measurement_update_count,
                "rejected_measurement_count": track.rejected_measurement_count,
                "phase_slip_count": track.phase_slip_count,
                "cfo_correction_count": track.cfo_correction_count,
                "median_prompt_coherence": _median(
                    [frame.prompt_coherence for frame in track.frames]
                ),
                "median_absolute_phase_innovation_rad": _median([abs(value) for value in phase]),
                "phase_innovation_resultant_length": _resultant_length(phase),
                "median_absolute_doppler_innovation_hz": _median(
                    [abs(value) for value in doppler_innovation]
                ),
                "rms_doppler_innovation_hz": _rms(doppler_innovation),
                "median_absolute_filtered_minus_current_cfo_hz": _median(
                    [abs(value) for value in cfo_delta]
                ),
                "median_absolute_filtered_minus_current_rate_hz_s": _median(
                    [abs(value) for value in rate_delta]
                ),
                "median_absolute_frame_phase_us": _median([abs(value) for value in timing]),
            }
        )

    updates = sum(track.measurement_update_count for track in product.tracks)
    slips = sum(track.phase_slip_count for track in product.tracks)
    aggregate = {
        "source_frame_count": sum(track.source_frame_count for track in product.tracks),
        "processed_frame_count": sum(track.processed_frame_count for track in product.tracks),
        "returned_frame_count": sum(track.returned_frame_count for track in product.tracks),
        "measurement_update_count": updates,
        "rejected_measurement_count": sum(
            track.rejected_measurement_count for track in product.tracks
        ),
        "phase_slip_count": slips,
        "phase_slip_fraction_of_updates": None if not updates else slips / updates,
        "cfo_correction_count": sum(track.cfo_correction_count for track in product.tracks),
        "median_absolute_phase_innovation_rad": _median([abs(value) for value in updated_phase]),
        "phase_innovation_resultant_length": _resultant_length(updated_phase),
        "uniform_phase_reference_median_absolute_rad": math.pi / 2,
        "median_absolute_doppler_innovation_hz": _median(
            [abs(value) for value in updated_doppler_innovation]
        ),
        "rms_doppler_innovation_hz": _rms(updated_doppler_innovation),
        "median_absolute_filtered_minus_current_cfo_hz": _median(
            [abs(value) for value in filtered_cfo_delta]
        ),
        "median_absolute_filtered_minus_current_rate_hz_s": _median(
            [abs(value) for value in filtered_rate_delta]
        ),
        "median_absolute_frame_phase_us": _median([abs(value) for value in frame_phase_us]),
    }
    return per_track, aggregate


def _current_metrics(path_report: dict[str, Any]) -> dict[str, Any]:
    raw = path_report["raw_report"]
    probes = raw["initial_glrt64"]
    positive = [
        item for item in probes if item["initial_margin"] >= 0.05 and item["qam_accuracy"] >= 0.60
    ]
    trajectories = path_report["final_trajectories"]
    return {
        "status": path_report["status"],
        "reason": path_report["reason"],
        "probe_count": len(probes),
        "positive_glrt64_margin_count": sum(item["initial_margin"] > 0 for item in probes),
        "exploratory_pilot_qam_positive_count": len(positive),
        "maximum_initial_margin": max(item["initial_margin"] for item in probes),
        "maximum_qam_accuracy": max(item["qam_accuracy"] for item in probes),
        "final_trajectory_count": len(trajectories),
        "summed_final_trajectory_span_s": sum(
            item["end_s"] - item["start_s"] for item in trajectories
        ),
    }


def _plot(
    output: Path,
    *,
    product: StandardKalmanTrackingV1,
    final_bank: FinalTrajectoryBankV3,
    session: str,
    stream: str,
    receiver: int,
) -> None:
    final_by_id = {item.trajectory_id: item for item in final_bank.trajectories}
    figure, axes = plt.subplots(2, 2, figsize=(18, 11), constrained_layout=True)
    cfo_axis, rate_axis, phase_axis, frame_axis = axes.flat
    colors = plt.get_cmap("tab10")

    for index, track in enumerate(product.tracks):
        source = final_by_id[track.source_trajectory_id]
        model = PolynomialFrequencyModel(
            source.reference_time_s,
            tuple(source.absolute_coefficients_hz),
        )
        color = colors(index % 10)
        label = f"T{index + 1}: {source.start_s:.2f}–{source.end_s:.2f} s"
        times = np.linspace(source.start_s, source.end_s, 160)
        cfo_axis.plot(
            times,
            model.frequency_hz(times) / 1e3,
            color=color,
            linewidth=2.0,
            linestyle="--",
            label=f"current {label}",
        )
        frames = [frame for frame in track.frames if frame.update_applied]
        if not frames:
            continue
        stride = max(1, len(frames) // 500)
        shown = frames[::stride]
        frame_times = np.asarray([frame.time_s for frame in shown])
        cfo_axis.scatter(
            frame_times,
            [frame.doppler_shift_hz / 1e3 for frame in shown],
            s=7,
            color=color,
            alpha=0.32,
        )
        rate_axis.plot(
            times,
            model.doppler_rate_hz_s(times) / 1e3,
            color=color,
            linewidth=2.0,
            linestyle="--",
        )
        rate_axis.scatter(
            frame_times,
            [frame.doppler_rate_hz_s / 1e3 for frame in shown],
            s=7,
            color=color,
            alpha=0.32,
        )
        phase_axis.scatter(
            frame_times,
            [frame.phase_innovation_rad for frame in shown],
            s=7,
            color=color,
            alpha=0.32,
        )
        frame_axis.scatter(
            frame_times,
            [frame.frame_phase_s * 1e6 for frame in shown],
            s=7,
            color=color,
            alpha=0.32,
        )

    cfo_axis.set_title("Doppler/CFO: current final polynomial (dashed) vs Kalman frames")
    cfo_axis.set_ylabel("Baseband CFO (kHz)")
    cfo_axis.legend(loc="best", fontsize=8, ncol=2)
    rate_axis.set_title("Doppler rate: current polynomial (dashed) vs Kalman state")
    rate_axis.set_ylabel("Doppler rate (kHz/s)")
    rate_axis.set_yscale("symlog", linthresh=10)
    phase_axis.set_title("Wrapped carrier-phase innovation; shaded band is the π/8 slip gate")
    phase_axis.axhspan(-math.pi / 8, math.pi / 8, color="#2ca02c", alpha=0.12)
    phase_axis.axhline(0, color="black", linewidth=0.8)
    phase_axis.set_ylim(-math.pi, math.pi)
    phase_axis.set_ylabel("Phase innovation (rad)")
    frame_axis.set_title("Estimated frame phase (timing residual; no pseudorange claim)")
    frame_axis.axhline(0, color="black", linewidth=0.8)
    frame_axis.set_ylabel("Frame phase (µs)")
    for axis in axes.flat:
        axis.set_xlabel("Elapsed recording time (s)")
        axis.grid(alpha=0.22)
    figure.suptitle(
        "Verified known-pilot five-state Kalman comparison\n"
        f"{session} · {stream}/RX{receiver} · candidate-only · no payload/attribution",
        fontsize=15,
    )
    figure.savefig(output, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_frame_bunches(
    output: Path,
    *,
    bunches: list[FrameBunch],
    analysis: dict[str, Any],
    session: str,
    stream: str,
    receiver: int,
) -> None:
    by_track: dict[int, list[FrameBunch]] = {}
    for bunch in bunches:
        by_track.setdefault(bunch.track_index, []).append(bunch)
    transitions: list[tuple[float, int, FrameBunch, FrameBunch]] = []
    for track_index, track_bunches in by_track.items():
        transitions.extend(
            (
                abs(_wrap_frame_phase_s(right.filtered_center_s - left.filtered_center_s)) * 1e6,
                track_index,
                left,
                right,
            )
            for left, right in zip(track_bunches, track_bunches[1:], strict=False)
        )
    largest = max(transitions, key=lambda item: item[0])
    _, zoom_track_index, _, zoom_right = largest
    zoom_start = zoom_right.start_s - 0.16
    zoom_end = zoom_right.start_s + 0.16

    figure, axes = plt.subplots(2, 2, figsize=(18, 11), constrained_layout=True)
    overview_axis, zoom_axis, transition_axis, center_axis = axes.flat
    colors = plt.get_cmap("tab10")
    for track_index, track_bunches in sorted(by_track.items()):
        color = colors((track_index - 1) % 10)
        overview_axis.plot(
            [bunch.start_s for bunch in track_bunches],
            [bunch.filtered_center_s * 1e6 for bunch in track_bunches],
            marker="o",
            markersize=3,
            linewidth=0.8,
            alpha=0.72,
            color=color,
            label=f"T{track_index}",
        )
    overview_axis.axhline(FRAME_PERIOD_S * 0.5e6, color="black", linestyle=":")
    overview_axis.axhline(-FRAME_PERIOD_S * 0.5e6, color="black", linestyle=":")
    overview_axis.set_title("One center per 20 ms frame bunch (wrapped modulo 1/750 s)")
    overview_axis.set_xlabel("Elapsed recording time (s)")
    overview_axis.set_ylabel("Bunch frame-phase center (µs)")
    overview_axis.legend(ncol=4, fontsize=8)

    zoom_bunches = [
        bunch for bunch in by_track[zoom_track_index] if zoom_start <= bunch.start_s <= zoom_end
    ]
    for index, bunch in enumerate(zoom_bunches):
        color = colors(index % 2)
        zoom_axis.scatter(
            [frame.time_s for frame in bunch.updated],
            [_wrap_frame_phase_s(frame.frame_phase_s) * 1e6 for frame in bunch.updated],
            s=16,
            alpha=0.72,
            color=color,
        )
        zoom_axis.plot(
            [bunch.start_s, bunch.end_s],
            [bunch.filtered_center_s * 1e6] * 2,
            color=color,
            linewidth=2.2,
        )
    zoom_axis.axhline(FRAME_PERIOD_S * 0.5e6, color="black", linestyle=":")
    zoom_axis.axhline(-FRAME_PERIOD_S * 0.5e6, color="black", linestyle=":")
    zoom_axis.set_xlim(zoom_start, zoom_end)
    zoom_axis.set_ylim(-FRAME_PERIOD_S * 0.53e6, FRAME_PERIOD_S * 0.53e6)
    zoom_axis.set_title(
        f"T{zoom_track_index} zoom: ≈15 projected frames share each acquired probe epoch"
    )
    zoom_axis.set_xlabel("Elapsed recording time (s)")
    zoom_axis.set_ylabel("Estimated frame phase (µs)")

    transition_values = [item[0] for item in transitions]
    transition_axis.hist(
        transition_values,
        bins=np.linspace(0, FRAME_PERIOD_S * 0.5e6, 45),
        color="#4c78a8",
        alpha=0.84,
    )
    for threshold, color in ((100, "#59a14f"), (250, "#f28e2b"), (500, "#e15759")):
        transition_axis.axvline(threshold, color=color, linewidth=2, label=f">{threshold} µs")
    transition_axis.set_title("Wrapped change between adjacent bunch centers")
    transition_axis.set_xlabel("Absolute frame-phase change (µs)")
    transition_axis.set_ylabel("Adjacent transitions (log count)")
    transition_axis.set_yscale("log")
    transition_axis.legend()

    center_axis.hist(
        [bunch.filtered_center_s * 1e6 for bunch in bunches],
        bins=np.linspace(-FRAME_PERIOD_S * 0.5e6, FRAME_PERIOD_S * 0.5e6, 45),
        color="#b279a2",
        alpha=0.84,
    )
    center_axis.set_title(
        "Bunch centers span the frame period; "
        f"circular R = {analysis['filtered_bunch_center_resultant_length']:.3f}"
    )
    center_axis.set_xlabel("Wrapped bunch center (µs)")
    center_axis.set_ylabel("Bunches")
    center_axis.axvline(0, color="black", linewidth=0.8)

    for axis in axes.flat:
        axis.grid(alpha=0.22)
    figure.suptitle(
        "Why estimated frame phase appears in bunches\n"
        f"{session} · {stream}/RX{receiver} · timing lattice, not code phase",
        fontsize=15,
    )
    figure.savefig(output, dpi=170, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def main() -> None:
    args = _arguments()
    scientific_root = (
        args.bulk_root
        / "analysis"
        / args.session
        / args.run_id
        / "scientific"
        / "path-standard"
        / args.scope_key
    )
    pilot_path = scientific_root / "standard.pilot-scan.v3.json"
    canonical_path = scientific_root / "standard.dealiased-trajectory-bank.v4.json"
    final_path = scientific_root / "standard.final-trajectory-bank.v3.json"
    report_path = scientific_root / "standard.path-report.v2.json"
    presentation_root = (
        args.bulk_root
        / "analysis"
        / args.session
        / args.run_id
        / "presentation"
        / "path-standard"
        / args.scope_key
    )
    pilot_document = _read_json(pilot_path)
    path_report = _read_json(report_path)
    canonical_bank = DealiasedTrajectoryBankV4.model_validate_json(canonical_path.read_bytes())
    final_bank = FinalTrajectoryBankV3.model_validate_json(final_path.read_bytes())

    store = RecordingStore.open_read_only(args.bulk_root)
    bundle = store.inspect(args.session)
    stream_reader = store.reader(bundle, args.stream, verify=True)
    reader = SingleReceiverIqReader(stream_reader, args.receiver)
    config = ReceiverStandardConfig()
    offline_binding_digest = canonical_digest(
        {
            "mode": "offline-verified-kalman-comparison-v1",
            "session_id": args.session,
            "recording_manifest_digest": bundle.manifest_sha256,
            "scope_key": args.scope_key,
            "stream_id": args.stream,
            "receiver_id": args.receiver,
        }
    )
    started = time.monotonic()
    product = build_standard_kalman_tracking(
        reader,
        path_input_binding_digest=offline_binding_digest,
        pilot_scan_digest=canonical_digest(pilot_document),
        detections=_pilot_detections(pilot_document),
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        feedback_config=config.feedback,
        config=config.kalman,
        edge=StarlinkEdge(args.edge),
    )
    elapsed_s = time.monotonic() - started
    tracks, aggregate = _track_metrics(product, final_bank)
    frame_bunch_analysis, frame_bunches = _frame_bunch_analysis(product)
    current_pngs = {}
    for path in sorted(presentation_root.glob("standard.*-png.v*.png")):
        current_pngs[path.name] = {
            "path": str(path.resolve()),
            "digest": sha256_digest(path.read_bytes()),
        }
    summary = {
        "schema_version": 1,
        "analysis": "offline-verified-kalman-phase-comparison-v1",
        "session_id": args.session,
        "run_id": args.run_id,
        "scope_key": args.scope_key,
        "stream_id": args.stream,
        "receiver_id": args.receiver,
        "edge": args.edge,
        "recording_manifest_digest": bundle.manifest_sha256,
        "pilot_scan_digest": canonical_digest(pilot_document),
        "dealiased_bank_digest": canonical_bank.content_digest,
        "final_bank_digest": final_bank.content_digest,
        "kalman_product_digest": product.content_digest,
        "runtime_s": elapsed_s,
        "integrity_verification": "enabled_for_every_consumed_iq_shard",
        "current_standard": _current_metrics(path_report),
        "current_standard_pngs": current_pngs,
        "kalman_aggregate": aggregate,
        "kalman_tracks": tracks,
        "frame_bunch_analysis": frame_bunch_analysis,
        "interpretation": {
            "phase_tracking": "not coherent on this known-pilot observable",
            "basis": (
                "median absolute wrapped phase innovation is near the pi/2 uniform-phase "
                "reference and most accepted updates exceed the pi/8 slip gate"
            ),
            "doppler_tracking": "diagnostic only; does not replace the current final polynomial",
            "frame_tracking": "receiver-relative frame timing only; no code phase or pseudorange",
            "claims": "candidate-only; known-pilots-only; no payload decoding or attribution",
        },
    }
    summary["content_digest"] = canonical_digest(summary)

    args.output_root.mkdir(parents=True, exist_ok=True)
    product_path = args.output_root / "standard.kalman-tracking.v1.json.gz"
    summary_path = args.output_root / "kalman-phase-comparison-summary.json"
    plot_path = args.output_root / "kalman-phase-vs-current-standard.png"
    bunch_plot_path = args.output_root / "frame-phase-bunches-and-switches.png"
    product_path.write_bytes(
        gzip.compress(canonical_json_bytes(product.model_dump(mode="json")), mtime=0)
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _plot(
        plot_path,
        product=product,
        final_bank=final_bank,
        session=args.session,
        stream=args.stream,
        receiver=args.receiver,
    )
    _plot_frame_bunches(
        bunch_plot_path,
        bunches=frame_bunches,
        analysis=frame_bunch_analysis,
        session=args.session,
        stream=args.stream,
        receiver=args.receiver,
    )
    print(
        json.dumps(
            {
                "product": str(product_path),
                "summary": str(summary_path),
                "plot": str(plot_path),
                "frame_bunch_plot": str(bunch_plot_path),
                "runtime_s": elapsed_s,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
