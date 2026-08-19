"""Concrete adapters connecting processing ports to recording and artifact stores."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Protocol

import numpy as np
from pydantic import JsonValue

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CaptureRecordingIdentity, CatalogRepository, RunExecutionInfo
from leo.contracts.digests import canonical_digest
from leo.domain.iq import IqBlock
from leo.pipeline import (
    IqReader,
    ProductReader,
    ProductRequirement,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ScopeIdentityV1,
    ScopeKind,
    UpstreamJsonProduct,
)
from leo.storage import RecordingStore


class InputManifestMismatchError(RuntimeError):
    """The recording at a catalog URI is not the run's pinned input."""


class IqReaderProvider(Protocol):
    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader: ...

    def open_scope(self, execution: RunExecutionInfo, scope: ScopeIdentityV1) -> IqReader: ...

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1: ...


class RecordingIqReaderProvider:
    """Resolve one job scope to a real compressed recording stream."""

    def __init__(
        self,
        recordings: RecordingStore,
        *,
        verify: bool = True,
        allow_unpinned_integrity_for_tests: bool = False,
    ) -> None:
        self._recordings = recordings
        self._verify = verify
        self._allow_unpinned_integrity_for_tests = allow_unpinned_integrity_for_tests

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

    def open_scope(self, execution: RunExecutionInfo, scope: ScopeIdentityV1) -> IqReader:
        if scope.kind is not ScopeKind.RECEIVER_PATH:
            raise ValueError("only receiver_path scopes may open raw IQ")
        if scope.stream_id is None or scope.receiver_id is None:
            raise ValueError("receiver_path scope is incomplete")
        bundle = self._recordings.inspect_uri(execution.bundle_uri)
        if bundle.manifest_sha256 != execution.input_manifest_digest:
            raise InputManifestMismatchError(
                "recording manifest digest disagrees with analysis run input: "
                f"{bundle.manifest_sha256} != {execution.input_manifest_digest}"
            )
        source = self._recordings.reader(bundle, scope.stream_id, verify=self._verify)
        return _ReceiverPathReader(source, scope.receiver_id)

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1:
        if (
            self._recordings.pinned_root_identity is None
            and not self._allow_unpinned_integrity_for_tests
        ):
            raise RuntimeError(
                "typed run creation requires a pinned recording-store integrity authority"
            )
        bundle = self._recordings.inspect_uri(identity.bundle_uri)
        if (
            bundle.session_id != identity.session_id
            or bundle.manifest_sha256 != identity.manifest_digest
        ):
            raise InputManifestMismatchError(
                "recording-store identity disagrees with the catalog before verification"
            )
        self._recordings.verify(bundle)
        streams = []
        for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id):
            inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": chunk.sample_start,
                    "sample_count": chunk.sample_count,
                    "digest": chunk.compressed_sha256,
                }
                for chunk in stream.chunks
            ]
            uncompressed_inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": chunk.sample_start,
                    "sample_count": chunk.sample_count,
                    "digest": chunk.uncompressed_sha256,
                }
                for chunk in stream.chunks
            ]
            streams.append(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=len(stream.chunks),
                    compressed_closure_digest=canonical_digest(inventory),
                    uncompressed_closure_digest=canonical_digest(uncompressed_inventory),
                )
            )
        return RawIntegrityAttestationV1(
            session_id=identity.session_id,
            manifest_digest=identity.manifest_digest,
            streams=tuple(streams),
            verifier_version="recording-store-full-v1",
            verified_utc_ns=time.time_ns(),
        )


class _ReceiverPathReader:
    def __init__(self, source: IqReader, receiver_id: int) -> None:
        if receiver_id not in source.receiver_ids:
            raise ValueError(f"receiver {receiver_id} is absent from the selected stream")
        self._source = source
        self._receiver_id = receiver_id
        self._column = source.receiver_ids.index(receiver_id)

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (self._receiver_id,)

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        for block in self._source.iter_blocks(block_samples=block_samples):
            samples = np.ascontiguousarray(block.samples[:, self._column : self._column + 1, :])
            yield IqBlock(
                samples=samples,
                metadata=block.metadata.model_copy(update={"receiver_ids": self.receiver_ids}),
            )


class CatalogArtifactProductReader(ProductReader):
    """Read registered upstream JSON products for one run/scope."""

    def __init__(
        self,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        *,
        run_id: str,
        scope_key: str,
        job_id: int | None = None,
    ) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._run_id = run_id
        self._scope_key = scope_key
        self._job_id = job_id
        self._consumed_product_ids: set[int] = set()

    @property
    def consumed_product_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._consumed_product_ids))

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        snapshot = self._catalog.run_seal_snapshot(self._run_id)
        authorized = None
        if self._job_id is not None:
            authorized = self._catalog.authorized_job_input_products(self._job_id)
        if requirement.producer_stage_key is not None:
            authorized_nodes = (
                {node_id for node_id, _ in authorized if node_id is not None}
                if authorized is not None
                else set()
            )
            jobs = tuple(
                job
                for job in snapshot.jobs
                if job.stage_key == requirement.producer_stage_key
                and (
                    (
                        requirement.producer_node_id is not None
                        and job.node_id == requirement.producer_node_id
                    )
                    or (
                        requirement.producer_node_id is None
                        and (job.node_id in authorized_nodes or job.scope_key == self._scope_key)
                    )
                )
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
        candidates = (
            tuple(product for _, product in authorized)
            if authorized is not None
            else snapshot.products
        )
        matches = tuple(
            product
            for product in candidates
            if (
                product.run_id == self._run_id
                and product.kind == requirement.kind
                and (authorized is not None or product.scope_key == self._scope_key)
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
                and (
                    requirement.producer_node_id is None
                    or authorized is not None
                    and any(
                        node_id == requirement.producer_node_id
                        and authorized_product.product_id == product.product_id
                        for node_id, authorized_product in authorized
                    )
                )
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

    def read_json_many(
        self,
        requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]:
        if self._job_id is None:
            raise ValueError("bounded fan-in requires a typed persisted job plan")
        if (
            not producer_node_ids
            or len(producer_node_ids) > 64
            or tuple(sorted(producer_node_ids)) != producer_node_ids
            or len(set(producer_node_ids)) != len(producer_node_ids)
        ):
            raise ValueError("producer node IDs must be non-empty, unique, bounded and ordered")
        authorized = self._catalog.authorized_job_input_products(self._job_id)
        authorized_nodes = tuple(sorted({node for node, _ in authorized if node is not None}))
        if authorized_nodes != producer_node_ids:
            raise ValueError("fan-in nodes do not equal the exact required dependency inventory")

        output = []
        for node_id in producer_node_ids:
            matches = tuple(
                product
                for producer_node, product in authorized
                if producer_node == node_id
                and product.kind == requirement.kind
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
            selected = None
            for version in requirement.accepted_schema_versions:
                candidates = tuple(
                    product for product in matches if product.schema_version == version
                )
                if len(candidates) > 1:
                    raise ValueError(f"fan-in product is ambiguous for producer node {node_id}")
                if candidates:
                    selected = candidates[0]
                    break
            if selected is None:
                raise KeyError(f"fan-in product is absent for producer node {node_id}")
            if selected.scope is None:
                raise ValueError(f"fan-in producer node {node_id} has no typed scope")
            document = self._artifacts.read_json(selected.logical_uri, selected.digest)
            self._consumed_product_ids.add(selected.product_id)
            output.append(
                UpstreamJsonProduct(
                    producer_node_id=node_id,
                    producer_scope=selected.scope,
                    product_digest=selected.digest,
                    document=document,
                )
            )
        return tuple(output)
