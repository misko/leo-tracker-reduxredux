"""Deterministic in-memory reader/sink fakes for analyzer unit tests."""

from __future__ import annotations

from pydantic import JsonValue

from leo.artifacts.store import ArtifactConflictError
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.pipeline import (
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
)


class MemoryOutputSink(OutputSink):
    def __init__(self) -> None:
        self.documents: dict[tuple[str, int], dict[str, JsonValue]] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        identity = (product.kind, product.schema_version)
        payload = canonical_json_bytes(document)
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


class MemoryProductReader(ProductReader):
    def __init__(
        self,
        documents: dict[tuple[str, int], dict[str, JsonValue]] | None = None,
    ) -> None:
        self.documents = {} if documents is None else documents

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        for version in requirement.accepted_schema_versions:
            document = self.documents.get((requirement.kind, version))
            if document is not None:
                return document
        if requirement.required:
            raise KeyError(f"required product is absent: {requirement.kind}")
        return None


class EmptyProductReader(MemoryProductReader):
    def __init__(self) -> None:
        super().__init__()
