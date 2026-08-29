"""Global V3 pilot Doppler and held-out phase evidence for Standard-native paths."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict
from typing import cast

import numpy as np

from leo.analysis.standard.native_stateful import StandardNativeStatefulResult
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.starlink.local_doppler import (
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentV2,
    PilotDopplerSegmentV3,
    PilotPhaseLockletConfigV1,
    StandardPilotDopplerSegmentsV3,
)
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV2
from leo.contracts.standard_pipeline import StandardPathInputBindV4, StandardScientificStatus
from leo.contracts.states import StarlinkEdge

_LEGACY_PHASE_FAILURE = "modulo-pi phase lock did not qualify"


def build_standard_native_pilot_doppler_segments_v3(
    result: StandardNativeStatefulResult,
    binding: StandardPathInputBindV4,
    stateful_path: StandardNativeStatefulPathV2,
    *,
    stateful_path_product_digest: Sha256Digest,
    config: ReceiverStandardConfig,
    edge: StarlinkEdge,
) -> StandardPilotDopplerSegmentsV3:
    """Rebind phase-safe segment evidence while preserving embedded V2 bytes."""

    source = StandardNativeSourceV1.from_path_binding(binding)
    if (
        stateful_path.source != source
        or stateful_path.starlink_edge != edge
        or stateful_path_product_digest != canonical_digest(stateful_path.model_dump(mode="json"))
        or result.path_input_binding_digest != binding.binding_digest
        or tuple(item.segment for item in result.segments) != source.continuity_segments
    ):
        raise ValueError("pilot Doppler V3 source or stateful authority does not close")

    phase_configs = {
        science.pilot_phase_config
        for segment in result.segments
        if (science := segment.local_science) is not None
    }
    if len(phase_configs) > 1:
        raise ValueError("pilot Doppler V3 segments used inconsistent phase policies")
    phase_runtime_config = next(iter(phase_configs), None)
    phase_config = PilotPhaseLockletConfigV1.model_validate(
        {} if phase_runtime_config is None else asdict(phase_runtime_config)
    )

    segment_documents: list[dict[str, object]] = []
    analyzed_continuity_segment_count = 0
    bounded_local_truncation = False
    persisted_by_index = {item.continuity_segment_index: item for item in stateful_path.segments}
    for segment_result in result.segments:
        persisted_segment = persisted_by_index.get(segment_result.continuity_segment_index)
        if persisted_segment is None:
            raise ValueError("pilot Doppler V3 runtime segment escaped persisted authority")
        science = segment_result.local_science
        if science is None:
            if persisted_segment.local_science is not None:
                raise ValueError("pilot Doppler V3 runtime omitted persisted local science")
            continue
        if (
            persisted_segment.local_science is None
            or persisted_segment.local_science.pilot_doppler_segments
            != science.pilot_doppler_segments
        ):
            raise ValueError("pilot Doppler V3 runtime V2 evidence differs from persisted state")
        analyzed_continuity_segment_count += 1
        legacy_product = science.pilot_doppler_segments
        bounded_local_truncation = bool(
            bounded_local_truncation or legacy_product.truncated_track_count
        )
        if len(legacy_product.segments) != len(science.pilot_phase_locklets):
            raise ValueError("pilot Doppler V3 local phase inventory does not close")
        for legacy, phase in zip(
            legacy_product.segments,
            science.pilot_phase_locklets,
            strict=True,
        ):
            segment_documents.append(
                _segment_document(
                    segment_result.device_sample_start,
                    segment_result.continuity_segment_index,
                    binding.sample_rate_hz,
                    legacy_product.content_digest,
                    legacy,
                    phase,
                    config,
                )
            )

    segment_documents.sort(
        key=lambda item: (
            cast(int, item["continuity_segment_index"]),
            cast(int, item["global_source_probe_sample_start"]),
            str(item["source_trajectory_id"]),
        )
    )
    segments = tuple(
        PilotDopplerSegmentV3.model_validate(stable_measurement_floats(item))
        for item in segment_documents
    )
    phase_trackability_count = sum(item.phase_trackability_qualified for item in segments)
    qualified_count = sum(item.qualified for item in segments)
    status = (
        StandardScientificStatus.PARTIAL
        if qualified_count
        and (stateful_path.stateful_science_status != "complete" or bounded_local_truncation)
        else StandardScientificStatus.COMPLETE
        if qualified_count
        else StandardScientificStatus.INSUFFICIENT_DATA
        if segments
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "held-out adjacent modulo-pi phase and independent local Doppler completed with bounded "
        "coverage or track truncation"
        if status is StandardScientificStatus.PARTIAL
        else "held-out adjacent modulo-pi phase and independent local Doppler completed"
        if status is StandardScientificStatus.COMPLETE
        else "no V2-selected locklet passed corrected phase-trackability and independent "
        "frequency gates"
        if segments
        else "no V2-selected pilot Doppler locklet was available"
    )
    document = {
        "schema_version": 3,
        "algorithm_version": "standard-native-pilot-doppler-segments-v3",
        "source": source.model_dump(mode="json"),
        "starlink_edge": edge.value,
        "stateful_path_product_digest": stateful_path_product_digest,
        "stateful_path_digest": stateful_path.stateful_path_digest,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "phase_config": phase_config.model_dump(mode="json"),
        "phase_config_digest": phase_config.digest,
        "source_stateful_science_status": stateful_path.stateful_science_status,
        "bounded_local_track_truncation_present": bounded_local_truncation,
        "continuity_segment_count": len(source.continuity_segments),
        "analyzed_continuity_segment_count": analyzed_continuity_segment_count,
        "source_v2_locklet_count": len(segments),
        "corrected_phase_trackability_count": phase_trackability_count,
        "qualified_segment_count": qualified_count,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "status": status.value,
        "reason": reason,
        "primary_cfo_source": "independent-intraframe-pilot-slope",
        "primary_rate_estimator": "direct-local-frequency-line",
        "phase_trackability_method": "prefix-trained-held-out-one-step-phase-v1",
        "phase_frequency_nuisance_scope": ("locklet-local-modulo-frame-rate-over-two-v1"),
        "nuisance_transferable_to_cfo_or_rate": False,
        "held_out_used_for_nuisance_fit": False,
        "open_loop_absolute_phase_prediction_claimed": False,
        "absolute_carrier_phase_resolved": False,
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardPilotDopplerSegmentsV3.model_validate(
        {**document, "content_digest": canonical_digest(document)}
    )


def _segment_document(
    global_segment_start: int,
    continuity_segment_index: int,
    sample_rate_hz: int,
    legacy_content_digest: Sha256Digest,
    legacy: PilotDopplerSegmentV2,
    phase: object,
    config: ReceiverStandardConfig,
) -> dict[str, object]:
    # Kept local to avoid making an analyzer depend on a concrete storage or
    # orchestration layer; the runtime object is a pure DSP result.
    from leo.analysis.qam.pilot_phase_locklet import PilotPhaseLockletResult

    if not isinstance(phase, PilotPhaseLockletResult):
        raise TypeError("pilot Doppler V3 received non-phase locklet evidence")
    supported = tuple(item for item in phase.frames if item.measurement_supported)
    relative_times = np.asarray(
        [item.reference_sample / sample_rate_hz for item in supported],
        dtype=float,
    )
    frequencies = np.asarray(
        [item.absolute_cfo_measurement_hz for item in supported],
        dtype=float,
    )
    fit = frequency_line(relative_times, frequencies)
    held_out_frequency_rms = interleaved_held_out_rms(relative_times, frequencies)
    local_cfo = None if fit is None else fit.intercept_at_reference_hz
    local_rate = None if fit is None else fit.slope_hz_per_s
    frequency_rms = None if fit is None else fit.residual_rms_hz
    rate_sigma = line_slope_sigma(relative_times, fit)
    _require_same_direct_metric("local CFO", local_cfo, legacy.local_cfo_at_reference_hz)
    _require_same_direct_metric("local rate", local_rate, legacy.local_doppler_rate_hz_s)
    _require_same_direct_metric("frequency RMS", frequency_rms, legacy.frequency_line_rms_hz)
    _require_same_direct_metric(
        "held-out frequency RMS",
        held_out_frequency_rms,
        legacy.held_out_frequency_rms_hz,
    )
    lattice_count = phase.complete_frame_count
    supported_fraction = len(supported) / lattice_count if lattice_count else 0.0
    gaps = np.diff(relative_times)
    maximum_gap = float(np.max(gaps)) if gaps.size else None
    median_exact = _median_optional(item.exact_coherence for item in supported)
    median_control = _median_optional(item.control_coherence for item in supported)
    median_margin = _median_optional(item.coherence_margin for item in supported)
    policy = config.pilot_doppler_segments
    failures: list[str] = []
    if supported_fraction < policy.minimum_supported_frame_fraction:
        failures.append("supported frame coverage below threshold")
    if maximum_gap is None or maximum_gap > policy.maximum_supported_frame_gap_s:
        failures.append("supported frame gap exceeds threshold")
    if median_margin is None or median_margin < policy.minimum_median_coherence_margin:
        failures.append("exact-versus-control coherence margin below threshold")
    if fit is None:
        failures.append("too few supported frames for a local frequency line")
    elif fit.residual_rms_hz > policy.maximum_frequency_line_rms_hz:
        failures.append("local frequency-line RMS exceeds threshold")
    if held_out_frequency_rms is None:
        failures.append("too few supported frames for interleaved held-out prediction")
    elif held_out_frequency_rms > policy.maximum_held_out_frequency_rms_hz:
        failures.append("held-out local frequency prediction RMS exceeds threshold")
    if not phase.phase_trackability_qualified:
        failures.append("held-out modulo-pi phase trackability did not qualify")
    legacy_nonphase_failures = tuple(
        item for item in legacy.qualification_failures if item != _LEGACY_PHASE_FAILURE
    )
    corrected_nonphase_failures = tuple(
        item for item in failures if item != "held-out modulo-pi phase trackability did not qualify"
    )
    if corrected_nonphase_failures != legacy_nonphase_failures:
        raise ValueError("pilot Doppler V3 changed the V2 nonphase qualification gates")
    if lattice_count != legacy.lattice_frame_count:
        raise ValueError("pilot Doppler V3 complete-frame inventory changed V2 evidence")
    _require_same_direct_metric(
        "supported fraction", supported_fraction, legacy.supported_frame_fraction
    )
    _require_same_direct_metric(
        "maximum supported gap", maximum_gap, legacy.maximum_supported_frame_gap_s
    )
    _require_same_direct_metric(
        "median exact coherence", median_exact, legacy.median_exact_coherence
    )
    _require_same_direct_metric(
        "median control coherence", median_control, legacy.median_control_coherence
    )
    _require_same_direct_metric(
        "median coherence margin", median_margin, legacy.median_coherence_margin
    )
    global_offset_s = global_segment_start / sample_rate_hz
    interval_documents = tuple(
        {
            "schema_version": 1,
            "previous_frame_index": item.previous_frame_index,
            "frame_index": item.frame_index,
            "previous_global_reference_device_sample": (
                global_segment_start
                + legacy.source_probe_sample_start
                + item.previous_reference_sample
            ),
            "global_reference_device_sample": (
                global_segment_start + legacy.source_probe_sample_start + item.reference_sample
            ),
            "time_delta_s": item.time_delta_s,
            "channel_similarity": item.channel_similarity,
            "previous_intraframe_residual_cfo_hz": (item.previous_intraframe_residual_cfo_hz),
            "intraframe_residual_cfo_hz": item.intraframe_residual_cfo_hz,
            "measured_phase_advance_modulo_pi_rad": (item.measured_phase_advance_modulo_pi_rad),
            "expected_phase_advance_modulo_pi_rad": (item.expected_phase_advance_modulo_pi_rad),
            "uncentered_innovation_modulo_pi_rad": (item.uncentered_innovation_modulo_pi_rad),
            "centered_innovation_modulo_pi_rad": (item.centered_innovation_modulo_pi_rad),
            "training": item.training,
            "held_out": item.held_out,
            "gate_passed": item.gate_passed,
        }
        for item in phase.intervals
    )
    return {
        "schema_version": 3,
        "continuity_segment_index": continuity_segment_index,
        "source_v2_pilot_doppler_content_digest": legacy_content_digest,
        "source_v2_segment_index": legacy.segment_index,
        "source_trajectory_id": legacy.source_trajectory_id,
        "source_branch_id": legacy.source_branch_id,
        "global_source_probe_sample_start": global_segment_start + legacy.source_probe_sample_start,
        "global_start_time_s": global_offset_s + legacy.start_time_s,
        "global_end_time_s": global_offset_s + legacy.end_time_s,
        "global_reference_time_s": global_offset_s + legacy.reference_time_s,
        "lattice_frame_count": lattice_count,
        "supported_frame_fraction": supported_fraction,
        "maximum_supported_frame_gap_s": maximum_gap,
        "median_exact_coherence": median_exact,
        "median_control_coherence": median_control,
        "median_coherence_margin": median_margin,
        "local_cfo_at_reference_hz": local_cfo,
        "local_doppler_rate_hz_s": local_rate,
        "local_doppler_rate_sigma_hz_s": rate_sigma,
        "frequency_line_rms_hz": frequency_rms,
        "held_out_frequency_rms_hz": held_out_frequency_rms,
        "frozen_cfo_at_reference_hz": legacy.frozen_cfo_at_reference_hz,
        "frozen_doppler_rate_hz_s": legacy.frozen_doppler_rate_hz_s,
        "local_minus_frozen_rate_hz_s": (
            None if local_rate is None else local_rate - legacy.frozen_doppler_rate_hz_s
        ),
        "primary_cfo_source": "independent-intraframe-pilot-slope",
        "primary_rate_estimator": "direct-local-frequency-line",
        "legacy_v2_phase_lock_qualified": legacy.phase_lock_qualified,
        "legacy_v2_qualified": legacy.qualified,
        "legacy_v2_phase_update_count": legacy.phase_update_count,
        "legacy_v2_reacquisition_count": legacy.reacquisition_count,
        "legacy_v2_phase_innovation_rms_rad": legacy.phase_innovation_rms_rad,
        "legacy_v2_kalman_doppler_rate_hz_s": legacy.kalman_doppler_rate_hz_s,
        "legacy_v2_filter_version": legacy.filter_version,
        "complete_frame_count": phase.complete_frame_count,
        "supported_frame_count": phase.supported_frame_count,
        "supported_frame_indexes": tuple(
            item.frame_index for item in phase.frames if item.measurement_supported
        ),
        "adjacent_supported_interval_count": phase.adjacent_supported_interval_count,
        "training_interval_count": phase.training_interval_count,
        "held_out_interval_count": phase.held_out_interval_count,
        "held_out_gate_pass_count": phase.held_out_gate_pass_count,
        "phase_bias_hz_modulo": phase.phase_bias_hz_modulo,
        "phase_bias_period_hz": phase.phase_bias_period_hz,
        "training_phase_rms_rad": phase.training_phase_rms_rad,
        "training_circular_concentration": phase.training_circular_concentration,
        "held_out_gate_pass_fraction": phase.held_out_gate_pass_fraction,
        "held_out_phase_rms_rad": phase.held_out_phase_rms_rad,
        "held_out_maximum_absolute_innovation_rad": (
            phase.held_out_maximum_absolute_innovation_rad
        ),
        "held_out_circular_concentration": phase.held_out_circular_concentration,
        "phase_trackability_qualified": phase.phase_trackability_qualified,
        "phase_trackability_reason": phase.phase_trackability_reason,
        "qualified": not failures,
        "qualification_failures": tuple(failures),
        "intervals": interval_documents,
        "phase_frequency_nuisance_scope": ("locklet-local-modulo-frame-rate-over-two-v1"),
        "nuisance_transferable_to_cfo_or_rate": False,
        "absolute_carrier_phase_resolved": phase.absolute_carrier_phase_resolved,
        "phase_does_not_update_cfo_or_rate": phase.phase_does_not_update_cfo_or_rate,
        "held_out_used_for_nuisance_fit": phase.held_out_used_for_nuisance_fit,
        "adjacent_one_step_innovations": phase.adjacent_one_step_innovations,
        "held_out_gate_does_not_control_future_reference": (
            phase.held_out_gate_does_not_control_future_reference
        ),
        "candidate_only": phase.candidate_only,
    }


def _require_same_direct_metric(
    name: str,
    measured: float | None,
    legacy: float | None,
) -> None:
    if (measured is None) != (legacy is None) or (
        measured is not None
        and legacy is not None
        and not math.isclose(measured, legacy, rel_tol=1e-10, abs_tol=1e-6)
    ):
        raise ValueError(f"pilot Doppler V3 independent {name} changed V2 direct evidence")


def _median_optional(values: Iterable[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(value)]
    return float(np.median(finite)) if finite else None


__all__ = ["build_standard_native_pilot_doppler_segments_v3"]
