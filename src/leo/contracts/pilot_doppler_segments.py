"""Immutable candidate-only pilot Doppler segment contracts."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import StandardScientificStatus

BoundedReason = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


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
