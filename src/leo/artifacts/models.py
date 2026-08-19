"""Versioned immutable analysis-run manifest contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


class AnalysisJobReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    job_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    outcome: Annotated[str, StringConstraints(min_length=1, max_length=32)]


class AnalysisProductReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    product_id: Annotated[int, Field(gt=0)]
    stage_key: Identifier
    scope_key: Identifier
    kind: Identifier
    product_schema_version: Annotated[int, Field(gt=0)]
    role: Literal["scientific", "presentation"]
    status: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    logical_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    digest: Sha256Digest
    byte_size: Annotated[int, Field(ge=0)]
    coverage: Annotated[float | None, Field(ge=0.0, le=1.0)] = None


class AnalysisRunManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: Identifier
    run_id: Identifier
    pipeline_release_id: Identifier
    input_manifest_digest: Sha256Digest
    trigger: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    jobs: tuple[AnalysisJobReceiptV1, ...]
    products: tuple[AnalysisProductReceiptV1, ...]

    @field_validator("jobs")
    @classmethod
    def _jobs_are_canonical(
        cls, value: tuple[AnalysisJobReceiptV1, ...]
    ) -> tuple[AnalysisJobReceiptV1, ...]:
        identities = [(item.stage_key, item.scope_key) for item in value]
        if len(set(identities)) != len(identities):
            raise ValueError("run manifest job identities must be unique")
        if identities != sorted(identities):
            raise ValueError("run manifest jobs must be sorted")
        return value

    @field_validator("products")
    @classmethod
    def _products_are_canonical(
        cls, value: tuple[AnalysisProductReceiptV1, ...]
    ) -> tuple[AnalysisProductReceiptV1, ...]:
        identities = [
            (item.stage_key, item.scope_key, item.kind, item.product_schema_version)
            for item in value
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("run manifest product identities must be unique")
        if identities != sorted(identities):
            raise ValueError("run manifest products must be sorted")
        return value

    @model_validator(mode="after")
    def _products_belong_to_terminal_jobs(self) -> Self:
        jobs = {(item.stage_key, item.scope_key) for item in self.jobs}
        if any((item.stage_key, item.scope_key) not in jobs for item in self.products):
            raise ValueError("run manifest product has no corresponding job")
        return self
