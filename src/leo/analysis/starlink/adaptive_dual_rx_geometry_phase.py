"""Calibrated dual-RX geometric phase reconstruction with explicit ambiguities.

This module begins after signal association.  It never uses carrier phase to
choose a source identity.  Missing physical calibration yields an unavailable
result rather than a geometric interpretation of receiver phase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

SPEED_OF_LIGHT_M_S = 299_792_458.0


@dataclass(frozen=True, slots=True)
class CalibratedPhaseGeometry:
    """Verified RX1-minus-RX0 phase-center baseline in local ENU coordinates."""

    baseline_enu_m: tuple[float, float, float] | None
    baseline_standard_error_m: float | None
    geometry_digest: str | None
    receiver_mapping_verified: bool
    phase_centers_verified: bool
    enu_pose_verified: bool


@dataclass(frozen=True, slots=True)
class ReceiverChainCalibration:
    """Frequency and time-dependent RX1-minus-RX0 phase calibration.

    A static differential phase cancels from a same-chain two-signal double
    difference.  Differential group delay does not.  ``residual_*`` permits a
    measured non-linear correction at the two frequencies.
    """

    differential_group_delay_s: float | None
    group_delay_standard_error_s: float | None
    residual_double_difference_rad: float | None
    residual_standard_error_rad: float | None
    calibration_digest: str | None
    measurement_truth_verified: bool
    absolute_cycle_referenced: bool


@dataclass(frozen=True, slots=True)
class GeometryPhaseObservation:
    """One phase-blind-associated high-minus-low receiver double difference."""

    utc_ns: int
    wrapped_double_difference_rad: float
    measurement_standard_error_rad: float
    low_rf_hz: float
    high_rf_hz: float
    low_direction_enu: tuple[float, float, float] | None
    high_direction_enu: tuple[float, float, float] | None
    direction_standard_error_rad: float | None
    low_frame_utc_ns: int
    high_frame_utc_ns: int
    common_mode_rate_rad_s: float | None
    common_mode_rate_standard_error_rad_s: float | None
    direction_track_verified: bool
    association_uses_phase: Literal[False] = False


@dataclass(frozen=True, slots=True)
class IntegerAmbiguityCandidate:
    cycles: int
    unwrapped_corrected_phase_rad: float
    residual_rad: float
    normalized_residual: float


@dataclass(frozen=True, slots=True)
class GeometryPhasePoint:
    utc_ns: int
    measured_wrapped_rad: float
    corrected_wrapped_rad: float
    predicted_geometry_rad: float
    predicted_geometry_wrapped_rad: float
    hardware_correction_rad: float
    asynchronous_common_mode_correction_rad: float
    total_standard_error_rad: float
    ambiguity_candidates: tuple[IntegerAmbiguityCandidate, ...]


@dataclass(frozen=True, slots=True)
class GeometryPhaseReconstruction:
    state: Literal["available", "unavailable"]
    ambiguity_state: Literal["conditionally_unique", "ambiguous", "unavailable"]
    reasons: tuple[str, ...]
    points: tuple[GeometryPhasePoint, ...]
    geometry_digest: str | None
    calibration_digest: str | None


def _vector(value: tuple[float, float, float] | None) -> np.ndarray | None:
    if value is None:
        return None
    output = np.asarray(value, dtype=float)
    if output.shape != (3,) or not np.all(np.isfinite(output)):
        raise ValueError("ENU vectors must contain three finite values")
    return output


def _unit(value: tuple[float, float, float] | None) -> np.ndarray | None:
    output = _vector(value)
    if output is None:
        return None
    norm = float(np.linalg.norm(output))
    if not math.isclose(norm, 1.0, rel_tol=0, abs_tol=1e-6):
        raise ValueError("source directions must be unit ENU vectors")
    return output


def _wrap(value: float) -> float:
    return float(math.atan2(math.sin(value), math.cos(value)))


def _missing_inputs(
    geometry: CalibratedPhaseGeometry,
    calibration: ReceiverChainCalibration,
    observations: tuple[GeometryPhaseObservation, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if geometry.baseline_enu_m is None or geometry.baseline_standard_error_m is None:
        reasons.append("missing_phase_center_baseline_enu")
    if not geometry.receiver_mapping_verified:
        reasons.append("receiver_mapping_unverified")
    if not geometry.phase_centers_verified:
        reasons.append("rf_phase_centers_unverified")
    if not geometry.enu_pose_verified:
        reasons.append("fixture_to_enu_pose_unverified")
    if geometry.geometry_digest is None:
        reasons.append("geometry_authority_unbound")
    if (
        calibration.differential_group_delay_s is None
        or calibration.group_delay_standard_error_s is None
        or calibration.residual_double_difference_rad is None
        or calibration.residual_standard_error_rad is None
        or calibration.calibration_digest is None
    ):
        reasons.append("receiver_chain_phase_calibration_missing")
    if not calibration.measurement_truth_verified:
        reasons.append("receiver_chain_calibration_unverified")
    for observation in observations:
        if observation.association_uses_phase is not False:
            reasons.append("source_association_used_phase")
        if observation.low_direction_enu is None or observation.high_direction_enu is None:
            reasons.append("source_direction_track_missing")
        if not observation.direction_track_verified:
            reasons.append("source_direction_track_unverified")
        if observation.direction_standard_error_rad is None:
            reasons.append("source_direction_uncertainty_missing")
        if observation.low_frame_utc_ns != observation.high_frame_utc_ns and (
            observation.common_mode_rate_rad_s is None
            or observation.common_mode_rate_standard_error_rad_s is None
        ):
            reasons.append("asynchronous_frame_common_mode_uncalibrated")
    return tuple(dict.fromkeys(reasons))


def reconstruct_geometry_phase(
    geometry: CalibratedPhaseGeometry,
    calibration: ReceiverChainCalibration,
    observations: tuple[GeometryPhaseObservation, ...],
    *,
    ambiguity_sigma_gate: float = 3.0,
    maximum_ambiguity_candidates: int = 17,
) -> GeometryPhaseReconstruction:
    """Compare measured phase with calibrated geometry and retain cycle sets."""
    if not observations:
        return GeometryPhaseReconstruction(
            state="unavailable",
            ambiguity_state="unavailable",
            reasons=("no_phase_observations",),
            points=(),
            geometry_digest=geometry.geometry_digest,
            calibration_digest=calibration.calibration_digest,
        )
    if (
        not math.isfinite(ambiguity_sigma_gate)
        or ambiguity_sigma_gate <= 0
        or not 1 <= maximum_ambiguity_candidates <= 129
    ):
        raise ValueError("ambiguity bounds must be positive and finite")
    missing = _missing_inputs(geometry, calibration, observations)
    if missing:
        return GeometryPhaseReconstruction(
            state="unavailable",
            ambiguity_state="unavailable",
            reasons=missing,
            points=(),
            geometry_digest=geometry.geometry_digest,
            calibration_digest=calibration.calibration_digest,
        )

    baseline = _vector(geometry.baseline_enu_m)
    assert baseline is not None
    baseline_sigma = float(geometry.baseline_standard_error_m)
    group_delay_s = float(calibration.differential_group_delay_s)
    group_delay_sigma_s = float(calibration.group_delay_standard_error_s)
    residual_hw_rad = float(calibration.residual_double_difference_rad)
    residual_hw_sigma_rad = float(calibration.residual_standard_error_rad)
    calibration_scalars = (
        baseline_sigma,
        group_delay_s,
        group_delay_sigma_s,
        residual_hw_rad,
        residual_hw_sigma_rad,
    )
    if not all(math.isfinite(value) for value in calibration_scalars):
        raise ValueError("calibration scalars must be finite")
    if min(baseline_sigma, group_delay_sigma_s, residual_hw_sigma_rad) < 0:
        raise ValueError("calibration standard errors must be non-negative")

    points: list[GeometryPhasePoint] = []
    all_unique = calibration.absolute_cycle_referenced
    for observation in observations:
        if (
            not math.isfinite(observation.wrapped_double_difference_rad)
            or observation.measurement_standard_error_rad <= 0
            or not math.isfinite(observation.measurement_standard_error_rad)
            or not math.isfinite(observation.low_rf_hz)
            or not math.isfinite(observation.high_rf_hz)
            or observation.low_rf_hz <= 0
            or observation.high_rf_hz <= 0
        ):
            raise ValueError("phase observations must carry positive finite measurements")
        low_direction = _unit(observation.low_direction_enu)
        high_direction = _unit(observation.high_direction_enu)
        assert low_direction is not None and high_direction is not None
        direction_sigma = float(observation.direction_standard_error_rad)
        if direction_sigma < 0 or not math.isfinite(direction_sigma):
            raise ValueError("direction uncertainty must be finite and non-negative")

        wave_difference = (
            observation.high_rf_hz * high_direction - observation.low_rf_hz * low_direction
        )
        # With source direction s and b = r_RX1 - r_RX0, y1*conj(y0)
        # contributes +2*pi*f*b.s/c.  This observation is high-minus-low.
        predicted_rad = float(
            2.0 * math.pi * np.dot(baseline, wave_difference) / SPEED_OF_LIGHT_M_S
        )
        delta_frequency_hz = observation.high_rf_hz - observation.low_rf_hz
        hardware_rad = 2.0 * math.pi * group_delay_s * delta_frequency_hz + residual_hw_rad
        delta_time_s = (observation.high_frame_utc_ns - observation.low_frame_utc_ns) / 1e9
        if delta_time_s and (
            not math.isfinite(float(observation.common_mode_rate_rad_s))
            or not math.isfinite(float(observation.common_mode_rate_standard_error_rad_s))
            or float(observation.common_mode_rate_standard_error_rad_s) < 0
        ):
            raise ValueError("asynchronous common-mode calibration must be finite")
        asynchronous_rad = (
            0.0
            if delta_time_s == 0
            else float(observation.common_mode_rate_rad_s) * delta_time_s
        )
        asynchronous_sigma_rad = (
            0.0
            if delta_time_s == 0
            else abs(delta_time_s) * float(observation.common_mode_rate_standard_error_rad_s)
        )
        geometry_sigma_rad = 2.0 * math.pi / SPEED_OF_LIGHT_M_S * math.sqrt(
            (float(np.linalg.norm(wave_difference)) * baseline_sigma) ** 2
            + (
                float(np.linalg.norm(baseline))
                * direction_sigma
                * math.hypot(observation.high_rf_hz, observation.low_rf_hz)
            )
            ** 2
        )
        hardware_sigma_rad = math.hypot(
            2.0 * math.pi * abs(delta_frequency_hz) * group_delay_sigma_s,
            residual_hw_sigma_rad,
        )
        total_sigma_rad = math.sqrt(
            observation.measurement_standard_error_rad**2
            + geometry_sigma_rad**2
            + hardware_sigma_rad**2
            + asynchronous_sigma_rad**2
        )
        corrected_wrapped_rad = _wrap(
            observation.wrapped_double_difference_rad - hardware_rad - asynchronous_rad
        )
        center_cycles = round((predicted_rad - corrected_wrapped_rad) / (2.0 * math.pi))
        radius = max(1, math.ceil(ambiguity_sigma_gate * total_sigma_rad / (2.0 * math.pi)))
        radius = min(radius, (maximum_ambiguity_candidates - 1) // 2)
        candidates = []
        for cycles in range(center_cycles - radius, center_cycles + radius + 1):
            unwrapped_rad = corrected_wrapped_rad + 2.0 * math.pi * cycles
            residual_rad = unwrapped_rad - predicted_rad
            if (
                abs(residual_rad) <= ambiguity_sigma_gate * total_sigma_rad
                or cycles == center_cycles
            ):
                candidates.append(
                    IntegerAmbiguityCandidate(
                        cycles=cycles,
                        unwrapped_corrected_phase_rad=unwrapped_rad,
                        residual_rad=residual_rad,
                        normalized_residual=residual_rad / total_sigma_rad,
                    )
                )
        point = GeometryPhasePoint(
            utc_ns=observation.utc_ns,
            measured_wrapped_rad=_wrap(observation.wrapped_double_difference_rad),
            corrected_wrapped_rad=corrected_wrapped_rad,
            predicted_geometry_rad=predicted_rad,
            predicted_geometry_wrapped_rad=_wrap(predicted_rad),
            hardware_correction_rad=hardware_rad,
            asynchronous_common_mode_correction_rad=asynchronous_rad,
            total_standard_error_rad=total_sigma_rad,
            ambiguity_candidates=tuple(candidates),
        )
        points.append(point)
        all_unique = all_unique and len(candidates) == 1

    reasons = (
        ("cycle_choice_conditioned_on_calibrated_geometry_and_direction_tracks",)
        if all_unique
        else (
            "integer_cycles_not_uniquely_identified",
            *(
                ()
                if calibration.absolute_cycle_referenced
                else ("calibration_not_cycle_referenced",)
            ),
        )
    )
    return GeometryPhaseReconstruction(
        state="available",
        ambiguity_state="conditionally_unique" if all_unique else "ambiguous",
        reasons=reasons,
        points=tuple(points),
        geometry_digest=geometry.geometry_digest,
        calibration_digest=calibration.calibration_digest,
    )
