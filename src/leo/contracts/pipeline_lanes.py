"""Immutable Standard/Research lane and probe-pattern authority."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class PipelineLane(StrEnum):
    STANDARD = "standard"
    RESEARCH = "research"


class AutomaticLaneSelectionPolicyV1(ContractModel):
    """Versioned authority for deterministic dwell-level Research sampling."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["deterministic-manifest-bucket-v1"] = (
        "deterministic-manifest-bucket-v1"
    )
    enabled: bool
    allocation_epoch: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=64,
            pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
        ),
    ]
    research_numerator: Annotated[int, Field(ge=0, le=1024)]
    denominator: Annotated[int, Field(ge=1, le=1024)]

    @model_validator(mode="after")
    def _probability_is_valid(self) -> Self:
        if self.research_numerator > self.denominator:
            raise ValueError("Research sampling numerator cannot exceed its denominator")
        if not self.enabled and self.research_numerator:
            raise ValueError("disabled automatic lane selection must have zero numerator")
        return self

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class DwellLaneAssignmentV1(ContractModel):
    """Reproducible assignment derivable from persisted release and capture facts."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["dwell-lane-assignment-v1"] = "dwell-lane-assignment-v1"
    manifest_digest: Sha256Digest
    policy_digest: Sha256Digest
    selection_digest: Sha256Digest
    bucket: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=1, le=1024)]
    selected_lane: PipelineLane
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _assignment_is_closed(self) -> Self:
        if self.bucket >= self.denominator:
            raise ValueError("lane-assignment bucket lies outside its denominator")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"content_digest"}))
        if self.content_digest != expected:
            raise ValueError("lane-assignment content digest does not match its content")
        return self


PRODUCTION_AUTOMATIC_LANE_SELECTION_V1 = AutomaticLaneSelectionPolicyV1(
    enabled=True,
    allocation_epoch="standard10-dense-research-202608",
    research_numerator=1,
    denominator=8,
)

DISABLED_AUTOMATIC_LANE_SELECTION_V1 = AutomaticLaneSelectionPolicyV1(
    enabled=False,
    allocation_epoch="disabled",
    research_numerator=0,
    denominator=8,
)


def assign_dwell_pipeline_lane(
    manifest_digest: Sha256Digest,
    policy: AutomaticLaneSelectionPolicyV1,
) -> DwellLaneAssignmentV1:
    """Map immutable capture identity to one stable lane and sampling bucket."""

    selection_digest = canonical_digest(
        {
            "algorithm_version": policy.algorithm_version,
            "allocation_epoch": policy.allocation_epoch,
            "manifest_digest": manifest_digest,
        }
    )
    bucket = int(selection_digest.removeprefix("sha256:")[:16], 16) % policy.denominator
    lane = (
        PipelineLane.RESEARCH
        if policy.enabled and bucket < policy.research_numerator
        else PipelineLane.STANDARD
    )
    values = {
        "schema_version": 1,
        "algorithm_version": "dwell-lane-assignment-v1",
        "manifest_digest": manifest_digest,
        "policy_digest": policy.digest,
        "selection_digest": selection_digest,
        "bucket": bucket,
        "denominator": policy.denominator,
        "selected_lane": lane,
    }
    return DwellLaneAssignmentV1(
        **values,
        content_digest=canonical_digest(values),
    )


class ProbePatternV2(ContractModel):
    schema_version: Literal[2] = 2
    subwindow_ms: Annotated[int, Field(gt=0, le=1000)]
    probe_ms: Annotated[int, Field(gt=0, le=1000)]
    start_offsets_ms: Annotated[tuple[int, ...], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def _geometry_is_exact(self) -> Self:
        if 1000 % self.subwindow_ms:
            raise ValueError("probe subwindow must divide one second exactly")
        if self.probe_ms > self.subwindow_ms:
            raise ValueError("probe support exceeds its subwindow")
        if self.start_offsets_ms != tuple(sorted(set(self.start_offsets_ms))):
            raise ValueError("probe offsets must be unique and ordered")
        if any(
            isinstance(offset, bool) or offset < 0 or offset + self.probe_ms > self.subwindow_ms
            for offset in self.start_offsets_ms
        ):
            raise ValueError("probe offset is outside the subwindow")
        return self

    def sample_geometry(self, sample_rate_hz: int) -> tuple[int, int, tuple[int, ...]]:
        if isinstance(sample_rate_hz, bool) or sample_rate_hz <= 0:
            raise ValueError("sample rate must be positive")
        values_ms = (self.subwindow_ms, self.probe_ms, *self.start_offsets_ms)
        if any(sample_rate_hz * value % 1000 for value in values_ms):
            raise ValueError("probe geometry does not map to integral sample coordinates")
        return (
            sample_rate_hz * self.subwindow_ms // 1000,
            sample_rate_hz * self.probe_ms // 1000,
            tuple(sample_rate_hz * value // 1000 for value in self.start_offsets_ms),
        )

    def probe_count(self, complete_seconds: int) -> int:
        if isinstance(complete_seconds, bool) or complete_seconds < 0:
            raise ValueError("complete-second count must be nonnegative")
        return complete_seconds * (1000 // self.subwindow_ms) * len(self.start_offsets_ms)

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class PipelineDefinitionV1(ContractModel):
    schema_version: Literal[1] = 1
    definition_id: Sha256Digest
    lane: PipelineLane
    executable_git_sha: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    graph_digest: Sha256Digest
    configuration_digest: Sha256Digest
    product_namespace: Literal["standard", "research"]
    automatic_eligible: bool
    promotion_allowed: bool

    @model_validator(mode="after")
    def _definition_is_closed(self) -> Self:
        if self.product_namespace != self.lane.value:
            raise ValueError("pipeline lane and product namespace disagree")
        if self.lane is PipelineLane.RESEARCH and (
            self.automatic_eligible or self.promotion_allowed
        ):
            raise ValueError("Research begins manual and cannot promote as Standard")
        expected = canonical_digest(self.model_dump(mode="json", exclude={"definition_id"}))
        if self.definition_id != expected:
            raise ValueError("pipeline definition digest does not match content")
        return self


STANDARD_PROBE_PATTERN_V2 = ProbePatternV2(
    subwindow_ms=50,
    probe_ms=20,
    start_offsets_ms=(0, 25),
)
RESEARCH_PROBE_PATTERN_V2 = ProbePatternV2(
    subwindow_ms=50,
    probe_ms=20,
    start_offsets_ms=(0, 15, 30),
)
