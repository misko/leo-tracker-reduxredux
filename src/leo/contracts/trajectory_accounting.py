"""Immutable trajectory-conditioned replay accounting contracts."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class TrajectoryAccountingConfigV1(ContractModel):
    """Declared policy for comparing replay with the same CFO component."""

    schema_version: Literal[1] = 1
    detector_method: Literal["glrt64"] = "glrt64"
    association_gate_hz: Annotated[float, Field(gt=0)] = 2_500.0
    positive_margin: Annotated[float, Field(ge=0)] = 0.05
    baseline_selection: Literal["nearest_same_method_candidate"] = (
        "nearest_same_method_candidate"
    )
    unmatched_policy: Literal["exclude_from_transitions"] = "exclude_from_transitions"
    unique_probe_policy: Literal["maximum_corrected_margin"] = "maximum_corrected_margin"

    @field_validator("association_gate_hz", "positive_margin")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("trajectory-accounting configuration must be finite")
        return value

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class ReplayTransitionCountsV1(ContractModel):
    positive_to_positive: Annotated[int, Field(ge=0)] = 0
    positive_to_negative: Annotated[int, Field(ge=0)] = 0
    negative_to_positive: Annotated[int, Field(ge=0)] = 0
    negative_to_negative: Annotated[int, Field(ge=0)] = 0

    @property
    def total(self) -> int:
        return (
            self.positive_to_positive
            + self.positive_to_negative
            + self.negative_to_positive
            + self.negative_to_negative
        )


class TrajectoryConditionedEvaluationV1(ContractModel):
    trajectory_id: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    detector_method: Literal["glrt64"]
    corrected_margin: float
    global_baseline_margin: float | None
    baseline_candidate_rank: Annotated[int | None, Field(ge=0, le=31)]
    baseline_association_error_hz: Annotated[float | None, Field(ge=0)]
    baseline_tracking_cfo_hz: float | None
    baseline_margin: float | None

    @field_validator(
        "time_s",
        "corrected_margin",
        "global_baseline_margin",
        "baseline_association_error_hz",
        "baseline_tracking_cfo_hz",
        "baseline_margin",
    )
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("trajectory-accounting evaluation must be finite")
        return value

    @model_validator(mode="after")
    def _association_is_complete(self) -> Self:
        associated = (
            self.baseline_candidate_rank,
            self.baseline_association_error_hz,
            self.baseline_tracking_cfo_hz,
            self.baseline_margin,
        )
        if any(value is None for value in associated) != all(
            value is None for value in associated
        ):
            raise ValueError("trajectory baseline association must be complete or absent")
        return self


class TrajectoryReplaySummaryV1(ContractModel):
    trajectory_id: Sha256Digest
    evaluation_count: Annotated[int, Field(ge=0)]
    associated_count: Annotated[int, Field(ge=0)]
    unassociated_count: Annotated[int, Field(ge=0)]
    unassociated_corrected_positive_count: Annotated[int, Field(ge=0)]
    transitions: ReplayTransitionCountsV1

    @model_validator(mode="after")
    def _counts_close(self) -> Self:
        if self.associated_count + self.unassociated_count != self.evaluation_count:
            raise ValueError("trajectory accounting row inventory is inconsistent")
        if self.transitions.total != self.associated_count:
            raise ValueError("trajectory accounting transitions disagree with associations")
        if self.unassociated_corrected_positive_count > self.unassociated_count:
            raise ValueError("unassociated positive count exceeds unmatched inventory")
        return self


class TrajectoryConditionedReplayAccountingV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["trajectory-conditioned-replay-accounting-v1"] = (
        "trajectory-conditioned-replay-accounting-v1"
    )
    pilot_scan_digest: Sha256Digest
    trajectory_bank_digest: Sha256Digest
    trajectory_feedback_digest: Sha256Digest
    configuration_digest: Sha256Digest
    configuration: TrajectoryAccountingConfigV1
    evaluation_count: Annotated[int, Field(ge=0, le=100_000)]
    associated_evaluation_count: Annotated[int, Field(ge=0, le=100_000)]
    unassociated_evaluation_count: Annotated[int, Field(ge=0, le=100_000)]
    evaluations: tuple[TrajectoryConditionedEvaluationV1, ...] = Field(max_length=100_000)
    trajectories: tuple[TrajectoryReplaySummaryV1, ...] = Field(max_length=64)
    associated_transitions: ReplayTransitionCountsV1
    unique_probe_transitions: ReplayTransitionCountsV1
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False

    @model_validator(mode="after")
    def _inventory_is_exact(self) -> Self:
        if self.configuration_digest != self.configuration.digest:
            raise ValueError("trajectory-accounting configuration digest disagrees")
        if self.evaluation_count != len(self.evaluations):
            raise ValueError("trajectory-accounting evaluation count disagrees with rows")
        if (
            self.associated_evaluation_count + self.unassociated_evaluation_count
            != self.evaluation_count
        ):
            raise ValueError("trajectory-accounting matched inventory is inconsistent")
        associated = sum(item.baseline_margin is not None for item in self.evaluations)
        if associated != self.associated_evaluation_count:
            raise ValueError("trajectory-accounting association count disagrees with rows")
        identities = tuple(
            (item.trajectory_id, item.sample_start, item.detector_method)
            for item in self.evaluations
        )
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ValueError("trajectory-accounting evaluations are not unique and ordered")
        trajectory_ids = tuple(item.trajectory_id for item in self.trajectories)
        if trajectory_ids != tuple(sorted(trajectory_ids)) or len(set(trajectory_ids)) != len(
            trajectory_ids
        ):
            raise ValueError("trajectory-accounting summaries are not unique and ordered")
        if sum(item.evaluation_count for item in self.trajectories) != self.evaluation_count:
            raise ValueError("trajectory summaries do not cover every evaluation")
        if self.associated_transitions.total != self.associated_evaluation_count:
            raise ValueError("associated transitions do not cover matched evaluations")
        unique_probe_count = len(
            {
                item.sample_start
                for item in self.evaluations
                if item.global_baseline_margin is not None
            }
        )
        if self.unique_probe_transitions.total != unique_probe_count:
            raise ValueError("unique-probe transitions do not cover physical probes")
        return self
