"""Catalog-backed reader for immutable run-owned Standard subject snapshots."""

from __future__ import annotations

from leo.catalog.repository import CatalogRepository
from leo.contracts.standard_pipeline import StandardPairInputBindV2, StandardPathInputBindV3
from leo.pipeline.scopes import ScopeIdentityV1, ScopeKind


class CatalogSubjectBindingReader:
    """Read only the snapshot frozen for an exact analysis run and scope."""

    def __init__(self, catalog: CatalogRepository) -> None:
        self._catalog = catalog

    def receiver_path(self, run_id: str, scope: ScopeIdentityV1) -> StandardPathInputBindV3:
        if scope.kind is not ScopeKind.RECEIVER_PATH:
            raise ValueError("receiver-path binding requires a receiver_path scope")
        record = self._catalog.run_subject_binding(run_id, scope)
        return StandardPathInputBindV3.model_validate(record.document)

    def paired(self, run_id: str, scope: ScopeIdentityV1) -> StandardPairInputBindV2:
        if scope.kind is not ScopeKind.PAIRED:
            raise ValueError("paired binding requires a paired scope")
        record = self._catalog.run_subject_binding(run_id, scope)
        return StandardPairInputBindV2.model_validate(record.document)

    def snapshot_digest(self, run_id: str, scope: ScopeIdentityV1) -> str:
        return self._catalog.run_subject_binding(run_id, scope).snapshot_digest
