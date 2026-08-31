"""Immutable candidate-only pilot Doppler segment contracts."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1, StandardNativeSourceV2
from leo.contracts.standard_pipeline import StandardScientificStatus
from leo.contracts.states import StarlinkEdge

BoundedReason = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
_PILOT_FRAME_RATE_HZ = 750.0
_MODULO_PI_TOLERANCE = 1e-8


def _wrap_modulo_pi(value: float) -> float:
    return float((value + math.pi / 2) % math.pi - math.pi / 2)


def _phase_rms(values: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))


def _phase_concentration(values: tuple[float, ...]) -> float:
    mean_cos = sum(math.cos(2 * value) for value in values) / len(values)
    mean_sin = sum(math.sin(2 * value) for value in values) / len(values)
    return math.hypot(mean_cos, mean_sin)


def _stable_measurement_sample_tolerance(time_s: float, sample_rate_hz: int) -> float:
    """Bound sample error introduced by the persisted 12-significant-digit float policy."""

    if time_s == 0:
        return 1e-5
    decimal_exponent = math.floor(math.log10(abs(time_s))) - 11
    half_quantum_samples = 0.5 * 10**decimal_exponent * sample_rate_hz
    binary_roundoff_samples = 4 * math.ulp(time_s) * sample_rate_hz
    return max(1e-5, half_quantum_samples + binary_roundoff_samples)


class PilotDopplerSegmentConfigV1(ContractModel):
    """Bounded policy for local, complete-lattice pilot tracking windows."""

    schema_version: Literal[1] = 1
    model_version: Literal["piecewise-modulo-pi-pilot-doppler-v1"] = (
        "piecewise-modulo-pi-pilot-doppler-v1"
    )
    window_duration_s: Annotated[float, Field(gt=0, le=0.100)] = 0.075
    minimum_window_separation_s: Annotated[float, Field(gt=0, le=1.0)] = 0.075
    maximum_windows_per_track: Annotated[int, Field(ge=1, le=64)] = 16
    maximum_tracks: Annotated[int, Field(ge=1, le=64)] = 16
    maximum_residual_cfo_hz: Annotated[float, Field(gt=0, le=10_000)] = 2_000.0
    minimum_supported_frame_fraction: Annotated[float, Field(gt=0, le=1)] = 0.75
    maximum_supported_frame_gap_s: Annotated[float, Field(gt=0, le=0.050)] = 0.0041
    minimum_median_coherence_margin: Annotated[float, Field(ge=0, le=1)] = 0.0
    maximum_frequency_line_rms_hz: Annotated[float, Field(gt=0)] = 75.0
    maximum_held_out_frequency_rms_hz: Annotated[float, Field(gt=0)] = 100.0
    maximum_local_kalman_rate_disagreement_hz_s: Annotated[float, Field(gt=0)] = 1_000.0

    @field_validator(
        "window_duration_s",
        "minimum_window_separation_s",
        "maximum_residual_cfo_hz",
        "minimum_supported_frame_fraction",
        "maximum_supported_frame_gap_s",
        "minimum_median_coherence_margin",
        "maximum_frequency_line_rms_hz",
        "maximum_held_out_frequency_rms_hz",
        "maximum_local_kalman_rate_disagreement_hz_s",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("pilot Doppler segment configuration must be finite")
        return value

    @model_validator(mode="after")
    def _window_geometry_is_coherent(self) -> Self:
        if self.minimum_window_separation_s < self.window_duration_s:
            raise ValueError("pilot Doppler analysis windows must not overlap")
        return self

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class PilotDopplerSegmentV1(ContractModel):
    """One independently qualified 50--75 ms receiver-relative carrier segment."""

    schema_version: Literal[1] = 1
    segment_index: Annotated[int, Field(ge=0)]
    source_trajectory_id: Sha256Digest
    source_branch_id: Sha256Digest
    source_probe_sample_start: Annotated[int, Field(ge=0)]
    start_time_s: Annotated[float, Field(ge=0)]
    end_time_s: Annotated[float, Field(ge=0)]
    reference_time_s: Annotated[float, Field(ge=0)]
    lattice_frame_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_count: Annotated[int, Field(ge=0, le=100)]
    phase_update_count: Annotated[int, Field(ge=0, le=100)]
    frequency_update_count: Annotated[int, Field(ge=0, le=100)]
    timing_update_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_fraction: Annotated[float, Field(ge=0, le=1)]
    maximum_supported_frame_gap_s: Annotated[float, Field(ge=0)] | None
    median_exact_coherence: Annotated[float, Field(ge=0, le=1)] | None
    median_control_coherence: Annotated[float, Field(ge=0, le=1)] | None
    median_coherence_margin: Annotated[float, Field(ge=-1, le=1)] | None
    phase_innovation_rms_rad: Annotated[float, Field(ge=0)] | None
    phase_ambiguity_transition_count: Annotated[int, Field(ge=0, le=100)]
    local_doppler_rate_hz_s: float | None
    local_doppler_rate_sigma_hz_s: Annotated[float, Field(ge=0)] | None
    kalman_doppler_rate_hz_s: float | None
    frozen_doppler_rate_hz_s: float
    local_minus_kalman_rate_hz_s: float | None
    local_minus_frozen_rate_hz_s: float | None
    local_cfo_at_reference_hz: float | None
    frozen_cfo_at_reference_hz: float
    carrier_bias_at_reference_hz: float | None
    carrier_bias_change_hz: float | None
    frequency_line_rms_hz: Annotated[float, Field(ge=0)] | None
    held_out_frequency_rms_hz: Annotated[float, Field(ge=0)] | None
    final_fractional_timing_samples: float | None
    final_timing_rate_s_s: float | None
    phase_lock_qualified: bool
    qualified: bool
    qualification_failures: Annotated[tuple[BoundedReason, ...], Field(max_length=16)]

    @field_validator(
        "start_time_s",
        "end_time_s",
        "reference_time_s",
        "supported_frame_fraction",
        "maximum_supported_frame_gap_s",
        "median_exact_coherence",
        "median_control_coherence",
        "median_coherence_margin",
        "phase_innovation_rms_rad",
        "local_doppler_rate_hz_s",
        "local_doppler_rate_sigma_hz_s",
        "kalman_doppler_rate_hz_s",
        "frozen_doppler_rate_hz_s",
        "local_minus_kalman_rate_hz_s",
        "local_minus_frozen_rate_hz_s",
        "local_cfo_at_reference_hz",
        "frozen_cfo_at_reference_hz",
        "carrier_bias_at_reference_hz",
        "carrier_bias_change_hz",
        "frequency_line_rms_hz",
        "held_out_frequency_rms_hz",
        "final_fractional_timing_samples",
        "final_timing_rate_s_s",
    )
    @classmethod
    def _finite_metrics(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot Doppler segment metrics must be finite")
        return value

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        if not self.start_time_s <= self.reference_time_s <= self.end_time_s:
            raise ValueError("pilot Doppler segment reference lies outside its interval")
        if self.supported_frame_count > self.lattice_frame_count:
            raise ValueError("supported pilot frames exceed complete lattice frames")
        if any(
            value > self.lattice_frame_count
            for value in (
                self.phase_update_count,
                self.frequency_update_count,
                self.timing_update_count,
            )
        ):
            raise ValueError("pilot Doppler update count exceeds frame inventory")
        if self.qualified != (not self.qualification_failures):
            raise ValueError("pilot Doppler qualification flag and failures disagree")
        return self


class PilotDopplerTrajectorySummaryV1(ContractModel):
    schema_version: Literal[1] = 1
    source_trajectory_id: Sha256Digest
    source_branch_id: Sha256Digest
    candidate_window_count: Annotated[int, Field(ge=0, le=64)]
    analyzed_segment_count: Annotated[int, Field(ge=0, le=64)]
    qualified_segment_count: Annotated[int, Field(ge=0, le=64)]
    median_qualified_local_rate_hz_s: float | None
    median_qualified_kalman_rate_hz_s: float | None
    median_qualified_frozen_rate_hz_s: float | None

    @field_validator(
        "median_qualified_local_rate_hz_s",
        "median_qualified_kalman_rate_hz_s",
        "median_qualified_frozen_rate_hz_s",
    )
    @classmethod
    def _finite_summaries(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot Doppler trajectory summaries must be finite")
        return value

    @model_validator(mode="after")
    def _counts_are_closed(self) -> Self:
        if not (
            self.qualified_segment_count
            <= self.analyzed_segment_count
            <= self.candidate_window_count
        ):
            raise ValueError("pilot Doppler trajectory segment accounting is inconsistent")
        return self


class StandardPilotDopplerSegmentsV1(ContractModel):
    """Additive Standard product for local pilot Doppler-rate monitoring."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-pilot-doppler-segments-v1"] = (
        "standard-pilot-doppler-segments-v1"
    )
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    final_trajectory_bank_digest: Sha256Digest
    kalman_tracking_digest: Sha256Digest
    config: PilotDopplerSegmentConfigV1
    config_digest: Sha256Digest
    source_track_count: Annotated[int, Field(ge=0)]
    analyzed_track_count: Annotated[int, Field(ge=0, le=64)]
    truncated_track_count: Annotated[int, Field(ge=0)]
    candidate_window_count: Annotated[int, Field(ge=0, le=4096)]
    analyzed_segment_count: Annotated[int, Field(ge=0, le=4096)]
    qualified_segment_count: Annotated[int, Field(ge=0, le=4096)]
    trajectory_summaries: Annotated[
        tuple[PilotDopplerTrajectorySummaryV1, ...], Field(max_length=64)
    ]
    segments: Annotated[tuple[PilotDopplerSegmentV1, ...], Field(max_length=4096)]
    status: StandardScientificStatus
    reason: BoundedReason
    carrier_phase_period_rad: float = math.pi
    carrier_discontinuities_are_piecewise_bias: Literal[True] = True
    frame_timing_is_receiver_relative: Literal[True] = True
    absolute_carrier_phase_resolved: Literal[False] = False
    candidate_only: Literal[True] = True
    known_pilots_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        if self.carrier_phase_period_rad != math.pi:
            raise ValueError("pilot Doppler carrier phase must remain modulo pi")
        if self.config_digest != self.config.digest:
            raise ValueError("pilot Doppler segment configuration digest disagrees")
        if (
            self.analyzed_track_count + self.truncated_track_count != self.source_track_count
            or self.analyzed_track_count != len(self.trajectory_summaries)
            or self.analyzed_segment_count != len(self.segments)
            or self.qualified_segment_count != sum(item.qualified for item in self.segments)
            or self.candidate_window_count
            != sum(item.candidate_window_count for item in self.trajectory_summaries)
        ):
            raise ValueError("pilot Doppler segment product accounting is inconsistent")
        trajectory_ids = tuple(item.source_trajectory_id for item in self.trajectory_summaries)
        if trajectory_ids != tuple(sorted(set(trajectory_ids))):
            raise ValueError("pilot Doppler trajectory summaries must be unique and ordered")
        indexes = tuple(item.segment_index for item in self.segments)
        if indexes != tuple(range(len(self.segments))):
            raise ValueError("pilot Doppler segment indexes must be contiguous and ordered")
        document = self.model_dump(mode="json")
        document.pop("content_digest")
        if self.content_digest != canonical_digest(document):
            raise ValueError("pilot Doppler segment content digest does not match")
        return self


class PilotDopplerSegmentConfigV2(PilotDopplerSegmentConfigV1):
    """Additive policy selecting the independently reacquiring phase loop."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    model_version: Literal["piecewise-modulo-pi-pilot-doppler-v2"] = (  # type: ignore[assignment]  # fmt: skip
        "piecewise-modulo-pi-pilot-doppler-v2"  # type: ignore[assignment]
    )
    independent_phase_reacquisition: Literal[True] = True
    kalman_rate_disagreement_gate_applied: Literal[False] = False


class PilotDopplerSegmentV2(PilotDopplerSegmentV1):
    """One V2 locklet with explicit filter-reacquisition evidence."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    reacquisition_count: Annotated[int, Field(ge=0, le=100)]
    filter_version: Literal["pilot-pnt-kalman-v2"] = "pilot-pnt-kalman-v2"
    primary_rate_estimator: Literal["direct-local-frequency-line"] = "direct-local-frequency-line"
    kalman_rate_is_diagnostic_only: Literal[True] = True


class PilotDopplerTrajectorySummaryV2(PilotDopplerTrajectorySummaryV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    reacquisition_count: Annotated[int, Field(ge=0, le=6_400)]


class StandardPilotDopplerSegmentsV2(StandardPilotDopplerSegmentsV1):
    """Corrected additive locklet product; V1 remains byte-readable."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    algorithm_version: Literal["standard-pilot-doppler-segments-v2"] = (  # type: ignore[assignment]  # fmt: skip
        "standard-pilot-doppler-segments-v2"  # type: ignore[assignment]
    )
    config: PilotDopplerSegmentConfigV2
    trajectory_summaries: Annotated[
        tuple[PilotDopplerTrajectorySummaryV2, ...], Field(max_length=64)
    ]
    segments: Annotated[tuple[PilotDopplerSegmentV2, ...], Field(max_length=4096)]
    phase_reacquisition_policy: Literal["independent-phase-v2"] = "independent-phase-v2"
    legacy_kalman_is_diagnostic_only: Literal[True] = True
    primary_rate_estimator: Literal["direct-local-frequency-line"] = "direct-local-frequency-line"
    kalman_rate_is_diagnostic_only: Literal[True] = True


class PilotPhaseLockletConfigV1(ContractModel):
    """Immutable policy for prefix-trained, held-out carrier-phase evidence."""

    schema_version: Literal[1] = 1
    model_version: Literal["prefix-trained-held-out-modulo-pi-phase-v1"] = (
        "prefix-trained-held-out-modulo-pi-phase-v1"
    )
    minimum_exact_coherence: Annotated[float, Field(ge=0, le=1)] = 0.02
    minimum_coherence_margin: Annotated[float, Field(ge=-1, le=1)] = 0.0
    minimum_channel_similarity: Annotated[float, Field(ge=0, le=1)] = 0.65
    training_interval_count: Annotated[int, Field(ge=3, le=40)] = 12
    minimum_held_out_interval_count: Annotated[int, Field(ge=3, le=80)] = 20
    phase_innovation_gate_rad: Annotated[float, Field(gt=0, le=math.pi / 2)] = 1.2
    minimum_held_out_gate_pass_fraction: Annotated[float, Field(ge=0, le=1)] = 0.80
    minimum_training_circular_concentration: Annotated[float, Field(ge=0, le=1)] = 0.65
    maximum_training_rms_rad: Annotated[float, Field(gt=0, le=math.pi / 2)] = 0.50
    maximum_held_out_rms_rad: Annotated[float, Field(gt=0, le=math.pi / 2)] = 0.50
    maximum_fractional_timing_samples: Annotated[float, Field(gt=0, le=2)] = 0.75
    fractional_timing_grid_points: Annotated[int, Field(ge=3, le=4_001)] = 301

    @field_validator(
        "minimum_exact_coherence",
        "minimum_coherence_margin",
        "minimum_channel_similarity",
        "phase_innovation_gate_rad",
        "minimum_held_out_gate_pass_fraction",
        "minimum_training_circular_concentration",
        "maximum_training_rms_rad",
        "maximum_held_out_rms_rad",
        "maximum_fractional_timing_samples",
    )
    @classmethod
    def _phase_policy_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("pilot phase-locklet configuration must be finite")
        return value

    @field_validator("fractional_timing_grid_points")
    @classmethod
    def _phase_grid_is_odd(cls, value: int) -> int:
        if value % 2 == 0:
            raise ValueError("pilot phase-locklet grids must have odd sizes")
        return value

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class PilotPhaseLockletIntervalV1(ContractModel):
    """One globally located, one-step modulo-pi phase innovation."""

    schema_version: Literal[1] = 1
    previous_frame_index: Annotated[int, Field(ge=0, le=100)]
    frame_index: Annotated[int, Field(ge=1, le=100)]
    previous_global_reference_device_sample: Annotated[float, Field(ge=0)]
    global_reference_device_sample: Annotated[float, Field(ge=0)]
    time_delta_s: Annotated[float, Field(gt=0)]
    channel_similarity: Annotated[float, Field(ge=0, le=1)]
    previous_intraframe_residual_cfo_hz: float
    intraframe_residual_cfo_hz: float
    measured_phase_advance_modulo_pi_rad: float
    expected_phase_advance_modulo_pi_rad: float
    uncentered_innovation_modulo_pi_rad: float
    centered_innovation_modulo_pi_rad: float | None
    training: bool
    held_out: bool
    gate_passed: bool

    @field_validator(
        "previous_global_reference_device_sample",
        "global_reference_device_sample",
        "time_delta_s",
        "channel_similarity",
        "previous_intraframe_residual_cfo_hz",
        "intraframe_residual_cfo_hz",
        "measured_phase_advance_modulo_pi_rad",
        "expected_phase_advance_modulo_pi_rad",
        "uncentered_innovation_modulo_pi_rad",
        "centered_innovation_modulo_pi_rad",
    )
    @classmethod
    def _phase_interval_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot phase-locklet interval must be finite")
        return value

    @model_validator(mode="after")
    def _phase_interval_is_closed(self) -> Self:
        if self.frame_index != self.previous_frame_index + 1:
            raise ValueError("pilot phase-locklet interval must compare adjacent frames")
        if self.global_reference_device_sample <= self.previous_global_reference_device_sample:
            raise ValueError("pilot phase-locklet interval device coordinates regressed")
        if self.training and self.held_out:
            raise ValueError("pilot phase-locklet interval cannot be training and held out")
        if self.training and (self.centered_innovation_modulo_pi_rad is None or self.gate_passed):
            raise ValueError("pilot phase-locklet training interval is not closed evidence")
        if self.held_out and self.centered_innovation_modulo_pi_rad is None:
            raise ValueError("pilot phase-locklet held-out interval lacks a scored innovation")
        if (
            not self.training
            and not self.held_out
            and self.centered_innovation_modulo_pi_rad is not None
        ):
            raise ValueError("unclassified pilot phase interval carries a centered innovation")
        if self.gate_passed and (
            not self.held_out or self.centered_innovation_modulo_pi_rad is None
        ):
            raise ValueError("pilot phase-locklet gate pass lacks scored held-out evidence")
        half_period = math.pi / 2
        for value in (
            self.measured_phase_advance_modulo_pi_rad,
            self.expected_phase_advance_modulo_pi_rad,
            self.uncentered_innovation_modulo_pi_rad,
            self.centered_innovation_modulo_pi_rad,
        ):
            if value is not None and not -half_period <= value < half_period:
                raise ValueError("pilot phase-locklet angle escaped modulo-pi authority")
        expected_innovation = _wrap_modulo_pi(
            self.measured_phase_advance_modulo_pi_rad - self.expected_phase_advance_modulo_pi_rad
        )
        if not math.isclose(
            self.uncentered_innovation_modulo_pi_rad,
            expected_innovation,
            rel_tol=0,
            abs_tol=_MODULO_PI_TOLERANCE,
        ):
            raise ValueError("pilot phase-locklet innovation does not close")
        expected_advance = _wrap_modulo_pi(
            2
            * math.pi
            * 0.5
            * (self.previous_intraframe_residual_cfo_hz + self.intraframe_residual_cfo_hz)
            * self.time_delta_s
        )
        if not math.isclose(
            self.expected_phase_advance_modulo_pi_rad,
            expected_advance,
            rel_tol=0,
            abs_tol=_MODULO_PI_TOLERANCE,
        ):
            raise ValueError("pilot phase-locklet expected advance does not close to CFO")
        return self


class PilotDopplerSegmentV3(ContractModel):
    """Independent CFO/rate plus corrected one-step carrier-phase evidence."""

    schema_version: Literal[3] = 3
    continuity_segment_index: Annotated[int, Field(ge=0)]
    source_v2_pilot_doppler_content_digest: Sha256Digest
    source_v2_segment_index: Annotated[int, Field(ge=0)]
    source_trajectory_id: Sha256Digest
    source_branch_id: Sha256Digest
    global_source_probe_sample_start: Annotated[int, Field(ge=0)]
    global_start_time_s: Annotated[float, Field(ge=0)]
    global_end_time_s: Annotated[float, Field(gt=0)]
    global_reference_time_s: Annotated[float, Field(ge=0)]
    lattice_frame_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_fraction: Annotated[float, Field(ge=0, le=1)]
    maximum_supported_frame_gap_s: Annotated[float | None, Field(ge=0)]
    median_exact_coherence: Annotated[float | None, Field(ge=0, le=1)]
    median_control_coherence: Annotated[float | None, Field(ge=0, le=1)]
    median_coherence_margin: Annotated[float | None, Field(ge=-1, le=1)]
    local_cfo_at_reference_hz: float | None
    local_doppler_rate_hz_s: float | None
    local_doppler_rate_sigma_hz_s: Annotated[float | None, Field(ge=0)]
    frequency_line_rms_hz: Annotated[float | None, Field(ge=0)]
    held_out_frequency_rms_hz: Annotated[float | None, Field(ge=0)]
    frozen_cfo_at_reference_hz: float
    frozen_doppler_rate_hz_s: float
    local_minus_frozen_rate_hz_s: float | None
    primary_cfo_source: Literal["independent-intraframe-pilot-slope"] = (
        "independent-intraframe-pilot-slope"
    )
    primary_rate_estimator: Literal["direct-local-frequency-line"] = "direct-local-frequency-line"
    legacy_v2_phase_lock_qualified: bool
    legacy_v2_qualified: bool
    legacy_v2_phase_update_count: Annotated[int, Field(ge=0, le=100)]
    legacy_v2_reacquisition_count: Annotated[int, Field(ge=0, le=100)]
    legacy_v2_phase_innovation_rms_rad: Annotated[float | None, Field(ge=0)]
    legacy_v2_kalman_doppler_rate_hz_s: float | None
    legacy_v2_filter_version: Literal["pilot-pnt-kalman-v2"] = "pilot-pnt-kalman-v2"
    complete_frame_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_count: Annotated[int, Field(ge=0, le=100)]
    supported_frame_indexes: Annotated[
        tuple[Annotated[int, Field(ge=0, le=100)], ...],
        Field(max_length=100),
    ]
    adjacent_supported_interval_count: Annotated[int, Field(ge=0, le=100)]
    training_interval_count: Annotated[int, Field(ge=0, le=40)]
    held_out_interval_count: Annotated[int, Field(ge=0, le=100)]
    held_out_gate_pass_count: Annotated[int, Field(ge=0, le=100)]
    phase_bias_hz_modulo: Annotated[float | None, Field(ge=-187.5, lt=187.5)]
    phase_bias_period_hz: float = 375.0
    training_phase_rms_rad: Annotated[float | None, Field(ge=0)]
    training_circular_concentration: Annotated[float | None, Field(ge=0, le=1)]
    held_out_gate_pass_fraction: Annotated[float | None, Field(ge=0, le=1)]
    held_out_phase_rms_rad: Annotated[float | None, Field(ge=0)]
    held_out_maximum_absolute_innovation_rad: Annotated[float | None, Field(ge=0)]
    held_out_circular_concentration: Annotated[float | None, Field(ge=0, le=1)]
    phase_trackability_qualified: bool
    phase_trackability_reason: BoundedReason
    qualified: bool
    qualification_failures: Annotated[tuple[BoundedReason, ...], Field(max_length=16)]
    intervals: Annotated[tuple[PilotPhaseLockletIntervalV1, ...], Field(max_length=100)]
    phase_frequency_nuisance_scope: Literal["locklet-local-modulo-frame-rate-over-two-v1"] = (
        "locklet-local-modulo-frame-rate-over-two-v1"
    )
    nuisance_transferable_to_cfo_or_rate: Literal[False] = False
    carrier_phase_period_rad: float = math.pi
    absolute_carrier_phase_resolved: Literal[False] = False
    phase_does_not_update_cfo_or_rate: Literal[True] = True
    held_out_used_for_nuisance_fit: Literal[False] = False
    adjacent_one_step_innovations: Literal[True] = True
    held_out_gate_does_not_control_future_reference: Literal[True] = True
    candidate_only: Literal[True] = True

    @field_validator(
        "global_start_time_s",
        "global_end_time_s",
        "global_reference_time_s",
        "maximum_supported_frame_gap_s",
        "median_exact_coherence",
        "median_control_coherence",
        "median_coherence_margin",
        "local_cfo_at_reference_hz",
        "local_doppler_rate_hz_s",
        "local_doppler_rate_sigma_hz_s",
        "frequency_line_rms_hz",
        "held_out_frequency_rms_hz",
        "frozen_cfo_at_reference_hz",
        "frozen_doppler_rate_hz_s",
        "local_minus_frozen_rate_hz_s",
        "legacy_v2_phase_innovation_rms_rad",
        "legacy_v2_kalman_doppler_rate_hz_s",
        "phase_bias_hz_modulo",
        "training_phase_rms_rad",
        "training_circular_concentration",
        "held_out_gate_pass_fraction",
        "held_out_phase_rms_rad",
        "held_out_maximum_absolute_innovation_rad",
        "held_out_circular_concentration",
    )
    @classmethod
    def _v3_metric_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("pilot Doppler V3 metric must be finite")
        return value

    @model_validator(mode="after")
    def _v3_segment_is_closed(self) -> Self:
        if not self.global_start_time_s <= self.global_reference_time_s <= self.global_end_time_s:
            raise ValueError("pilot Doppler V3 reference lies outside its locklet")
        if self.supported_frame_count > self.complete_frame_count:
            raise ValueError("pilot Doppler V3 supported frames exceed complete frames")
        if self.supported_frame_count != len(self.supported_frame_indexes):
            raise ValueError("pilot Doppler V3 supported-frame inventory does not close")
        if self.supported_frame_indexes != tuple(sorted(set(self.supported_frame_indexes))):
            raise ValueError("pilot Doppler V3 supported frame indexes must be unique and ordered")
        if any(index >= self.complete_frame_count for index in self.supported_frame_indexes):
            raise ValueError("pilot Doppler V3 supported frame escaped complete-frame inventory")
        if self.complete_frame_count != self.lattice_frame_count:
            raise ValueError("pilot Doppler V3 complete-frame inventory changed V2 evidence")
        expected_supported_fraction = (
            self.supported_frame_count / self.complete_frame_count
            if self.complete_frame_count
            else 0.0
        )
        if not math.isclose(
            self.supported_frame_fraction,
            expected_supported_fraction,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("pilot Doppler V3 supported-frame fraction does not close")
        if self.adjacent_supported_interval_count != len(self.intervals):
            raise ValueError("pilot Doppler V3 adjacent interval inventory does not close")
        interval_keys = tuple(
            (item.previous_frame_index, item.frame_index) for item in self.intervals
        )
        if interval_keys != tuple(sorted(set(interval_keys))):
            raise ValueError("pilot Doppler V3 intervals must be unique and chronological")
        expected_interval_keys = tuple(
            (previous, current)
            for previous, current in zip(
                self.supported_frame_indexes,
                self.supported_frame_indexes[1:],
                strict=False,
            )
            if current == previous + 1
        )
        if interval_keys != expected_interval_keys:
            raise ValueError(
                "pilot Doppler V3 interval inventory omitted an adjacent supported-frame pair"
            )
        if self.adjacent_supported_interval_count > max(0, self.supported_frame_count - 1):
            raise ValueError("pilot Doppler V3 adjacent intervals exceed supported frames")
        if self.training_interval_count + self.held_out_interval_count > len(self.intervals):
            raise ValueError("pilot Doppler V3 interval accounting exceeds evidence")
        if self.held_out_gate_pass_count > self.held_out_interval_count:
            raise ValueError("pilot Doppler V3 held-out gate passes exceed interval support")
        if self.training_interval_count != sum(item.training for item in self.intervals):
            raise ValueError("pilot Doppler V3 training accounting does not close")
        if self.held_out_interval_count != sum(item.held_out for item in self.intervals):
            raise ValueError("pilot Doppler V3 held-out accounting does not close")
        if self.held_out_gate_pass_count != sum(item.gate_passed for item in self.intervals):
            raise ValueError("pilot Doppler V3 phase-gate accounting does not close")
        training_residuals = tuple(
            item.centered_innovation_modulo_pi_rad
            for item in self.intervals
            if item.training and item.centered_innovation_modulo_pi_rad is not None
        )
        held_out_residuals = tuple(
            item.centered_innovation_modulo_pi_rad
            for item in self.intervals
            if item.held_out and item.centered_innovation_modulo_pi_rad is not None
        )
        if self.held_out_interval_count:
            if any(
                value is None
                for value in (
                    self.held_out_gate_pass_fraction,
                    self.held_out_phase_rms_rad,
                    self.held_out_maximum_absolute_innovation_rad,
                    self.held_out_circular_concentration,
                )
            ):
                raise ValueError("pilot Doppler V3 held-out aggregate is incomplete")
            expected_gate_fraction = self.held_out_gate_pass_count / self.held_out_interval_count
            if not math.isclose(
                self.held_out_gate_pass_fraction or 0.0,
                expected_gate_fraction,
                rel_tol=0,
                abs_tol=1e-12,
            ):
                raise ValueError("pilot Doppler V3 held-out gate fraction does not close")
            expected_held_out_rms = _phase_rms(held_out_residuals)
            expected_held_out_maximum = max(abs(value) for value in held_out_residuals)
            expected_held_out_concentration = _phase_concentration(held_out_residuals)
            for name, measured, expected in (
                ("RMS", self.held_out_phase_rms_rad, expected_held_out_rms),
                (
                    "maximum innovation",
                    self.held_out_maximum_absolute_innovation_rad,
                    expected_held_out_maximum,
                ),
                (
                    "concentration",
                    self.held_out_circular_concentration,
                    expected_held_out_concentration,
                ),
            ):
                if measured is None or not math.isclose(
                    measured,
                    expected,
                    rel_tol=1e-9,
                    abs_tol=_MODULO_PI_TOLERANCE,
                ):
                    raise ValueError(f"pilot Doppler V3 held-out {name} does not close")
        elif any(
            value is not None
            for value in (
                self.held_out_gate_pass_fraction,
                self.held_out_phase_rms_rad,
                self.held_out_maximum_absolute_innovation_rad,
                self.held_out_circular_concentration,
            )
        ):
            raise ValueError("pilot Doppler V3 empty held-out set carries aggregate metrics")
        if self.phase_bias_hz_modulo is None:
            if (
                self.training_interval_count
                or self.held_out_interval_count
                or any(item.training or item.held_out for item in self.intervals)
                or any(
                    value is not None
                    for value in (
                        self.training_phase_rms_rad,
                        self.training_circular_concentration,
                    )
                )
            ):
                raise ValueError("pilot Doppler V3 missing nuisance carries training metrics")
        elif (
            not self.training_interval_count
            or self.training_phase_rms_rad is None
            or self.training_circular_concentration is None
        ):
            raise ValueError("pilot Doppler V3 fitted nuisance lacks training evidence")
        else:
            if self.training_interval_count + self.held_out_interval_count != len(self.intervals):
                raise ValueError("pilot Doppler V3 fitted nuisance has unclassified intervals")
            resultant_cos = (
                sum(
                    math.cos(2 * item.uncentered_innovation_modulo_pi_rad)
                    for item in self.intervals
                    if item.training
                )
                / self.training_interval_count
            )
            resultant_sin = (
                sum(
                    math.sin(2 * item.uncentered_innovation_modulo_pi_rad)
                    for item in self.intervals
                    if item.training
                )
                / self.training_interval_count
            )
            doubled_angle = math.atan2(resultant_sin, resultant_cos)
            if math.isclose(abs(doubled_angle), math.pi, abs_tol=1e-12):
                doubled_angle = -math.pi
            expected_bias = _PILOT_FRAME_RATE_HZ * doubled_angle / (4 * math.pi)
            if expected_bias >= _PILOT_FRAME_RATE_HZ / 4:
                expected_bias -= _PILOT_FRAME_RATE_HZ / 2
            if not math.isclose(
                self.phase_bias_hz_modulo,
                expected_bias,
                rel_tol=1e-9,
                abs_tol=1e-8,
            ):
                raise ValueError("pilot Doppler V3 phase nuisance does not close")
            for interval in self.intervals:
                if not interval.training and not interval.held_out:
                    continue
                expected_centered = _wrap_modulo_pi(
                    interval.uncentered_innovation_modulo_pi_rad
                    - 2 * math.pi * self.phase_bias_hz_modulo / _PILOT_FRAME_RATE_HZ
                )
                if interval.centered_innovation_modulo_pi_rad is None or not math.isclose(
                    interval.centered_innovation_modulo_pi_rad,
                    expected_centered,
                    rel_tol=0,
                    abs_tol=_MODULO_PI_TOLERANCE,
                ):
                    raise ValueError("pilot Doppler V3 centered innovation does not close")
            expected_training_rms = _phase_rms(training_residuals)
            expected_training_concentration = _phase_concentration(training_residuals)
            if not math.isclose(
                self.training_phase_rms_rad,
                expected_training_rms,
                rel_tol=1e-9,
                abs_tol=_MODULO_PI_TOLERANCE,
            ) or not math.isclose(
                self.training_circular_concentration,
                expected_training_concentration,
                rel_tol=1e-9,
                abs_tol=_MODULO_PI_TOLERANCE,
            ):
                raise ValueError("pilot Doppler V3 training aggregates do not close")
        if (self.local_doppler_rate_hz_s is None) != (
            self.local_minus_frozen_rate_hz_s is None
        ) or (
            self.local_doppler_rate_hz_s is not None
            and self.local_minus_frozen_rate_hz_s is not None
            and not math.isclose(
                self.local_minus_frozen_rate_hz_s,
                self.local_doppler_rate_hz_s - self.frozen_doppler_rate_hz_s,
                rel_tol=1e-10,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("pilot Doppler V3 local-minus-frozen rate does not close")
        if self.qualified != (not self.qualification_failures):
            raise ValueError("pilot Doppler V3 qualification flag and failures disagree")
        phase_failure = "held-out modulo-pi phase trackability did not qualify"
        if (phase_failure in self.qualification_failures) == self.phase_trackability_qualified:
            raise ValueError("pilot Doppler V3 phase flag and qualification failures disagree")
        if self.carrier_phase_period_rad != math.pi:
            raise ValueError("pilot Doppler V3 carrier phase must remain modulo pi")
        if self.phase_bias_period_hz != 375.0:
            raise ValueError("pilot Doppler V3 phase nuisance must remain modulo 375 Hz")
        qualified_reason = "qualified held-out adjacent modulo-pi phase trackability"
        if self.phase_trackability_qualified:
            if (
                self.phase_bias_hz_modulo is None
                or not self.held_out_interval_count
                or self.phase_trackability_reason != qualified_reason
            ):
                raise ValueError("pilot Doppler V3 qualified phase lacks closed evidence")
        elif self.phase_trackability_reason == qualified_reason:
            raise ValueError("pilot Doppler V3 failed phase carries a qualified reason")
        return self


class StandardPilotDopplerSegmentsV3(ContractModel):
    """Path-wide additive V3 evidence; embedded V2 products remain immutable."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["standard-native-pilot-doppler-segments-v3"] = (
        "standard-native-pilot-doppler-segments-v3"
    )
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    stateful_path_product_digest: Sha256Digest
    stateful_path_digest: Sha256Digest
    science_configuration_digest: Sha256Digest
    phase_config: PilotPhaseLockletConfigV1
    phase_config_digest: Sha256Digest
    source_stateful_science_status: Literal[
        "complete",
        "partial_coverage",
        "unavailable_global_schedule",
    ]
    bounded_local_track_truncation_present: bool
    continuity_segment_count: Annotated[int, Field(ge=1)]
    analyzed_continuity_segment_count: Annotated[int, Field(ge=0)]
    source_v2_locklet_count: Annotated[int, Field(ge=0, le=4096)]
    corrected_phase_trackability_count: Annotated[int, Field(ge=0, le=4096)]
    qualified_segment_count: Annotated[int, Field(ge=0, le=4096)]
    segments: Annotated[tuple[PilotDopplerSegmentV3, ...], Field(max_length=4096)]
    status: StandardScientificStatus
    reason: BoundedReason
    primary_cfo_source: Literal["independent-intraframe-pilot-slope"] = (
        "independent-intraframe-pilot-slope"
    )
    primary_rate_estimator: Literal["direct-local-frequency-line"] = "direct-local-frequency-line"
    phase_trackability_method: Literal["prefix-trained-held-out-one-step-phase-v1"] = (
        "prefix-trained-held-out-one-step-phase-v1"
    )
    phase_frequency_nuisance_scope: Literal["locklet-local-modulo-frame-rate-over-two-v1"] = (
        "locklet-local-modulo-frame-rate-over-two-v1"
    )
    nuisance_transferable_to_cfo_or_rate: Literal[False] = False
    held_out_used_for_nuisance_fit: Literal[False] = False
    open_loop_absolute_phase_prediction_claimed: Literal[False] = False
    absolute_carrier_phase_resolved: Literal[False] = False
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _v3_product_is_closed(self) -> Self:
        if self.phase_config_digest != self.phase_config.digest:
            raise ValueError("pilot Doppler V3 phase configuration digest disagrees")
        if self.continuity_segment_count != len(self.source.continuity_segments):
            raise ValueError("pilot Doppler V3 omitted continuity authority")
        if self.analyzed_continuity_segment_count > self.continuity_segment_count:
            raise ValueError("pilot Doppler V3 analyzed continuity count exceeds authority")
        if self.source_v2_locklet_count != len(self.segments):
            raise ValueError("pilot Doppler V3 source-locklet accounting does not close")
        if self.corrected_phase_trackability_count != sum(
            item.phase_trackability_qualified for item in self.segments
        ):
            raise ValueError("pilot Doppler V3 phase-trackability accounting does not close")
        if self.qualified_segment_count != sum(item.qualified for item in self.segments):
            raise ValueError("pilot Doppler V3 qualification accounting does not close")
        ordering = tuple(
            (
                item.continuity_segment_index,
                item.global_source_probe_sample_start,
                item.source_trajectory_id,
            )
            for item in self.segments
        )
        if ordering != tuple(sorted(ordering)) or len(ordering) != len(set(ordering)):
            raise ValueError("pilot Doppler V3 segments must be unique and globally ordered")
        for item in self.segments:
            if item.continuity_segment_index >= self.continuity_segment_count:
                raise ValueError("pilot Doppler V3 segment escaped continuity authority")
            authoritative = self.source.continuity_segments[item.continuity_segment_index]
            if not (
                authoritative.device_sample_start
                <= item.global_source_probe_sample_start
                < authoritative.device_sample_stop
            ):
                raise ValueError("pilot Doppler V3 locklet escaped its continuity segment")
            segment_sample_start = item.global_start_time_s * self.source.sample_rate_hz
            segment_sample_stop = item.global_end_time_s * self.source.sample_rate_hz
            start_tolerance = _stable_measurement_sample_tolerance(
                item.global_start_time_s,
                self.source.sample_rate_hz,
            )
            stop_tolerance = _stable_measurement_sample_tolerance(
                item.global_end_time_s,
                self.source.sample_rate_hz,
            )
            if (
                not math.isclose(
                    segment_sample_start,
                    item.global_source_probe_sample_start,
                    rel_tol=0,
                    abs_tol=start_tolerance,
                )
                or segment_sample_stop > authoritative.device_sample_stop + stop_tolerance
            ):
                raise ValueError("pilot Doppler V3 locklet time/sample geometry does not close")
            if any(
                interval.previous_global_reference_device_sample
                < segment_sample_start - start_tolerance
                or interval.global_reference_device_sample > segment_sample_stop + stop_tolerance
                for interval in item.intervals
            ):
                raise ValueError("pilot Doppler V3 interval escaped its locklet")
            lattice_origin: float | None = None
            frame_evidence: dict[int, tuple[float, float]] = {}
            for interval in item.intervals:
                expected_delta_s = (
                    interval.global_reference_device_sample
                    - interval.previous_global_reference_device_sample
                ) / self.source.sample_rate_hz
                if not math.isclose(
                    interval.time_delta_s,
                    expected_delta_s,
                    rel_tol=1e-9,
                    abs_tol=1e-12,
                ):
                    raise ValueError("pilot Doppler V3 interval time/sample delta does not close")
                previous_origin = interval.previous_global_reference_device_sample - round(
                    interval.previous_frame_index
                    * self.source.sample_rate_hz
                    / _PILOT_FRAME_RATE_HZ
                )
                current_origin = interval.global_reference_device_sample - round(
                    interval.frame_index * self.source.sample_rate_hz / _PILOT_FRAME_RATE_HZ
                )
                if not math.isclose(previous_origin, current_origin, rel_tol=0, abs_tol=1e-5):
                    raise ValueError("pilot Doppler V3 interval escaped the 750-Hz frame lattice")
                if lattice_origin is None:
                    lattice_origin = previous_origin
                elif not math.isclose(
                    previous_origin,
                    lattice_origin,
                    rel_tol=0,
                    abs_tol=1e-5,
                ):
                    raise ValueError(
                        "pilot Doppler V3 intervals lack a common frame-lattice origin"
                    )
                for frame_index, reference_sample, residual_cfo_hz in (
                    (
                        interval.previous_frame_index,
                        interval.previous_global_reference_device_sample,
                        interval.previous_intraframe_residual_cfo_hz,
                    ),
                    (
                        interval.frame_index,
                        interval.global_reference_device_sample,
                        interval.intraframe_residual_cfo_hz,
                    ),
                ):
                    previous_evidence = frame_evidence.setdefault(
                        frame_index,
                        (reference_sample, residual_cfo_hz),
                    )
                    if not math.isclose(
                        previous_evidence[0],
                        reference_sample,
                        rel_tol=0,
                        abs_tol=1e-5,
                    ) or not math.isclose(
                        previous_evidence[1],
                        residual_cfo_hz,
                        rel_tol=1e-12,
                        abs_tol=1e-9,
                    ):
                        raise ValueError("pilot Doppler V3 repeated frame evidence is inconsistent")
                if interval.held_out:
                    expected_gate = bool(
                        interval.channel_similarity
                        >= self.phase_config.minimum_channel_similarity - 1e-12
                        and interval.centered_innovation_modulo_pi_rad is not None
                        and abs(interval.centered_innovation_modulo_pi_rad)
                        <= self.phase_config.phase_innovation_gate_rad + 1e-12
                    )
                    if interval.gate_passed != expected_gate:
                        raise ValueError("pilot Doppler V3 held-out gate decision does not close")
            if item.phase_bias_hz_modulo is not None:
                expected_training_keys = tuple(
                    (index, index + 1) for index in range(self.phase_config.training_interval_count)
                )
                training_keys = tuple(
                    (interval.previous_frame_index, interval.frame_index)
                    for interval in item.intervals
                    if interval.training
                )
                if training_keys != expected_training_keys:
                    raise ValueError("pilot Doppler V3 training evidence is not the fixed prefix")
                if any(
                    interval.channel_similarity
                    < self.phase_config.minimum_channel_similarity - 1e-12
                    for interval in item.intervals
                    if interval.training
                ):
                    raise ValueError(
                        "pilot Doppler V3 training prefix lacks channel similarity support"
                    )
                if any(
                    not interval.held_out
                    for interval in item.intervals
                    if interval.previous_frame_index >= self.phase_config.training_interval_count
                ):
                    raise ValueError("pilot Doppler V3 post-prefix interval is not held out")
            expected_phase_lock = bool(
                item.phase_bias_hz_modulo is not None
                and item.training_interval_count == self.phase_config.training_interval_count
                and item.held_out_interval_count
                >= self.phase_config.minimum_held_out_interval_count
                and item.training_phase_rms_rad is not None
                and item.training_phase_rms_rad <= self.phase_config.maximum_training_rms_rad
                and item.training_circular_concentration is not None
                and item.training_circular_concentration
                >= self.phase_config.minimum_training_circular_concentration
                and item.held_out_gate_pass_fraction is not None
                and item.held_out_gate_pass_fraction
                >= self.phase_config.minimum_held_out_gate_pass_fraction
                and item.held_out_phase_rms_rad is not None
                and item.held_out_phase_rms_rad <= self.phase_config.maximum_held_out_rms_rad
            )
            if item.phase_trackability_qualified != expected_phase_lock:
                raise ValueError(
                    "pilot Doppler V3 phase-trackability flag disagrees with its policy"
                )
        if self.qualified_segment_count:
            expected_status = (
                StandardScientificStatus.PARTIAL
                if self.source_stateful_science_status != "complete"
                or self.bounded_local_track_truncation_present
                else StandardScientificStatus.COMPLETE
            )
        else:
            expected_status = (
                StandardScientificStatus.INSUFFICIENT_DATA
                if self.segments
                else StandardScientificStatus.NO_RESULT
            )
        expected_reason = {
            StandardScientificStatus.PARTIAL: (
                "held-out adjacent modulo-pi phase and independent local Doppler completed "
                "with bounded coverage or track truncation"
            ),
            StandardScientificStatus.COMPLETE: (
                "held-out adjacent modulo-pi phase and independent local Doppler completed"
            ),
            StandardScientificStatus.INSUFFICIENT_DATA: (
                "no V2-selected locklet passed corrected phase-trackability and independent "
                "frequency gates"
            ),
            StandardScientificStatus.NO_RESULT: (
                "no V2-selected pilot Doppler locklet was available"
            ),
        }[expected_status]
        if self.status is not expected_status or self.reason != expected_reason:
            raise ValueError(
                "pilot Doppler V3 status or reason disagrees with qualification authority"
            )
        document = self.model_dump(mode="json")
        document.pop("content_digest")
        if self.content_digest != canonical_digest(document):
            raise ValueError("pilot Doppler V3 content digest does not match")
        return self


class StandardPilotDopplerSegmentsV4(StandardPilotDopplerSegmentsV3):
    """Additive pilot-Doppler evidence carrying StandardNativeSourceV2."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    algorithm_version: Literal["standard-native-pilot-doppler-segments-v4"] = (
        "standard-native-pilot-doppler-segments-v4"  # type: ignore[assignment]
    )
    source: StandardNativeSourceV2  # type: ignore[assignment]
