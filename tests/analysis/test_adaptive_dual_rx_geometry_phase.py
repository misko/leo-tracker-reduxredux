from __future__ import annotations

import math

import pytest

from leo.analysis.starlink.adaptive_dual_rx_geometry_phase import (
    SPEED_OF_LIGHT_M_S,
    CalibratedPhaseGeometry,
    GeometryPhaseObservation,
    ReceiverChainCalibration,
    reconstruct_geometry_phase,
)


def geometry(**changes) -> CalibratedPhaseGeometry:
    values = {
        "baseline_enu_m": (0.08, 0.0, 0.0),
        "baseline_standard_error_m": 0.0002,
        "geometry_digest": "sha256:" + "1" * 64,
        "receiver_mapping_verified": True,
        "phase_centers_verified": True,
        "enu_pose_verified": True,
    }
    values.update(changes)
    return CalibratedPhaseGeometry(**values)


def calibration(**changes) -> ReceiverChainCalibration:
    values = {
        "differential_group_delay_s": 3.2e-9,
        "group_delay_standard_error_s": 0.05e-9,
        "residual_double_difference_rad": 0.13,
        "residual_standard_error_rad": 0.01,
        "calibration_digest": "sha256:" + "2" * 64,
        "measurement_truth_verified": True,
        "absolute_cycle_referenced": True,
    }
    values.update(changes)
    return ReceiverChainCalibration(**values)


def observation(**changes) -> GeometryPhaseObservation:
    low_rf_hz = 11_000_000_000.0
    high_rf_hz = 11_000_227_272.727
    low_direction = (0.0, 0.0, 1.0)
    high_direction = (0.1, 0.0, math.sqrt(0.99))
    baseline = (0.08, 0.0, 0.0)
    predicted = 2 * math.pi / SPEED_OF_LIGHT_M_S * sum(
        component
        * (high_rf_hz * high - low_rf_hz * low)
        for component, high, low in zip(baseline, high_direction, low_direction, strict=True)
    )
    hardware = 2 * math.pi * 3.2e-9 * (high_rf_hz - low_rf_hz) + 0.13
    asynchronous = 7.0 * 0.0004
    measured = predicted + hardware + asynchronous - 2 * math.pi * 3
    values = {
        "utc_ns": 1_800_000_000_000_000_000,
        "wrapped_double_difference_rad": math.atan2(math.sin(measured), math.cos(measured)),
        "measurement_standard_error_rad": 0.02,
        "low_rf_hz": low_rf_hz,
        "high_rf_hz": high_rf_hz,
        "low_direction_enu": low_direction,
        "high_direction_enu": high_direction,
        "direction_standard_error_rad": 1e-5,
        "low_frame_utc_ns": 1_800_000_000_000_000_000,
        "high_frame_utc_ns": 1_800_000_000_000_400_000,
        "common_mode_rate_rad_s": 7.0,
        "common_mode_rate_standard_error_rad_s": 0.1,
        "direction_track_verified": True,
        "association_uses_phase": False,
    }
    values.update(changes)
    return GeometryPhaseObservation(**values)


def test_recovers_known_geometry_after_group_delay_alias_and_async_drift() -> None:
    result = reconstruct_geometry_phase(geometry(), calibration(), (observation(),))
    assert result.state == "available"
    assert result.ambiguity_state == "conditionally_unique"
    assert result.reasons == (
        "cycle_choice_conditioned_on_calibrated_geometry_and_direction_tracks",
    )
    point = result.points[0]
    assert len(point.ambiguity_candidates) == 1
    assert point.ambiguity_candidates[0].residual_rad == pytest.approx(0.0, abs=1e-12)
    assert point.asynchronous_common_mode_correction_rad == pytest.approx(0.0028)


@pytest.mark.parametrize(
    ("geometry_change", "calibration_change", "observation_change", "reason"),
    [
        ({"baseline_enu_m": None}, {}, {}, "missing_phase_center_baseline_enu"),
        ({"receiver_mapping_verified": False}, {}, {}, "receiver_mapping_unverified"),
        ({"phase_centers_verified": False}, {}, {}, "rf_phase_centers_unverified"),
        ({"enu_pose_verified": False}, {}, {}, "fixture_to_enu_pose_unverified"),
        ({}, {"differential_group_delay_s": None}, {}, "receiver_chain_phase_calibration_missing"),
        ({}, {}, {"high_direction_enu": None}, "source_direction_track_missing"),
        (
            {},
            {},
            {"common_mode_rate_rad_s": None},
            "asynchronous_frame_common_mode_uncalibrated",
        ),
    ],
)
def test_missing_authority_is_explicitly_unavailable(
    geometry_change, calibration_change, observation_change, reason
) -> None:
    result = reconstruct_geometry_phase(
        geometry(**geometry_change),
        calibration(**calibration_change),
        (observation(**observation_change),),
    )
    assert result.state == "unavailable"
    assert reason in result.reasons
    assert result.points == ()


def test_modulo_cycle_calibration_preserves_ambiguity() -> None:
    result = reconstruct_geometry_phase(
        geometry(), calibration(absolute_cycle_referenced=False), (observation(),)
    )
    assert result.state == "available"
    assert result.ambiguity_state == "ambiguous"
    assert "calibration_not_cycle_referenced" in result.reasons


def test_large_uncertainty_retains_multiple_integer_cycles() -> None:
    result = reconstruct_geometry_phase(
        geometry(baseline_standard_error_m=0.1), calibration(), (observation(),)
    )
    assert result.state == "available"
    assert result.ambiguity_state == "ambiguous"
    assert len(result.points[0].ambiguity_candidates) > 1


def test_receiver_swap_cannot_be_silently_interpreted() -> None:
    result = reconstruct_geometry_phase(
        geometry(receiver_mapping_verified=False), calibration(), (observation(),)
    )
    assert result.state == "unavailable"
    assert result.reasons == ("receiver_mapping_unverified",)


def test_phase_guided_association_is_rejected() -> None:
    result = reconstruct_geometry_phase(
        geometry(), calibration(), (observation(association_uses_phase=True),)
    )
    assert result.state == "unavailable"
    assert result.reasons == ("source_association_used_phase",)


@pytest.mark.parametrize(
    ("geometry_change", "calibration_change", "observation_change", "gate", "message"),
    [
        ({}, {"differential_group_delay_s": math.nan}, {}, 3.0, "calibration scalars"),
        ({}, {}, {"low_rf_hz": math.inf}, 3.0, "positive finite measurements"),
        ({}, {}, {"common_mode_rate_rad_s": math.inf}, 3.0, "common-mode calibration"),
        ({}, {}, {}, math.nan, "ambiguity bounds"),
    ],
)
def test_nonfinite_physical_inputs_are_rejected(
    geometry_change, calibration_change, observation_change, gate, message
) -> None:
    with pytest.raises(ValueError, match=message):
        reconstruct_geometry_phase(
            geometry(**geometry_change),
            calibration(**calibration_change),
            (observation(**observation_change),),
            ambiguity_sigma_gate=gate,
        )
