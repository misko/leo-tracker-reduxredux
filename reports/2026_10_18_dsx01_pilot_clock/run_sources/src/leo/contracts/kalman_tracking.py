"""Persisted candidate-only frame Kalman tracking contracts."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import StandardScientificStatus

BoundedReason = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class KalmanTrackingConfigV1(ContractModel):
    """Bounded five-state receiver loop adapted from Kozhaya et al. (2025).

    The first three states are beat carrier phase, angular frequency, and
    angular-frequency rate.  The last two are Starlink frame phase and its
    drift, mirroring the paper's code-phase state without claiming payload or
    pseudorange recovery from the known Qin edge pilots.
    """

    schema_version: Literal[1] = 1
    model_version: Literal["kassas-five-state-frame-kf-v1"] = "kassas-five-state-frame-kf-v1"
    frame_rate_hz: Annotated[float, Field(gt=0)] = 750.0
    pilot_symbol_count: Annotated[int, Field(ge=8, le=300)] = 64
    carrier_acceleration_psd_rad2_s3: Annotated[float, Field(gt=0)] = (2 * math.pi) ** 2
    frame_rate_psd_s2_s: Annotated[float, Field(gt=0)] = 0.004**2
    carrier_phase_measurement_sigma_rad: Annotated[float, Field(gt=0)] = 2 * math.pi * 1e-5
    carrier_frequency_measurement_sigma_rad_s: Annotated[float, Field(gt=0)] = math.pi * 1e-2
    frame_phase_measurement_sigma_s: Annotated[float, Field(gt=0)] = 3e-7
    initial_doppler_rate_sigma_hz_s: Annotated[float, Field(gt=0)] = 5_000.0
    minimum_prompt_coherence: Annotated[float, Field(ge=0, le=1)] = 0.10
    phase_slip_threshold_rad: Annotated[float, Field(gt=0, le=math.pi)] = math.pi / 8
    cfo_correction_threshold_hz: Annotated[float, Field(gt=0)] = 75.0
    cfo_correction_minimum_separation_s: Annotated[float, Field(gt=0)] = 0.5
    maximum_tracks: Annotated[int, Field(ge=1, le=64)] = 16
    maximum_source_frames_per_track: Annotated[int, Field(ge=2, le=250_000)] = 90_000
    maximum_returned_frames_per_track: Annotated[int, Field(ge=2, le=25_000)] = 4_096

    @field_validator(
        "frame_rate_hz",
        "carrier_acceleration_psd_rad2_s3",
        "frame_rate_psd_s2_s",
        "carrier_phase_measurement_sigma_rad",
        "carrier_frequency_measurement_sigma_rad_s",
        "frame_phase_measurement_sigma_s",
        "initial_doppler_rate_sigma_hz_s",
        "minimum_prompt_coherence",
        "phase_slip_threshold_rad",
        "cfo_correction_threshold_hz",
        "cfo_correction_minimum_separation_s",
    )
    @classmethod
    def _finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Kalman tracking configuration must be finite")
        return value

    @model_validator(mode="after")
    def _bounded_inventory(self) -> Self:
        if self.maximum_returned_frames_per_track > self.maximum_source_frames_per_track:
            raise ValueError("returned Kalman frames cannot exceed the source-frame bound")
        return self

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class KalmanFrameEstimateV1(ContractModel):
    """One received Starlink frame measurement and closed-loop state estimate."""

    schema_version: Literal[1] = 1
    frame_index: int
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    prompt_coherence: Annotated[float, Field(ge=0, le=1)]
    measurement_phase_rad: float
    measurement_doppler_hz: float
    measurement_frame_phase_s: float
    update_applied: bool
    phase_innovation_rad: float
    doppler_innovation_hz: float
    frame_phase_innovation_s: float
    carrier_phase_rad: float
    phase_shift_rad: Annotated[float, Field(ge=-math.pi, le=math.pi)]
    doppler_shift_hz: float
    doppler_rate_hz_s: float
    frame_phase_s: float
    frame_rate_error_s_s: float
    carrier_phase_sigma_rad: Annotated[float, Field(ge=0)]
    doppler_sigma_hz: Annotated[float, Field(ge=0)]
    doppler_rate_sigma_hz_s: Annotated[float, Field(ge=0)]
    frame_phase_sigma_s: Annotated[float, Field(ge=0)]
    phase_slip_detected: bool
    cfo_correction_detected: bool
    estimated_cfo_correction_hz: float | None

    @field_validator(
        "time_s",
        "prompt_coherence",
        "measurement_phase_rad",
        "measurement_doppler_hz",
        "measurement_frame_phase_s",
        "phase_innovation_rad",
        "doppler_innovation_hz",
        "frame_phase_innovation_s",
        "carrier_phase_rad",
        "phase_shift_rad",
        "doppler_shift_hz",
        "doppler_rate_hz_s",
        "frame_phase_s",
        "frame_rate_error_s_s",
        "carrier_phase_sigma_rad",
        "doppler_sigma_hz",
        "doppler_rate_sigma_hz_s",
        "frame_phase_sigma_s",
        "estimated_cfo_correction_hz",
    )
    @classmethod
    def _finite_frame_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Kalman frame values must be finite")
        return value

    @model_validator(mode="after")
    def _correction_is_explicit(self) -> Self:
        if self.cfo_correction_detected != (self.estimated_cfo_correction_hz is not None):
            raise ValueError("CFO correction flag and estimate disagree")
        return self


class KalmanTrajectoryTrackV1(ContractModel):
    """Frame-resolved Kalman history for one final CFO trajectory candidate."""

    schema_version: Literal[1] = 1
    source_trajectory_id: Sha256Digest
    source_branch_id: Sha256Digest
    source_frame_count: Annotated[int, Field(ge=0)]
    processed_frame_count: Annotated[int, Field(ge=0)]
    returned_frame_count: Annotated[int, Field(ge=0, le=25_000)]
    omitted_frame_count: Annotated[int, Field(ge=0)]
    truncated_frame_count: Annotated[int, Field(ge=0)]
    measurement_update_count: Annotated[int, Field(ge=0)]
    rejected_measurement_count: Annotated[int, Field(ge=0)]
    phase_slip_count: Annotated[int, Field(ge=0)]
    cfo_correction_count: Annotated[int, Field(ge=0)]
    status: StandardScientificStatus
    reason: BoundedReason
    frames: Annotated[tuple[KalmanFrameEstimateV1, ...], Field(max_length=25_000)]

    @model_validator(mode="after")
    def _track_is_closed(self) -> Self:
        if (
            self.processed_frame_count + self.truncated_frame_count != self.source_frame_count
            or self.returned_frame_count != len(self.frames)
            or self.returned_frame_count + self.omitted_frame_count != self.processed_frame_count
            or self.measurement_update_count + self.rejected_measurement_count
            != self.processed_frame_count
        ):
            raise ValueError("Kalman trajectory frame accounting is inconsistent")
        indexes = tuple(item.frame_index for item in self.frames)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("Kalman frames must be unique and ordered")
        return self


class StandardKalmanTrackingV1(ContractModel):
    """Additive Standard product for five-state frame/carrier tracking."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-kalman-tracking-v1"] = "standard-kalman-tracking-v1"
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    final_trajectory_bank_digest: Sha256Digest
    config: KalmanTrackingConfigV1
    config_digest: Sha256Digest
    source_track_count: Annotated[int, Field(ge=0)]
    returned_track_count: Annotated[int, Field(ge=0, le=64)]
    truncated_track_count: Annotated[int, Field(ge=0)]
    tracks: Annotated[tuple[KalmanTrajectoryTrackV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    known_pilots_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _product_is_closed(self) -> Self:
        if self.config_digest != self.config.digest:
            raise ValueError("Kalman tracking configuration digest disagrees")
        if (
            self.returned_track_count + self.truncated_track_count != self.source_track_count
            or self.returned_track_count != len(self.tracks)
        ):
            raise ValueError("Kalman tracking trajectory accounting is inconsistent")
        ids = tuple(item.source_trajectory_id for item in self.tracks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Kalman tracks must be unique and ordered")
        document = self.model_dump(mode="json")
        document.pop("content_digest")
        if self.content_digest != canonical_digest(document):
            raise ValueError("Kalman tracking content digest does not match")
        return self
