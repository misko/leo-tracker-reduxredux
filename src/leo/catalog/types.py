"""Infrastructure-neutral inputs and receipts for catalog operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class JobDefinition:
    stage_key: str
    scope_key: str = "session"
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class JobLease:
    job_id: int
    run_id: str
    stage_key: str
    scope_key: str
    attempt_number: int
    worker_id: str
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProductRegistration:
    run_id: str
    stage_key: str
    kind: str
    schema_version: int
    role: str
    status: str
    media_type: str
    logical_uri: str
    digest: str
    byte_size: int
    scope_key: str = "session"
    coverage: float | None = None
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CurrentSummary:
    mean_power_dbfs: float | None = None
    best_qam_accuracy: float | None = None
    best_cfo_hz: float | None = None
    doppler_slope_hz_s: float | None = None
    candidate_count: int | None = None
    coverage: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionSearch:
    source_type: str | None = None
    state: str | None = None
    tag: str | None = None
    held: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class SessionSearchResult:
    session_id: str
    source_type: str
    state: str
    created_at: datetime
    bundle_uri: str | None
    held: bool
    tags: tuple[str, ...]
    current_run_id: str | None


@dataclass(frozen=True, slots=True)
class RunExecutionInfo:
    run_id: str
    session_id: str
    pipeline_release_id: str
    pipeline_configuration: dict[str, Any]
    input_manifest_digest: str
    trigger: str
    bundle_uri: str


@dataclass(frozen=True, slots=True)
class CatalogProductRecord:
    product_id: int
    run_id: str
    stage_key: str
    scope_key: str
    kind: str
    schema_version: int
    role: str
    status: str
    media_type: str
    logical_uri: str
    digest: str
    byte_size: int
    available: bool
    coverage: float | None
    summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CatalogRetentionCandidate:
    """One independently reclaimable unit returned in stable oldest-first order."""

    kind: str
    item_id: str
    session_id: str
    created_at: datetime
    allocated_bytes: int
    logical_uri: str


@dataclass(frozen=True, slots=True)
class CatalogSessionPurgeClaim:
    session_id: str
    claim_token: str
    previous_state: str
    bundle_uri: str
    allocated_bytes: int
    products: tuple[CatalogProductRecord, ...]


@dataclass(frozen=True, slots=True)
class CatalogProductPurgeClaim:
    product: CatalogProductRecord
    session_id: str
    claim_token: str


@dataclass(frozen=True, slots=True)
class CatalogJobRecord:
    job_id: int
    stage_key: str
    scope_key: str
    state: str
    outcome: str | None


@dataclass(frozen=True, slots=True)
class RunSealSnapshot:
    execution: RunExecutionInfo
    jobs: tuple[CatalogJobRecord, ...]
    products: tuple[CatalogProductRecord, ...]


@dataclass(frozen=True, slots=True)
class CatalogRunReadSnapshot:
    run_id: str
    pipeline_release_id: str
    pipeline_configuration: dict[str, Any]
    state: str
    created_at: datetime
    started_at: datetime | None
    sealed_at: datetime | None
    failure: str | None
    input_manifest_digest: str
    manifest_uri: str | None
    manifest_digest: str | None
    is_current: bool
    summary: CurrentSummary | None
    jobs: tuple[CatalogJobRecord, ...]
    products: tuple[CatalogProductRecord, ...]


@dataclass(frozen=True, slots=True)
class CatalogSessionReadSnapshot:
    session_id: str
    source_type: str
    state: str
    created_at: datetime
    bundle_uri: str | None
    manifest_digest: str | None
    attributes: dict[str, Any]
    tags: tuple[str, ...]
    hold_reason: str | None
    analysis: CatalogRunReadSnapshot | None


@dataclass(frozen=True, slots=True)
class CatalogBacklogSnapshot:
    queued: int
    running: int
    failed: int
    oldest_queued_seconds: float | None
