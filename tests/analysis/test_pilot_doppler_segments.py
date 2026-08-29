from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.starlink.local_doppler import (
    frequency_line,
    interleaved_held_out_rms,
    stable_measurement_floats,
)
from leo.analysis.starlink.pilot_doppler_segments import (
    render_standard_pilot_carrier_tracking_v2_png,
    render_standard_pilot_doppler_segments_png,
    render_standard_pilot_segment_rates_png,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentConfigV1,
    PilotDopplerSegmentConfigV2,
    PilotDopplerSegmentV1,
    PilotDopplerSegmentV2,
    PilotDopplerSegmentV3,
    PilotDopplerTrajectorySummaryV1,
    PilotDopplerTrajectorySummaryV2,
    PilotPhaseLockletConfigV1,
    PilotPhaseLockletIntervalV1,
    StandardPilotDopplerSegmentsV1,
    StandardPilotDopplerSegmentsV2,
    StandardPilotDopplerSegmentsV3,
)
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64
_DIGEST_E = "sha256:" + "e" * 64


def test_local_line_and_interleaved_holdout_recover_linear_frequency() -> None:
    times = np.arange(56, dtype=float) / 750.0
    values = 42_000.0 - 3_800.0 * times + 2.0 * np.sin(np.arange(56))

    fit = frequency_line(times, values)
    held_out = interleaved_held_out_rms(times, values)

    assert fit is not None
    assert fit.slope_hz_per_s == pytest.approx(-3_800.0, abs=15.0)
    assert fit.residual_rms_hz < 2.0
    assert held_out is not None and held_out < 3.0


def test_segment_configuration_requires_nonoverlapping_windows() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        PilotDopplerSegmentConfigV1(
            window_duration_s=0.075,
            minimum_window_separation_s=0.050,
        )


def test_persisted_measurements_are_stable_below_rf_precision() -> None:
    left = {"rate_hz_s": -3326.9905104280233, "counts": [55, 53]}
    right = {"rate_hz_s": -3326.9905104276954, "counts": [55, 53]}

    assert stable_measurement_floats(left) == stable_measurement_floats(right)


def test_product_contract_closes_accounting_and_renders_png() -> None:
    config = PilotDopplerSegmentConfigV1()
    segment = PilotDopplerSegmentV1(
        segment_index=0,
        source_trajectory_id=_DIGEST_A,
        source_branch_id=_DIGEST_B,
        source_probe_sample_start=100,
        start_time_s=1.0,
        end_time_s=1.075,
        reference_time_s=1.0375,
        lattice_frame_count=56,
        supported_frame_count=54,
        phase_update_count=50,
        frequency_update_count=54,
        timing_update_count=52,
        supported_frame_fraction=54 / 56,
        maximum_supported_frame_gap_s=2 / 750,
        median_exact_coherence=0.4,
        median_control_coherence=0.1,
        median_coherence_margin=0.3,
        phase_innovation_rms_rad=0.2,
        phase_ambiguity_transition_count=4,
        local_doppler_rate_hz_s=-3_800.0,
        local_doppler_rate_sigma_hz_s=120.0,
        kalman_doppler_rate_hz_s=-3_750.0,
        frozen_doppler_rate_hz_s=-6_900.0,
        local_minus_kalman_rate_hz_s=-50.0,
        local_minus_frozen_rate_hz_s=3_100.0,
        local_cfo_at_reference_hz=41_000.0,
        frozen_cfo_at_reference_hz=40_700.0,
        carrier_bias_at_reference_hz=300.0,
        carrier_bias_change_hz=None,
        frequency_line_rms_hz=12.0,
        held_out_frequency_rms_hz=15.0,
        final_fractional_timing_samples=0.1,
        final_timing_rate_s_s=1e-8,
        phase_lock_qualified=True,
        qualified=True,
        qualification_failures=(),
    )
    summary = PilotDopplerTrajectorySummaryV1(
        source_trajectory_id=_DIGEST_A,
        source_branch_id=_DIGEST_B,
        candidate_window_count=1,
        analyzed_segment_count=1,
        qualified_segment_count=1,
        median_qualified_local_rate_hz_s=-3_800.0,
        median_qualified_kalman_rate_hz_s=-3_750.0,
        median_qualified_frozen_rate_hz_s=-6_900.0,
    )
    body = {
        "path_input_binding_digest": _DIGEST_A,
        "pilot_scan_digest": _DIGEST_B,
        "dealiased_bank_digest": _DIGEST_C,
        "final_trajectory_bank_digest": _DIGEST_D,
        "kalman_tracking_digest": _DIGEST_E,
        "config": config.model_dump(mode="json"),
        "config_digest": config.digest,
        "source_track_count": 1,
        "analyzed_track_count": 1,
        "truncated_track_count": 0,
        "candidate_window_count": 1,
        "analyzed_segment_count": 1,
        "qualified_segment_count": 1,
        "trajectory_summaries": [summary.model_dump(mode="json")],
        "segments": [segment.model_dump(mode="json")],
        "status": StandardScientificStatus.COMPLETE,
        "reason": "test product",
        "carrier_phase_period_rad": math.pi,
        "carrier_discontinuities_are_piecewise_bias": True,
        "frame_timing_is_receiver_relative": True,
        "absolute_carrier_phase_resolved": False,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    identity = {
        "schema_version": 1,
        "algorithm_version": "standard-pilot-doppler-segments-v1",
        **body,
    }
    product = StandardPilotDopplerSegmentsV1.model_validate(
        {**body, "content_digest": canonical_digest(identity)}
    )

    png = render_standard_pilot_doppler_segments_png(
        product,
        session_id="cap-test",
        path_label="stream-0 · radio-test · RX0",
    )

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000
    segment_rates_png = render_standard_pilot_segment_rates_png(
        product,
        session_id="cap-test",
        path_label="stream-0 · radio-test · RX0",
    )
    assert segment_rates_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(segment_rates_png) > 10_000


def test_additive_v2_contract_binds_reacquisition_and_renders_only_locklets() -> None:
    config = PilotDopplerSegmentConfigV2()
    segment = PilotDopplerSegmentV2(
        segment_index=0,
        source_trajectory_id=_DIGEST_A,
        source_branch_id=_DIGEST_B,
        source_probe_sample_start=100,
        start_time_s=1.0,
        end_time_s=1.075,
        reference_time_s=1.0375,
        lattice_frame_count=56,
        supported_frame_count=54,
        phase_update_count=48,
        frequency_update_count=54,
        timing_update_count=52,
        supported_frame_fraction=54 / 56,
        maximum_supported_frame_gap_s=2 / 750,
        median_exact_coherence=0.4,
        median_control_coherence=0.1,
        median_coherence_margin=0.3,
        phase_innovation_rms_rad=0.2,
        phase_ambiguity_transition_count=4,
        local_doppler_rate_hz_s=-3_800.0,
        local_doppler_rate_sigma_hz_s=120.0,
        kalman_doppler_rate_hz_s=-3_750.0,
        frozen_doppler_rate_hz_s=-6_900.0,
        local_minus_kalman_rate_hz_s=-50.0,
        local_minus_frozen_rate_hz_s=3_100.0,
        local_cfo_at_reference_hz=41_000.0,
        frozen_cfo_at_reference_hz=40_700.0,
        carrier_bias_at_reference_hz=300.0,
        carrier_bias_change_hz=None,
        frequency_line_rms_hz=12.0,
        held_out_frequency_rms_hz=15.0,
        final_fractional_timing_samples=0.1,
        final_timing_rate_s_s=1e-8,
        phase_lock_qualified=True,
        qualified=True,
        qualification_failures=(),
        reacquisition_count=2,
    )
    summary = PilotDopplerTrajectorySummaryV2(
        source_trajectory_id=_DIGEST_A,
        source_branch_id=_DIGEST_B,
        candidate_window_count=1,
        analyzed_segment_count=1,
        qualified_segment_count=1,
        median_qualified_local_rate_hz_s=-3_800.0,
        median_qualified_kalman_rate_hz_s=-3_750.0,
        median_qualified_frozen_rate_hz_s=-6_900.0,
        reacquisition_count=2,
    )
    body = {
        "path_input_binding_digest": _DIGEST_A,
        "pilot_scan_digest": _DIGEST_B,
        "dealiased_bank_digest": _DIGEST_C,
        "final_trajectory_bank_digest": _DIGEST_D,
        "kalman_tracking_digest": _DIGEST_E,
        "config": config.model_dump(mode="json"),
        "config_digest": config.digest,
        "source_track_count": 1,
        "analyzed_track_count": 1,
        "truncated_track_count": 0,
        "candidate_window_count": 1,
        "analyzed_segment_count": 1,
        "qualified_segment_count": 1,
        "trajectory_summaries": [summary.model_dump(mode="json")],
        "segments": [segment.model_dump(mode="json")],
        "status": StandardScientificStatus.COMPLETE,
        "reason": "V2 test product",
        "carrier_phase_period_rad": math.pi,
        "carrier_discontinuities_are_piecewise_bias": True,
        "frame_timing_is_receiver_relative": True,
        "absolute_carrier_phase_resolved": False,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "phase_reacquisition_policy": "independent-phase-v2",
        "legacy_kalman_is_diagnostic_only": True,
        "primary_rate_estimator": "direct-local-frequency-line",
        "kalman_rate_is_diagnostic_only": True,
    }
    identity = {
        "schema_version": 2,
        "algorithm_version": "standard-pilot-doppler-segments-v2",
        **body,
    }
    product = StandardPilotDopplerSegmentsV2.model_validate(
        {**body, "content_digest": canonical_digest(identity)}
    )

    png = render_standard_pilot_carrier_tracking_v2_png(
        product,
        session_id="cap-test",
        path_label="stream-0 · radio-test · RX0",
    )

    assert product.legacy_kalman_is_diagnostic_only
    assert product.kalman_rate_is_diagnostic_only
    assert product.primary_rate_estimator == "direct-local-frequency-line"
    assert product.trajectory_summaries[0].reacquisition_count == 2
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000


def _closed_v3_product(
    *,
    sample_rate_hz: int = 2_500_000,
    window_start: int = 1_000,
) -> StandardPilotDopplerSegmentsV3:

    def reference_sample(frame_index: int) -> int:
        return window_start + 100 + round(frame_index * sample_rate_hz / 750)

    intervals = tuple(
        PilotPhaseLockletIntervalV1(
            previous_frame_index=index,
            frame_index=index + 1,
            previous_global_reference_device_sample=reference_sample(index),
            global_reference_device_sample=reference_sample(index + 1),
            time_delta_s=(reference_sample(index + 1) - reference_sample(index)) / sample_rate_hz,
            channel_similarity=0.95,
            previous_intraframe_residual_cfo_hz=0.0,
            intraframe_residual_cfo_hz=0.0,
            measured_phase_advance_modulo_pi_rad=0.0,
            expected_phase_advance_modulo_pi_rad=0.0,
            uncentered_innovation_modulo_pi_rad=0.0,
            centered_innovation_modulo_pi_rad=0.0,
            training=index < 12,
            held_out=index >= 12,
            gate_passed=index >= 12,
        )
        for index in range(33)
    )
    segment = PilotDopplerSegmentV3(
        continuity_segment_index=0,
        source_v2_pilot_doppler_content_digest=_DIGEST_A,
        source_v2_segment_index=0,
        source_trajectory_id=_DIGEST_B,
        source_branch_id=_DIGEST_C,
        global_source_probe_sample_start=window_start,
        global_start_time_s=stable_measurement_floats(window_start / sample_rate_hz),
        global_end_time_s=stable_measurement_floats(window_start / sample_rate_hz + 0.075),
        global_reference_time_s=stable_measurement_floats(window_start / sample_rate_hz + 0.0375),
        lattice_frame_count=34,
        supported_frame_fraction=1.0,
        maximum_supported_frame_gap_s=1 / 750,
        median_exact_coherence=0.6,
        median_control_coherence=0.05,
        median_coherence_margin=0.55,
        local_cfo_at_reference_hz=-522_455.0,
        local_doppler_rate_hz_s=-3_775.0,
        local_doppler_rate_sigma_hz_s=20.0,
        frequency_line_rms_hz=10.0,
        held_out_frequency_rms_hz=12.0,
        frozen_cfo_at_reference_hz=-522_575.0,
        frozen_doppler_rate_hz_s=-3_500.0,
        local_minus_frozen_rate_hz_s=-275.0,
        legacy_v2_phase_lock_qualified=False,
        legacy_v2_qualified=False,
        legacy_v2_phase_update_count=14,
        legacy_v2_reacquisition_count=1,
        legacy_v2_phase_innovation_rms_rad=0.77,
        legacy_v2_kalman_doppler_rate_hz_s=-3_600.0,
        complete_frame_count=34,
        supported_frame_count=34,
        supported_frame_indexes=tuple(range(34)),
        adjacent_supported_interval_count=33,
        training_interval_count=12,
        held_out_interval_count=21,
        held_out_gate_pass_count=21,
        phase_bias_hz_modulo=0.0,
        training_phase_rms_rad=0.0,
        training_circular_concentration=1.0,
        held_out_gate_pass_fraction=1.0,
        held_out_phase_rms_rad=0.0,
        held_out_maximum_absolute_innovation_rad=0.0,
        held_out_circular_concentration=1.0,
        phase_trackability_qualified=True,
        phase_trackability_reason="qualified held-out adjacent modulo-pi phase trackability",
        qualified=True,
        qualification_failures=(),
        intervals=intervals,
    )
    capture_sample_count = max(sample_rate_hz, window_start + sample_rate_hz)
    continuity = ContinuitySegmentV1(
        segment_index=0,
        device_sample_start=0,
        device_sample_stop=capture_sample_count,
        stored_sample_start=0,
        stored_sample_stop=capture_sample_count,
    )
    source = StandardNativeSourceV1(
        session_id="cap-v3-phase-contract",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=1,
        manifest_digest=_DIGEST_A,
        synchronization_inventory_digest=_DIGEST_B,
        path_input_binding_digest=_DIGEST_C,
        validity_inventory_digest=_DIGEST_D,
        tuned_center_frequency_hz=959_687_500,
        sample_rate_hz=sample_rate_hz,
        logical_sample_count=capture_sample_count,
        observed_sample_count=capture_sample_count,
        missing_sample_count=0,
        timing={
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 2_000_000_000,
            "last_earliest_utc_ns": 1_999_999_900,
            "last_latest_utc_ns": 2_000_000_100,
        },
        continuity_segments=(continuity,),
    )
    phase_config = PilotPhaseLockletConfigV1()
    body = {
        "schema_version": 3,
        "algorithm_version": "standard-native-pilot-doppler-segments-v3",
        "source": source.model_dump(mode="json"),
        "starlink_edge": StarlinkEdge.LOWER.value,
        "stateful_path_product_digest": _DIGEST_A,
        "stateful_path_digest": _DIGEST_B,
        "science_configuration_digest": _DIGEST_C,
        "phase_config": phase_config.model_dump(mode="json"),
        "phase_config_digest": phase_config.digest,
        "source_stateful_science_status": "complete",
        "bounded_local_track_truncation_present": False,
        "continuity_segment_count": 1,
        "analyzed_continuity_segment_count": 1,
        "source_v2_locklet_count": 1,
        "corrected_phase_trackability_count": 1,
        "qualified_segment_count": 1,
        "segments": (segment.model_dump(mode="json"),),
        "status": StandardScientificStatus.COMPLETE.value,
        "reason": "held-out adjacent modulo-pi phase and independent local Doppler completed",
        "primary_cfo_source": "independent-intraframe-pilot-slope",
        "primary_rate_estimator": "direct-local-frequency-line",
        "phase_trackability_method": "prefix-trained-held-out-one-step-phase-v1",
        "phase_frequency_nuisance_scope": "locklet-local-modulo-frame-rate-over-two-v1",
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
        {**body, "content_digest": canonical_digest(body)}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("held_out_phase_rms_rad", 0.1),
        ("held_out_gate_pass_count", 19),
        ("phase_trackability_qualified", False),
        ("local_minus_frozen_rate_hz_s", 123_456.0),
    ),
)
def test_v3_contract_rejects_unclosed_phase_evidence(field: str, value: object) -> None:
    product = _closed_v3_product()
    document = product.model_dump(mode="json")
    segment = document["segments"][0]
    segment[field] = value
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_crossed_interval_time_coordinates() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    document["segments"][0]["intervals"][12]["time_delta_s"] = 0.01
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="time/sample delta"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_training_prefix_relabeling() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    first = document["segments"][0]["intervals"][0]
    later = document["segments"][0]["intervals"][12]
    first.update(training=False, held_out=True, gate_passed=True)
    later.update(training=True, held_out=False, gate_passed=False)
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="fixed prefix"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_unsupported_training_prefix() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    document["segments"][0]["intervals"][0]["channel_similarity"] = 0.1
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="training prefix lacks channel similarity support"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_expected_phase_not_derived_from_intraframe_cfo() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    interval = document["segments"][0]["intervals"][12]
    interval["measured_phase_advance_modulo_pi_rad"] = 1.0
    interval["expected_phase_advance_modulo_pi_rad"] = 1.0
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="expected advance does not close to CFO"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_interval_off_common_frame_lattice() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    interval = document["segments"][0]["intervals"][12]
    interval["previous_global_reference_device_sample"] = 50_000
    interval["global_reference_device_sample"] = 75_000
    interval["time_delta_s"] = 0.01
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="750-Hz frame lattice"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_accepts_late_three_msps_geometry_after_wire_quantization() -> None:
    product = _closed_v3_product(
        sample_rate_hz=3_000_000,
        window_start=131_942_341,
    )

    assert product.source.sample_rate_hz == 3_000_000
    assert product.segments[0].global_source_probe_sample_start == 131_942_341


def test_v3_contract_rejects_contradictory_repeated_frame_cfo() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    intervals = document["segments"][0]["intervals"]
    for index, interval in enumerate(intervals):
        interval["previous_intraframe_residual_cfo_hz"] = 100.0 + index
        interval["intraframe_residual_cfo_hz"] = -(100.0 + index)
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="repeated frame evidence is inconsistent"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_omitted_adjacent_supported_interval() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    segment = document["segments"][0]
    segment["intervals"].pop()
    segment["adjacent_supported_interval_count"] = 32
    segment["held_out_interval_count"] = 20
    segment["held_out_gate_pass_count"] = 20
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="omitted an adjacent supported-frame pair"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )


def test_v3_contract_rejects_status_reason_relabeling() -> None:
    document = _closed_v3_product().model_dump(mode="json")
    document["status"] = "partial"
    document["reason"] = (
        "held-out adjacent modulo-pi phase and independent local Doppler completed with bounded "
        "coverage or track truncation"
    )
    body = {key: item for key, item in document.items() if key != "content_digest"}

    with pytest.raises(ValueError, match="status or reason"):
        StandardPilotDopplerSegmentsV3.model_validate(
            {**body, "content_digest": canonical_digest(body)}
        )
