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

    @property
    def recordings(self) -> RecordingStore:
        return self._recordings

    @property
    def verifies_digests(self) -> bool:
        return self._verify

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
        self._consumed_product_ids: set[int] = set()

    @property
    def consumed_product_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._consumed_product_ids))

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        snapshot = self._catalog.run_seal_snapshot(self._run_id)
        if requirement.producer_stage_key is not None:
            jobs = tuple(
                job
                for job in snapshot.jobs
                if job.stage_key == requirement.producer_stage_key
                and job.scope_key == self._scope_key
            )
            if len(jobs) != 1:
                raise ValueError(
                    f"required producer job is absent or ambiguous for {self._scope_key}: "
                    f"{requirement.producer_stage_key}"
                )
            job = jobs[0]
            if job.state != "succeeded" or (
                requirement.required_status is not None
                and job.outcome != requirement.required_status.value
            ):
                raise ValueError(
                    f"required producer job is not complete for {self._scope_key}: "
                    f"{requirement.producer_stage_key}"
                )
        matches = tuple(
            product
            for product in snapshot.products
            if (
                product.run_id == self._run_id
                and product.kind == requirement.kind
                and product.scope_key == self._scope_key
                and product.schema_version in requirement.accepted_schema_versions
                and (
                    requirement.producer_stage_key is None
                    or product.stage_key == requirement.producer_stage_key
                )
                and (
                    requirement.required_role is None
                    or product.role == requirement.required_role.value
                )
                and (
                    requirement.required_status is None
                    or product.status == requirement.required_status.value
                )
                and (not requirement.require_available or product.available)
            )
        )
        for version in requirement.accepted_schema_versions:
            candidates = tuple(item for item in matches if item.schema_version == version)
            if len(candidates) > 1:
                raise ValueError(
                    f"required product is ambiguous for {self._scope_key}: "
                    f"{requirement.kind} v{version}"
                )
            if candidates:
                selected = candidates[0]
                document = self._artifacts.read_json(selected.logical_uri, selected.digest)
                self._consumed_product_ids.add(selected.product_id)
                return document
        if requirement.required:
            raise KeyError(f"required product is absent for {self._scope_key}: {requirement.kind}")
        return None
