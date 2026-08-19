"""Concrete adapters connecting processing ports to recording and artifact stores."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, RunExecutionInfo
from leo.pipeline import IqReader, ProductReader, ProductRequirement
from leo.storage import RecordingStore


class InputManifestMismatchError(RuntimeError):
    """The recording at a catalog URI is not the run's pinned input."""


class IqReaderProvider(Protocol):
    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader: ...


class RecordingIqReaderProvider:
    """Resolve one job scope to a real compressed recording stream."""

    def __init__(self, recordings: RecordingStore, *, verify: bool = True) -> None:
        self._recordings = recordings
        self._verify = verify

    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader:
        bundle = self._recordings.inspect_uri(execution.bundle_uri)
        if bundle.manifest_sha256 != execution.input_manifest_digest:
            raise InputManifestMismatchError(
                "recording manifest digest disagrees with analysis run input: "
                f"{bundle.manifest_sha256} != {execution.input_manifest_digest}"
            )
        return self._recordings.reader(bundle, scope_key, verify=self._verify)


class CatalogArtifactProductReader(ProductReader):
    """Read registered upstream JSON products for one run/scope."""

    def __init__(
        self,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        *,
        run_id: str,
        scope_key: str,
    ) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._run_id = run_id
        self._scope_key = scope_key

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        snapshot = self._catalog.run_seal_snapshot(self._run_id)
        by_version = {
            product.schema_version: product
            for product in snapshot.products
            if product.kind == requirement.kind and product.scope_key == self._scope_key
        }
        for version in requirement.accepted_schema_versions:
            product = by_version.get(version)
            if product is not None:
                return self._artifacts.read_json(product.logical_uri, product.digest)
        if requirement.required:
            raise KeyError(f"required product is absent for {self._scope_key}: {requirement.kind}")
        return None
