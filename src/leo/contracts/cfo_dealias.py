"""Bounded candidate-only contracts for CFO de-aliasing and final trajectories."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_target import MultiTargetAssociationV1
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


class LiftReplayTierV2(StrEnum):
    """Scientific disposition of a replayed lift, separate from V1 pass/fail."""

    REPLAY_IMPROVED = "replay_improved"
    REPLAY_STABLE = "replay_stable"
    GEOMETRY_ONLY = "geometry_only"
    REPLAY_REJECTED = "replay_rejected"
    INSUFFICIENT = "insufficient"


class LiftReplayTierV3(StrEnum):
    """Absolute-evidence replay disposition; relative delta is audit-only."""

    AUTOMATIC = "automatic"
    GEOMETRY_ONLY = "geometry_only"
    REPLAY_REJECTED = "replay_rejected"
    INSUFFICIENT = "insufficient"


class ReplayGateConfigV2(ContractModel):
    """Frozen block-level replay gate and its explicit null calibration."""

    schema_version: Literal[2] = 2
    gate_version: Literal["glrt64-block-equivalence-v2"] = "glrt64-block-equivalence-v2"
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    block_duration_s: Annotated[float, Field(gt=0)] = 1.0
    minimum_observation_count: Annotated[int, Field(ge=3)] = 5
    minimum_duration_s: Annotated[float, Field(gt=0)] = 1.0
    maximum_geometry_residual_rms_hz: Annotated[float, Field(gt=0)] = 2_500.0
    maximum_geometry_residual_hz: Annotated[float, Field(gt=0)] = 8_000.0
    minimum_probe_count: Annotated[int, Field(ge=1)] = 20
    minimum_block_count: Annotated[int, Field(ge=1)] = 3
    minimum_block_coverage_ratio: Annotated[float, Field(gt=0, le=1)] = 0.5
    minimum_median_corrected_margin: Annotated[float, Field(ge=0)] = 0.05
    maximum_harmful_block_fraction: Annotated[float, Field(ge=0, le=1)] = 0.25
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)] = 2
    harmful_block_delta: Annotated[float, Field(lt=0)] = -0.02
    simpler_model_bic_delta: Annotated[float, Field(ge=0)] = 2.0
    equivalence_control_receipt_digest: Sha256Digest
    equivalence_control_block_count: Annotated[int, Field(ge=20)]
    equivalence_control_p95_absolute_delta: Annotated[float, Field(gt=0)]
    equivalence_safety_multiplier: Annotated[float, Field(ge=1)] = 2.0

    @field_validator(
        "block_duration_s",
        "minimum_duration_s",
        "maximum_geometry_residual_rms_hz",
        "maximum_geometry_residual_hz",
        "minimum_block_coverage_ratio",
        "minimum_median_corrected_margin",
        "maximum_harmful_block_fraction",
        "harmful_block_delta",
        "simpler_model_bic_delta",
        "equivalence_control_p95_absolute_delta",
        "equivalence_safety_multiplier",
    )
    @classmethod
    def _finite_gate_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("replay gate values must be finite")
        return value

    @model_validator(mode="after")
    def _gate_is_coherent(self) -> Self:
        if self.maximum_geometry_residual_rms_hz > self.maximum_geometry_residual_hz:
            raise ValueError("geometry RMS gate cannot exceed the maximum-residual gate")
        _ = self.samples_per_block
        if not math.isfinite(self.equivalence_tolerance):
            raise ValueError("derived equivalence tolerance must be finite")
        return self

    @property
    def equivalence_tolerance(self) -> float:
        return self.equivalence_control_p95_absolute_delta * self.equivalence_safety_multiplier

    @property
    def samples_per_block(self) -> int:
        samples = self.sample_rate_hz * self.block_duration_s
        rounded = round(samples)
        if not math.isclose(samples, rounded, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("replay block duration must map to an integral sample count")
        return rounded

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class ReplayGateConfigV3(ContractModel):
    """Absolute GLRT evidence and harmful-tail gate.

    Block metrics remain auditable, but neither block count nor comparison with
    the independently optimized baseline decides eligibility.
    """

    schema_version: Literal[3] = 3
    gate_version: Literal["glrt64-absolute-tail-v3"] = "glrt64-absolute-tail-v3"
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    block_duration_s: Annotated[float, Field(gt=0)] = 1.0
    minimum_observation_count: Annotated[int, Field(ge=3)] = 5
    minimum_duration_s: Annotated[float, Field(gt=0)] = 1.0
    maximum_geometry_residual_rms_hz: Annotated[float, Field(gt=0)] = 2_500.0
    maximum_geometry_residual_hz: Annotated[float, Field(gt=0)] = 8_000.0
    minimum_probe_count: Annotated[int, Field(ge=1)] = 20
    minimum_block_coverage_ratio: Annotated[float, Field(gt=0, le=1)] = 0.5
    minimum_median_corrected_margin: Annotated[float, Field(ge=0)] = 0.05
    maximum_harmful_block_fraction: Annotated[float, Field(ge=0, le=1)] = 0.25
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)] = 2
    harmful_block_delta: Annotated[float, Field(lt=0)] = -0.02
    simpler_model_bic_delta: Annotated[float, Field(ge=0)] = 2.0

    @field_validator(
        "block_duration_s",
        "minimum_duration_s",
        "maximum_geometry_residual_rms_hz",
        "maximum_geometry_residual_hz",
        "minimum_block_coverage_ratio",
        "minimum_median_corrected_margin",
        "maximum_harmful_block_fraction",
        "harmful_block_delta",
        "simpler_model_bic_delta",
    )
    @classmethod
    def _finite_gate_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("V3 replay gate values must be finite")
        return value

    @model_validator(mode="after")
    def _gate_is_coherent(self) -> Self:
        if self.maximum_geometry_residual_rms_hz > self.maximum_geometry_residual_hz:
            raise ValueError("geometry RMS gate cannot exceed the maximum-residual gate")
        _ = self.samples_per_block
        return self

    @property
    def samples_per_block(self) -> int:
        samples = self.sample_rate_hz * self.block_duration_s
        rounded = round(samples)
        if not math.isclose(samples, rounded, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("replay block duration must map to an integral sample count")
        return rounded

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class ReplayGateConfigV4(ContractModel):
    """Absolute GLRT evidence gate with harmful deltas retained for audit only."""

    schema_version: Literal[4] = 4
    gate_version: Literal["glrt64-absolute-audit-v4"] = "glrt64-absolute-audit-v4"
    sample_rate_hz: Annotated[int, Field(gt=0)] = 2_500_000
    block_duration_s: Annotated[float, Field(gt=0)] = 1.0
    minimum_observation_count: Annotated[int, Field(ge=3)] = 5
    minimum_duration_s: Annotated[float, Field(gt=0)] = 1.0
    maximum_geometry_residual_rms_hz: Annotated[float, Field(gt=0)] = 2_500.0
    maximum_geometry_residual_hz: Annotated[float, Field(gt=0)] = 8_000.0
    minimum_probe_count: Annotated[int, Field(ge=1)] = 20
    minimum_block_coverage_ratio: Annotated[float, Field(gt=0, le=1)] = 0.5
    minimum_median_corrected_margin: Annotated[float, Field(ge=0)] = 0.05
    harmful_block_delta: Annotated[float, Field(lt=0)] = -0.02
    simpler_model_bic_delta: Annotated[float, Field(ge=0)] = 2.0

    @field_validator(
        "block_duration_s",
        "minimum_duration_s",
        "maximum_geometry_residual_rms_hz",
        "maximum_geometry_residual_hz",
        "minimum_block_coverage_ratio",
        "minimum_median_corrected_margin",
        "harmful_block_delta",
        "simpler_model_bic_delta",
    )
    @classmethod
    def _finite_gate_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("V4 replay gate values must be finite")
        return value

    @model_validator(mode="after")
    def _gate_is_coherent(self) -> Self:
        if self.maximum_geometry_residual_rms_hz > self.maximum_geometry_residual_hz:
            raise ValueError("geometry RMS gate cannot exceed the maximum-residual gate")
        _ = self.samples_per_block
        return self

    @property
    def samples_per_block(self) -> int:
        samples = self.sample_rate_hz * self.block_duration_s
        rounded = round(samples)
        if not math.isclose(samples, rounded, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("replay block duration must map to an integral sample count")
        return rounded

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class FinalTrajectorySelectionConfigV1(ContractModel):
    """Display-only fallback policy, deliberately separate from replay science."""

    schema_version: Literal[1] = 1
    policy_version: Literal["one-safe-geometry-fallback-v1"] = "one-safe-geometry-fallback-v1"
    minimum_corrected_margin: Annotated[float, Field(ge=0)] = 0.0025
    require_zero_harmful_blocks: Literal[True] = True
    maximum_fallbacks_per_branch: Literal[1] = 1
    ranking: Literal["corrected-margin-desc-absolute-alias-asc"] = (
        "corrected-margin-desc-absolute-alias-asc"
    )

    @field_validator("minimum_corrected_margin")
    @classmethod
    def _finite_floor(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("selection evidence floor must be finite")
        return value

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class FinalTrajectorySelectionConfigV2(ContractModel):
    """Display fallback policy whose harmful metrics are audit-only."""

    schema_version: Literal[2] = 2
    policy_version: Literal["one-evidence-geometry-fallback-v2"] = (
        "one-evidence-geometry-fallback-v2"
    )
    minimum_corrected_margin: Annotated[float, Field(ge=0)] = 0.0025
    maximum_fallbacks_per_branch: Literal[1] = 1
    ranking: Literal["corrected-margin-desc-absolute-alias-asc"] = (
        "corrected-margin-desc-absolute-alias-asc"
    )

    @field_validator("minimum_corrected_margin")
    @classmethod
    def _finite_floor(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("selection evidence floor must be finite")
        return value

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class AliasComponentStatus(StrEnum):
    RESOLVED = "resolved"
    INSUFFICIENT_CONTRADICTORY_CYCLE = "insufficient_contradictory_cycle"


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


class SeededAliasEmConfigV1(ContractModel):
    """Bounded seed-preserving refinement used after the first trajectory EM."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["seed-preserving-alias-hard-em-v1"] = (
        "seed-preserving-alias-hard-em-v1"
    )
    maximum_alias_index: Annotated[int, Field(ge=0, le=8)] = 4
    maximum_iterations: Annotated[int, Field(ge=1, le=32)] = 12
    huber_scale_floor_hz: Annotated[float, Field(gt=0)] = 100.0
    one_candidate_per_probe: Literal[True] = True
    preserve_seed_identity: Literal[True] = True

    @field_validator("huber_scale_floor_hz")
    @classmethod
    def _finite_huber_floor(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("seeded alias EM Huber floor must be finite")
        return value

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


class CfoAliasComponentV2(ContractModel):
    schema_version: Literal[2] = 2
    component_id: Sha256Digest
    trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=64)]
    status: AliasComponentStatus
    contradictory_edge_count: Annotated[int, Field(ge=0, le=2016)]
    reason: BoundedReason

    @model_validator(mode="after")
    def _status_is_truthful(self) -> Self:
        if self.trajectory_ids != tuple(sorted(set(self.trajectory_ids))):
            raise ValueError("alias component trajectory IDs must be unique and ordered")
        if (self.status is AliasComponentStatus.RESOLVED) != (self.contradictory_edge_count == 0):
            raise ValueError("alias component status disagrees with contradictory edges")
        return self


class CfoAliasMapV2(ContractModel):
    """Alias graph whose contradictory components fail locally and explicitly."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["cfo-alias-map-v2"] = "cfo-alias-map-v2"
    config_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    alias_spacing_numerator_hz: Literal[2_500_000] = 2_500_000
    alias_spacing_denominator: Literal[11] = 11
    source_representative_count: Annotated[int, Field(ge=0)]
    returned_representative_count: Annotated[int, Field(ge=0, le=64)]
    truncated_representative_count: Annotated[int, Field(ge=0)]
    component_count: Annotated[int, Field(ge=0, le=64)]
    insufficient_component_count: Annotated[int, Field(ge=0, le=64)]
    components: Annotated[tuple[CfoAliasComponentV2, ...], Field(max_length=64)]
    members: Annotated[tuple[CfoAliasMemberV1, ...], Field(max_length=64)]
    pair_decisions: Annotated[tuple[CfoAliasPairDecisionV1, ...], Field(max_length=2016)]
    status: StandardScientificStatus
    reason: BoundedReason
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
            or len(self.components) != self.component_count
        ):
            raise ValueError("alias-map V2 accounting is inconsistent")
        member_ids = tuple(item.trajectory_id for item in self.members)
        if member_ids != tuple(sorted(member_ids)) or len(set(member_ids)) != len(member_ids):
            raise ValueError("alias-map V2 members must be unique and ordered")
        member_by_id = {item.trajectory_id: item for item in self.members}
        component_ids = tuple(item.component_id for item in self.components)
        if component_ids != tuple(sorted(component_ids)) or len(set(component_ids)) != len(
            component_ids
        ):
            raise ValueError("alias-map V2 components must be unique and ordered")
        if {item.component_id for item in self.members} != set(component_ids):
            raise ValueError("alias-map V2 members must exactly cover declared components")
        by_component = {
            component_id: tuple(
                item.trajectory_id for item in self.members if item.component_id == component_id
            )
            for component_id in component_ids
        }
        if any(
            tuple(sorted(by_component[item.component_id])) != item.trajectory_ids
            for item in self.components
        ):
            raise ValueError("alias-map V2 component membership disagrees")
        insufficient = sum(
            item.status is AliasComponentStatus.INSUFFICIENT_CONTRADICTORY_CYCLE
            for item in self.components
        )
        if insufficient != self.insufficient_component_count:
            raise ValueError("alias-map V2 insufficient component count disagrees")
        expected_status = (
            StandardScientificStatus.PARTIAL
            if insufficient and insufficient < self.component_count
            else StandardScientificStatus.INSUFFICIENT_DATA
            if insufficient
            else StandardScientificStatus.COMPLETE
            if self.components
            else StandardScientificStatus.NO_RESULT
        )
        if self.status is not expected_status:
            raise ValueError("alias-map V2 status disagrees with component outcomes")
        pair_keys = tuple(
            (item.left_trajectory_id, item.right_trajectory_id) for item in self.pair_decisions
        )
        if pair_keys != tuple(sorted(pair_keys)) or len(set(pair_keys)) != len(pair_keys):
            raise ValueError("alias-map V2 pair decisions must be unique and ordered")
        expected_pair_keys = tuple(
            (left, right)
            for left_index, left in enumerate(member_ids)
            for right in member_ids[left_index + 1 :]
        )
        if pair_keys != expected_pair_keys:
            raise ValueError("alias-map V2 pair decisions must exactly cover retained members")

        adjacency: dict[Sha256Digest, set[Sha256Digest]] = {
            trajectory_id: set() for trajectory_id in member_ids
        }
        accepted_by_component: dict[Sha256Digest, list[CfoAliasPairDecisionV1]] = {
            component_id: [] for component_id in component_ids
        }
        contradiction_counts = {component_id: 0 for component_id in component_ids}
        for pair in self.pair_decisions:
            if pair.status is not AliasPairStatus.ALIAS_EQUIVALENT:
                continue
            left = member_by_id[pair.left_trajectory_id]
            right = member_by_id[pair.right_trajectory_id]
            if left.component_id != right.component_id:
                raise ValueError("accepted alias edge crosses declared components")
            adjacency[left.trajectory_id].add(right.trajectory_id)
            adjacency[right.trajectory_id].add(left.trajectory_id)
            accepted_by_component[left.component_id].append(pair)
            assert pair.alias_index_delta is not None
            actual_delta = right.relative_alias_index - left.relative_alias_index
            if actual_delta != pair.alias_index_delta:
                contradiction_counts[left.component_id] += 1

        discovered: list[tuple[Sha256Digest, ...]] = []
        unseen = set(member_ids)
        while unseen:
            pending = [min(unseen)]
            connected: set[Sha256Digest] = set()
            while pending:
                trajectory_id = pending.pop()
                if trajectory_id in connected:
                    continue
                connected.add(trajectory_id)
                pending.extend(sorted(adjacency[trajectory_id] - connected, reverse=True))
            unseen -= connected
            discovered.append(tuple(sorted(connected)))
        declared = tuple(sorted(item.trajectory_ids for item in self.components))
        if tuple(sorted(discovered)) != declared:
            raise ValueError("alias-map V2 components disagree with accepted-edge connectivity")
        for component in self.components:
            accepted_edges = tuple(
                item.model_dump(mode="json")
                for item in sorted(
                    accepted_by_component[component.component_id],
                    key=lambda item: (item.left_trajectory_id, item.right_trajectory_id),
                )
            )
            expected_component_id = canonical_digest(
                {"trajectory_ids": component.trajectory_ids, "edges": accepted_edges}
            )
            if component.component_id != expected_component_id:
                raise ValueError("alias-map V2 component identity disagrees with accepted edges")
            if component.contradictory_edge_count != contradiction_counts[component.component_id]:
                raise ValueError(
                    "alias-map V2 contradiction count disagrees with integer potentials"
                )
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("alias-map V2 content digest does not match")
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


class DealiasedTrajectoryBankV2(ContractModel):
    """Canonical branch bank with its exact global assignment evidence."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["dealiased-trajectory-bank-v2"] = "dealiased-trajectory-bank-v2"
    config_digest: Sha256Digest
    alias_map_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    association_config_digest: Sha256Digest
    association: MultiTargetAssociationV1
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
    def _association_is_bound(self) -> Self:
        if (
            self.returned_observation_count + self.truncated_observation_count
            != self.source_observation_count
            or len(self.observations) != self.returned_observation_count
            or self.returned_branch_count + self.truncated_branch_count != self.source_branch_count
            or len(self.branches) != self.returned_branch_count
        ):
            raise ValueError("de-aliased v2 bank accounting is inconsistent")
        if self.association.config_digest != self.association_config_digest:
            raise ValueError("de-aliased bank association configuration digest mismatch")
        retained_paths = {
            frozenset(item.observation_ids)
            for item in self.association.branches
            if item.retained and len(item.observation_ids) >= 5
        }
        fitted_paths = {frozenset(item.observation_ids) for item in self.branches}
        if not fitted_paths.issubset(retained_paths):
            raise ValueError("de-aliased fitted branch is absent from global assignment")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("de-aliased v2 bank content digest does not match")
        return self


class SeededAliasEmDispositionV1(ContractModel):
    """Exact closure between one upstream seed and one refined branch."""

    schema_version: Literal[1] = 1
    seed_trajectory_id: Sha256Digest
    component_id: Sha256Digest
    output_branch_id: Sha256Digest
    source_observation_count: Annotated[int, Field(ge=5, le=9600)]
    selected_probe_count: Annotated[int, Field(ge=5, le=9600)]
    iteration_count: Annotated[int, Field(ge=1, le=32)]
    converged: bool
    observed_alias_indices: Annotated[tuple[int, ...], Field(min_length=1, max_length=5)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    maximum_absolute_residual_hz: Annotated[float, Field(ge=0)]
    reason: BoundedReason

    @field_validator("residual_rms_hz", "maximum_absolute_residual_hz")
    @classmethod
    def _finite_residuals(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("seeded alias EM residuals must be finite")
        return value

    @model_validator(mode="after")
    def _disposition_is_coherent(self) -> Self:
        if self.selected_probe_count > self.source_observation_count:
            raise ValueError("selected seed probes exceed source observations")
        if self.observed_alias_indices != tuple(sorted(set(self.observed_alias_indices))):
            raise ValueError("seeded alias indices must be unique and ordered")
        return self


class DealiasedTrajectoryBankV3(ContractModel):
    """Seed-preserving alias refinement with exact seed/output closure."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["seed-preserving-dealiased-trajectory-bank-v3"] = (
        "seed-preserving-dealiased-trajectory-bank-v3"
    )
    config_digest: Sha256Digest
    seeded_em_config_digest: Sha256Digest
    alias_map_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    source_observation_count: Annotated[int, Field(ge=0)]
    returned_observation_count: Annotated[int, Field(ge=0)]
    truncated_observation_count: Annotated[int, Field(ge=0)]
    source_branch_count: Annotated[int, Field(ge=0, le=64)]
    returned_branch_count: Annotated[int, Field(ge=0, le=64)]
    truncated_branch_count: Literal[0] = 0
    observations: Annotated[tuple[CanonicalObservationV1, ...], Field(max_length=64_000)]
    branches: Annotated[tuple[CanonicalBranchV1, ...], Field(max_length=64)]
    seed_dispositions: Annotated[tuple[SeededAliasEmDispositionV1, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _seed_closure_is_exact(self) -> Self:
        if (
            self.returned_observation_count + self.truncated_observation_count
            != self.source_observation_count
            or len(self.observations) != self.returned_observation_count
            or self.returned_branch_count != self.source_branch_count
            or len(self.branches) != self.returned_branch_count
            or len(self.seed_dispositions) != self.source_branch_count
        ):
            raise ValueError("seed-preserving de-aliased bank accounting is inconsistent")
        seed_ids = tuple(item.seed_trajectory_id for item in self.seed_dispositions)
        if seed_ids != tuple(sorted(set(seed_ids))):
            raise ValueError("seed dispositions must be unique and ordered")
        branch_by_id = {item.branch_id: item for item in self.branches}
        if len(branch_by_id) != len(self.branches):
            raise ValueError("seed-preserving branches must be unique")
        if {item.output_branch_id for item in self.seed_dispositions} != set(branch_by_id):
            raise ValueError("seed dispositions must exactly cover refined branches")
        observation_by_id = {item.observation_id: item for item in self.observations}
        if len(observation_by_id) != len(self.observations):
            raise ValueError("seed-preserving observations must be unique")
        for disposition in self.seed_dispositions:
            branch = branch_by_id[disposition.output_branch_id]
            if branch.component_id != disposition.component_id:
                raise ValueError("seed disposition component disagrees with its branch")
            if len(branch.observation_ids) != disposition.selected_probe_count:
                raise ValueError("seed disposition probe count disagrees with its branch")
            for observation_id in branch.observation_ids:
                observation = observation_by_id.get(observation_id)
                if observation is None or observation.source_trajectory_ids != (
                    disposition.seed_trajectory_id,
                ):
                    raise ValueError("refined branch does not preserve its seed membership")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("seed-preserving de-aliased bank content digest does not match")
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


class ReplayBlockMetricV2(ContractModel):
    schema_version: Literal[2] = 2
    block_index: Annotated[int, Field(ge=0)]
    probe_count: Annotated[int, Field(ge=1)]
    median_margin_delta: float
    median_corrected_margin: float

    @field_validator("median_margin_delta", "median_corrected_margin")
    @classmethod
    def _finite_block_metrics(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("block replay metrics must be finite")
        return value


class CfoLiftReplayRowV2(ContractModel):
    schema_version: Literal[2] = 2
    branch_id: Sha256Digest
    canonical_model_id: Sha256Digest
    alias_index: int
    tier: LiftReplayTierV2
    automatic_correction_eligible: bool
    geometry_display_eligible: bool
    observation_count: Annotated[int, Field(ge=0)]
    duration_s: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    polynomial_degree: Literal[1, 2, 3]
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    evaluated_block_count: Annotated[int, Field(ge=0)]
    eligible_block_count: Annotated[int, Field(ge=0)]
    block_coverage_ratio: Annotated[float, Field(ge=0, le=1)]
    improved_block_count: Annotated[int, Field(ge=0)]
    harmful_block_count: Annotated[int, Field(ge=0)]
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)]
    median_block_margin_delta: float | None
    q10_block_margin_delta: float | None
    median_block_corrected_margin: float | None
    equivalence_tolerance: Annotated[float, Field(gt=0)]
    blocks: Annotated[tuple[ReplayBlockMetricV2, ...], Field(max_length=600)]
    reasons: Annotated[tuple[BoundedReason, ...], Field(min_length=1, max_length=16)]

    @field_validator(
        "duration_s",
        "residual_rms_hz",
        "residual_max_hz",
        "block_coverage_ratio",
        "median_block_margin_delta",
        "q10_block_margin_delta",
        "median_block_corrected_margin",
        "equivalence_tolerance",
    )
    @classmethod
    def _finite_v2_metrics(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("V2 lift replay metrics must be finite")
        return value

    @model_validator(mode="after")
    def _tier_and_inventory_agree(self) -> Self:
        if len(self.blocks) != self.evaluated_block_count:
            raise ValueError("V2 block inventory count disagrees")
        if self.improved_block_count > self.evaluated_block_count:
            raise ValueError("improved blocks exceed evaluated blocks")
        if self.harmful_block_count > self.evaluated_block_count:
            raise ValueError("harmful blocks exceed evaluated blocks")
        automatic = self.tier in {
            LiftReplayTierV2.REPLAY_IMPROVED,
            LiftReplayTierV2.REPLAY_STABLE,
        }
        if self.automatic_correction_eligible != automatic:
            raise ValueError("automatic correction inventory disagrees with replay tier")
        if self.geometry_display_eligible and self.tier is LiftReplayTierV2.INSUFFICIENT:
            raise ValueError("insufficient geometry cannot enter the geometry display")
        return self


class CfoLiftReplayV2(ContractModel):
    schema_version: Literal[2] = 2
    algorithm_version: Literal["cfo-lift-replay-v2"] = "cfo-lift-replay-v2"
    gate_config: ReplayGateConfigV2
    gate_config_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    source_lift_count: Annotated[int, Field(ge=0)]
    returned_lift_count: Annotated[int, Field(ge=0, le=320)]
    truncated_lift_count: Annotated[int, Field(ge=0)]
    rows: Annotated[tuple[CfoLiftReplayRowV2, ...], Field(max_length=320)]
    automatic_correction_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    geometry_display_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _v2_replay_is_closed(self) -> Self:
        if self.gate_config_digest != self.gate_config.digest:
            raise ValueError("V2 replay gate digest disagrees with embedded configuration")
        if (
            self.returned_lift_count + self.truncated_lift_count != self.source_lift_count
            or len(self.rows) != self.returned_lift_count
        ):
            raise ValueError("V2 lift replay accounting is inconsistent")
        row_keys = tuple((row.branch_id, row.alias_index) for row in self.rows)
        keys = tuple(f"{branch_id}:{alias_index}" for branch_id, alias_index in row_keys)
        if row_keys != tuple(sorted(row_keys)) or len(set(row_keys)) != len(row_keys):
            raise ValueError("V2 lift replay rows must be unique and ordered")
        expected_automatic = tuple(
            key
            for key, row in zip(keys, self.rows, strict=True)
            if row.automatic_correction_eligible
        )
        expected_display = tuple(
            key for key, row in zip(keys, self.rows, strict=True) if row.geometry_display_eligible
        )
        if self.automatic_correction_lifts != expected_automatic:
            raise ValueError("automatic correction inventory is not derived from rows")
        if self.geometry_display_lifts != expected_display:
            raise ValueError("geometry display inventory is not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("V2 lift replay content digest does not match")
        return self


class ReplayBlockMetricV3(ContractModel):
    schema_version: Literal[3] = 3
    block_index: Annotated[int, Field(ge=0)]
    probe_count: Annotated[int, Field(ge=1)]
    median_margin_delta: float
    median_corrected_margin: float

    @field_validator("median_margin_delta", "median_corrected_margin")
    @classmethod
    def _finite_metrics(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("V3 block replay metrics must be finite")
        return value


class CfoLiftReplayRowV3(ContractModel):
    schema_version: Literal[3] = 3
    branch_id: Sha256Digest
    canonical_model_id: Sha256Digest
    alias_index: int
    tier: LiftReplayTierV3
    automatic_correction_eligible: bool
    geometry_display_eligible: bool
    observation_count: Annotated[int, Field(ge=0)]
    duration_s: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    polynomial_degree: Literal[1, 2, 3]
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    evaluated_block_count: Annotated[int, Field(ge=0)]
    eligible_block_count: Annotated[int, Field(ge=0)]
    block_coverage_ratio: Annotated[float, Field(ge=0, le=1)]
    improved_block_count: Annotated[int, Field(ge=0)]
    harmful_block_count: Annotated[int, Field(ge=0)]
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)]
    median_block_margin_delta: float | None
    q10_block_margin_delta: float | None
    median_block_corrected_margin: float | None
    blocks: Annotated[tuple[ReplayBlockMetricV3, ...], Field(max_length=600)]
    reasons: Annotated[tuple[BoundedReason, ...], Field(min_length=1, max_length=16)]

    @field_validator(
        "duration_s",
        "residual_rms_hz",
        "residual_max_hz",
        "block_coverage_ratio",
        "median_block_margin_delta",
        "q10_block_margin_delta",
        "median_block_corrected_margin",
    )
    @classmethod
    def _finite_metrics(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("V3 lift replay metrics must be finite")
        return value

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if len(self.blocks) != self.evaluated_block_count:
            raise ValueError("V3 block inventory count disagrees")
        if self.improved_block_count > self.evaluated_block_count:
            raise ValueError("improved blocks exceed evaluated blocks")
        if self.harmful_block_count > self.evaluated_block_count:
            raise ValueError("harmful blocks exceed evaluated blocks")
        if self.automatic_correction_eligible != (self.tier is LiftReplayTierV3.AUTOMATIC):
            raise ValueError("V3 correction inventory disagrees with replay tier")
        if self.geometry_display_eligible and self.tier is LiftReplayTierV3.INSUFFICIENT:
            raise ValueError("insufficient geometry cannot enter the geometry display")
        return self


class CfoLiftReplayV3(ContractModel):
    schema_version: Literal[3] = 3
    algorithm_version: Literal["cfo-lift-replay-v3"] = "cfo-lift-replay-v3"
    gate_config: ReplayGateConfigV3
    gate_config_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    source_lift_count: Annotated[int, Field(ge=0)]
    returned_lift_count: Annotated[int, Field(ge=0, le=320)]
    truncated_lift_count: Annotated[int, Field(ge=0)]
    rows: Annotated[tuple[CfoLiftReplayRowV3, ...], Field(max_length=320)]
    automatic_correction_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    geometry_display_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if self.gate_config_digest != self.gate_config.digest:
            raise ValueError("V3 replay gate digest disagrees with embedded configuration")
        if self.returned_lift_count + self.truncated_lift_count != self.source_lift_count:
            raise ValueError("V3 lift replay accounting is inconsistent")
        if len(self.rows) != self.returned_lift_count:
            raise ValueError("V3 returned lift count disagrees with rows")
        row_keys = tuple((row.branch_id, row.alias_index) for row in self.rows)
        keys = tuple(f"{branch}:{alias}" for branch, alias in row_keys)
        if row_keys != tuple(sorted(row_keys)) or len(set(row_keys)) != len(row_keys):
            raise ValueError("V3 lift replay rows must be unique and ordered")
        automatic = tuple(
            k for k, r in zip(keys, self.rows, strict=True) if r.automatic_correction_eligible
        )
        display = tuple(
            k for k, r in zip(keys, self.rows, strict=True) if r.geometry_display_eligible
        )
        if self.automatic_correction_lifts != automatic or self.geometry_display_lifts != display:
            raise ValueError("V3 replay inventories are not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("V3 lift replay content digest does not match")
        return self


class ReplayBlockMetricV4(ContractModel):
    schema_version: Literal[4] = 4
    block_index: Annotated[int, Field(ge=0)]
    probe_count: Annotated[int, Field(ge=1)]
    median_margin_delta: float
    median_corrected_margin: float

    @field_validator("median_margin_delta", "median_corrected_margin")
    @classmethod
    def _finite_metrics(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("V4 block replay metrics must be finite")
        return value


class CfoLiftReplayRowV4(ContractModel):
    """Replay decision with harmful-block values explicitly audit-only."""

    schema_version: Literal[4] = 4
    branch_id: Sha256Digest
    canonical_model_id: Sha256Digest
    alias_index: int
    tier: LiftReplayTierV3
    automatic_correction_eligible: bool
    geometry_display_eligible: bool
    observation_count: Annotated[int, Field(ge=0)]
    duration_s: Annotated[float, Field(ge=0)]
    residual_rms_hz: Annotated[float, Field(ge=0)]
    residual_max_hz: Annotated[float, Field(ge=0)]
    polynomial_degree: Literal[1, 2, 3]
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    evaluated_block_count: Annotated[int, Field(ge=0)]
    eligible_block_count: Annotated[int, Field(ge=0)]
    block_coverage_ratio: Annotated[float, Field(ge=0, le=1)]
    improved_block_count: Annotated[int, Field(ge=0)]
    harmful_block_count: Annotated[int, Field(ge=0)]
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)]
    median_block_margin_delta: float | None
    q10_block_margin_delta: float | None
    median_block_corrected_margin: float | None
    blocks: Annotated[tuple[ReplayBlockMetricV4, ...], Field(max_length=600)]
    reasons: Annotated[tuple[BoundedReason, ...], Field(min_length=1, max_length=16)]

    @field_validator(
        "duration_s",
        "residual_rms_hz",
        "residual_max_hz",
        "block_coverage_ratio",
        "median_block_margin_delta",
        "q10_block_margin_delta",
        "median_block_corrected_margin",
    )
    @classmethod
    def _finite_metrics(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("V4 lift replay metrics must be finite")
        return value

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if len(self.blocks) != self.evaluated_block_count:
            raise ValueError("V4 block inventory count disagrees")
        if self.improved_block_count > self.evaluated_block_count:
            raise ValueError("improved blocks exceed evaluated blocks")
        if self.harmful_block_count > self.evaluated_block_count:
            raise ValueError("harmful blocks exceed evaluated blocks")
        if self.maximum_consecutive_harmful_blocks > self.harmful_block_count:
            raise ValueError("harmful block run exceeds harmful block count")
        if self.automatic_correction_eligible != (self.tier is LiftReplayTierV3.AUTOMATIC):
            raise ValueError("V4 correction inventory disagrees with replay tier")
        if self.geometry_display_eligible and self.tier is LiftReplayTierV3.INSUFFICIENT:
            raise ValueError("insufficient geometry cannot enter the geometry display")
        return self


class CfoLiftReplayV4(ContractModel):
    schema_version: Literal[4] = 4
    algorithm_version: Literal["cfo-lift-replay-v4"] = "cfo-lift-replay-v4"
    gate_config: ReplayGateConfigV4
    gate_config_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    source_lift_count: Annotated[int, Field(ge=0)]
    returned_lift_count: Annotated[int, Field(ge=0, le=320)]
    truncated_lift_count: Annotated[int, Field(ge=0)]
    rows: Annotated[tuple[CfoLiftReplayRowV4, ...], Field(max_length=320)]
    automatic_correction_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    geometry_display_lifts: Annotated[tuple[str, ...], Field(max_length=320)]
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if self.gate_config_digest != self.gate_config.digest:
            raise ValueError("V4 replay gate digest disagrees with embedded configuration")
        if self.returned_lift_count + self.truncated_lift_count != self.source_lift_count:
            raise ValueError("V4 lift replay accounting is inconsistent")
        if len(self.rows) != self.returned_lift_count:
            raise ValueError("V4 returned lift count disagrees with rows")
        row_keys = tuple((row.branch_id, row.alias_index) for row in self.rows)
        keys = tuple(f"{branch}:{alias}" for branch, alias in row_keys)
        if row_keys != tuple(sorted(row_keys)) or len(set(row_keys)) != len(row_keys):
            raise ValueError("V4 lift replay rows must be unique and ordered")
        automatic = tuple(
            key
            for key, row in zip(keys, self.rows, strict=True)
            if row.automatic_correction_eligible
        )
        display = tuple(
            key for key, row in zip(keys, self.rows, strict=True) if row.geometry_display_eligible
        )
        if self.automatic_correction_lifts != automatic or self.geometry_display_lifts != display:
            raise ValueError("V4 replay inventories are not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("V4 lift replay content digest does not match")
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


class FinalTrajectoryV2(ContractModel):
    """A retained candidate trajectory with an explicit replay disposition.

    Geometry suitable for inspection is deliberately broader than the subset
    allowed to drive automatic IQ correction.  Keeping those two decisions in
    one immutable row prevents a visually credible line from disappearing while
    also preventing weak replay evidence from being promoted as correction-safe.
    """

    schema_version: Literal[2] = 2
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
    replay_tier: LiftReplayTierV2 | LiftReplayTierV3
    automatic_correction_eligible: bool
    geometry_display_eligible: Literal[True] = True
    evaluated_probe_count: Annotated[int, Field(ge=0)]
    evaluated_block_count: Annotated[int, Field(ge=0)]
    block_coverage_ratio: Annotated[float, Field(ge=0, le=1)]
    harmful_block_count: Annotated[int, Field(ge=0)]
    median_block_margin_delta: float | None
    median_block_corrected_margin: float | None

    @field_validator(
        "reference_time_s",
        "start_s",
        "end_s",
        "block_coverage_ratio",
        "median_block_margin_delta",
        "median_block_corrected_margin",
    )
    @classmethod
    def _finite_trajectory_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("final V2 trajectory values must be finite")
        return value

    @model_validator(mode="after")
    def _trajectory_is_consistent(self) -> Self:
        expected = self.polynomial_degree + 1
        if (
            len(self.canonical_coefficients_hz) != expected
            or len(self.absolute_coefficients_hz) != expected
            or self.start_s > self.end_s
        ):
            raise ValueError("final V2 trajectory geometry is inconsistent")
        if any(
            not math.isfinite(value)
            for value in (*self.canonical_coefficients_hz, *self.absolute_coefficients_hz)
        ):
            raise ValueError("final V2 trajectory coefficients must be finite")
        if self.observation_ids != tuple(sorted(set(self.observation_ids))):
            raise ValueError("final V2 trajectory observations must be unique and ordered")
        automatic = self.replay_tier in {
            LiftReplayTierV2.REPLAY_IMPROVED,
            LiftReplayTierV2.REPLAY_STABLE,
            LiftReplayTierV3.AUTOMATIC,
        }
        if self.automatic_correction_eligible != automatic:
            raise ValueError("final V2 correction eligibility disagrees with replay tier")
        return self


class FinalTrajectoryBankV2(ContractModel):
    """Closed display inventory plus its strict automatic-correction subset."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["final-trajectory-bank-v2"] = "final-trajectory-bank-v2"
    config_digest: Sha256Digest
    replay_gate_config_digest: Sha256Digest
    selection_config: FinalTrajectorySelectionConfigV1
    selection_config_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    lift_replay_digest: Sha256Digest
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV2, ...], Field(max_length=64)]
    automatic_correction_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _final_bank_is_closed(self) -> Self:
        if self.selection_config_digest != self.selection_config.digest:
            raise ValueError("final V2 selection configuration digest disagrees")
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final V2 trajectory accounting is inconsistent")
        ids = tuple(item.trajectory_id for item in self.trajectories)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("final V2 trajectories must be unique and ordered")
        expected_automatic = tuple(
            item.trajectory_id for item in self.trajectories if item.automatic_correction_eligible
        )
        if self.automatic_correction_trajectory_ids != expected_automatic:
            raise ValueError("final V2 automatic-correction inventory is not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final V2 trajectory bank content digest does not match")
        return self


class Glrt64FinalTrajectoryTableV2(ContractModel):
    """Bounded UI/reducer projection of the V2 final candidate inventory."""

    schema_version: Literal[2] = 2
    algorithm_version: Literal["glrt64-final-trajectory-table-v2"] = (
        "glrt64-final-trajectory-table-v2"
    )
    final_trajectory_bank_digest: Sha256Digest
    frequency_model: Literal["cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"] = (
        "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
    )
    coefficient_order: Literal["highest_polynomial_power_first"] = "highest_polynomial_power_first"
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV2, ...], Field(max_length=64)]
    automatic_correction_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(max_length=64)]
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
            raise ValueError("final V2 trajectory table accounting is inconsistent")
        expected_automatic = tuple(
            item.trajectory_id for item in self.trajectories if item.automatic_correction_eligible
        )
        if self.automatic_correction_trajectory_ids != expected_automatic:
            raise ValueError("final V2 table correction inventory is not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final V2 trajectory table content digest does not match")
        return self


class FinalTrajectoryV3(FinalTrajectoryV2):
    """Retained V4 replay geometry with complete harmful-metric audit fields."""

    # Contract majors deliberately narrow the inherited discriminator. Mypy
    # treats attribute overrides invariantly even though ContractModel is
    # frozen, so keep the exception on this discriminator only.
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    replay_tier: LiftReplayTierV3
    maximum_consecutive_harmful_blocks: Annotated[int, Field(ge=0)]
    replay_reasons: Annotated[tuple[BoundedReason, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def _harmful_inventory_is_consistent(self) -> Self:
        if self.maximum_consecutive_harmful_blocks > self.harmful_block_count:
            raise ValueError("final V3 harmful block run exceeds harmful block count")
        return self


class FinalTrajectoryBankV3(ContractModel):
    """Final inventory selected without using harmful metrics as vetoes."""

    schema_version: Literal[3] = 3
    algorithm_version: Literal["final-trajectory-bank-v3"] = "final-trajectory-bank-v3"
    config_digest: Sha256Digest
    replay_gate_config_digest: Sha256Digest
    selection_config: FinalTrajectorySelectionConfigV2
    selection_config_digest: Sha256Digest
    dealiased_bank_digest: Sha256Digest
    lift_replay_digest: Sha256Digest
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV3, ...], Field(max_length=64)]
    automatic_correction_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(max_length=64)]
    status: StandardScientificStatus
    reason: BoundedReason
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if self.selection_config_digest != self.selection_config.digest:
            raise ValueError("final V3 selection configuration digest disagrees")
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final V3 trajectory accounting is inconsistent")
        ids = tuple(item.trajectory_id for item in self.trajectories)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("final V3 trajectories must be unique and ordered")
        automatic = tuple(
            item.trajectory_id for item in self.trajectories if item.automatic_correction_eligible
        )
        if self.automatic_correction_trajectory_ids != automatic:
            raise ValueError("final V3 automatic inventory is not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final V3 trajectory bank content digest does not match")
        return self


class Glrt64FinalTrajectoryTableV3(ContractModel):
    schema_version: Literal[3] = 3
    algorithm_version: Literal["glrt64-final-trajectory-table-v3"] = (
        "glrt64-final-trajectory-table-v3"
    )
    final_trajectory_bank_digest: Sha256Digest
    frequency_model: Literal["cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"] = (
        "cfo_hz = polyval(coefficients_hz, time_s - reference_time_s)"
    )
    coefficient_order: Literal["highest_polynomial_power_first"] = "highest_polynomial_power_first"
    source_trajectory_count: Annotated[int, Field(ge=0)]
    returned_trajectory_count: Annotated[int, Field(ge=0, le=64)]
    truncated_trajectory_count: Annotated[int, Field(ge=0)]
    trajectories: Annotated[tuple[FinalTrajectoryV3, ...], Field(max_length=64)]
    automatic_correction_trajectory_ids: Annotated[tuple[Sha256Digest, ...], Field(max_length=64)]
    status: StandardScientificStatus
    candidate_only: Literal[True] = True
    specificity_claimed: Literal[False] = False
    payload_decoded: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _closed(self) -> Self:
        if (
            self.returned_trajectory_count + self.truncated_trajectory_count
            != self.source_trajectory_count
            or len(self.trajectories) != self.returned_trajectory_count
        ):
            raise ValueError("final V3 trajectory table accounting is inconsistent")
        automatic = tuple(
            item.trajectory_id for item in self.trajectories if item.automatic_correction_eligible
        )
        if self.automatic_correction_trajectory_ids != automatic:
            raise ValueError("final V3 table correction inventory is not derived from rows")
        if self.content_digest != _digest_without(self, "content_digest"):
            raise ValueError("final V3 trajectory table content digest does not match")
        return self


def _digest_without(model: ContractModel, field: str) -> Sha256Digest:
    document = model.model_dump(mode="json")
    document.pop(field)
    return canonical_digest(document)
