"""Deterministic in-memory reader/sink fakes for analyzer unit tests."""

from __future__ import annotations

from pydantic import JsonValue

from leo.artifacts.store import ArtifactConflictError
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.pipeline import (
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    ScopeIdentityV1,
    UpstreamJsonProduct,
)


class MemoryOutputSink(OutputSink):
    def __init__(self) -> None:
        self.documents: dict[tuple[str, int], dict[str, JsonValue]] = {}
        self.payloads: dict[tuple[str, int], bytes] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        identity = (product.kind, product.schema_version)
        payload = canonical_json_bytes(document)
        if identity in self.payloads:
            raise ArtifactConflictError(f"in-memory product media differs: {identity}")
        existing = self.documents.get(identity)
        if existing is not None and canonical_json_bytes(existing) != payload:
            raise ArtifactConflictError(f"in-memory product differs: {identity}")
        self.documents[identity] = document
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}/v{product.schema_version}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        identity = (product.kind, product.schema_version)
        if identity in self.documents:
            raise ArtifactConflictError(f"in-memory product media differs: {identity}")
        existing = self.payloads.get(identity)
        if existing is not None and existing != payload:
            raise ArtifactConflictError(f"in-memory product differs: {identity}")
        self.payloads[identity] = payload
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}/v{product.schema_version}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


class MemoryProductReader(ProductReader):
    def __init__(
        self,
        documents: dict[tuple[str, int], dict[str, JsonValue]] | None = None,
        *,
        subject_binding: dict[str, JsonValue] | None = None,
        memberships: dict[tuple[str, int], dict[str, JsonValue]] | None = None,
        producer_scope: ScopeIdentityV1 | None = None,
    ) -> None:
        self.documents = {} if documents is None else documents
        self.subject_binding = subject_binding
        self.memberships = {} if memberships is None else memberships
        self.producer_scope = producer_scope

    def read_subject_binding(self) -> dict[str, JsonValue]:
        if self.subject_binding is None:
            raise KeyError("subject binding is absent")
        return self.subject_binding

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        for version in requirement.accepted_schema_versions:
            document = self.documents.get((requirement.kind, version))
            if document is not None:
                return document
        if requirement.required:
            raise KeyError(f"required product is absent: {requirement.kind}")
        return None

    def read_json_bound(self, requirement: ProductRequirement) -> UpstreamJsonProduct | None:
        document = self.read_json(requirement)
        if document is None:
            return None
        if self.producer_scope is None:
            raise ValueError("bound in-memory product requires a producer scope")
        version = next(
            version
            for version in requirement.accepted_schema_versions
            if (requirement.kind, version) in self.documents
        )
        return UpstreamJsonProduct(
            producer_node_id=requirement.producer_node_id
            or requirement.producer_stage_key
            or "memory-producer",
            producer_scope=self.producer_scope,
            product_digest=canonical_digest(document),
            document=document,
            membership=self.memberships.get((requirement.kind, version), {}),
        )

    def read_json_many(
        self,
        requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]:
        del requirement, producer_node_ids
        raise NotImplementedError("fan-in requires an explicit test reader")


class EmptyProductReader(MemoryProductReader):
    def __init__(self) -> None:
        super().__init__()
