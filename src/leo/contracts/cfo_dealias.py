"""Bounded candidate-only contracts for CFO de-aliasing and final trajectories."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import StandardScientificStatus

BoundedReason = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class AliasPairStatus(StrEnum):
    ALIAS_EQUIVALENT = "alias_equivalent"
    REJECTED_RESIDUAL = "rejected_residual"
    NOT_COMPARED_NO_OVERLAP = "not_compared_no_overlap"


class LiftReplayStatus(StrEnum):
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INSUFFICIENT_DATA = "insufficient_data"


class CfoDealiasConfigV1(ContractModel):
    schema_version: Literal[1] = 1
    alias_spacing_numerator_hz: Literal[2_500_000] = 2_500_000
    alias_spacing_denominator: Literal[11] = 11
    minimum_overlap_s: Annotated[float, Field(gt=0)]
    comparison_point_count: Literal[128]
    maximum_alias_residual_hz: Annotated[float, Field(gt=0)]
    maximum_raw_representatives: Annotated[int, Field(ge=1, le=64)]
    maximum_pair_comparisons: Annotated[int, Field(ge=1, le=2016)]
    maximum_alias_components: Annotated[int, Field(ge=1, le=64)]
    maximum_observations_per_component: Annotated[int, Field(ge=4, le=9600)]
    maximum_observed_lifts_per_component: Annotated[int, Field(ge=1, le=5)]
    maximum_final_lifts_per_component: Annotated[int, Field(ge=1, le=3)]
    maximum_final_trajectories: Annotated[int, Field(ge=1, le=64)]
    polynomial_degrees: tuple[Literal[1, 2, 3], ...]
    continuity_gap_s: Annotated[float, Field(gt=0)]
    association_frequency_gate_hz: Annotated[float, Field(gt=0)]
    association_slope_gate_hz_per_s: Annotated[float, Field(gt=0)]
    association_acceleration_gate_hz_per_s2: Annotated[float, Field(gt=0)]
    maximum_branches_per_component: Annotated[int, Field(ge=1, le=16)]
    maximum_assignment_iterations: Annotated[int, Field(ge=1, le=32)]
    replay_gate_version: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9._-]+$"),
    ]

    @field_validator(
        "minimum_overlap_s",
        "maximum_alias_residual_hz",
        "continuity_gap_s",
        "association_frequency_gate_hz",
        "association_slope_gate_hz_per_s",
        "association_acceleration_gate_hz_per_s2",
    )
    @classmethod
    def _finite_floats(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("CFO de-alias configuration values must be finite")
        return value

    @model_validator(mode="after")
    def _canonical_inventory(self) -> Self:
        if self.polynomial_degrees != (1, 2, 3):
            raise ValueError("CFO de-alias polynomial degrees must be exactly (1, 2, 3)")
        maximum_pairs = (
            self.maximum_raw_representatives * (self.maximum_raw_representatives - 1) // 2
        )
        if self.maximum_pair_comparisons > maximum_pairs:
            raise ValueError("pair-comparison bound exceeds the representative inventory")
        return self

    @property
    def alias_spacing_hz(self) -> float:
        return self.alias_spacing_numerator_hz / self.alias_spacing_denominator

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class CfoAliasPairDecisionV1(ContractModel):
    schema_version: Literal[1] = 1
    left_trajectory_id: Sha256Digest
    right_trajectory_id: Sha256Digest
    status: AliasPairStatus
    overlap_s: Annotated[float, Field(ge=0)]
    alias_index_delta: int | None
    residual_rms_hz: Annotated[float | None, Field(ge=0)]
    maximum_absolute_residual_hz: Annotated[float | None, Field(ge=0)]
    reason: BoundedReason

    @field_validator("overlap_s", "residual_rms_hz", "maximum_absolute_residual_hz")
    @classmethod
    def _finite_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("CFO alias pair values must be finite")
        return value

    @model_validator(mode="after")
    def _status_fields_match(self) -> Self:
        has_fit = (
            self.alias_index_delta is not None
            and self.residual_rms_hz is not None
            and self.maximum_absolute_residual_hz is not None
        )
        if self.status is AliasPairStatus.NOT_COMPARED_NO_OVERLAP and has_fit:
            raise ValueError("non-overlap pair cannot carry residual evidence")
        if self.status is not AliasPairStatus.NOT_COMPARED_NO_OVERLAP and not has_fit:
            raise ValueError("evaluated alias pair requires complete residual evidence")
        if self.left_trajectory_id >= self.right_trajectory_id:
            raise ValueError("alias pair identities must be canonically ordered")
        return self


class CfoAliasMemberV1(ContractModel):
    schema_version: Literal[1] = 1
    trajectory_id: Sha256Digest
    component_id: Sha256Digest
    relative_alias_index: int


class CfoAliasMapV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["cfo-alias-map-v1"] = "cfo-alias-map-v1"
    config_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    alias_spacing_numerator_hz: Literal[2_500_000] = 2_500_000
    alias_spacing_denominator: Literal[11] = 11
    source_representative_count: Annotated[int, Field(ge=0)]
    returned_representative_count: Annotated[int, Field(ge=0, le=64)]
    truncated_representative_count: Annotated[int, Field(ge=0)]
    component_count: Annotated[int, Field(ge=0, le=64)]
    members: Annotated[tuple[CfoAliasMemberV1, ...], Field(max_length=64)]
    pair_decisions: Annotated[tuple[CfoAliasPairDecisionV1, ...], Field(max_length=2016)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closure_is_exact(self) -> Self:
        if (
            self.returned_representative_count + self.truncated_representative_count
            != self.source_representative_count
            or len(self.members) != self.returned_representative_count
        ):
            raise ValueError("alias representative accounting is inconsistent")
        member_ids = tuple(item.trajectory_id for item in self.members)
        if member_ids != tuple(sorted(member_ids)) or len(set(member_ids)) != len(member_ids):
            raise ValueError("alias members must be unique and canonically ordered")
        components = {item.component_id for item in self.members}
        if len(components) != self.component_count:
            raise ValueError("alias component count disagrees with members")
        pair_keys = tuple(
            (item.left_trajectory_id, item.right_trajectory_id) for item in self.pair_decisions
        )
        if pair_keys != tuple(sorted(pair_keys)) or len(set(pair_keys)) != len(pair_keys):
            raise ValueError("alias pair decisions must be unique and canonically ordered")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("alias-map content digest does not match")
        return self


class CanonicalObservationV1(ContractModel):
    schema_version: Literal[1] = 1
    observation_id: Sha256Digest
    component_id: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    time_s: Annotated[float, Field(ge=0)]
    raw_cfo_hz: float
    component_cfo_hz: float
    residue_cfo_hz: float
    alias_index: int
    source_alias_indices: Annotated[tuple[int, ...], Field(min_length=1, max_length=5)]
    source_observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=8)]
    source_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=64)]

    @field_validator("time_s", "raw_cfo_hz", "component_cfo_hz", "residue_cfo_hz")
    @classmethod
    def _finite_observation(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("canonical observation values must be finite")
        return value

    @model_validator(mode="after")
    def _sources_are_canonical(self) -> Self:
        if (
            self.source_alias_indices != tuple(sorted(set(self.source_alias_indices)))
            or self.source_observation_ids != tuple(sorted(set(self.source_observation_ids)))
            or self.source_trajectory_ids != tuple(sorted(set(self.source_trajectory_ids)))
        ):
            raise ValueError("canonical observation sources must be unique and ordered")
        return self


class CanonicalPolynomialV1(ContractModel):
    schema_version: Literal[1] = 1
    model_id: Sha256Digest
    polynomial_degree: Literal[1, 2, 3]
    reference_time_s: Annotated[float, Field(ge=0)]
    coefficients_hz: Annotated[tuple[float, ...], Field(min_length=2, max_length=4)]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=9600)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    bic: float

    @field_validator(
        "reference_time_s", "start_s", "end_s", "residual_rms_hz", "residual_max_hz", "bic"
    )
    @classmethod
    def _finite_model_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("canonical polynomial values must be finite")
        return value

    @field_validator("coefficients_hz")
    @classmethod
    def _finite_coefficients(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("canonical polynomial coefficients must be finite")
        return value

    @model_validator(mode="after")
    def _geometry_is_consistent(self) -> Self:
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("canonical polynomial coefficient count is invalid")
        if self.start_s > self.end_s:
            raise ValueError("canonical polynomial interval is reversed")
        if self.observation_ids != tuple(sorted(set(self.observation_ids))):
            raise ValueError("canonical polynomial observation IDs must be unique and ordered")
        return self


class CanonicalBranchV1(ContractModel):
    schema_version: Literal[1] = 1
    branch_id: Sha256Digest
    component_id: Sha256Digest
    observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=9600)]
    observed_alias_indices: Annotated[tuple[int, ...], Field(min_length=1, max_length=5)]
    models: Annotated[tuple[CanonicalPolynomialV1, ...], Field(min_length=1, max_length=3)]
    selected_model_id: Sha256Digest
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _branch_is_closed(self) -> Self:
        if self.observation_ids != tuple(sorted(set(self.observation_ids))):
            raise ValueError("branch observations must be unique and ordered")
        if self.observed_alias_indices != tuple(sorted(set(self.observed_alias_indices))):
            raise ValueError("branch alias indices must be unique and ordered")
        if tuple(item.polynomial_degree for item in self.models) != (1, 2, 3):
            raise ValueError("branch must contain ordered degree 1/2/3 models")
        if self.selected_model_id not in {item.model_id for item in self.models}:
            raise ValueError("branch selected model is absent")
        if self.start_s > self.end_s:
            raise ValueError("branch interval is reversed")
        return self


class DealiasedTrajectoryBankV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["dealiased-trajectory-bank-v1"] = "dealiased-trajectory-bank-v1"
    config_digest: Sha256Digest
    alias_map_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    source_observation_count: Annotated[int, Field(ge=0)]
    returned_observation_count: Annotated[int, Field(ge=0)]
    truncated_observation_count: Annotated[int, Field(ge=0)]
    source_branch_count: Annotated[int, Field(ge=0)]
    returned_branch_count: Annotated[int, Field(ge=0, le=64)]
    truncated_branch_count: Annotated[int, Field(ge=0)]
    observations: Annotated[tuple[CanonicalObservationV1, ...], Field(max_length=9600)]
    branches: Annotated[tuple[CanonicalBranchV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _bank_is_closed(self) -> Self:
        if (
            self.returned_observation_count + self.truncated_observation_count
            != self.source_observation_count
            or len(self.observations) != self.returned_observation_count
            or self.returned_branch_count + self.truncated_branch_count != self.source_branch_count
            or len(self.branches) != self.returned_branch_count
        ):
            raise ValueError("de-aliased bank accounting is inconsistent")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("de-aliased bank content digest does not match")
        return self


class CfoLiftReplayRowV1(ContractModel):
    schema_version: Literal[1] = 1
    branch_id: Sha256Digest
    canonical_model_id: Sha256Digest
    alias_index: int
    status: LiftReplayStatus
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    improved_probe_count: Annotated[int, Field(ge=0)]
    median_margin_delta: float | None
    median_control_separation: float | None
    reason: BoundedReason

    @field_validator("median_margin_delta", "median_control_separation")
    @classmethod
    def _finite_metrics(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("lift replay metrics must be finite")
        return value

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> Self:
        if self.improved_probe_count > self.evaluated_probe_count:
            raise ValueError("improved replay probes exceed evaluated probes")
        return self


class CfoLiftReplayV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["cfo-lift-replay-v1"] = "cfo-lift-replay-v1"
    config_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    source_lift_count: Annotated[int, Field(ge=0)]
    returned_lift_count: Annotated[int, Field(ge=0, le=320)]
    truncated_lift_count: Annotated[int, Field(ge=0)]
    rows: Annotated[tuple[CfoLiftReplayRowV1, ...], Field(max_length=320)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _replay_is_closed(self) -> Self:
        if (
            self.returned_lift_count + self.truncated_lift_count != self.source_lift_count
            or len(self.rows) != self.returned_lift_count
        ):
            raise ValueError("lift replay accounting is inconsistent")
        keys = tuple((item.branch_id, item.alias_index) for item in self.rows)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("lift replay rows must be unique and ordered")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("lift replay content digest does not match")
        return self


class FinalTrajectoryV1(ContractModel):
    schema_version: Literal[1] = 1
    trajectory_id: Sha256Digest
    component_id: Sha256Digest
    branch_id: Sha256Digest
    canonical_model_id: Sha256Digest
    alias_index: int
    polynomial_degree: Literal[1, 2, 3]
    reference_time_s: Annotated[float, Field(ge=0)]
    canonical_coefficients_hz: Annotated[tuple[float, ...], Field(min_length=2, max_length=4)]
    absolute_coefficients_hz: Annotated[tuple[float, ...], Field(min_length=2, max_length=4)]
    start_s: Annotated[float, Field(ge=0)]
    end_s: Annotated[float, Field(ge=0)]
    observation_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=9600)]
    replayed_probe_count: Annotated[int, Field(ge=0)]
    median_margin_delta: float
    median_control_separation: float

    @model_validator(mode="after")
    def _trajectory_is_consistent(self) -> Self:
        expected = self.polynomial_degree + 1
        if (
            len(self.canonical_coefficients_hz) != expected
            or len(self.absolute_coefficients_hz) != expected
            or self.start_s > self.end_s
        ):
            raise ValueError("final trajectory geometry is inconsistent")
        finite = (
            self.reference_time_s,
            self.start_s,
            self.end_s,
            self.median_margin_delta,
            self.median_control_separation,
            *self.canonical_coefficients_hz,
            *self.absolute_coefficients_hz,
        )
        if any(not math.isfinite(value) for value in finite):
            raise ValueError("final trajectory values must be finite")
        if self.observation_ids != tuple(sorted(set(self.observation_ids))):
            raise ValueError("final trajectory observations must be unique and ordered")
        return self


class FinalTrajectoryBankV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["final-trajectory-bank-v1"] = "final-trajectory-bank-v1"
    config_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    lift_replay_digest: Sha256Digest
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _final_bank_is_closed(self) -> Self:
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final trajectory accounting is inconsistent")
        ids = tuple(item.trajectory_id for item in self.trajectories)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("final trajectories must be unique and ordered")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final trajectory bank content digest does not match")
        return self


class Glrt64FinalTrajectoryTableV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["glrt64-final-trajectory-table-v1"] = (
        "glrt64-final-trajectory-table-v1"
    )
    final_trajectory_bank_digest: Sha256Digest
    frequency_model: Literal["cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"] = (
        "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
    )
    coefficient_order: Literal["highest_polynomial_power_first"] = "highest_polynomial_power_first"
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _table_is_closed(self) -> Self:
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final trajectory table accounting is inconsistent")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final trajectory table content digest does not match")
        return self


def _digest_without(model: ContractModel, field: str) -> Sha256Digest:
    document = model.model_dump(mode="json")
    document.pop(field)
    return canonical_digest(document)
