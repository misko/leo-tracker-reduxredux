"""Infrastructure-neutral inputs and receipts for catalog operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from leo.pipeline.planning import ScopeIdentityV1


@dataclass(frozen=True, slots=True)
class JobDefinition:
    stage_key: str
    scope_key: str = "session"
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    max_attempts: int = 3
    node_id: str | None = None
    scope: ScopeIdentityV1 | None = None
    depends_on_node_ids: tuple[str, ...] = ()
    ordering_only_node_ids: tuple[str, ...] = ()
    resource_class: str = "streaming"
    iq_access: str = "legacy"


@dataclass(frozen=True, slots=True)
class JobLease:
    job_id: int
    run_id: str
    stage_key: str
    scope_key: str
    attempt_number: int
    worker_id: str
    lease_expires_at: datetime
    scope_id: int | None = None
    scope: ScopeIdentityV1 | None = None
    node_id: str | None = None
    dependency_node_ids: tuple[str, ...] = ()
    resource_class: str = "streaming"
    iq_access: str = "legacy"


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
    input_product_ids: tuple[int, ...] = ()
    scope: ScopeIdentityV1 | None = None
    derivation_output_id: int | None = None
    derivation_mode: str = "legacy"
    reused_from_product_id: int | None = None


@dataclass(frozen=True, slots=True)
class WorkerReleaseAuthority:
    pipeline_release_id: str
    code_revision: str
    environment_digest: str
    graph_digest: str
    configuration_digest: str
    executable_digest: str

    def __post_init__(self) -> None:
        for name, value in (
            ("pipeline_release_id", self.pipeline_release_id),
            ("code_revision", self.code_revision),
        ):
            if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{name} must be an exact lowercase 40-character Git SHA")


@dataclass(frozen=True, slots=True)
class RawIntegrityAttestationRegistration:
    session_id: str
    manifest_digest: str
    attestation_digest: str
    document: dict[str, Any]
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class StageDerivationRegistration:
    derivation_key: str
    stage_key: str
    algorithm_version: str
    implementation_digest: str
    configuration_digest: str
    environment_digest: str
    scope_digest: str
    input_closure_digest: str
    producing_release_id: str
    key_document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StageDerivationOutputRegistration:
    derivation_id: int
    kind: str
    schema_version: int
    role: str
    status: str
    media_type: str
    logical_uri: str
    digest: str
    byte_size: int
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StageDerivationOutputRecord:
    output_id: int
    derivation_id: int
    derivation_key: str
    kind: str
    schema_version: int
    role: str
    status: str
    media_type: str
    logical_uri: str
    digest: str
    byte_size: int
    summary: dict[str, Any]
    available: bool


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
class CaptureRecordingIdentity:
    session_id: str
    bundle_uri: str
    manifest_digest: str


@dataclass(frozen=True, slots=True)
class CaptureReceiverBinding:
    """Exact catalog half of a manifest-derived receiver-path input binding."""

    scope: ScopeIdentityV1
    radio_id: str
    radio_serial: str
    physical_receiver_id: str
    hardware_epoch_id: str
    manifest_digest: str
    stream_identity_digest: str
    profile_revision_digest: str
    capture_start_utc_ns: int
    capture_end_utc_ns: int


@dataclass(frozen=True, slots=True)
class ReceiverPathRegistration:
    radio_id: str
    radio_serial: str
    radio_uri: str
    transport: str
    receiver_id: int
    physical_receiver_id: str
    hardware_epoch_id: str
    hardware_epoch_started_utc_ns: int


@dataclass(frozen=True, slots=True)
class ReceiverPathRecord:
    receiver_path_id: int
    hardware_epoch_database_id: int
    registration: ReceiverPathRegistration


@dataclass(frozen=True, slots=True)
class FrequencyCalibrationRegistration:
    calibration_id: str
    calibration_digest: str
    radio_id: str
    radio_serial: str
    receiver_id: int
    physical_receiver_id: str
    hardware_epoch_id: str
    center_hz: float
    uncertainty_lower_hz: float
    uncertainty_upper_hz: float
    valid_from_utc_ns: int
    valid_until_utc_ns: int | None
    method: str
    created_utc_ns: int
    evidence_uri: str
    evidence_digest: str
    evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FrequencyCalibrationSetRegistration:
    set_id: str
    set_digest: str
    promotion_id: str
    sealed_utc_ns: int
    evidence_uri: str
    evidence_digest: str
    calibrations: tuple[FrequencyCalibrationRegistration, ...]


@dataclass(frozen=True, slots=True)
class FrequencyCalibrationRecord:
    database_id: int
    registration: FrequencyCalibrationRegistration


@dataclass(frozen=True, slots=True)
class FrequencyCalibrationSetRecord:
    registration: FrequencyCalibrationSetRegistration


@dataclass(frozen=True, slots=True)
class FrequencyCalibrationResolution:
    calibration: FrequencyCalibrationRecord
    calibration_set: FrequencyCalibrationSetRecord


@dataclass(frozen=True, slots=True)
class SessionSearch:
    query: str | None = None
    source_type: str | None = None
    state: str | None = None
    tag: str | None = None
    held: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    cursor: int = 0
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
class RecordingListRow:
    """Database-only projection for bounded recording list pages."""

    session_id: str
    source_type: str
    capture_state: str
    started_at: datetime
    ended_at: datetime | None
    attributes: dict[str, Any]
    tags: tuple[str, ...]
    hold_reason: str | None
    radio_count: int
    run_id: str | None
    pipeline_release_id: str | None
    run_state: str | None
    run_created_at: datetime | None
    run_started_at: datetime | None
    run_sealed_at: datetime | None
    run_failure: str | None
    run_is_current: bool
    coverage: float | None
    product_count: int
    job_outcomes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecordingListPage:
    rows: tuple[RecordingListRow, ...]
    total: int


@dataclass(frozen=True, slots=True)
class RunExecutionInfo:
    run_id: str
    session_id: str
    pipeline_release_id: str
    pipeline_configuration: dict[str, Any]
    input_manifest_digest: str
    trigger: str
    bundle_uri: str
    promotion_policy: str = "current"
    code_revision: str = ""
    environment_digest: str = ""
    graph_digest: str = ""
    configuration_digest: str = ""
    executable_digest: str = ""
    expanded_plan_digest: str | None = None
    raw_integrity_attestation_digest: str | None = None
    raw_integrity_attestation: dict[str, Any] | None = None


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
    scope_id: int | None = None
    scope: ScopeIdentityV1 | None = None
    derivation_output_id: int | None = None
    derivation_mode: str = "legacy"
    reused_from_product_id: int | None = None


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
class RecordingChunkRegistration:
    chunk_index: int
    sample_start: int
    sample_count: int
    logical_uri: str
    compressed_digest: str
    uncompressed_digest: str
    compressed_bytes: int
    uncompressed_bytes: int


@dataclass(frozen=True, slots=True)
class RadioStreamRegistration:
    stream_id: str
    radio_id: str
    radio_serial: str
    radio_uri: str
    radio_transport: str
    state: str
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    captured_sample_count: int
    observed_start_at: datetime | None
    observed_end_at: datetime | None
    attributes: dict[str, Any]
    chunks: tuple[RecordingChunkRegistration, ...]
    manifest_ordinal: int = 0


@dataclass(frozen=True, slots=True)
class ScientificCampaignRegistration:
    campaign_id: str
    capture_uri: str
    capture_digest: str


@dataclass(frozen=True, slots=True)
class ScientificCampaignStreamRegistration:
    ordinal: int
    session_id: str
    stream_id: str
    analysis_run_id: str
    analysis_run_uri: str
    analysis_run_digest: str
    pipeline_release_id: str
    analysis_product_id: int
    frequency_calibration_id: int
    capture_uri: str
    capture_digest: str
    calibration_uri: str
    calibration_digest: str
    scientific_uri: str
    scientific_digest: str
    status: str


@dataclass(frozen=True, slots=True)
class ScientificCampaignSeal:
    scientific_uri: str
    scientific_digest: str
    presentation_uri: str
    presentation_digest: str
    result_status: str
    outer_seal_uri: str
    outer_seal_digest: str


@dataclass(frozen=True, slots=True)
class ScientificCampaignRecord:
    campaign_id: str
    state: str
    capture_uri: str
    capture_digest: str
    scientific_uri: str | None
    scientific_digest: str | None
    presentation_uri: str | None
    presentation_digest: str | None
    outer_seal_uri: str | None
    outer_seal_digest: str | None
    result_status: str | None
    seal_authority_version: int
    created_at: datetime
    sealed_at: datetime | None
    streams: tuple[ScientificCampaignStreamRegistration, ...]


@dataclass(frozen=True, slots=True)
class CatalogJobRecord:
    job_id: int
    stage_key: str
    scope_key: str
    state: str
    outcome: str | None
    scope_id: int | None = None
    scope: ScopeIdentityV1 | None = None
    node_id: str | None = None
    resource_class: str = "streaming"
    iq_access: str = "legacy"


@dataclass(frozen=True, slots=True)
class RunManifestReference:
    logical_uri: str
    digest: str


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
    promotion_policy: str = "current"


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
