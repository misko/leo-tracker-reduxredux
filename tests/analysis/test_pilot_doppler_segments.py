from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.starlink.local_doppler import (
    frequency_line,
    interleaved_held_out_rms,
    stable_measurement_floats,
)
from leo.analysis.starlink.pilot_doppler_segments import render_standard_pilot_doppler_segments_png
from leo.contracts.digests import canonical_digest
from leo.contracts.pilot_doppler_segments import (
    PilotDopplerSegmentConfigV1,
    PilotDopplerSegmentV1,
    PilotDopplerTrajectorySummaryV1,
    StandardPilotDopplerSegmentsV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus

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
