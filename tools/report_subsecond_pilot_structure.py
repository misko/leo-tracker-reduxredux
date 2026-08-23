#!/usr/bin/env python3
"""Audit sub-second Qin pilot phase/CFO structure across independent dwells.

The analysis is deliberately offline and read-only.  It selects one supported
degree-one carrier from each frozen dwell, returns to digest-verified raw IQ,
fills an 80 ms 750 Hz frame lattice from one independently acquired timing
epoch, and applies the same modulo-pi phase audit used by the edge-pilot phase
report.  The resulting JSON is intended to separate deterministic pilot phase
states from physical Doppler structure before changing any tracker.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from report_edge_pilot_phase_slope_figures import (
    DEFAULT_ANALYSIS_ROOT,
    SESSION_ID,
    DenseTrackingDetail,
    DenseTrackingFrame,
    FrozenTrajectory,
    _complex_receiver,
    _frequency_update_runs,
    _offline_phase_continuity_audit,
    _trajectory,
)

from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

DEFAULT_FIVE_DWELL_EVIDENCE = Path(
    "reports/figures/2026_08_21_five_dwell_degree1_only_rerun/five-dwell-d1only-evidence.json"
)
DEFAULT_EXISTING_DETAIL = Path(
    "reports/figures/2026_08_22_edge_pilot_phase_slope/detailed-results.json"
)
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_22_subsecond_pilot_structure")
BLUE = "#2678a8"
GREEN = "#4f9b66"
AMBER = "#d28a29"
RED = "#c44e52"
INK = "#193549"
GRAY = "#728694"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--five-dwell-evidence", type=Path, default=DEFAULT_FIVE_DWELL_EVIDENCE)
    parser.add_argument("--existing-detail", type=Path, default=DEFAULT_EXISTING_DETAIL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--interval-ms", type=float, default=80.0)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _path_from_bulk_uri(uri: str, bulk_root: Path) -> Path:
    prefix = "bulk://"
    if not uri.startswith(prefix):
        raise ValueError(f"unsupported artifact URI: {uri}")
    return bulk_root / uri[len(prefix) :]


def _glrt64(candidate: dict[str, Any]) -> dict[str, Any]:
    rows = [item for item in candidate["scores"] if item["method"] == "glrt64"]
    if len(rows) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return rows[0]


def _trajectory_candidates(
    scan: dict[str, Any],
    trajectory: FrozenTrajectory,
    *,
    start_s: float,
    end_s: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if not start_s <= time_s <= end_s:
            continue
        model_hz = float(trajectory.frequency_hz(time_s))
        choices = []
        for candidate in detection["candidates"]:
            score = _glrt64(candidate)
            choices.append(
                (
                    abs(float(score["tracking_cfo_hz"]) - model_hz),
                    -float(score["margin"]),
                    int(candidate["rank"]),
                    candidate,
                    score,
                )
            )
        if not choices:
            continue
        error_hz, _negative_margin, _rank, candidate, score = min(choices)
        if error_hz > 2_500 or float(score["margin"]) < 0.05:
            continue
        output.append(
            {
                "time_s": time_s,
                "sample_start": int(detection["sample_start"]),
                "local_epoch_sample": int(candidate["local_epoch_sample"]),
                "tracking_cfo_hz": float(score["tracking_cfo_hz"]),
                "margin": float(score["margin"]),
                "model_error_hz": float(error_hz),
            }
        )
    return output


def _select_carrier_and_anchor(
    analysis_root: Path,
) -> tuple[FrozenTrajectory, dict[str, Any], dict[str, Any]]:
    scan = _load_json(analysis_root / "standard.pilot-scan.v3.json")
    bank_paths = sorted(analysis_root.glob("standard.final-trajectory-bank.v*.json"))
    if not bank_paths:
        raise FileNotFoundError(f"no final trajectory bank in {analysis_root}")
    bank = _load_json(bank_paths[-1])
    choices = []
    for item in bank["trajectories"]:
        coefficients = tuple(float(value) for value in item["absolute_coefficients_hz"])
        if len(coefficients) != 2:
            continue
        trajectory = FrozenTrajectory(
            coefficients_hz=coefficients,
            reference_time_s=float(item["reference_time_s"]),
            branch_id=str(item["branch_id"]),
            trajectory_id=str(item["trajectory_id"]),
        )
        candidates = _trajectory_candidates(
            scan,
            trajectory,
            start_s=float(item["start_s"]),
            end_s=float(item["end_s"]),
        )
        if not candidates:
            continue
        times = np.asarray([row["time_s"] for row in candidates])
        for row in candidates:
            neighbors = int(np.count_nonzero(np.abs(times - row["time_s"]) <= 0.10))
            row["neighbor_count_200ms"] = neighbors
        supported = [row for row in candidates if row["neighbor_count_200ms"] >= 3]
        anchor = max(
            supported or candidates,
            key=lambda row: (
                row["margin"],
                row["neighbor_count_200ms"],
                -row["model_error_hz"],
            ),
        )
        choices.append(
            (
                len(candidates),
                anchor["neighbor_count_200ms"],
                anchor["margin"],
                trajectory,
                anchor,
            )
        )
    if not choices:
        raise ValueError(f"no supported degree-one carrier in {analysis_root}")
    _count, _neighbors, _margin, trajectory, anchor = max(
        choices,
        key=lambda row: (row[2], row[1], row[0]),
    )
    return trajectory, anchor, scan


def _anchor_detail(
    *,
    frame_start_sample: int,
    reference_time_s: float,
    cfo_hz: float,
    trajectory: FrozenTrajectory,
) -> DenseTrackingDetail:
    model = float(trajectory.frequency_hz(reference_time_s))
    rate = float(trajectory.doppler_rate_hz_s(reference_time_s))
    frame = DenseTrackingFrame(
        frame_start_sample=frame_start_sample,
        reference_time_s=reference_time_s,
        source_window_index=0,
        glrt64_cfo_hz=cfo_hz,
        model_cfo_hz=model,
        absolute_cfo_measurement_hz=cfo_hz,
        tracked_absolute_cfo_hz=cfo_hz,
        tracked_doppler_rate_hz_s=rate,
        model_doppler_rate_hz_s=rate,
        residual_cfo_measurement_hz=cfo_hz - model,
        frequency_uncertainty_hz=25.0,
        tracked_frequency_sigma_hz=25.0,
        tracked_rate_sigma_hz_s=5_000.0,
        phase_measurement_rad=0.0,
        tracked_phase_rad=0.0,
        exact_coherence=1.0,
        control_coherence=0.0,
        coherence_margin=1.0,
        phase_innovation_rad=0.0,
        channel_similarity=1.0,
        phase_segment_id=0,
        phase_update_applied=True,
        frequency_update_applied=True,
        phase_reset_detected=False,
    )
    return DenseTrackingDetail(1, 1, 1, 0, 1, 1, 0.0, (frame,))


def _audit_dwell(
    store: RecordingStore,
    *,
    session_id: str,
    stream_id: str,
    receiver_id: int,
    edge: StarlinkEdge,
    analysis_root: Path,
    interval_s: float,
) -> dict[str, Any]:
    trajectory, anchor, _scan = _select_carrier_and_anchor(analysis_root)
    bundle = store.inspect(session_id)
    reader = store.reader(bundle, stream_id, verify=True)
    sample_rate_hz = float(reader.sample_rate_hz)
    aligned_start = int(anchor["sample_start"] + anchor["local_epoch_sample"])
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    reference_time_s = aligned_start / sample_rate_hz + reference_offset_s
    raw_start = aligned_start
    frame_count = math.ceil(interval_s * 750) + 2
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    raw_count = math.ceil(frame_count * sample_rate_hz / 750) + frame_content
    raw = reader.read(raw_start, raw_count, receiver_ids=(receiver_id,))
    iq = _complex_receiver(raw)
    dense = _anchor_detail(
        frame_start_sample=0,
        reference_time_s=reference_time_s,
        cfo_hz=float(anchor["tracking_cfo_hz"]),
        trajectory=trajectory,
    )
    detail = _offline_phase_continuity_audit(
        iq,
        raw_sample_start=raw_start,
        sample_rate_hz=sample_rate_hz,
        edge=edge,
        trajectory=trajectory,
        dense_tracking=dense,
        start_s=reference_time_s,
        end_s=reference_time_s + interval_s,
    )
    result = asdict(detail)
    result.update(
        {
            "session_id": session_id,
            "stream_id": stream_id,
            "receiver_id": receiver_id,
            "edge": edge.value,
            "analysis_root": str(analysis_root),
            "trajectory_id": trajectory.trajectory_id,
            "branch_id": trajectory.branch_id,
            "trajectory_coefficients_hz": list(trajectory.coefficients_hz),
            "trajectory_reference_time_s": trajectory.reference_time_s,
            "anchor": anchor,
            "recording_manifest_digest": bundle.manifest_sha256,
        }
    )
    return result


def _audit_target_intervals(
    store: RecordingStore,
    *,
    existing_path: Path,
    interval_s: float,
) -> list[dict[str, Any]]:
    document = _load_json(existing_path)
    trajectory = _trajectory(
        _load_json(DEFAULT_ANALYSIS_ROOT / "standard.final-trajectory-bank.v2.json")
    )
    bundle = store.inspect(SESSION_ID)
    reader = store.reader(bundle, "stream-0", verify=True)
    sample_rate_hz = float(reader.sample_rate_hz)
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    dense_frames = document["dense_tracking"]["frames"]
    output = []
    for requested_start_s in (34.08, 34.73, 35.80, 36.00, 36.60):
        anchors = [
            item
            for item in dense_frames
            if requested_start_s <= item["reference_time_s"] < requested_start_s + 0.02
        ]
        if not anchors:
            continue
        anchor = anchors[0]
        raw_start = round(
            float(anchor["reference_time_s"]) * sample_rate_hz - reference_offset_s * sample_rate_hz
        )
        reference_time_s = raw_start / sample_rate_hz + reference_offset_s
        frame_count = math.ceil(interval_s * 750) + 2
        frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
        raw_count = math.ceil(frame_count * sample_rate_hz / 750) + frame_content
        iq = _complex_receiver(reader.read(raw_start, raw_count, receiver_ids=(0,)))
        dense = _anchor_detail(
            frame_start_sample=0,
            reference_time_s=reference_time_s,
            cfo_hz=float(anchor["glrt64_cfo_hz"]),
            trajectory=trajectory,
        )
        detail = _offline_phase_continuity_audit(
            iq,
            raw_sample_start=raw_start,
            sample_rate_hz=sample_rate_hz,
            edge=StarlinkEdge.UPPER,
            trajectory=trajectory,
            dense_tracking=dense,
            start_s=reference_time_s,
            end_s=reference_time_s + interval_s,
        )
        row = asdict(detail)
        row.update(
            {
                "requested_start_s": requested_start_s,
                "session_id": SESSION_ID,
                "stream_id": "stream-0",
                "receiver_id": 0,
                "edge": "upper",
                "trajectory_id": trajectory.trajectory_id,
                "branch_id": trajectory.branch_id,
            }
        )
        output.append(row)
    return output


def _state_period_metrics(frames: list[dict[str, Any]]) -> dict[str, Any]:
    bits = np.asarray([int(item["pi_ambiguity_state"]) for item in frames], dtype=int)
    signed = 2 * bits - 1
    maximum_lag = min(30, len(bits) // 2)
    rows = []
    for lag in range(1, maximum_lag + 1):
        agreement = float(np.mean(bits[:-lag] == bits[lag:]))
        correlation = float(np.mean(signed[:-lag] * signed[lag:]))
        rows.append({"lag_frames": lag, "agreement": agreement, "correlation": correlation})
    strongest = max(rows[1:], key=lambda item: (item["agreement"], item["correlation"]))
    period = int(strongest["lag_frames"])
    template = np.asarray(
        [
            int(np.mean(bits[np.arange(len(bits)) % period == index]) >= 0.5)
            for index in range(period)
        ]
    )
    predicted = template[np.arange(len(bits)) % period]
    template_agreement = max(
        float(np.mean(bits == predicted)),
        float(np.mean(bits == 1 - predicted)),
    )
    transitions = np.flatnonzero(np.diff(bits) != 0) + 1
    boundaries = np.r_[0, transitions, len(bits)]
    run_lengths = np.diff(boundaries)
    return {
        "bit_sequence": "".join(str(value) for value in bits),
        "transition_count": int(len(transitions)),
        "transition_fraction": float(len(transitions) / max(1, len(bits) - 1)),
        "run_lengths_frames": run_lengths.tolist(),
        "median_run_length_frames": float(np.median(run_lengths)),
        "lag_metrics": rows,
        "strongest_repeat_lag_frames": period,
        "strongest_repeat_period_ms": period / 0.75,
        "strongest_repeat_agreement": float(strongest["agreement"]),
        "template": "".join(str(value) for value in template),
        "template_agreement": template_agreement,
    }


def _frequency_mode_metrics(frames: list[dict[str, Any]]) -> dict[str, Any]:
    bits = np.asarray([int(item["pi_ambiguity_state"]) for item in frames], dtype=int)
    ordinary = np.asarray(
        [
            np.nan
            if item["phase_implied_frequency_error_hz"] is None
            else item["phase_implied_frequency_error_hz"]
            for item in frames
        ]
    )
    corrected = np.asarray(
        [
            np.nan
            if item["pi_corrected_phase_implied_frequency_error_hz"] is None
            else item["pi_corrected_phase_implied_frequency_error_hz"]
            for item in frames
        ]
    )
    quality = np.asarray(
        [item["exact_coherence"] >= 0.02 and item["coherence_margin"] >= 0 for item in frames]
    )
    pair_quality = quality[1:] & quality[:-1]
    categories = {
        "same_binary_state": (bits[1:] == bits[:-1]) & pair_quality,
        "binary_state_transition": (bits[1:] != bits[:-1]) & pair_quality,
    }
    modes = {}
    for label, selected in categories.items():
        values = ordinary[1:][selected]
        modes[label] = {
            "count": int(len(values)),
            "median_hz": float(np.median(values)) if len(values) else None,
            "mad_hz": float(np.median(np.abs(values - np.median(values)))) if len(values) else None,
        }
    finite = np.isfinite(corrected)
    finite &= np.r_[False, pair_quality]
    return {
        "ordinary_modes_by_binary_transition": modes,
        "pi_corrected_rms_hz": float(np.sqrt(np.mean(corrected[finite] ** 2))),
        "pi_corrected_median_absolute_hz": float(np.median(np.abs(corrected[finite]))),
    }


def _local_rate_metrics(frames: list[dict[str, Any]]) -> dict[str, Any]:
    times = np.asarray([item["reference_time_s"] for item in frames])
    centered = times - float(np.mean(times))
    quality = np.asarray(
        [item["exact_coherence"] >= 0.02 and item["coherence_margin"] >= 0 for item in frames]
    )
    weights = np.asarray([item["exact_coherence"] for item in frames])
    fitted_frequency = np.asarray([item["frequency_fit_cfo_hz"] for item in frames])
    model_frequency = np.asarray([item["model_cfo_hz"] for item in frames])
    frequency_coefficients = np.polyfit(centered, fitted_frequency, 2)
    model_coefficients = np.polyfit(centered, model_frequency, 1)
    within_frame_rate = float(frequency_coefficients[1])
    model_rate = float(model_coefficients[0])

    phase = np.asarray([item["phase_measurement_rad"] for item in frames])
    bits = np.asarray([item["pi_ambiguity_state"] for item in frames])
    integrated_frequency = (
        2
        * np.pi
        * (
            (frequency_coefficients[2] - model_coefficients[1]) * centered
            + 0.5 * frequency_coefficients[1] * centered**2
            + (frequency_coefficients[0] / 3) * centered**3
        )
    )
    residual_phase = np.unwrap(np.angle(np.exp(1j * (phase - integrated_frequency - np.pi * bits))))
    if np.count_nonzero(quality) >= 8:
        phase_coefficients = np.polyfit(
            centered[quality],
            residual_phase[quality],
            3,
            w=np.sqrt(weights[quality]),
        )
        phase_model = np.polyval(phase_coefficients, centered)
        phase_residual = np.angle(np.exp(1j * (residual_phase - phase_model)))
        phase_supported_rate = within_frame_rate + float(phase_coefficients[-3] / np.pi)
        phase_rms = float(np.sqrt(np.mean(phase_residual[quality] ** 2)))
    else:
        phase_supported_rate = None
        phase_rms = None
    return {
        "quality_fraction": float(np.mean(quality)),
        "frozen_model_rate_hz_s": model_rate,
        "within_frame_cfo_rate_hz_s": within_frame_rate,
        "within_frame_minus_frozen_hz_s": within_frame_rate - model_rate,
        "phase_supported_rate_hz_s": phase_supported_rate,
        "phase_minus_within_frame_hz_s": (
            phase_supported_rate - within_frame_rate if phase_supported_rate is not None else None
        ),
        "reconstructed_phase_residual_rms_rad": phase_rms,
    }


def _weighted_local_linear_prediction(
    train_time: np.ndarray,
    train_residual: np.ndarray,
    train_weight: np.ndarray,
    test_time: np.ndarray,
    *,
    bandwidth_s: float,
) -> np.ndarray:
    output = np.full(len(test_time), np.nan)
    for index, value in enumerate(test_time):
        delta = train_time - value
        weights = train_weight * np.exp(-0.5 * (delta / bandwidth_s) ** 2)
        selected = weights > float(np.max(weights)) * 1e-6
        if np.count_nonzero(selected) < 3:
            continue
        design = np.column_stack((np.ones(np.count_nonzero(selected)), delta[selected]))
        root = np.sqrt(weights[selected])
        coefficients = np.linalg.lstsq(
            design * root[:, None],
            train_residual[selected] * root,
            rcond=None,
        )[0]
        output[index] = coefficients[0]
    return output


def _error_metrics(error: np.ndarray) -> dict[str, Any]:
    values = np.asarray(error)
    values = values[np.isfinite(values)]
    return {
        "count": int(len(values)),
        "rms_hz": float(np.sqrt(np.mean(values**2))),
        "median_absolute_hz": float(np.median(np.abs(values))),
        "p90_absolute_hz": float(np.quantile(np.abs(values), 0.9)),
    }


def _cfo_holdout_metrics(existing_path: Path) -> dict[str, Any]:
    document = _load_json(existing_path)
    frames = [
        item
        for item in document["dense_tracking"]["frames"]
        if item["frequency_update_applied"] and item["coherence_margin"] > 0
    ]
    times = np.asarray([item["reference_time_s"] for item in frames])
    measured = np.asarray([item["absolute_cfo_measurement_hz"] for item in frames])
    model = np.asarray([item["model_cfo_hz"] for item in frames])
    glrt = np.asarray([item["glrt64_cfo_hz"] for item in frames])
    uncertainty = np.asarray([item["frequency_uncertainty_hz"] for item in frames])
    coherence = np.asarray([item["exact_coherence"] for item in frames])
    weights = coherence / np.maximum(uncertainty, 5.0) ** 2
    indices = np.arange(len(frames))
    train = indices % 2 == 0
    test = ~train
    residual = measured - model

    interleaved = []
    for bandwidth_ms in (5, 10, 20, 50, 100, 250):
        prediction = _weighted_local_linear_prediction(
            times[train],
            residual[train],
            weights[train],
            times[test],
            bandwidth_s=bandwidth_ms / 1_000,
        )
        interleaved.append(
            {
                "bandwidth_ms": bandwidth_ms,
                **_error_metrics(measured[test] - model[test] - prediction),
            }
        )

    block_holdout = []
    for block_ms in (5, 10, 20, 50):
        block_id = np.floor((times - float(np.min(times))) / (block_ms / 1_000)).astype(int)
        block_test = block_id % 4 == 2
        block_train = ~block_test
        prediction = _weighted_local_linear_prediction(
            times[block_train],
            residual[block_train],
            weights[block_train],
            times[block_test],
            bandwidth_s=0.010,
        )
        block_holdout.append(
            {
                "heldout_block_ms": block_ms,
                "smoother_bandwidth_ms": 10,
                **_error_metrics(measured[block_test] - model[block_test] - prediction),
            }
        )

    forward = []
    for history_ms in (20, 50, 100, 250):
        predictions = []
        selected_indices = []
        history_s = history_ms / 1_000
        for index, value in enumerate(times):
            selected = (times < value) & (times >= value - history_s)
            if np.count_nonzero(selected) < 5:
                continue
            delta = times[selected] - value
            design = np.column_stack((np.ones(np.count_nonzero(selected)), delta))
            root = np.sqrt(weights[selected])
            coefficients = np.linalg.lstsq(
                design * root[:, None],
                residual[selected] * root,
                rcond=None,
            )[0]
            predictions.append(coefficients[0])
            selected_indices.append(index)
        selected_array = np.asarray(selected_indices, dtype=int)
        forward.append(
            {
                "history_ms": history_ms,
                **_error_metrics(
                    measured[selected_array] - model[selected_array] - np.asarray(predictions)
                ),
            }
        )

    return {
        "frame_count": len(frames),
        "median_reported_frame_uncertainty_hz": float(np.median(uncertainty)),
        "frozen_model_interleaved": _error_metrics(measured[test] - model[test]),
        "source_glrt_held_over_window_interleaved": _error_metrics(measured[test] - glrt[test]),
        "interleaved_local_linear": interleaved,
        "contiguous_block_holdout": block_holdout,
        "forward_local_linear": forward,
    }


def _frequency_run_metrics(existing_path: Path) -> dict[str, Any]:
    document = _load_json(existing_path)
    frames = tuple(DenseTrackingFrame(**item) for item in document["dense_tracking"]["frames"])
    runs = _frequency_update_runs(frames)
    rows = []
    for run_id, run in enumerate(runs, start=1):
        times = np.asarray([item.reference_time_s for item in run])
        residual = np.asarray(
            [item.absolute_cfo_measurement_hz - item.model_cfo_hz for item in run]
        )
        weights = np.asarray(
            [item.exact_coherence / max(item.frequency_uncertainty_hz, 5.0) ** 2 for item in run]
        )
        centered = times - float(np.mean(times))
        design = np.column_stack((np.ones(len(times)), centered))
        root = np.sqrt(weights)
        coefficients = np.linalg.lstsq(design * root[:, None], residual * root, rcond=None)[0]
        fitted = design @ coefficients
        rows.append(
            {
                "run_id": run_id,
                "start_s": float(times[0]),
                "end_s": float(times[-1]),
                "span_ms": float((times[-1] - times[0]) * 1_000),
                "frame_count": len(run),
                "center_time_s": float(np.mean(times)),
                "center_residual_hz": float(coefficients[0]),
                "residual_rate_hz_s": float(coefficients[1]),
                "fit_rms_hz": float(np.sqrt(np.mean((residual - fitted) ** 2))),
            }
        )
    for index, row in enumerate(rows[:-1]):
        following = rows[index + 1]
        delta = following["start_s"] - row["center_time_s"]
        predicted = row["center_residual_hz"] + row["residual_rate_hz_s"] * delta
        row["next_run_gap_ms"] = (following["start_s"] - row["end_s"]) * 1_000
        row["next_run_residual_jump_hz"] = following["center_residual_hz"] - predicted
    rows[-1]["next_run_gap_ms"] = None
    rows[-1]["next_run_residual_jump_hz"] = None
    supported_slopes = np.asarray(
        [item["residual_rate_hz_s"] for item in rows if item["frame_count"] >= 8]
    )
    supported_rms = np.asarray([item["fit_rms_hz"] for item in rows if item["frame_count"] >= 8])
    return {
        "run_count": len(rows),
        "supported_run_count": int(len(supported_slopes)),
        "median_residual_rate_hz_s": float(np.median(supported_slopes)),
        "p10_residual_rate_hz_s": float(np.quantile(supported_slopes, 0.1)),
        "p90_residual_rate_hz_s": float(np.quantile(supported_slopes, 0.9)),
        "median_fit_rms_hz": float(np.median(supported_rms)),
        "runs": rows,
    }


def _existing_target(existing_path: Path) -> dict[str, Any]:
    document = _load_json(existing_path)
    detail = dict(document["offline_phase_continuity"])
    detail.update(
        {
            "session_id": document["input"]["session_id"],
            "stream_id": document["input"]["stream_id"],
            "receiver_id": document["input"]["receiver_id"],
            "edge": document["input"]["edge"],
            "analysis_scope": document["input"]["analysis_scope"],
            "trajectory_id": document["input"]["trajectory_id"],
            "branch_id": document["input"]["trajectory_branch_id"],
            "source": "existing target interval with complete raw-lattice recovery",
        }
    )
    return detail


def _plot(results: list[dict[str, Any]], output: Path) -> None:
    labels = [item["session_id"].split("-")[-1][:6] for item in results]
    pi_rms = np.asarray([item["pi_ambiguity_batch_phase_residual_rms_rad"] for item in results])
    ordinary_rms = np.asarray([item["cubic_batch_phase_residual_rms_rad"] for item in results])
    corrected_cfo = np.asarray([item["frequency_modes"]["pi_corrected_rms_hz"] for item in results])
    fit_cfo = np.asarray([item["frequency_fit_rms_hz"] for item in results])
    frozen_rate = np.asarray([item["local_rate"]["frozen_model_rate_hz_s"] for item in results])
    local_rate = np.asarray(
        [
            item["local_rate"]["within_frame_cfo_rate_hz_s"]
            if item["local_rate"]["quality_fraction"] >= 0.75
            else np.nan
            for item in results
        ]
    )
    phase_rate = np.asarray(
        [
            np.nan
            if (
                not item["phase_rate_qualified"]
                or item["local_rate"]["phase_supported_rate_hz_s"] is None
            )
            else item["local_rate"]["phase_supported_rate_hz_s"]
            for item in results
        ]
    )
    x = np.arange(len(results))
    with plt.rc_context(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "figure.dpi": 180,
        }
    ):
        figure, axes = plt.subplots(2, 2, figsize=(14.2, 9.0), constrained_layout=True)
        axes[0, 0].bar(x - 0.18, ordinary_rms, width=0.36, color=GRAY, label="ordinary 2π phase")
        axes[0, 0].bar(x + 0.18, pi_rms, width=0.36, color=GREEN, label="binary-π-aware phase")
        axes[0, 0].set_ylabel("phase residual RMS (rad)")
        axes[0, 0].set_title(
            "A · A discrete π state explains recurring phase families",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend()
        axes[0, 0].grid(True, axis="y", alpha=0.3)

        axes[0, 1].bar(
            x - 0.18, fit_cfo, width=0.36, color=BLUE, label="within-frame CFO about smooth fit"
        )
        axes[0, 1].bar(
            x + 0.18, corrected_cfo, width=0.36, color=AMBER, label="π-corrected adjacent phase CFO"
        )
        axes[0, 1].set_ylabel("RMS residual (Hz)")
        axes[0, 1].set_title(
            "B · Correcting π slips makes cross-frame CFO numerically usable",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].legend(fontsize=8.5)
        axes[0, 1].grid(True, axis="y", alpha=0.3)

        axes[1, 0].plot(
            x, frozen_rate / 1_000, marker="o", color=INK, label="multi-second frozen rate"
        )
        axes[1, 0].plot(
            x, local_rate / 1_000, marker="o", color=BLUE, label="80 ms within-frame CFO rate"
        )
        axes[1, 0].plot(
            x,
            phase_rate / 1_000,
            marker="x",
            color=GREEN,
            linestyle="none",
            label="π-aware phase-supported rate",
        )
        axes[1, 0].set_xticks(x, labels, rotation=25, ha="right")
        axes[1, 0].set_ylabel("CFO rate (kHz/s)")
        axes[1, 0].set_title(
            "C · Local CFO rate differs materially from the multi-second line",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].legend(fontsize=8.5)
        axes[1, 0].grid(True, alpha=0.3)

        target = results[0]
        frames = target["frames"]
        times = np.asarray([item["reference_time_s"] for item in frames])
        ordinary = np.asarray(
            [
                np.nan
                if item["phase_implied_frequency_error_hz"] is None
                else item["phase_implied_frequency_error_hz"]
                for item in frames
            ]
        )
        corrected = np.asarray(
            [
                np.nan
                if item["pi_corrected_phase_implied_frequency_error_hz"] is None
                else item["pi_corrected_phase_implied_frequency_error_hz"]
                for item in frames
            ]
        )
        axes[1, 1].scatter(
            (times - times[0]) * 1e3,
            ordinary,
            s=24,
            color=RED,
            alpha=0.68,
            label="ordinary adjacent phase",
        )
        axes[1, 1].plot(
            (times - times[0]) * 1e3,
            corrected,
            marker="o",
            markersize=3,
            linewidth=1.0,
            color=GREEN,
            label="after binary π correction",
        )
        axes[1, 1].axhline(0, color=INK, linewidth=0.8)
        axes[1, 1].set_xlabel("time from target interval start (ms)")
        axes[1, 1].set_ylabel("phase-implied CFO residual (Hz)")
        axes[1, 1].set_title(
            "D · The attached CFO bands are the π-transition classes", loc="left", fontweight="bold"
        )
        axes[1, 1].legend(fontsize=8.5)
        axes[1, 1].grid(True, alpha=0.3)

        for axis in axes[0]:
            axis.set_xticks(x, labels, rotation=25, ha="right")
        figure.suptitle(
            "Sub-second Qin pilot structure across independent raw-IQ dwells",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def _plot_cfo_holdout(
    existing_path: Path,
    metrics: dict[str, Any],
    output: Path,
) -> None:
    document = _load_json(existing_path)
    frames = [
        item
        for item in document["dense_tracking"]["frames"]
        if item["frequency_update_applied"] and item["coherence_margin"] > 0
    ]
    times = np.asarray([item["reference_time_s"] for item in frames])
    measured = np.asarray([item["absolute_cfo_measurement_hz"] for item in frames])
    model = np.asarray([item["model_cfo_hz"] for item in frames])
    uncertainty = np.asarray([item["frequency_uncertainty_hz"] for item in frames])
    coherence = np.asarray([item["exact_coherence"] for item in frames])
    residual = measured - model
    indices = np.arange(len(frames))
    train = indices % 2 == 0
    prediction = _weighted_local_linear_prediction(
        times[train],
        residual[train],
        coherence[train] / np.maximum(uncertainty[train], 5.0) ** 2,
        times,
        bandwidth_s=0.010,
    )
    interleaved = metrics["interleaved_local_linear"]
    blocks = metrics["contiguous_block_holdout"]
    forward = metrics["forward_local_linear"]
    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 180}):
        figure, axes = plt.subplots(2, 2, figsize=(14.2, 9.0), constrained_layout=True)
        axes[0, 0].scatter(
            times, residual, s=9, color=BLUE, alpha=0.32, label="independent frame CFO"
        )
        order = np.argsort(times)
        axes[0, 0].plot(
            times[order],
            prediction[order],
            color=AMBER,
            linewidth=1.1,
            label="10 ms local-linear smoother",
        )
        axes[0, 0].axhline(0, color=INK, linewidth=0.7)
        axes[0, 0].set_xlabel("capture time (s)")
        axes[0, 0].set_ylabel("CFO residual vs frozen model (Hz)")
        axes[0, 0].set_title(
            "A · Sub-second residual structure is smooth locally, not globally",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend(fontsize=8.5)
        axes[0, 0].grid(True, alpha=0.3)

        axes[0, 1].plot(
            [item["bandwidth_ms"] for item in interleaved],
            [item["rms_hz"] for item in interleaved],
            marker="o",
            color=GREEN,
        )
        axes[0, 1].axhline(
            metrics["median_reported_frame_uncertainty_hz"],
            color=INK,
            linestyle="--",
            label="median frame uncertainty",
        )
        axes[0, 1].set_xscale("log")
        axes[0, 1].set_xlabel("local smoother bandwidth (ms, log scale)")
        axes[0, 1].set_ylabel("interleaved held-out RMS (Hz)")
        axes[0, 1].set_title(
            "B · 5–20 ms bandwidth reaches the measurement floor", loc="left", fontweight="bold"
        )
        axes[0, 1].legend(fontsize=8.5)
        axes[0, 1].grid(True, alpha=0.3)

        axes[1, 0].plot(
            [item["heldout_block_ms"] for item in blocks],
            [item["rms_hz"] for item in blocks],
            marker="o",
            color=RED,
        )
        axes[1, 0].set_xlabel("contiguous omitted interval (ms)")
        axes[1, 0].set_ylabel("10 ms smoother held-out RMS (Hz)")
        axes[1, 0].set_title(
            "C · Recovery degrades as an actual time hole approaches 50 ms",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].grid(True, alpha=0.3)

        axes[1, 1].plot(
            [item["history_ms"] for item in forward],
            [item["rms_hz"] for item in forward],
            marker="o",
            color=BLUE,
        )
        axes[1, 1].set_xscale("log")
        axes[1, 1].set_xlabel("trailing history used (ms, log scale)")
        axes[1, 1].set_ylabel("forward one-frame RMS (Hz)")
        axes[1, 1].set_title(
            "D · A 20–50 ms local state predicts the next frame best", loc="left", fontweight="bold"
        )
        axes[1, 1].grid(True, alpha=0.3)
        figure.suptitle(
            "Held-out test of a structure-aware local CFO state", fontsize=15, fontweight="bold"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def _plot_target_screens(results: list[dict[str, Any]], output: Path) -> None:
    labels = [f"{item['requested_start_s']:.2f} s" for item in results]
    x = np.arange(len(results))
    ordinary = np.asarray([item["cubic_batch_phase_residual_rms_rad"] for item in results])
    corrected = np.asarray([item["pi_ambiguity_batch_phase_residual_rms_rad"] for item in results])
    transitions = np.asarray([item["binary_state"]["transition_fraction"] for item in results])
    frozen_rate = np.asarray([item["local_rate"]["frozen_model_rate_hz_s"] for item in results])
    local_rate = np.asarray([item["local_rate"]["within_frame_cfo_rate_hz_s"] for item in results])
    phase_rate = np.asarray([item["local_rate"]["phase_supported_rate_hz_s"] for item in results])
    maximum_frames = max(len(item["frames"]) for item in results)
    state_image = np.full((len(results), maximum_frames), np.nan)
    for row, item in enumerate(results):
        bits = np.asarray([frame["pi_ambiguity_state"] for frame in item["frames"]])
        state_image[row, : len(bits)] = bits

    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 180}):
        figure, axes = plt.subplots(2, 2, figsize=(14.2, 8.8), constrained_layout=True)
        image = axes[0, 0].imshow(
            state_image,
            aspect="auto",
            interpolation="nearest",
            cmap="coolwarm",
            vmin=0,
            vmax=1,
        )
        axes[0, 0].set_yticks(np.arange(len(labels)), labels)
        axes[0, 0].set_xlabel("frame index within 80 ms interval")
        axes[0, 0].set_title(
            "A · Binary π sequences change form between nearby intervals",
            loc="left",
            fontweight="bold",
        )
        figure.colorbar(image, ax=axes[0, 0], ticks=(0, 1), label="binary phase state")

        axes[0, 1].bar(x - 0.18, ordinary, width=0.36, color=GRAY, label="ordinary 2π")
        axes[0, 1].bar(x + 0.18, corrected, width=0.36, color=GREEN, label="binary-π-aware")
        axes[0, 1].set_xticks(x, labels, rotation=25, ha="right")
        axes[0, 1].set_ylabel("phase residual RMS (rad)")
        axes[0, 1].set_title(
            "B · Phase doubling recovers coherence in all five screens",
            loc="left",
            fontweight="bold",
        )
        axes[0, 1].legend(fontsize=8.5)
        axes[0, 1].grid(True, axis="y", alpha=0.3)

        axes[1, 0].bar(x, transitions, color=AMBER)
        axes[1, 0].set_xticks(x, labels, rotation=25, ha="right")
        axes[1, 0].set_ylabel("fraction of adjacent frames changing π state")
        axes[1, 0].set_ylim(0, 1)
        axes[1, 0].set_title(
            "C · There is no single lock/unlock or fixed-rate phase cadence",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].grid(True, axis="y", alpha=0.3)

        axes[1, 1].plot(x, frozen_rate / 1_000, marker="o", color=INK, label="frozen rate")
        axes[1, 1].plot(x, local_rate / 1_000, marker="o", color=BLUE, label="local CFO rate")
        axes[1, 1].plot(
            x,
            phase_rate / 1_000,
            marker="x",
            linestyle="none",
            color=GREEN,
            label="π-aware phase rate",
        )
        axes[1, 1].set_xticks(x, labels, rotation=25, ha="right")
        axes[1, 1].set_ylabel("CFO rate (kHz/s)")
        axes[1, 1].set_title(
            "D · Phase independently supports the interval-local CFO slope",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].legend(fontsize=8.5)
        axes[1, 1].grid(True, alpha=0.3)
        figure.suptitle(
            "Five raw-lattice screens inside the original dwell",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def _plot_frequency_runs(metrics: dict[str, Any], output: Path) -> None:
    rows = metrics["runs"]
    run_id = np.asarray([item["run_id"] for item in rows])
    center_time = np.asarray([item["center_time_s"] for item in rows])
    rate = np.asarray([item["residual_rate_hz_s"] for item in rows])
    rms = np.asarray([item["fit_rms_hz"] for item in rows])
    span = np.asarray([item["span_ms"] for item in rows])
    bias = np.asarray([item["center_residual_hz"] for item in rows])
    jump = np.asarray(
        [
            np.nan
            if item["next_run_residual_jump_hz"] is None
            else item["next_run_residual_jump_hz"]
            for item in rows
        ]
    )
    with plt.rc_context({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 180}):
        figure, axes = plt.subplots(2, 2, figsize=(14.2, 8.8), constrained_layout=True)
        axes[0, 0].bar(run_id, rate / 1_000, color=BLUE)
        axes[0, 0].axhline(
            metrics["median_residual_rate_hz_s"] / 1_000,
            color=RED,
            linestyle="--",
            label=f"median {metrics['median_residual_rate_hz_s'] / 1_000:+.2f} kHz/s",
        )
        axes[0, 0].set_xlabel("contiguous frequency-update run")
        axes[0, 0].set_ylabel("local rate minus frozen rate (kHz/s)")
        axes[0, 0].set_title(
            "A · Most runs share a repeatable positive residual slope",
            loc="left",
            fontweight="bold",
        )
        axes[0, 0].legend(fontsize=8.5)
        axes[0, 0].grid(True, axis="y", alpha=0.3)

        scatter = axes[0, 1].scatter(span, rms, c=rate, cmap="coolwarm", s=38)
        axes[0, 1].set_xlabel("observed run span (ms)")
        axes[0, 1].set_ylabel("within-run line residual RMS (Hz)")
        axes[0, 1].set_title(
            "B · High-RMS runs are mixtures, not evidence for one smooth line",
            loc="left",
            fontweight="bold",
        )
        figure.colorbar(scatter, ax=axes[0, 1], label="residual rate (Hz/s)")
        axes[0, 1].grid(True, alpha=0.3)

        axes[1, 0].scatter(center_time, bias, s=30, color=AMBER)
        axes[1, 0].plot(center_time, bias, linewidth=0.8, color=AMBER, alpha=0.7)
        axes[1, 0].axhline(0, color=INK, linewidth=0.7)
        axes[1, 0].set_xlabel("capture time (s)")
        axes[1, 0].set_ylabel("run-center CFO residual (Hz)")
        axes[1, 0].set_title(
            "C · Slow ramps are repeatedly relieved by discrete bias changes",
            loc="left",
            fontweight="bold",
        )
        axes[1, 0].grid(True, alpha=0.3)

        axes[1, 1].bar(run_id[:-1], jump[:-1], color=np.where(jump[:-1] < 0, RED, GREEN))
        axes[1, 1].axhline(0, color=INK, linewidth=0.7)
        axes[1, 1].set_xlabel("run preceding the estimated discontinuity")
        axes[1, 1].set_ylabel("next-run residual jump (Hz)")
        axes[1, 1].set_title(
            "D · Treat jumps as nuisance states, not accumulated range",
            loc="left",
            fontweight="bold",
        )
        axes[1, 1].grid(True, axis="y", alpha=0.3)
        figure.suptitle(
            "All 34 contiguous frequency-update runs in the original dwell",
            fontsize=15,
            fontweight="bold",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, bbox_inches="tight")
        plt.close(figure)


def main() -> int:
    args = _arguments()
    if not math.isfinite(args.interval_ms) or not 40 <= args.interval_ms <= 250:
        raise ValueError("interval-ms must be finite and between 40 and 250")
    evidence = _load_json(args.five_dwell_evidence)
    results = [_existing_target(args.existing_detail)]
    pinned = PinnedLocalRoot(args.bulk_root)
    store: RecordingStore | None = None
    target_screens: list[dict[str, Any]] = []
    try:
        store = RecordingStore.open_pinned(pinned)
        for dwell in evidence["dwells"]:
            source_choices = []
            for source in dwell["pilot_scan_sources"]:
                scan_path = _path_from_bulk_uri(source["uri"], args.bulk_root)
                try:
                    _trajectory, anchor, _scan = _select_carrier_and_anchor(scan_path.parent)
                except (FileNotFoundError, ValueError):
                    continue
                source_choices.append((float(anchor["margin"]), source, scan_path.parent))
            for _margin, source, analysis_root in sorted(source_choices, reverse=True):
                stream_id, receiver_name = str(source["path"]).split("/")
                receiver_id = int(receiver_name.removeprefix("RX"))
                try:
                    result = _audit_dwell(
                        store,
                        session_id=str(dwell["session_id"]),
                        stream_id=stream_id,
                        receiver_id=receiver_id,
                        edge=StarlinkEdge.UPPER,
                        analysis_root=analysis_root,
                        interval_s=args.interval_ms / 1_000,
                    )
                except ValueError:
                    continue
                results.append(result)
                break
        target_screens = _audit_target_intervals(
            store,
            existing_path=args.existing_detail,
            interval_s=args.interval_ms / 1_000,
        )
    finally:
        if store is not None:
            store.close()
    for result in [*results, *target_screens]:
        result["binary_state"] = _state_period_metrics(result["frames"])
        result["frequency_modes"] = _frequency_mode_metrics(result["frames"])
        result["local_rate"] = _local_rate_metrics(result["frames"])
        local_rate = result["local_rate"]
        result["phase_rate_qualified"] = bool(
            local_rate["quality_fraction"] >= 0.75
            and local_rate["reconstructed_phase_residual_rms_rad"] is not None
            and local_rate["reconstructed_phase_residual_rms_rad"] <= 0.35
            and max(
                result["even_to_odd_heldout_phase_residual_rms_rad"],
                result["odd_to_even_heldout_phase_residual_rms_rad"],
            )
            <= 0.35
        )
    cfo_holdout = _cfo_holdout_metrics(args.existing_detail)
    frequency_runs = _frequency_run_metrics(args.existing_detail)
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": "org.leo.research.subsecond-pilot-structure/v1",
        "candidate_only": True,
        "payload_decoded": False,
        "interval_ms": args.interval_ms,
        "dwell_count": len(results),
        "target_cfo_holdout": cfo_holdout,
        "target_frequency_runs": frequency_runs,
        "target_interval_screens": target_screens,
        "results": results,
    }
    (output_root / "subsecond-pilot-structure.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _plot(results, output_root / "subsecond-pilot-structure.png")
    _plot_cfo_holdout(
        args.existing_detail,
        cfo_holdout,
        output_root / "structure-aware-cfo-holdout.png",
    )
    _plot_target_screens(
        target_screens,
        output_root / "target-interval-phase-cadence.png",
    )
    _plot_frequency_runs(
        frequency_runs,
        output_root / "all-frequency-run-structure.png",
    )
    print(json.dumps({"dwell_count": len(results), "output_root": str(output_root)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
