"""Bounded contracts for deterministic multi-target CFO association."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import StandardScientificStatus


class AssociationEdgeStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED_GAP = "rejected_gap"
    REJECTED_FREQUENCY = "rejected_frequency"
    REJECTED_SLOPE = "rejected_slope"
    REJECTED_ACCELERATION = "rejected_acceleration"


class DuplicateBranchStatus(StrEnum):
    COLLAPSED_EXACT_SUPPORT = "collapsed_exact_support"
    COLLAPSED_ALIAS_HYPOTHESIS = "collapsed_alias_hypothesis"
    RETAINED_DISTINCT_SUPPORT = "retained_distinct_support"
    RETAINED_MODEL_RESIDUAL = "retained_model_residual"


class MultiTargetAssociationConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    gate_id: Annotated[
        str, StringConstraints(pattern=r"^[a-z0-9._-]+$", min_length=1, max_length=128)
    ]
    expected_probe_interval_s: Annotated[float, Field(gt=0)]
    maximum_gap_s: Annotated[float, Field(gt=0)]
    maximum_frequency_error_hz: Annotated[float, Field(gt=0)]
    maximum_slope_error_hz_per_s: Annotated[float, Field(gt=0)]
    maximum_acceleration_error_hz_per_s2: Annotated[float, Field(gt=0)]
    frequency_weight: Annotated[float, Field(gt=0)]
    slope_weight: Annotated[float, Field(gt=0)]
    acceleration_weight: Annotated[float, Field(gt=0)]
    birth_penalty: Annotated[float, Field(gt=0)]
    death_penalty: Annotated[float, Field(gt=0)]
    missed_probe_penalty: Annotated[float, Field(ge=0)]
    duplicate_frequency_gate_hz: Annotated[float, Field(gt=0)]
    duplicate_slope_gate_hz_per_s: Annotated[float, Field(gt=0)]
    maximum_observations: Annotated[int, Field(ge=1, le=9_600)]
    maximum_edge_decisions: Annotated[int, Field(ge=1, le=65_536)]
    maximum_branches: Annotated[int, Field(ge=1, le=64)]
    maximum_assignment_iterations: Annotated[int, Field(ge=1, le=32)]

    @field_validator(
        "expected_probe_interval_s",
        "maximum_gap_s",
        "maximum_frequency_error_hz",
        "maximum_slope_error_hz_per_s",
        "maximum_acceleration_error_hz_per_s2",
        "frequency_weight",
        "slope_weight",
        "acceleration_weight",
        "birth_penalty",
        "death_penalty",
        "missed_probe_penalty",
        "duplicate_frequency_gate_hz",
        "duplicate_slope_gate_hz_per_s",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("association configuration values must be finite")
        return value

    @model_validator(mode="after")
    def _geometry_is_coherent(self) -> Self:
        if self.maximum_gap_s < self.expected_probe_interval_s:
            raise ValueError("association gap cannot be shorter than one probe interval")
        return self

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class MultiTargetObservationV1(ContractModel):
    schema_version: Literal[1] = 1
    observation_id: Sha256Digest
    component_id: Sha256Digest
    hypothesis_set_id: Sha256Digest
    time_s: Annotated[float, Field(ge=0)]
    canonical_cfo_hz: float
    slope_hint_hz_per_s: float
    acceleration_hint_hz_per_s2: float

    @field_validator(
        "time_s", "canonical_cfo_hz", "slope_hint_hz_per_s", "acceleration_hint_hz_per_s2"
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("multi-target observation values must be finite")
        return value


class AssociationEdgeDecisionV1(ContractModel):
    schema_version: Literal[1] = 1
    source_observation_id: Sha256Digest
    destination_observation_id: Sha256Digest
    status: AssociationEdgeStatus
    delta_time_s: Annotated[float, Field(gt=0)]
    missed_probe_count: Annotated[int, Field(ge=0)]
    frequency_error_hz: Annotated[float, Field(ge=0)]
    slope_error_hz_per_s: Annotated[float, Field(ge=0)]
    acceleration_error_hz_per_s2: Annotated[float, Field(ge=0)]
    link_cost: Annotated[float, Field(ge=0)]
    selected: bool
    reason: Annotated[str, StringConstraints(min_length=1, max_length=512)]

    @field_validator(
        "delta_time_s",
        "frequency_error_hz",
        "slope_error_hz_per_s",
        "acceleration_error_hz_per_s2",
        "link_cost",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("association edge values must be finite")
        return value

    @model_validator(mode="after")
    def _selection_is_allowed(self) -> Self:
        if self.selected and self.status is not AssociationEdgeStatus.ACCEPTED:
            raise ValueError("a rejected association edge cannot be selected")
        return self


class MultiTargetBranchV1(ContractModel):
    schema_version: Literal[1] = 1
    branch_id: Sha256Digest
    component_id: Sha256Digest
    observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=9_600)]
    hypothesis_set_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=9_600)]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    birth_penalty: Annotated[float, Field(gt=0)]
    death_penalty: Annotated[float, Field(gt=0)]
    selected_link_cost: Annotated[float, Field(ge=0)]
    retained: bool
    duplicate_of_branch_id: Sha256Digest | None

    @model_validator(mode="after")
    def _branch_is_ordered(self) -> Self:
        if len(self.observation_ids) != len(self.hypothesis_set_ids):
            raise ValueError("branch observation and hypothesis inventories disagree")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("branch observations must be unique")
        if self.start_s > self.end_s:
            raise ValueError("branch interval is reversed")
        if self.retained == (self.duplicate_of_branch_id is not None):
            raise ValueError("branch duplicate retention state is inconsistent")
        return self


class DuplicateBranchDecisionV1(ContractModel):
    schema_version: Literal[1] = 1
    left_branch_id: Sha256Digest
    right_branch_id: Sha256Digest
    status: DuplicateBranchStatus
    overlap_s: Annotated[float, Field(ge=0)]
    maximum_frequency_residual_hz: Annotated[float | None, Field(ge=0)]
    maximum_slope_residual_hz_per_s: Annotated[float | None, Field(ge=0)]
    retained_branch_id: Sha256Digest | None
    reason: Annotated[str, StringConstraints(min_length=1, max_length=512)]

    @model_validator(mode="after")
    def _identity_is_canonical(self) -> Self:
        if self.left_branch_id >= self.right_branch_id:
            raise ValueError("duplicate branch identities must be ordered")
        collapsed = self.status in {
            DuplicateBranchStatus.COLLAPSED_EXACT_SUPPORT,
            DuplicateBranchStatus.COLLAPSED_ALIAS_HYPOTHESIS,
        }
        if collapsed != (self.retained_branch_id is not None):
            raise ValueError("duplicate collapse retention identity is inconsistent")
        return self


class MultiTargetAssociationV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["global-min-cost-path-cover-v1"] = "global-min-cost-path-cover-v1"
    config_digest: Sha256Digest
    source_observation_count: Annotated[int, Field(ge=0)]
    returned_observation_count: Annotated[int, Field(ge=0, le=9_600)]
    truncated_observation_count: Annotated[int, Field(ge=0)]
    source_edge_count: Annotated[int, Field(ge=0)]
    returned_edge_count: Annotated[int, Field(ge=0, le=65_536)]
    truncated_edge_count: Annotated[int, Field(ge=0)]
    source_branch_count: Annotated[int, Field(ge=0)]
    returned_branch_count: Annotated[int, Field(ge=0, le=64)]
    truncated_branch_count: Annotated[int, Field(ge=0)]
    assignment_iterations: Annotated[int, Field(ge=1, le=32)]
    converged: bool
    observations: Annotated[tuple[MultiTargetObservationV1, ...], Field(max_length=9_600)]
    edge_decisions: Annotated[tuple[AssociationEdgeDecisionV1, ...], Field(max_length=65_536)]
    branches: Annotated[tuple[MultiTargetBranchV1, ...], Field(max_length=64)]
    duplicate_decisions: Annotated[tuple[DuplicateBranchDecisionV1, ...], Field(max_length=2_016)]
    status: StandardScientificStatus
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closure_is_exact(self) -> Self:
        if (
            self.returned_observation_count + self.truncated_observation_count
            != self.source_observation_count
            or len(self.observations) != self.returned_observation_count
            or self.returned_edge_count + self.truncated_edge_count != self.source_edge_count
            or len(self.edge_decisions) != self.returned_edge_count
            or self.returned_branch_count + self.truncated_branch_count != self.source_branch_count
            or len(self.branches) != self.returned_branch_count
        ):
            raise ValueError("multi-target association accounting is inconsistent")
        branch_ids = tuple(item.branch_id for item in self.branches)
        if branch_ids != tuple(sorted(set(branch_ids))):
            raise ValueError("multi-target branches must be unique and ordered")
        selected = {
            (item.source_observation_id, item.destination_observation_id)
            for item in self.edge_decisions
            if item.selected
        }
        if sum(max(0, len(item.observation_ids) - 1) for item in self.branches) != len(selected):
            raise ValueError("selected edge inventory disagrees with branch paths")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("multi-target association digest does not match content")
        return self
