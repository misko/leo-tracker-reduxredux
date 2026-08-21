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
