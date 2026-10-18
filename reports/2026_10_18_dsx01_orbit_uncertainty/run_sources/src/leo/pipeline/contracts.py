"""Narrow contracts implemented by analysis and infrastructure components.

This module deliberately has no knowledge of a database, HTTP, or a concrete
filesystem. Infrastructure implements the reader and sink protocols; analyzers
only consume those protocols.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator

from leo.contracts.digests import Sha256Digest
from leo.domain.iq import IqBlock
from leo.pipeline.scopes import ScopeIdentityV1

Name = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
    ),
]


class PipelineModel(BaseModel):
    """Immutable, closed model for pipeline boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class ProductRole(StrEnum):
    SCIENTIFIC = "scientific"
    PRESENTATION = "presentation"


class ResourceClass(StrEnum):
    STREAMING = "streaming"
    CPU = "cpu"
    MEMORY = "memory"
    HEAVY = "heavy"


class StageOutcome(StrEnum):
    """Successful scientific terminal outcomes.

    Exceptions and exhausted worker retries are execution failures and are not
    represented here. In particular, ``NO_RESULT`` means sufficient evidence
    found no phenomenon, while ``INSUFFICIENT_DATA`` means no conclusion can be
    drawn.
    """

    COMPLETE = "complete"
    NO_RESULT = "no_result"
    PARTIAL_COVERAGE = "partial_coverage"
    INSUFFICIENT_DATA = "insufficient_data"


class ProductRequirement(PipelineModel):
    kind: Name
    accepted_schema_versions: tuple[Annotated[int, Field(ge=1)], ...] = (1,)
    required: bool = True
    producer_stage_key: Name | None = None
    producer_node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    required_role: ProductRole | None = None
    required_status: StageOutcome | None = None
    require_available: bool = False

    @field_validator("accepted_schema_versions")
    @classmethod
    def _versions_are_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("accepted product schema versions must be non-empty and unique")
        return value


class ProductSpec(PipelineModel):
    kind: Name
    schema_version: Annotated[int, Field(ge=1)] = 1
    role: ProductRole = ProductRole.SCIENTIFIC
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)] = "application/json"


class PublishedProduct(PipelineModel):
    product: ProductSpec
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(ge=0)]


class StageSpec(PipelineModel):
    key: Name
    algorithm_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    configuration_schema: Name
    dependencies: tuple[Name, ...] = ()
    input_products: tuple[ProductRequirement, ...] = ()
    output_products: tuple[ProductSpec, ...] = ()
    resource_class: ResourceClass = ResourceClass.STREAMING
    deterministic: bool = True
    accepted_outcomes: tuple[StageOutcome, ...] = (
        StageOutcome.COMPLETE,
        StageOutcome.NO_RESULT,
        StageOutcome.PARTIAL_COVERAGE,
        StageOutcome.INSUFFICIENT_DATA,
    )

    @field_validator("dependencies")
    @classmethod
    def _dependencies_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("stage dependencies must be unique")
        return value

    @field_validator("input_products")
    @classmethod
    def _inputs_are_unique(
        cls, value: tuple[ProductRequirement, ...]
    ) -> tuple[ProductRequirement, ...]:
        kinds = [item.kind for item in value]
        if len(set(kinds)) != len(kinds):
            raise ValueError("input product kinds must be unique")
        return value

    @field_validator("output_products")
    @classmethod
    def _outputs_are_unique(cls, value: tuple[ProductSpec, ...]) -> tuple[ProductSpec, ...]:
        identities = [(item.kind, item.schema_version) for item in value]
        if len(set(identities)) != len(identities):
            raise ValueError("output product kind/schema pairs must be unique")
        return value

    @field_validator("accepted_outcomes")
    @classmethod
    def _outcomes_are_unique(cls, value: tuple[StageOutcome, ...]) -> tuple[StageOutcome, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("accepted outcomes must be non-empty and unique")
        return value


class AnalysisContext(PipelineModel):
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    run_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    pipeline_release: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    scope_key: Annotated[str, StringConstraints(min_length=1, max_length=256)] = "session"
    scope: ScopeIdentityV1 | None = None
    job_node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    dependency_node_ids: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=128)], ...
    ] = ()
    stage_config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("dependency_node_ids")
    @classmethod
    def _dependency_inventory_is_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) > 64 or tuple(sorted(set(value))) != value:
            raise ValueError("dependency node IDs must be unique, bounded and ordered")
        return value


class StageResult(PipelineModel):
    outcome: StageOutcome
    products: tuple[PublishedProduct, ...] = ()
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    message: Annotated[str | None, StringConstraints(min_length=1, max_length=2048)] = None


class IqReader(Protocol):
    """Bounded, receiver-aware access to one analysis scope."""

    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def center_frequency_hz(self) -> int: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        """Return an iterable of blocks no larger than ``block_samples``."""
        ...


class ProductReader(Protocol):
    def read_subject_binding(self) -> dict[str, JsonValue]: ...

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None: ...

    def read_json_bound(self, requirement: ProductRequirement) -> UpstreamJsonProduct | None: ...

    def read_json_many(
        self,
        requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]: ...


class UpstreamJsonProduct(PipelineModel):
    producer_node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    producer_scope: ScopeIdentityV1
    outcome: StageOutcome
    product_digest: Sha256Digest
    document: dict[str, JsonValue]
    membership: dict[str, JsonValue] = Field(default_factory=dict)


class OutputSink(Protocol):
    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct: ...

    def publish_bytes(
        self,
        product: ProductSpec,
        payload: bytes,
    ) -> PublishedProduct: ...


class Analyzer(Protocol):
    @property
    def spec(self) -> StageSpec: ...

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult: ...
