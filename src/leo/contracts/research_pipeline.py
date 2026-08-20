"""Strict Research-lane envelopes around shared immutable scientific payloads."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.standard_pipeline import StandardSourceBindingV1

ProductKind = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
    ),
]


class ResearchProductEnvelopeV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["research-product-envelope-v1"] = "research-product-envelope-v1"
    pipeline_lane: Literal["research"] = "research"
    pipeline_definition_id: Sha256Digest
    payload_kind: ProductKind
    payload_schema_version: Annotated[int, Field(ge=1)]
    payload_content_digest: Sha256Digest
    payload: dict[str, object]
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _payload_and_envelope_are_bound(self) -> Self:
        if self.payload_content_digest != canonical_digest(self.payload):
            raise ValueError("Research payload digest does not match its content")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("Research envelope digest does not match its content")
        return self


class ResearchSourceBindingEnvelopeV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["research-source-binding-envelope-v1"] = (
        "research-source-binding-envelope-v1"
    )
    pipeline_lane: Literal["research"] = "research"
    pipeline_definition_id: Sha256Digest
    research_wrapper_kind: ProductKind
    research_product_kind: ProductKind
    research_payload_digest: Sha256Digest
    standard_binding: StandardSourceBindingV1
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _envelope_is_closed(self) -> Self:
        if self.research_payload_digest != self.standard_binding.product_content_digest:
            raise ValueError("Research source envelope and shared payload digest disagree")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("Research source envelope digest does not match content")
        return self
