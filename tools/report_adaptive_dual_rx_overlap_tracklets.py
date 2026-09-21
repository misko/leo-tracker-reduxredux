#!/usr/bin/env python3
"""Recover source-specific dual-RX phase on phase-blind overlap tracklets."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from report_adaptive_dual_rx_raw_coherence import (  # noqa: E402
    coherence_at,
    cross_ambiguity_peak,
)

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (  # noqa: E402
    DualReceiverPhaseObservation,
    ReceiverPhaseSeed,
    extract_dual_receiver_phase_with_offset_authority,
)
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs  # noqa: E402
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis  # noqa: E402
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402


@dataclass(frozen=True, slots=True)
class TrackWindow:
    track_id: str
    target_index: int
    first_visit: int
    last_visit: int
    retained_visits: int


TRACK_WINDOWS = (
    TrackWindow("lower-target-1", 1, 2140, 2238, 7),
    TrackWindow("lower-target-2", 2, 2140, 2205, 7),
    TrackWindow("lower-target-3", 3, 2214, 2320, 6),
)
OFFSET_CENTER_HZ = -677_000.0
OFFSET_GATE_HZ = 2_000.0
WRONG_OFFSET_HZ = 50_000.0
WRONG_TIME_SHIFT_SAMPLES = 997
BOOTSTRAP_REPLICATES = 2_000


def _phase_error(left: float, right: float) -> float:
    return float(np.angle(np.exp(1j * (left - right))))


def _series_arrays(observation: DualReceiverPhaseObservation) -> tuple[np.ndarray, ...]:
    frame_starts = np.asarray(observation.receivers[0].frame_starts, dtype=float)
    receiver0 = np.asarray(observation.receivers[0].frame_phasors)
    receiver1 = np.asarray(observation.receivers[1].frame_phasors)
    product = receiver1 * np.conj(receiver0)
    weights = np.sqrt(
        np.maximum(abs(receiver0), np.finfo(float).tiny)
        * np.maximum(abs(receiver1), np.finfo(float).tiny)
    )
    return frame_starts, product, weights


def phase_subset_at_reference(
    observation: DualReceiverPhaseObservation,
    receiver_offset_authority_hz: float,
    sample_rate_hz: float,
    indexes: np.ndarray,
) -> float:
    """Evaluate a frame subset at the full observation's fixed center epoch."""
    starts, product, weights = _series_arrays(observation)
    residual_hz = observation.relative_frequency_hz - receiver_offset_authority_hz
    centered_s = (starts - observation.center_sample) / sample_rate_hz
    derotated = product * np.exp(-2j * np.pi * residual_hz * centered_s)
    full = np.angle(np.sum(weights * derotated))
    subset = np.angle(np.sum(weights[indexes] * derotated[indexes]))
    return float(np.angle(np.exp(1j * (observation.wrapped_phase_rad + subset - full))))


def block_bootstrap_phase(
    observation: DualReceiverPhaseObservation,
    receiver_offset_authority_hz: float,
    sample_rate_hz: float,
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
    block_frames: int = 3,
) -> dict[str, float]:
    """Circular moving-block bootstrap conditional on the recovered CFO branch."""
    starts, product, weights = _series_arrays(observation)
    count = len(starts)
    if count < 2 * block_frames or replicates < 100:
        raise ValueError("insufficient frames or bootstrap replicates")
    residual_hz = observation.relative_frequency_hz - receiver_offset_authority_hz
    centered_s = (starts - observation.center_sample) / sample_rate_hz
    derotated = product * np.exp(-2j * np.pi * residual_hz * centered_s)
    nominal = np.angle(np.sum(weights * derotated))
    rng = np.random.default_rng(seed)
    errors = np.empty(replicates)
    maximum_start = count - block_frames
    blocks_needed = math.ceil(count / block_frames)
    for replicate in range(replicates):
        block_starts = rng.integers(0, maximum_start + 1, blocks_needed)
        indexes = np.concatenate(
            [np.arange(start, start + block_frames) for start in block_starts]
        )[:count]
        phase = np.angle(np.sum(weights[indexes] * derotated[indexes]))
        errors[replicate] = _phase_error(phase, nominal)
    return {
        "block_frames": block_frames,
        "replicates": replicates,
        "conditional_standard_error_deg": math.degrees(float(np.std(errors, ddof=1))),
        "conditional_95_interval_low_deg": math.degrees(float(np.quantile(errors, 0.025))),
        "conditional_95_interval_high_deg": math.degrees(float(np.quantile(errors, 0.975))),
    }


def _candidate_row(track: TrackWindow, visit: Any, pair: Any) -> dict[str, Any]:
    left, right, receiver_offset_hz, probe_start_samples = pair
    return {
        "track_id": track.track_id,
        "visit_index": visit.visit_index,
        "target_index": visit.target_index,
        "edge": visit.target.edge.value,
        "phase_blind_quality": min(left.fractional_margin, right.fractional_margin),
        "rx0_tracking_cfo_hz": left.fractional_tracking_cfo_hz,
        "rx1_tracking_cfo_hz": right.fractional_tracking_cfo_hz,
        "tracking_receiver_offset_hz": receiver_offset_hz,
        "probe_start_samples": probe_start_samples,
        "left": left,
        "right": right,
        "visit": visit,
    }


def select_tracklets(job: Any) -> list[dict[str, Any]]:
    """Select top overlap candidates using GLRT timing/quality and frequency only."""
    candidates: dict[str, list[dict[str, Any]]] = {row.track_id: [] for row in TRACK_WINDOWS}
    for index in job.completed_visits():
        matching = [row for row in TRACK_WINDOWS if row.first_visit <= index <= row.last_visit]
        if not matching:
            continue
        visit = job.read_visit(index)
        for track in matching:
            if visit.target_index != track.target_index or visit.target.edge.value != "lower":
                continue
            for pair in _phase_blind_pairs(visit):
                if abs(pair[2] - OFFSET_CENTER_HZ) <= OFFSET_GATE_HZ:
                    candidates[track.track_id].append(_candidate_row(track, visit, pair))
    selected = []
    for track in TRACK_WINDOWS:
        ordered = sorted(
            candidates[track.track_id],
            key=lambda row: (-row["phase_blind_quality"], row["visit_index"]),
        )
        selected.extend(ordered[: track.retained_visits])
    if len(selected) != sum(row.retained_visits for row in TRACK_WINDOWS):
        raise ValueError("phase-blind overlap selection did not fill its bounded cohort")
    return selected


def _extract(
    iq: np.ndarray,
    selected: dict[str, Any],
    authority_hz: float,
) -> tuple[DualReceiverPhaseObservation, tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]]:
    visit = selected["visit"]
    left, right = selected["left"], selected["right"]
    probe_start = selected["probe_start_samples"]
    references = (
        probe_start + left.integer_epoch_sample + left.fractional_epoch_offset_samples,
        probe_start + right.integer_epoch_sample + right.fractional_epoch_offset_samples,
    )
    seeds = (
        ReceiverPhaseSeed(left.acquired_cfo_hz, references[0]),
        ReceiverPhaseSeed(right.acquired_cfo_hz, references[1]),
    )
    result = extract_dual_receiver_phase_with_offset_authority(
        iq,
        visit.configuration.sample_rate_hz,
        visit.target.edge,
        probe_start + left.integer_epoch_sample,
        seeds,
        authority_hz,
        common_reference_sample=references[0],
    )
    return result.observation, seeds


def _quality(observation: DualReceiverPhaseObservation) -> dict[str, float]:
    return {
        "resultant": observation.resultant_length,
        "exact_to_control_floor": min(
            row.exact_to_control_power_ratio for row in observation.receivers
        ),
        "phase_standard_error_deg": observation.phase_standard_error_deg,
        "relative_frequency_standard_error_hz": (observation.relative_frequency_standard_error_hz),
    }


def _control_observation(
    iq: np.ndarray,
    selected: dict[str, Any],
    authority_hz: float,
) -> dict[str, Any]:
    try:
        observation, _ = _extract(iq, selected, authority_hz)
    except (ValueError, ArithmeticError) as error:
        return {"state": "unavailable", "reason": str(error)}
    return {"state": "measured", **_quality(observation)}


def analyze_selected(iq: np.ndarray, selected: dict[str, Any]) -> dict[str, Any]:
    visit = selected["visit"]
    rate = visit.configuration.sample_rate_hz
    midpoint = len(iq) // 2
    train = cross_ambiguity_peak(iq[:midpoint], rate, maximum_delay_samples=4)
    held = cross_ambiguity_peak(iq[midpoint:], rate, maximum_delay_samples=4)
    if train.delay_samples != 0:
        return {
            "state": "unavailable",
            "reason": "nonzero_raw_receiver_delay_not_applied",
            "train_authority": asdict(train),
            "held_authority": asdict(held),
        }
    observation, _ = _extract(iq, selected, train.frequency_hz)
    starts, product, weights = _series_arrays(observation)
    count = len(starts)
    first = np.arange(0, count // 2)
    second = np.arange(count // 2, count)
    first_phase = phase_subset_at_reference(observation, train.frequency_hz, rate, first)
    second_phase = phase_subset_at_reference(observation, train.frequency_hz, rate, second)
    origin_s = (visit.valid_start_counter - visit.source_origin_counter) / rate
    residual_hz = observation.relative_frequency_hz - train.frequency_hz
    centered_s = (starts - observation.center_sample) / rate
    derotated = product * np.exp(-2j * np.pi * residual_hz * centered_s)
    full_correlation_phase = np.angle(np.sum(weights * derotated))
    frame_rows = []
    for start, value, weight in zip(starts, derotated, weights, strict=True):
        deviation = _phase_error(float(np.angle(value)), float(full_correlation_phase))
        physical_phase = (
            observation.wrapped_phase_rad
            + 2
            * np.pi
            * observation.relative_frequency_hz
            * (start - observation.center_sample)
            / rate
            + deviation
        )
        frame_rows.append(
            {
                "session_time_s": origin_s + start / rate,
                "source_baseband_frequency_hz": selected["rx0_tracking_cfo_hz"],
                "rx1_conjugate_rx0_real": math.cos(physical_phase),
                "rx1_conjugate_rx0_imag": math.sin(physical_phase),
                "weight": float(weight),
            }
        )
    wrong_time = np.zeros_like(iq)
    wrong_time[:, 0] = iq[:, 0]
    wrong_time[WRONG_TIME_SHIFT_SAMPLES:, 1] = iq[:-WRONG_TIME_SHIFT_SAMPLES, 1]
    wrong_time[:WRONG_TIME_SHIFT_SAMPLES, 1] = 0
    nominal_quality = _quality(observation)
    wrong_offset = _control_observation(iq, selected, train.frequency_hz + WRONG_OFFSET_HZ)
    wrong_time_result = _control_observation(wrong_time, selected, train.frequency_hz)
    held_coherence = coherence_at(iq[midpoint:], rate, train.frequency_hz, train.delay_samples)
    wrong_time_coherence = coherence_at(
        np.column_stack((iq[midpoint:, 0], np.roll(iq[midpoint:, 1], 5000))),
        rate,
        train.frequency_hz,
        train.delay_samples,
    )
    gate = (
        nominal_quality["resultant"] >= 0.5
        and nominal_quality["exact_to_control_floor"] >= 2.0
        and (
            wrong_time_result["state"] != "measured"
            or nominal_quality["exact_to_control_floor"]
            >= 2 * wrong_time_result["exact_to_control_floor"]
        )
    )
    return {
        "state": "qualified_shared_source" if gate else "insufficient_shared_source_control",
        "train_authority": asdict(train),
        "held_authority": asdict(held),
        "train_held_frequency_difference_hz": held.frequency_hz - train.frequency_hz,
        "held_authority_coherence": held_coherence,
        "wrong_time_broadband_coherence": wrong_time_coherence,
        "source_phase_reference": "correlation_energy_centroid",
        "source_phase_session_time_s": origin_s + observation.center_sample / rate,
        "wrapped_rx1_minus_rx0_phase_deg": math.degrees(observation.wrapped_phase_rad),
        "relative_frequency_hz": observation.relative_frequency_hz,
        "quality": nominal_quality,
        "first_frame_half_phase_at_reference_deg": math.degrees(first_phase),
        "second_frame_half_phase_at_reference_deg": math.degrees(second_phase),
        "frame_half_disagreement_deg": math.degrees(_phase_error(second_phase, first_phase)),
        "bootstrap": block_bootstrap_phase(
            observation,
            train.frequency_hz,
            rate,
            seed=20260921 + selected["visit_index"],
        ),
        "frequency_seed_shift_sensitivity": wrong_offset,
        "frequency_seed_shift_used_as_gate": False,
        "wrong_time_control": wrong_time_result,
        "frame_transfers": frame_rows,
        "identifiability": "combined_geometry_instrument_and_channel_modulo_2pi",
        "absolute_phase_gauge_calibrated": False,
        "satellite_catalog_identity_claimed": False,
    }


def run(bulk_root: Path, session_id: str) -> dict[str, Any]:
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(bulk_root, read_only=True)
    try:
        inspected = captures.inspect(session_id)
        binding = bind_actual_visit_analysis(
            inspected.manifest.receipt,
            input_manifest_sha256=inspected.manifest_sha256,
            probe_stride_ms=120,
        )
        rows = []
        with analyses.job(binding) as job:
            selected = select_tracklets(job)
            with AdaptiveHopAnalysisInputStore(captures).source(session_id) as source:
                for item in selected:
                    evidence = analyze_selected(source.read_visit(item["visit_index"]), item)
                    rows.append(
                        {
                            key: value
                            for key, value in item.items()
                            if key not in ("left", "right", "visit")
                        }
                        | {"phase": evidence}
                    )
        document = {
            "schema_version": 1,
            "kind": "adaptive_dual_rx_overlap_tracklet_phase_research",
            "session_id": session_id,
            "input_manifest_sha256": inspected.manifest_sha256,
            "glrt_binding_sha256": binding.sha256,
            "selection_uses_phase": False,
            "maximum_iq_visits": 20,
            "track_windows": [asdict(row) for row in TRACK_WINDOWS],
            "tracking_receiver_offset_gate_hz": [
                OFFSET_CENTER_HZ - OFFSET_GATE_HZ,
                OFFSET_CENTER_HZ + OFFSET_GATE_HZ,
            ],
            "wrong_offset_hz": WRONG_OFFSET_HZ,
            "wrong_time_shift_samples": WRONG_TIME_SHIFT_SAMPLES,
            "rows": rows,
        }
        document["evidence_sha256"] = sha256_digest(canonical_json_bytes(document))
        return document
    finally:
        analyses.close()
        captures.close()


def render(document: dict[str, Any], output: Path) -> None:
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), layout="constrained")
    colors = {
        track.track_id: color
        for track, color in zip(TRACK_WINDOWS, ("C0", "C1", "C2"), strict=True)
    }
    for track in TRACK_WINDOWS:
        rows = sorted(
            [row for row in document["rows"] if row["track_id"] == track.track_id],
            key=lambda row: row["phase"].get("source_phase_session_time_s", math.inf),
        )
        qualified = [row for row in rows if row["phase"]["state"] == "qualified_shared_source"]
        rejected = [row for row in rows if row["phase"]["state"] != "qualified_shared_source"]
        if qualified:
            time = [row["phase"]["source_phase_session_time_s"] for row in qualified]
            phase = [row["phase"]["wrapped_rx1_minus_rx0_phase_deg"] for row in qualified]
            error = [
                row["phase"]["bootstrap"]["conditional_standard_error_deg"] for row in qualified
            ]
            axes[0].errorbar(
                time, phase, yerr=error, fmt="o", color=colors[track.track_id], label=track.track_id
            )
            axes[1].plot(
                time,
                [row["phase"]["frame_half_disagreement_deg"] for row in qualified],
                "o-",
                color=colors[track.track_id],
                label=track.track_id,
            )
        if rejected:
            axes[0].scatter(
                [row["visit_index"] for row in rejected],
                [0] * len(rejected),
                marker="x",
                color=colors[track.track_id],
            )
    axes[0].set_ylabel("RX1−RX0 phase (deg)\nwrapped 360°")
    axes[0].set_xlabel("source support time (s)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("second−first frame-half phase (deg)")
    axes[1].set_xlabel("source support time (s)")
    axes[1].grid(alpha=0.25)
    tracks = [track.track_id for track in TRACK_WINDOWS]
    qualified_counts = [
        sum(
            row["track_id"] == track and row["phase"]["state"] == "qualified_shared_source"
            for row in document["rows"]
        )
        for track in tracks
    ]
    axes[2].bar(tracks, qualified_counts)
    axes[2].set_ylabel("qualified visits")
    axes[2].set_ylim(0, max(track.retained_visits for track in TRACK_WINDOWS) + 1)
    axes[2].tick_params(axis="x", rotation=15)
    figure.suptitle(f"{document['session_id']} source-specific overlap phase")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(args.bulk_root, args.session_id)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(
        json.dumps(
            {
                "evidence_sha256": document["evidence_sha256"],
                "selected_visits": len(document["rows"]),
                "qualified_visits": sum(
                    row["phase"]["state"] == "qualified_shared_source" for row in document["rows"]
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
