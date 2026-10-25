"""Terminal Standard reports backed only by replay-selected CFO trajectories."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.cfo_dealias import FinalTrajectoryV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import (
    AssociationStatus,
    BoundedText,
    Identifier,
    PairTimingEvidenceV1,
    PathStandardReportV1,
    StandardScientificStatus,
)


class PathStandardReportV2(ContractModel):
    """One path's immutable raw summary plus its exact final trajectory boundary."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-path-report-v2"] = "standard-path-report-v2"
    raw_report: PathStandardReportV1
    cfo_alias_map_digest: Sha256Digest
    dealiased_trajectory_bank_digest: Sha256Digest
    cfo_lift_replay_digest: Sha256Digest
    final_trajectory_bank_digest: Sha256Digest
    final_trajectory_table_digest: Sha256Digest
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    final_trajectories: Annotated[tuple[FinalTrajectoryV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedText
    report_digest: Sha256Digest
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _closure_is_exact(self) -> Self:
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.final_trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final path trajectory accounting is inconsistent")
        ids = tuple(item.trajectory_id for item in self.final_trajectories)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("final path trajectories must be unique and ordered")
        if self.raw_report.candidate_only is not True:
            raise ValueError("final path report cannot weaken raw candidate-only authority")
        if self.report_digest != _digest_without(self, "report_digest"):
            raise ValueError("final path report digest does not match content")
        return self


class DerivativeTrajectoryAssociationV2(ContractModel):
    """One-to-one cross-path comparison that deliberately excludes CFO intercept."""

    schema_version: Literal[2] = 2
    association_id: Sha256Digest
    left_path_id: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    left_trajectory_id: Sha256Digest
    right_path_id: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    right_trajectory_id: Sha256Digest
    overlap_start_utc_ns: Annotated[int, Field(ge=0)]
    overlap_end_utc_ns: Annotated[int, Field(ge=0)]
    comparison_point_count: Literal[128] = 128
    slope_rms_difference_hz_per_s: Annotated[float, Field(ge=0)]
    slope_max_difference_hz_per_s: Annotated[float, Field(ge=0)]
    acceleration_rms_difference_hz_per_s2: Annotated[float, Field(ge=0)]
    acceleration_max_difference_hz_per_s2: Annotated[float, Field(ge=0)]
    jerk_rms_difference_hz_per_s3: Annotated[float, Field(ge=0)]
    jerk_max_difference_hz_per_s3: Annotated[float, Field(ge=0)]
    comparison_score: Annotated[float, Field(ge=0)]
    comparison_basis: Literal["slope_acceleration_jerk_only"] = "slope_acceleration_jerk_only"

    @field_validator(
        "slope_rms_difference_hz_per_s",
        "slope_max_difference_hz_per_s",
        "acceleration_rms_difference_hz_per_s2",
        "acceleration_max_difference_hz_per_s2",
        "jerk_rms_difference_hz_per_s3",
        "jerk_max_difference_hz_per_s3",
        "comparison_score",
    )
    @classmethod
    def _finite_metrics(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("derivative comparison metrics must be finite")
        return value

    @model_validator(mode="after")
    def _interval_is_positive(self) -> Self:
        if self.overlap_end_utc_ns <= self.overlap_start_utc_ns:
            raise ValueError("derivative comparison requires measured overlap")
        return self


class RadioStandardReportV2(ContractModel):
    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-radio-report-v2"] = "standard-radio-report-v2"
    session_id: Identifier
    stream_id: Identifier
    radio_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    status: StandardScientificStatus
    reason: BoundedText
    declared_receiver_ids: tuple[Annotated[int, Field(ge=0, le=255)], ...]
    paths: Annotated[tuple[PathStandardReportV2, ...], Field(min_length=1, max_length=2)]
    association_status: AssociationStatus
    derivative_associations: Annotated[
        tuple[DerivativeTrajectoryAssociationV2, ...], Field(max_length=4096)
    ]
    unmatched_trajectory_ids: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=640)], ...
    ]
    child_truncated_candidate_count: Annotated[int, Field(ge=0)]
    child_truncated_trajectory_count: Annotated[int, Field(ge=0)]
    report_digest: Sha256Digest
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _radio_is_closed(self) -> Self:
        receiver_ids = tuple(item.raw_report.receiver_id for item in self.paths)
        if receiver_ids != self.declared_receiver_ids or receiver_ids != tuple(
            sorted(set(receiver_ids))
        ):
            raise ValueError("final radio path inventory is not exact")
        if self.association_status is not AssociationStatus.EVALUATED and (
            self.derivative_associations
        ):
            raise ValueError("unevaluated radio report cannot contain derivative associations")
        if self.unmatched_trajectory_ids != tuple(sorted(set(self.unmatched_trajectory_ids))):
            raise ValueError("final radio unmatched trajectories must be unique and ordered")
        if self.report_digest != _digest_without(self, "report_digest"):
            raise ValueError("final radio report digest does not match content")
        return self


class PairedStandardReportV2(ContractModel):
    schema_version: Literal[2] = 2
    algorithm_version: Literal["standard-paired-report-v2"] = "standard-paired-report-v2"
    session_id: Identifier
    manifest_digest: Sha256Digest
    synchronization_inventory_digest: Sha256Digest
    status: StandardScientificStatus
    reason: BoundedText
    radios: tuple[RadioStandardReportV2, RadioStandardReportV2]
    timing: PairTimingEvidenceV1
    association_status: AssociationStatus
    derivative_associations: Annotated[
        tuple[DerivativeTrajectoryAssociationV2, ...], Field(max_length=4096)
    ]
    unmatched_trajectory_ids: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=640)], ...
    ]
    child_truncated_candidate_count: Annotated[int, Field(ge=0)]
    child_truncated_trajectory_count: Annotated[int, Field(ge=0)]
    report_digest: Sha256Digest
    phase_coherent: Literal[False] = False
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _pair_is_closed(self) -> Self:
        radio_keys = tuple((item.stream_id, item.radio_id) for item in self.radios)
        if radio_keys != tuple(sorted(set(radio_keys))) or len(radio_keys) != 2:
            raise ValueError("final paired radio inventory must be exact")
        if self.timing.synchronization_inventory_digest != self.synchronization_inventory_digest:
            raise ValueError("final paired timing inventory digest mismatch")
        if self.association_status is not AssociationStatus.EVALUATED and (
            self.derivative_associations
        ):
            raise ValueError("unevaluated pair cannot contain derivative associations")
        if self.unmatched_trajectory_ids != tuple(sorted(set(self.unmatched_trajectory_ids))):
            raise ValueError("final paired unmatched trajectories must be unique and ordered")
        if self.report_digest != _digest_without(self, "report_digest"):
            raise ValueError("final paired report digest does not match content")
        return self


def _digest_without(model: ContractModel, field: str) -> Sha256Digest:
    return canonical_digest(model.model_dump(mode="json", exclude={field}))
