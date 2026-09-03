"""Retune-bounded pilot phase and Doppler-rate analysis for scanner IQ."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np

from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfig,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.starlink.local_doppler import (
    complete_lattice_count,
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.scanner.analysis_models import (
    ScannerAnalysisMetricsV1,
    ScannerGlrt64CandidateMetricsV1,
    ScannerPilotDopplerConfigV1,
    ScannerPilotDopplerSegmentsV1,
    ScannerPilotDopplerSegmentV1,
    ScannerPilotFrameStateV1,
    ScannerPilotReceiverPairV1,
)

if TYPE_CHECKING:
    from leo.scanner.standard_analysis import SegmentedScannerSource


@dataclass(frozen=True, slots=True)
class _Hit:
    receiver_id: int
    probe_index: int
    probe_start_ms: int
    candidate: ScannerGlrt64CandidateMetricsV1


@dataclass(frozen=True, slots=True)
class _ConfirmedSeed:
    source: _Hit
    confirmation: _Hit


def build_scanner_pilot_doppler_segments(
    source: SegmentedScannerSource,
    metrics: ScannerAnalysisMetricsV1,
    *,
    config: ScannerPilotDopplerConfigV1 | None = None,
    fractional_epoch_offsets: Mapping[tuple[int, int, int, int], float] | None = None,
) -> ScannerPilotDopplerSegmentsV1:
    """Track complete pilot frames without crossing a scanner retune boundary."""

    resolved = config or ScannerPilotDopplerConfigV1()
    if source.scan_id != metrics.scan_id or source.configuration != metrics.configuration:
        raise ValueError("scanner pilot source and GLRT metrics disagree")
    metrics_sha256 = sha256_digest(canonical_json_bytes(metrics.model_dump(mode="json")))
    segments: list[ScannerPilotDopplerSegmentV1] = []
    confirmed_count = 0
    unavailable_count = 0
    preferred_count = 0
    fallback_count = 0
    for source_frame, metrics_frame in zip(source.frames, metrics.frames, strict=True):
        if source_frame.samples is None or metrics_frame.status == "failed":
            continue
        seeds = _confirmed_receiver_seeds(metrics_frame.probes, resolved)
        confirmed_count += len(seeds)
        for seed in seeds[: resolved.maximum_segments_per_frame]:
            duration_samples = _window_samples(
                source.configuration.dwell_samples,
                source.configuration.sample_rate_hz,
                seed.source.probe_start_ms,
                resolved,
            )
            if duration_samples is None:
                unavailable_count += 1
                continue
            if duration_samples == round(
                resolved.preferred_window_duration_s * source.configuration.sample_rate_hz
            ):
                preferred_count += 1
            else:
                fallback_count += 1
            segment = _analyze_segment(
                source_frame.samples,
                sample_rate_hz=source.configuration.sample_rate_hz,
                receiver_index=source.configuration.receiver_ids.index(seed.source.receiver_id),
                target_index=source_frame.target_index,
                target=source_frame.target,
                seed=seed,
                duration_samples=duration_samples,
                config=resolved,
                segment_index=len(segments),
                fractional_epoch_offset_samples=(
                    0.0
                    if fractional_epoch_offsets is None
                    else fractional_epoch_offsets.get(
                        (
                            source_frame.target_index,
                            seed.source.receiver_id,
                            seed.source.probe_index,
                            seed.source.candidate.candidate_rank,
                        ),
                        0.0,
                    )
                ),
            )
            segments.append(segment)
        unavailable_count += max(0, len(seeds) - resolved.maximum_segments_per_frame)

    pairs = _receiver_pairs(tuple(segments))
    qualified_count = sum(item.qualified for item in segments)
    if qualified_count == len(segments) and confirmed_count == len(segments) and segments:
        status = StandardScientificStatus.COMPLETE
        reason = "every acquisition-confirmed receiver track produced a qualified local segment"
    elif qualified_count:
        status = StandardScientificStatus.PARTIAL
        reason = "some acquisition-confirmed local pilot segments passed every qualification gate"
    elif segments:
        status = StandardScientificStatus.INSUFFICIENT_DATA
        reason = "local pilot segments were measured but none passed every qualification gate"
    elif confirmed_count:
        status = StandardScientificStatus.INSUFFICIENT_DATA
        reason = "confirmed GLRT tracks did not leave a complete 50 ms pilot window"
    else:
        status = StandardScientificStatus.NO_RESULT
        reason = "no receiver supplied a non-overlapping CFO-consistent GLRT confirmation pair"
    body: dict[str, Any] = {
        "scan_id": source.scan_id,
        "input_uri": source.input_uri,
        "input_manifest_sha256": source.input_manifest_sha256,
        "scanner_metrics_sha256": metrics_sha256,
        "config": resolved.model_dump(mode="json"),
        "config_digest": canonical_digest(resolved.model_dump(mode="json")),
        "source_frame_count": len(source.frames),
        "confirmed_receiver_track_count": confirmed_count,
        "analyzed_segment_count": len(segments),
        "unavailable_segment_count": unavailable_count,
        "qualified_segment_count": qualified_count,
        "preferred_window_segment_count": preferred_count,
        "fallback_window_segment_count": fallback_count,
        "segments": [stable_measurement_floats(item.model_dump(mode="json")) for item in segments],
        "receiver_pairs": [
            stable_measurement_floats(item.model_dump(mode="json")) for item in pairs
        ],
        "status": status,
        "reason": reason,
        "carrier_phase_period_rad": math.pi,
        "retune_boundaries_are_discontinuous": True,
        "frame_timing_is_receiver_relative": True,
        "absolute_carrier_phase_resolved": False,
        "long_baseline_trajectory_available": False,
        "range_dynamics_claimed": False,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    identity = {
        "schema_version": 1,
        "kind": "scanner.pilot-doppler-segments",
        "algorithm_version": "scanner-pilot-doppler-segments-v1",
        **body,
    }
    return ScannerPilotDopplerSegmentsV1.model_validate(
        {**body, "content_digest": canonical_digest(identity)}
    )


def _confirmed_receiver_seeds(probes, config: ScannerPilotDopplerConfigV1):
    minimum_ms = round(config.confirmation_minimum_separation_s * 1_000)
    seeds: list[_ConfirmedSeed] = []
    receiver_ids = tuple(sorted({probe.receiver_id for probe in probes}))
    for receiver_id in receiver_ids:
        history: list[_Hit] = []
        selected: _ConfirmedSeed | None = None
        receiver_probes = sorted(
            (probe for probe in probes if probe.receiver_id == receiver_id),
            key=lambda item: item.probe_index,
        )
        for probe in receiver_probes:
            hits = tuple(
                _Hit(receiver_id, probe.probe_index, probe.probe_start_ms, candidate)
                for candidate in sorted(
                    (item for item in probe.candidates if item.passed_margin_gate),
                    key=lambda item: (-item.margin, item.candidate_rank),
                )
            )
            for hit in hits:
                compatible = tuple(
                    prior
                    for prior in history
                    if hit.probe_start_ms - prior.probe_start_ms >= minimum_ms
                    and abs(hit.candidate.tracking_cfo_hz - prior.candidate.tracking_cfo_hz)
                    <= config.confirmation_cfo_gate_hz
                )
                if compatible:
                    source = min(
                        compatible,
                        key=lambda item: (
                            item.probe_index,
                            -item.candidate.margin,
                            item.candidate.candidate_rank,
                        ),
                    )
                    selected = _ConfirmedSeed(source=source, confirmation=hit)
                    break
            history.extend(hits)
            if selected is not None:
                break
        if selected is not None:
            seeds.append(selected)
    return tuple(sorted(seeds, key=lambda item: item.source.receiver_id))


def _window_samples(
    frame_samples: int,
    sample_rate_hz: int,
    source_probe_start_ms: int,
    config: ScannerPilotDopplerConfigV1,
) -> int | None:
    source_start = source_probe_start_ms * sample_rate_hz // 1_000
    remaining = frame_samples - source_start
    preferred = round(config.preferred_window_duration_s * sample_rate_hz)
    fallback = round(config.fallback_window_duration_s * sample_rate_hz)
    guard = round(config.preferred_window_capture_guard_s * sample_rate_hz)
    if frame_samples >= preferred + guard and remaining >= preferred:
        return preferred
    if remaining >= fallback:
        return fallback
    return None


def _analyze_segment(
    ci16: np.ndarray,
    *,
    sample_rate_hz: int,
    receiver_index: int,
    target_index: int,
    target,
    seed: _ConfirmedSeed,
    duration_samples: int,
    config: ScannerPilotDopplerConfigV1,
    segment_index: int,
    fractional_epoch_offset_samples: float,
) -> ScannerPilotDopplerSegmentV1:
    start_sample = seed.source.probe_start_ms * sample_rate_hz // 1_000
    stop_sample = start_sample + duration_samples
    values = ci16[start_sample:stop_sample, receiver_index]
    samples = (values[:, 0].astype(np.float64) + 1j * values[:, 1].astype(np.float64)) / 32_768.0
    result = analyze_contiguous_pilot_pnt_kalman(
        np.ascontiguousarray(samples),
        sample_rate_hz,
        epoch_sample=seed.source.candidate.epoch_sample,
        initial_absolute_cfo_hz=seed.source.candidate.tracking_cfo_hz,
        edge=target.edge,
        maximum_residual_cfo_hz=config.maximum_residual_cfo_hz,
        config=PilotPntKalmanConfig(
            phase_innovation_gate_rad=config.phase_innovation_gate_rad,
            timing_innovation_gate_sigma=config.timing_innovation_gate_sigma,
        ),
        initial_fractional_epoch_offset_samples=fractional_epoch_offset_samples,
    )
    lattice_count = complete_lattice_count(
        duration_samples,
        sample_rate_hz,
        seed.source.candidate.epoch_sample,
    )
    supported = tuple(item for item in result.frames if item.measurement_supported)
    supported_fraction = len(supported) / lattice_count if lattice_count else 0.0
    relative_times = np.asarray([item.time_s for item in supported], dtype=float)
    frequencies = np.asarray([item.absolute_cfo_measurement_hz for item in supported], dtype=float)
    fit = frequency_line(relative_times, frequencies)
    held_out_rms = interleaved_held_out_rms(relative_times, frequencies)
    window_start_s = start_sample / sample_rate_hz
    window_end_s = stop_sample / sample_rate_hz
    reference_time_s = (
        window_start_s + fit.reference_time_s
        if fit is not None
        else (window_start_s + window_end_s) / 2
    )
    local_rate = None if fit is None else fit.slope_hz_per_s
    kalman_rate = result.frames[-1].tracked_doppler_rate_hz_s if result.frames else None
    gaps = np.diff(relative_times)
    maximum_gap = float(np.max(gaps)) if gaps.size else None
    phase_rms = (
        float(math.sqrt(np.mean([item.phase_innovation_modulo_pi_rad**2 for item in supported])))
        if supported
        else None
    )
    median_margin = _median(item.coherence_margin for item in supported)
    failures: list[str] = []
    if supported_fraction < config.minimum_supported_frame_fraction:
        failures.append("supported frame coverage below threshold")
    if maximum_gap is None or maximum_gap > config.maximum_supported_frame_gap_s:
        failures.append("supported frame gap exceeds threshold")
    if not result.phase_lock_qualified:
        failures.append("modulo-pi phase lock did not qualify")
    if median_margin is None or median_margin < config.minimum_median_coherence_margin:
        failures.append("exact-versus-control coherence margin below threshold")
    if fit is None:
        failures.append("too few supported frames for a local frequency line")
    elif fit.residual_rms_hz > config.maximum_frequency_line_rms_hz:
        failures.append("local frequency-line RMS exceeds threshold")
    if held_out_rms is None:
        failures.append("too few supported frames for interleaved held-out prediction")
    elif held_out_rms > config.maximum_held_out_frequency_rms_hz:
        failures.append("held-out local frequency prediction RMS exceeds threshold")
    disagreement = None if local_rate is None or kalman_rate is None else local_rate - kalman_rate
    if (
        disagreement is None
        or abs(disagreement) > config.maximum_local_kalman_rate_disagreement_hz_s
    ):
        failures.append("local-line and Kalman Doppler rates disagree")

    frames = tuple(
        ScannerPilotFrameStateV1(
            frame_index=item.frame_index,
            time_since_retune_s=window_start_s + item.time_s,
            exact_coherence=item.exact_coherence,
            control_coherence=item.control_coherence,
            coherence_margin=item.coherence_margin,
            measurement_supported=item.measurement_supported,
            phase_innovation_modulo_pi_rad=item.phase_innovation_modulo_pi_rad,
            phase_ambiguity_bit=cast(Literal[0, 1], item.phase_ambiguity_bit),
            absolute_cfo_measurement_hz=item.absolute_cfo_measurement_hz,
            tracked_absolute_cfo_hz=item.tracked_absolute_cfo_hz,
            tracked_doppler_rate_hz_s=item.tracked_doppler_rate_hz_s,
            fractional_timing_measurement_samples=(item.fractional_timing_measurement_samples),
            tracked_fractional_timing_samples=item.tracked_fractional_timing_samples,
            tracked_timing_rate_s_s=item.tracked_timing_rate_s_s,
            phase_update_applied=item.phase_update_applied,
            frequency_update_applied=item.frequency_update_applied,
            timing_update_applied=item.timing_update_applied,
        )
        for item in result.frames
    )
    segment_id = canonical_digest(
        {
            "scan_frame_iq_sha256": sha256_digest(ci16.tobytes(order="C")),
            "target_index": target_index,
            "receiver_id": seed.source.receiver_id,
            "source_probe_index": seed.source.probe_index,
            "source_candidate_rank": seed.source.candidate.candidate_rank,
            "source_fractional_epoch_offset_samples": fractional_epoch_offset_samples,
            "window_start_sample": start_sample,
            "window_sample_count": duration_samples,
            "config": config.model_dump(mode="json"),
        }
    )
    document = {
        "segment_index": segment_index,
        "segment_id": segment_id,
        "target_index": target_index,
        "target": target.model_dump(mode="json"),
        "receiver_id": seed.source.receiver_id,
        "source_probe_index": seed.source.probe_index,
        "source_probe_start_ms": seed.source.probe_start_ms,
        "source_candidate_rank": seed.source.candidate.candidate_rank,
        "confirmation_probe_index": seed.confirmation.probe_index,
        "confirmation_probe_start_ms": seed.confirmation.probe_start_ms,
        "confirmation_candidate_rank": seed.confirmation.candidate.candidate_rank,
        "source_epoch_sample": seed.source.candidate.epoch_sample,
        "initial_tracking_cfo_hz": seed.source.candidate.tracking_cfo_hz,
        "window_start_s": window_start_s,
        "window_end_s": window_end_s,
        "reference_time_since_retune_s": reference_time_s,
        "lattice_frame_count": lattice_count,
        "returned_frame_count": len(result.frames),
        "supported_frame_count": len(supported),
        "phase_update_count": result.phase_update_count,
        "frequency_update_count": result.frequency_update_count,
        "timing_update_count": result.timing_update_count,
        "supported_frame_fraction": supported_fraction,
        "maximum_supported_frame_gap_s": maximum_gap,
        "median_exact_coherence": _median(item.exact_coherence for item in supported),
        "median_control_coherence": _median(item.control_coherence for item in supported),
        "median_coherence_margin": median_margin,
        "phase_innovation_rms_rad": phase_rms,
        "phase_ambiguity_transition_count": result.phase_ambiguity_transition_count,
        "local_doppler_rate_hz_s": local_rate,
        "local_doppler_rate_sigma_hz_s": line_slope_sigma(relative_times, fit),
        "kalman_doppler_rate_hz_s": kalman_rate,
        "local_minus_kalman_rate_hz_s": disagreement,
        "local_cfo_at_reference_hz": (None if fit is None else fit.intercept_at_reference_hz),
        "frequency_line_rms_hz": None if fit is None else fit.residual_rms_hz,
        "held_out_frequency_rms_hz": held_out_rms,
        "final_fractional_timing_samples": (
            result.frames[-1].tracked_fractional_timing_samples if result.frames else None
        ),
        "final_timing_rate_s_s": (
            result.frames[-1].tracked_timing_rate_s_s if result.frames else None
        ),
        "phase_lock_qualified": result.phase_lock_qualified,
        "qualified": not failures,
        "qualification_failures": tuple(failures),
        "long_baseline_reference_rate_hz_s": None,
        "frames": [item.model_dump(mode="json") for item in frames],
    }
    return ScannerPilotDopplerSegmentV1.model_validate(stable_measurement_floats(document))


def _receiver_pairs(
    segments: tuple[ScannerPilotDopplerSegmentV1, ...],
) -> tuple[ScannerPilotReceiverPairV1, ...]:
    by_target: dict[int, list[ScannerPilotDopplerSegmentV1]] = {}
    for segment in segments:
        by_target.setdefault(segment.target_index, []).append(segment)
    pairs: list[ScannerPilotReceiverPairV1] = []
    for target_index, values in sorted(by_target.items()):
        ordered = sorted(values, key=lambda item: item.receiver_id)
        if len(ordered) != 2 or ordered[0].receiver_id == ordered[1].receiver_id:
            continue
        left, right = ordered
        both_qualified = left.qualified and right.qualified
        rate_difference = None
        if (
            both_qualified
            and left.local_doppler_rate_hz_s is not None
            and right.local_doppler_rate_hz_s is not None
        ):
            rate_difference = left.local_doppler_rate_hz_s - right.local_doppler_rate_hz_s
        cfo_difference = None
        if (
            both_qualified
            and left.local_cfo_at_reference_hz is not None
            and right.local_cfo_at_reference_hz is not None
        ):
            cfo_difference = left.local_cfo_at_reference_hz - right.local_cfo_at_reference_hz
        pairs.append(
            ScannerPilotReceiverPairV1(
                target_index=target_index,
                target=left.target,
                receiver_ids=(left.receiver_id, right.receiver_id),
                segment_ids=(left.segment_id, right.segment_id),
                both_qualified=both_qualified,
                local_rate_difference_hz_s=rate_difference,
                local_cfo_difference_hz=cfo_difference,
                reason=(
                    "both receivers independently confirmed and qualified this edge"
                    if both_qualified
                    else "both receivers confirmed this edge but at least one segment failed gates"
                ),
            )
        )
    return tuple(pairs)


def _median(values) -> float | None:
    finite = [float(value) for value in values if math.isfinite(value)]
    return float(np.median(finite)) if finite else None
