"""Persisted segment-local stateful science for the Standard-native path.

The numerical kernels represented here are the existing Standard kernels, but
their sample and time coordinates are explicitly local to one authoritative
continuity segment.  The enclosing segment record is the only mapping back to
the recording's global device axis.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.cfo_dealias import (
    CfoAliasMapV2,
    CfoLiftReplayV4,
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV3,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.kalman_tracking import StandardKalmanTrackingV1
from leo.contracts.pilot_doppler_segments import StandardPilotDopplerSegmentsV2
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_pipeline import BoundedText, MethodName
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1


class NativeStatefulSegmentDispositionV1(StrEnum):
    """Truthful reason a continuity segment did or did not enter the chain."""

    ANALYZED = "analyzed"
    EMPTY_TERMINAL = "empty_terminal"
    NO_COMPLETE_OUTER_WINDOW = "no_complete_outer_window"
    OUTER_WINDOW_BUDGET_EXHAUSTED = "outer_window_budget_exhausted"
    GLOBAL_SCHEDULE_UNAVAILABLE = "global_schedule_unavailable"


class NativePilotMethodScoreV1(ContractModel):
    schema_version: Literal[1] = 1
    method: MethodName
    exact_score: float
    control_score: float | None
    margin: float
    residual_cfo_hz: float
    tracking_cfo_hz: float

    @field_validator(
        "exact_score",
        "control_score",
        "margin",
        "residual_cfo_hz",
        "tracking_cfo_hz",
    )
    @classmethod
    def _score_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native pilot score must be finite")
        return value


class NativePilotCandidateV1(ContractModel):
    schema_version: Literal[1] = 1
    rank: Annotated[int, Field(ge=0)]
    local_epoch_sample: Annotated[int, Field(ge=0)]
    acquired_cfo_hz: float
    scores: tuple[NativePilotMethodScoreV1, ...]
    qam_accuracy: Annotated[float | None, Field(ge=0, le=1)] = None
    qam_evm: Annotated[float | None, Field(gt=0)] = None

    @field_validator("acquired_cfo_hz", "qam_accuracy", "qam_evm")
    @classmethod
    def _candidate_value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native pilot candidate value must be finite")
        return value

    @model_validator(mode="after")
    def _candidate_methods_are_unique(self) -> Self:
        methods = tuple(item.method for item in self.scores)
        if methods != tuple(dict.fromkeys(methods)):
            raise ValueError("native pilot candidate methods must be unique and ordered")
        return self


class NativePilotProbeDetectionV1(ContractModel):
    """Lossless typed projection of one segment-local pilot/QAM detection."""

    schema_version: Literal[1] = 1
    status: Literal["complete", "no_result", "insufficient"]
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    local_epoch_sample: Annotated[int, Field(ge=0)] | None
    acquired_cfo_hz: float | None
    scores: tuple[NativePilotMethodScoreV1, ...]
    qam_accuracy: Annotated[float | None, Field(ge=0, le=1)] = None
    qam_evm: Annotated[float | None, Field(gt=0)] = None
    reason: BoundedText
    source_candidate_count: Annotated[int, Field(ge=0)] = 0
    truncated_candidate_count: Annotated[int, Field(ge=0)] = 0
    candidates: tuple[NativePilotCandidateV1, ...] = ()

    @field_validator("time_s", "acquired_cfo_hz", "qam_accuracy", "qam_evm")
    @classmethod
    def _detection_value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native pilot detection value must be finite")
        return value

    @model_validator(mode="after")
    def _detection_is_closed(self) -> Self:
        methods = tuple(item.method for item in self.scores)
        if methods != tuple(dict.fromkeys(methods)):
            raise ValueError("native pilot detection methods must be unique and ordered")
        ranks = tuple(item.rank for item in self.candidates)
        if ranks != tuple(range(len(ranks))):
            raise ValueError("native pilot candidate ranks must be contiguous from zero")
        if self.source_candidate_count != len(self.candidates) + self.truncated_candidate_count:
            raise ValueError("native pilot candidate accounting does not close")
        primary_present = self.local_epoch_sample is not None and self.acquired_cfo_hz is not None
        if primary_present != bool(self.scores):
            raise ValueError("native pilot primary coordinates disagree with method scores")
        if (self.local_epoch_sample is None) != (self.acquired_cfo_hz is None):
            raise ValueError("native pilot primary coordinates are only partially present")
        return self


class NativePolynomialTrajectoryV1(ContractModel):
    """One polynomial trajectory in segment-local seconds."""

    schema_version: Literal[1] = 1
    trajectory_id: Sha256Digest
    method: MethodName
    polynomial_degree: Annotated[int, Field(ge=1, le=3)]
    reference_time_s: Annotated[float, Field(ge=0)]
    coefficients_hz: tuple[float, ...]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    observation_ids: tuple[Sha256Digest, ...]
    point_count: Annotated[int, Field(gt=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    bic: float
    high_gate: float
    em_iterations: Annotated[int, Field(ge=0)]
    candidate_only: Literal[True] = True

    @field_validator(
        "reference_time_s",
        "start_s",
        "end_s",
        "residual_rms_hz",
        "bic",
        "high_gate",
    )
    @classmethod
    def _trajectory_value_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native trajectory value must be finite")
        return value

    @field_validator("coefficients_hz")
    @classmethod
    def _trajectory_coefficients_are_finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("native trajectory coefficients must be finite")
        return value

    @model_validator(mode="after")
    def _trajectory_is_closed(self) -> Self:
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("native trajectory coefficient count disagrees with degree")
        if self.start_s > self.end_s or self.point_count != len(self.observation_ids):
            raise ValueError("native trajectory support geometry is invalid")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("native trajectory observation IDs must be unique")
        return self


class NativeTrajectoryFamilyV1(ContractModel):
    schema_version: Literal[1] = 1
    family_id: Sha256Digest
    representative_trajectory_id: Sha256Digest
    member_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1)]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]

    @field_validator("start_s", "end_s")
    @classmethod
    def _family_time_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("native trajectory family time must be finite")
        return value

    @model_validator(mode="after")
    def _family_is_closed(self) -> Self:
        if self.start_s > self.end_s:
            raise ValueError("native trajectory family end precedes its start")
        if self.member_trajectory_ids != tuple(dict.fromkeys(self.member_trajectory_ids)):
            raise ValueError("native trajectory family members must be unique and ordered")
        if self.representative_trajectory_id not in self.member_trajectory_ids:
            raise ValueError("native trajectory representative is not a family member")
        return self


class NativeRawTrajectoryBankV1(ContractModel):
    schema_version: Literal[1] = 1
    config_digest: Sha256Digest
    trajectories: tuple[NativePolynomialTrajectoryV1, ...]
    families: tuple[NativeTrajectoryFamilyV1, ...]
    observation_count: Annotated[int, Field(ge=0)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    candidate_only: Literal[True] = True

    @model_validator(mode="after")
    def _bank_is_closed(self) -> Self:
        trajectory_ids = tuple(item.trajectory_id for item in self.trajectories)
        family_ids = tuple(item.family_id for item in self.families)
        if len(trajectory_ids) != len(set(trajectory_ids)):
            raise ValueError("native raw trajectory IDs must be unique")
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("native raw trajectory family IDs must be unique")
        known = set(trajectory_ids)
        if any(not set(item.member_trajectory_ids) <= known for item in self.families):
            raise ValueError("native raw trajectory family contains an unknown member")
        return self


class NativeTrajectoryRepresentativeV1(ContractModel):
    schema_version: Literal[1] = 1
    family_id: Sha256Digest
    trajectory: NativePolynomialTrajectoryV1


class NativeConditionedHoughReplayRowV1(ContractModel):
    """One exact conditioned replay row in segment-local coordinates."""

    schema_version: Literal[1] = 1
    family_id: Sha256Digest
    trajectory_id: Sha256Digest
    trajectory_method: MethodName
    polynomial_degree: Annotated[int, Field(ge=1, le=3)]
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    detector_method: MethodName
    baseline_margin: float
    corrected_margin: float
    margin_delta: float
    corrected_residual_cfo_hz: float
    conditioned_corrected_margin: float | None = None
    conditioned_tracking_cfo_hz: float | None = None
    conditioned_epoch_sample: Annotated[int, Field(ge=0)] | None = None
    conditioned_seed_cfo_hz: float | None = None

    @field_validator(
        "time_s",
        "baseline_margin",
        "corrected_margin",
        "margin_delta",
        "corrected_residual_cfo_hz",
        "conditioned_corrected_margin",
        "conditioned_tracking_cfo_hz",
        "conditioned_seed_cfo_hz",
    )
    @classmethod
    def _replay_value_is_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("native conditioned replay value must be finite")
        return value

    @model_validator(mode="after")
    def _conditioned_fields_are_atomic(self) -> Self:
        conditioned = (
            self.conditioned_corrected_margin,
            self.conditioned_tracking_cfo_hz,
            self.conditioned_epoch_sample,
            self.conditioned_seed_cfo_hz,
        )
        if any(item is not None for item in conditioned) and not all(
            item is not None for item in conditioned
        ):
            raise ValueError("native conditioned replay fields are only partially present")
        if not math.isclose(
            self.margin_delta,
            self.corrected_margin - self.baseline_margin,
            abs_tol=1e-12,
        ):
            raise ValueError("native conditioned replay margin delta does not close")
        return self


class NativeSegmentLocalScienceV1(ContractModel):
    """Complete stateful kernel chain for one reset-local segment."""

    schema_version: Literal[1] = 1
    coordinate_basis: Literal["segment-local-device-axis-v1"] = "segment-local-device-axis-v1"
    segment_path_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    scheduled_outer_window_count: Annotated[int, Field(gt=0)]
    detections: tuple[NativePilotProbeDetectionV1, ...]
    residual_hough_bank: NativeRawTrajectoryBankV1
    residual_hough_representatives: tuple[NativeTrajectoryRepresentativeV1, ...]
    conditioned_hough_replay: tuple[NativeConditionedHoughReplayRowV1, ...]
    cfo_alias_map: CfoAliasMapV2
    dealiased_trajectory_bank: DealiasedTrajectoryBankV4
    cfo_lift_replay: CfoLiftReplayV4
    final_trajectory_bank: FinalTrajectoryBankV3
    kalman_tracking: StandardKalmanTrackingV1
    pilot_doppler_segments: StandardPilotDopplerSegmentsV2
    science_digest: Sha256Digest

    @model_validator(mode="after")
    def _local_science_is_closed(self) -> Self:
        starts = tuple(item.sample_start for item in self.detections)
        if starts != tuple(sorted(set(starts))):
            raise ValueError("native segment-local detections must be unique and ordered")
        representative_ids = tuple(
            item.trajectory.trajectory_id for item in self.residual_hough_representatives
        )
        if len(representative_ids) != len(set(representative_ids)):
            raise ValueError("native residual-Hough representatives must be unique")
        bank_by_id = {item.trajectory_id: item for item in self.residual_hough_bank.trajectories}
        if any(
            bank_by_id.get(item.trajectory.trajectory_id) != item.trajectory
            for item in self.residual_hough_representatives
        ):
            raise ValueError("native residual-Hough representative is not exact bank content")
        replay_keys = tuple(
            (item.family_id, item.sample_start, item.detector_method)
            for item in self.conditioned_hough_replay
        )
        if replay_keys != tuple(sorted(set(replay_keys))):
            raise ValueError("native conditioned-Hough replay rows are not canonical")
        if (
            self.cfo_alias_map.pilot_scan_digest != self.pilot_scan_digest
            or self.cfo_alias_map.raw_trajectory_bank_digest != self.raw_trajectory_bank_digest
            or self.dealiased_trajectory_bank.alias_map_digest != self.cfo_alias_map.content_digest
            or self.dealiased_trajectory_bank.raw_trajectory_bank_digest
            != self.raw_trajectory_bank_digest
            or self.cfo_lift_replay.path_input_binding_digest != self.segment_path_binding_digest
            or self.cfo_lift_replay.pilot_scan_digest != self.pilot_scan_digest
            or self.cfo_lift_replay.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.final_trajectory_bank.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.final_trajectory_bank.lift_replay_digest != self.cfo_lift_replay.content_digest
            or self.kalman_tracking.path_input_binding_digest != self.segment_path_binding_digest
            or self.kalman_tracking.pilot_scan_digest != self.pilot_scan_digest
            or self.kalman_tracking.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.kalman_tracking.final_trajectory_bank_digest
            != self.final_trajectory_bank.content_digest
            or self.pilot_doppler_segments.path_input_binding_digest
            != self.segment_path_binding_digest
            or self.pilot_doppler_segments.pilot_scan_digest != self.pilot_scan_digest
            or self.pilot_doppler_segments.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.pilot_doppler_segments.final_trajectory_bank_digest
            != self.final_trajectory_bank.content_digest
            or self.pilot_doppler_segments.kalman_tracking_digest
            != self.kalman_tracking.content_digest
        ):
            raise ValueError("native segment-local stateful kernel authority does not close")
        if self.science_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"science_digest"})
        ):
            raise ValueError("native segment-local science digest does not match content")
        return self


class NativeStatefulSegmentV1(ContractModel):
    """One authoritative reset segment and its exact global coordinate mapping."""

    schema_version: Literal[1] = 1
    continuity_segment: ContinuitySegmentV1
    continuity_segment_index: Annotated[int, Field(ge=0)]
    global_device_sample_start: Annotated[int, Field(ge=0)]
    global_device_sample_stop: Annotated[int, Field(ge=0)]
    disposition: NativeStatefulSegmentDispositionV1
    local_science: NativeSegmentLocalScienceV1 | None
    segment_digest: Sha256Digest

    @model_validator(mode="after")
    def _segment_is_closed(self) -> Self:
        segment = self.continuity_segment
        if (
            self.continuity_segment_index != segment.segment_index
            or self.global_device_sample_start != segment.device_sample_start
            or self.global_device_sample_stop != segment.device_sample_stop
        ):
            raise ValueError("native stateful segment changed authoritative global bounds")
        analyzed = self.disposition is NativeStatefulSegmentDispositionV1.ANALYZED
        if analyzed != (self.local_science is not None):
            raise ValueError("native stateful segment disposition disagrees with science")
        empty = segment.observed_sample_count == 0
        if (self.disposition is NativeStatefulSegmentDispositionV1.EMPTY_TERMINAL) != empty:
            raise ValueError("native empty-terminal disposition disagrees with segment support")
        if self.segment_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"segment_digest"})
        ):
            raise ValueError("native stateful segment digest does not match content")
        return self


class StandardNativeStatefulPathV1(ContractModel):
    """Digest-bound evidence-only stateful chain over every continuity segment."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["standard-native-stateful-path-v1"] = (
        "standard-native-stateful-path-v1"
    )
    source: StandardNativeSourceV1
    starlink_edge: StarlinkEdge
    science_configuration_digest: Sha256Digest
    stateful_science_status: Literal["complete", "unavailable_global_schedule"]
    maximum_outer_window_count: Annotated[int, Field(gt=0)]
    analyzed_outer_window_count: Annotated[int, Field(ge=0)]
    segments: tuple[NativeStatefulSegmentV1, ...]
    stateful_path_digest: Sha256Digest
    native_evidence_only: Literal[True] = True
    current_eligible: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _stateful_path_is_closed(self) -> Self:
        if len(self.segments) != len(self.source.continuity_segments):
            raise ValueError("native stateful path omitted an authoritative segment")
        for persisted, authoritative in zip(
            self.segments,
            self.source.continuity_segments,
            strict=True,
        ):
            if persisted.continuity_segment != authoritative:
                raise ValueError("native stateful path segment inventory changed")
            science = persisted.local_science
            if science is None:
                continue
            expected_binding = canonical_digest(
                {
                    "kind": "standard-native-segment-local-binding-v1",
                    "path_input_binding_digest": self.source.path_input_binding_digest,
                    "validity_inventory_digest": self.source.validity_inventory_digest,
                    "segment": authoritative.model_dump(mode="json"),
                    "science_configuration_digest": self.science_configuration_digest,
                    "effective_maximum_outer_windows": science.scheduled_outer_window_count,
                }
            )
            if science.segment_path_binding_digest != expected_binding:
                raise ValueError("native segment-local binding digest does not close")
            duration_s = authoritative.observed_sample_count / self.source.sample_rate_hz
            for detection in science.detections:
                if detection.sample_start > authoritative.observed_sample_count or not math.isclose(
                    detection.time_s,
                    detection.sample_start / self.source.sample_rate_hz,
                    abs_tol=1e-12,
                ):
                    raise ValueError("native pilot detection escaped segment-local coordinates")
            for row in science.conditioned_hough_replay:
                if row.sample_start > authoritative.observed_sample_count or not math.isclose(
                    row.time_s,
                    row.sample_start / self.source.sample_rate_hz,
                    abs_tol=1e-12,
                ):
                    raise ValueError("native replay row escaped segment-local coordinates")
            if any(
                item.start_s > duration_s or item.end_s > duration_s
                for item in science.residual_hough_bank.trajectories
            ):
                raise ValueError("native trajectory escaped segment-local time support")
        analyzed = sum(
            item.local_science.scheduled_outer_window_count
            for item in self.segments
            if item.local_science is not None
        )
        if (
            analyzed != self.analyzed_outer_window_count
            or analyzed > self.maximum_outer_window_count
        ):
            raise ValueError("native stateful outer-window accounting does not close")
        globally_schedulable = (
            self.source.missing_sample_count == 0
            and len(self.source.continuity_segments) == 1
            and self.source.continuity_segments[0].device_sample_start == 0
            and self.source.continuity_segments[0].device_sample_stop
            == self.source.logical_sample_count
        )
        expected_status = "complete" if globally_schedulable else "unavailable_global_schedule"
        if self.stateful_science_status != expected_status:
            raise ValueError("native stateful status disagrees with global schedule authority")
        if not globally_schedulable:
            if self.analyzed_outer_window_count or any(
                item.local_science is not None for item in self.segments
            ):
                raise ValueError("gapped native stateful evidence cannot publish local schedules")
            if any(
                item.disposition
                not in {
                    NativeStatefulSegmentDispositionV1.GLOBAL_SCHEDULE_UNAVAILABLE,
                    NativeStatefulSegmentDispositionV1.EMPTY_TERMINAL,
                }
                for item in self.segments
            ):
                raise ValueError("gapped native stateful evidence has a false schedule claim")
        if self.segments[-1].global_device_sample_stop != self.source.logical_sample_count:
            raise ValueError("native stateful segments do not close the global logical span")
        if self.stateful_path_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"stateful_path_digest"})
        ):
            raise ValueError("native stateful path digest does not match content")
        return self
