"""Typed command results shared by human and JSON CLI renderers."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leo.application.calibration_operations import (
    CalibrationPredeclarationResultV1,
    CalibrationPromotionResultV1,
    CalibrationQueueResultV1,
)
from leo.application.trusted_campaign import TrustedCampaignPublicationV1
from leo.application.wp11_legacy import WP11ConfigPublication, WP11LegacyRunResult
from leo.application.wp11_operations import (
    WP11CampaignSummary,
    WP11CreateResult,
    WP11QueueResult,
)
from leo.contracts.capture_control import CaptureControlStateV1
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileRevisionV2
from leo.contracts.states import CaptureState
from leo.qualification import (
    AcquisitionQualificationReceiptV1,
    CaptureModeCampaignAcceptanceReceiptV2,
    RuntimeContinuityEvidenceV1,
    SoakAcceptanceAuditReceiptV1,
    SoakSummaryV1,
    WriterBenchmarkReceiptV1,
)
from leo.scanner import (
    ScannerBurstReportV1,
    ScannerBurstReportV2,
    ScannerBurstReportV3,
    ScannerBurstReportV4,
    ScannerReport,
    ScannerReportV2,
    ScannerReportV3,
    ScannerReportV4,
)


class CliModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExitCode(IntEnum):
    OK = 0
    INVALID_CONFIGURATION = 10
    NOT_FOUND = 11
    UNHEALTHY = 12
    CONFLICT = 13
    CONFIRMATION_REQUIRED = 14
    ADMISSION_REJECTED = 20
    CAPTURE_FAILED = 21
    CAPTURE_DEGRADED = 22
    PROCESSING_FAILED = 30
    UNEXPECTED = 70
    INTERRUPTED = 130


class CheckState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class RadioItemV1(CliModel):
    radio_id: str
    serial: str
    backend: Literal["fake", "pluto"]
    host: str | None = None
    receiver_count: Literal[1, 2]
    state: Literal["configured", "ready", "error"]
    detail: str | None = None


class RadioListDataV1(CliModel):
    kind: Literal["radio_list"] = "radio_list"
    radios: tuple[RadioItemV1, ...]


class DoctorCheckV1(CliModel):
    name: str
    state: CheckState
    detail: str


class DoctorDataV1(CliModel):
    kind: Literal["doctor"] = "doctor"
    healthy: bool
    checks: tuple[DoctorCheckV1, ...]


class ProfileSummaryV1(CliModel):
    name: str
    revision_digest: str
    sample_rate_hz: int
    sample_count: int | None
    duration_seconds: str | None
    receivers: tuple[int, ...]
    tags: tuple[str, ...]
    path: str


class ProfileListDataV1(CliModel):
    kind: Literal["profile_list"] = "profile_list"
    profiles: tuple[ProfileSummaryV1, ...]


class ProfileShowDataV1(CliModel):
    kind: Literal["profile_show"] = "profile_show"
    path: str
    revision: CaptureProfileRevisionV1


class ProfileShowDataV2(CliModel):
    kind: Literal["profile_show_v2"] = "profile_show_v2"
    path: str
    revision: CaptureProfileRevisionV2


class ProfileValidationItemV1(CliModel):
    path: str
    name: str | None = None
    valid: bool
    revision_digest: str | None = None
    error: str | None = None


class ProfileValidationDataV1(CliModel):
    kind: Literal["profile_validation"] = "profile_validation"
    valid: bool
    items: tuple[ProfileValidationItemV1, ...]


class CaptureStreamCoverageV1(CliModel):
    radio_id: str
    stream_id: str
    delivery_unit: Literal["frames", "device_samples"]
    delivered_units: Annotated[int, Field(ge=0)]
    requested_units: Annotated[int, Field(gt=0)]
    delivery_coverage_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    observed_samples: Annotated[int, Field(ge=0)]
    logical_samples: Annotated[int, Field(ge=0)]
    observed_density_pct: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    in_segment_density_pct: Annotated[float | None, Field(gt=0.0, le=100.0)] = None
    transport_density_pct: Annotated[float | None, Field(gt=0.0, le=100.0)] = None

    @model_validator(mode="after")
    def _percentages_match_counts(self) -> Self:
        delivery = 100.0 * self.delivered_units / self.requested_units
        if abs(self.delivery_coverage_pct - delivery) > 1e-12:
            raise ValueError("delivery coverage percentage disagrees with exact counts")
        if self.observed_samples > self.logical_samples:
            raise ValueError("observed samples exceed the logical sample span")
        expected_density = (
            None
            if self.logical_samples == 0
            else 100.0 * self.observed_samples / self.logical_samples
        )
        if self.observed_density_pct != expected_density:
            raise ValueError("observed density percentage disagrees with exact counts")
        return self


class CaptureDataV1(CliModel):
    kind: Literal["capture"] = "capture"
    session_id: str
    state: CaptureState
    bundle_uri: str | None = None
    manifest_sha256: str | None = None
    radio_ids: tuple[str, ...]
    profile_name: str
    raw_iq_bytes: int
    required_free_bytes: int
    available_free_bytes: int
    storage_used_fraction: float | None = None
    storage_warning: bool = False
    admission_reason: str | None = None
    errors: tuple[str, ...] = ()
    stream_coverage: tuple[CaptureStreamCoverageV1, ...] = ()


class RunDataV1(CliModel):
    kind: Literal["run"] = "run"
    profile_name: str
    stopped_reason: Literal["cancelled", "maximum_captures", "error"]
    capture_count: int
    committed_count: int
    degraded_count: int
    failed_count: int
    last_capture: CaptureDataV1 | None = None
    error: str | None = None


class RunDataV2(CliModel):
    """Summary for a run that selects one exact profile for every dwell."""

    kind: Literal["run_v2"] = "run_v2"
    profile_names: tuple[str, ...]
    selection_policy: Literal["uniform_per_dwell"] = "uniform_per_dwell"
    stopped_reason: Literal["cancelled", "maximum_captures", "error"]
    capture_count: int
    committed_count: int
    degraded_count: int
    failed_count: int
    last_capture: CaptureDataV1 | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _profile_pool_is_exact(self) -> Self:
        if len(self.profile_names) < 2:
            raise ValueError("multi-profile run requires at least two profiles")
        if any(not name or name != name.strip() for name in self.profile_names):
            raise ValueError("run profile names must be non-empty exact values")
        if len(set(self.profile_names)) != len(self.profile_names):
            raise ValueError("run profile names must be unique")
        return self


class ScheduledDwellPayloadV1(CliModel):
    """Durable execution intent after choosing one profile for one dwell."""

    schema_version: Literal[1] = 1
    profile_name: str
    profile_names: tuple[str, ...] = ()
    selection_policy: Literal["single", "uniform_per_dwell"] = "single"
    radio_ids: tuple[str, ...]
    extra_tags: tuple[str, ...]

    @model_validator(mode="after")
    def _selected_profile_belongs_to_pool(self) -> Self:
        if not self.profile_name or self.profile_name != self.profile_name.strip():
            raise ValueError("scheduled dwell profile name must be one exact value")
        candidates = self.profile_names or (self.profile_name,)
        if any(not name or name != name.strip() for name in candidates):
            raise ValueError("scheduled dwell profile names must be non-empty exact values")
        if len(set(candidates)) != len(candidates):
            raise ValueError("scheduled dwell profile names must be unique")
        if self.profile_name not in candidates:
            raise ValueError("selected scheduled dwell profile is outside its candidate pool")
        expected_policy = "single" if len(candidates) == 1 else "uniform_per_dwell"
        if self.selection_policy != expected_policy:
            raise ValueError("scheduled dwell selection policy disagrees with its profile pool")
        if len(set(self.radio_ids)) != len(self.radio_ids):
            raise ValueError("scheduled dwell radio IDs must be unique")
        return self


class AcquisitionStatusDataV1(CliModel):
    kind: Literal["acquisition_status"] = "acquisition_status"
    backend: Literal["fake", "pluto"]
    bulk_root: str
    configured_radio_count: int
    valid_profile_count: int
    committed_recording_count: int
    incomplete_spool_count: int
    reconcile_issue_count: int
    catalog_registration_warning: str | None = None
    last_capture: CaptureDataV1 | None = None
    capture_control: CaptureControlStateV1 | None = None


class CaptureControlDataV1(CliModel):
    kind: Literal["capture_control"] = "capture_control"
    state: CaptureControlStateV1
    radio_ids: tuple[str, ...]


class ProcessHelpDataV1(CliModel):
    kind: Literal["process_help"] = "process_help"
    available_commands: tuple[str, ...] = (
        "search",
        "show",
        "paths",
        "reprocess",
        "cancel-run",
        "stop-and-fence",
        "jobs",
        "pin",
        "unpin",
        "import-qnap",
        "retention-status",
        "retention-run",
        "reconcile",
        "worker",
        "calibration",
        "wp11",
    )


class CalibrationPredeclareDataV1(CliModel):
    kind: Literal["calibration_predeclare"] = "calibration_predeclare"
    result: CalibrationPredeclarationResultV1


class CalibrationQueueDataV1(CliModel):
    kind: Literal["calibration_queue"] = "calibration_queue"
    result: CalibrationQueueResultV1


class CalibrationPromoteDataV1(CliModel):
    kind: Literal["calibration_promote"] = "calibration_promote"
    result: CalibrationPromotionResultV1


class CalibrationShowDataV1(CliModel):
    kind: Literal["calibration_show"] = "calibration_show"
    result: CalibrationPromotionResultV1


class WP11CreateDataV1(CliModel):
    kind: Literal["wp11_create"] = "wp11_create"
    result: WP11CreateResult


class WP11QueueDataV1(CliModel):
    kind: Literal["wp11_queue"] = "wp11_queue"
    result: WP11QueueResult


class WP11LegacyDataV1(CliModel):
    kind: Literal["wp11_legacy"] = "wp11_legacy"
    result: WP11LegacyRunResult


class WP11ConfigDataV1(CliModel):
    kind: Literal["wp11_config"] = "wp11_config"
    result: WP11ConfigPublication


class WP11FinalizeDataV1(CliModel):
    kind: Literal["wp11_finalize"] = "wp11_finalize"
    publication: TrustedCampaignPublicationV1


class WP11ShowDataV1(CliModel):
    kind: Literal["wp11_show"] = "wp11_show"
    summary: WP11CampaignSummary


class SessionSearchItemV1(CliModel):
    session_id: str
    source_type: str
    state: str
    created_at: datetime
    bundle_uri: str | None
    held: bool
    tags: tuple[str, ...]
    current_run_id: str | None


class SessionSearchDataV1(CliModel):
    kind: Literal["session_search"] = "session_search"
    sessions: tuple[SessionSearchItemV1, ...]


class JobItemDataV1(CliModel):
    job_id: int
    stage_key: str
    scope_key: str
    state: str
    outcome: str | None


class ProductItemDataV1(CliModel):
    product_id: int
    stage_key: str
    scope_key: str
    product_kind: str
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


class AnalysisRunDataV1(CliModel):
    run_id: str
    pipeline_release_id: str
    state: str
    created_at: datetime
    started_at: datetime | None
    sealed_at: datetime | None
    failure: str | None
    input_manifest_digest: str
    manifest_uri: str | None
    manifest_digest: str | None
    is_current: bool
    jobs: tuple[JobItemDataV1, ...]
    products: tuple[ProductItemDataV1, ...]


class SessionDetailDataV1(CliModel):
    kind: Literal["session_detail"] = "session_detail"
    session_id: str
    source_type: str
    state: str
    created_at: datetime
    bundle_uri: str | None
    manifest_digest: str | None
    attributes: dict[str, Any]
    tags: tuple[str, ...]
    held: bool
    hold_reason: str | None
    analysis: AnalysisRunDataV1 | None


class PathItemDataV1(CliModel):
    role: str
    logical_uri: str
    physical_path: str | None
    exists: bool
    digest: str | None = None


class SessionPathsDataV1(CliModel):
    kind: Literal["session_paths"] = "session_paths"
    session_id: str
    paths: tuple[PathItemDataV1, ...]


class ReprocessDataV1(CliModel):
    kind: Literal["reprocess"] = "reprocess"
    session_id: str
    run_id: str
    pipeline_release_id: str
    previous_current_run_id: str | None
    queued_scope_keys: tuple[str, ...]
    state: Literal["dry_run", "queued"] = "queued"


class NativeEvidenceReprocessDataV1(CliModel):
    kind: Literal["native_evidence_reprocess"] = "native_evidence_reprocess"
    pipeline_family: Literal["standard-native-evidence-v1"] = "standard-native-evidence-v1"
    promotion_policy: Literal["evidence_only"] = "evidence_only"
    session_id: str
    run_id: str
    pipeline_release_id: str
    previous_current_run_id: str | None
    queued_scope_keys: tuple[str, ...]
    queued_job_count: int = Field(ge=1, le=64)
    state: Literal["dry_run", "queued"] = "queued"


class CancelRunDataV1(CliModel):
    kind: Literal["cancel_analysis_run"] = "cancel_analysis_run"
    run_id: str
    state: Literal["cancelled"] = "cancelled"
    changed: bool
    reason: str
    cancelled_job_count: int = Field(ge=0)
    succeeded_job_count: int = Field(ge=0)
    failed_job_count: int = Field(ge=0)
    product_count: int = Field(ge=0)


class StopAndFenceDataV1(CliModel):
    kind: Literal["processing_stop_and_fence"] = "processing_stop_and_fence"
    operation_id: str
    pipeline_release_id: str
    run_ids: tuple[str, ...]
    changed: bool
    reason: str
    operator_id: str
    cancelled_run_count: int = Field(ge=0)
    cancelled_job_count: int = Field(ge=0)
    expired_attempt_count: int = Field(ge=0)
    preserved_succeeded_job_count: int = Field(ge=0)
    preserved_product_count: int = Field(ge=0)


class JobsDataV1(CliModel):
    kind: Literal["jobs"] = "jobs"
    queued: int
    running: int
    failed: int
    oldest_queued_seconds: float | None
    ready_to_finalize_run_ids: tuple[str, ...] = ()


class HoldDataV1(CliModel):
    kind: Literal["hold"] = "hold"
    session_id: str
    held: bool
    changed: bool
    reason: str | None = None


class ImportFixtureDataV1(CliModel):
    fixture_id: str
    directory: str
    status: Literal["created", "already_present"]
    session_id: str
    bundle_uri: str


class ImportDataV1(CliModel):
    kind: Literal["qnap_import"] = "qnap_import"
    corpus_id: str
    source_manifest: str
    local_root: str
    tags: tuple[Literal["TEST"], ...] = ("TEST",)
    held: Literal[True] = True
    copied: Literal[True] = True
    fixtures: tuple[ImportFixtureDataV1, ...]
    queued_run_ids: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


class RetentionDataV1(CliModel):
    kind: Literal["retention"] = "retention"
    dry_run: bool
    total_bytes: int
    used_bytes: int
    used_fraction: float
    high_watermark: float
    low_watermark: float
    warning_watermark: float
    admission_stop_watermark: float
    should_run: bool
    warning: bool
    admission_allowed_after_plan: bool
    blocked: bool
    selected_ids: tuple[str, ...]
    selected_bytes: int
    predicted_used_bytes: int
    target_used_bytes: int
    committed_ids: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()


class ReconcileDataV1(CliModel):
    kind: Literal["reconcile"] = "reconcile"
    restored_purges: tuple[str, ...]
    discarded_purges: tuple[str, ...]
    registered_sessions: tuple[str, ...]
    existing_sessions: tuple[str, ...]
    queued_run_ids: tuple[str, ...]
    issues: tuple[str, ...]
    historical_incompatibilities: tuple[str, ...] = ()


class WorkerExecutionDataV1(CliModel):
    job_id: int
    run_id: str
    stage_key: str
    scope_key: str
    succeeded: bool
    outcome: str | None
    error: str | None


class WorkerDataV1(CliModel):
    kind: Literal["worker"] = "worker"
    worker_id: str
    stopped_reason: Literal["cancelled", "idle", "maximum_jobs", "error"]
    claimed_count: int
    succeeded_count: int
    failed_count: int
    evidence_limit: int = Field(default=256, ge=1)
    execution_evidence_omitted_count: int = Field(default=0, ge=0)
    finalized_count: int = Field(default=0, ge=0)
    finalized_id_evidence_omitted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    rejected_id_evidence_omitted_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    error_evidence_omitted_count: int = Field(default=0, ge=0)
    finalized_run_ids: tuple[str, ...] = ()
    rejected_run_ids: tuple[str, ...] = ()
    executions: tuple[WorkerExecutionDataV1, ...] = ()
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _counts_match_bounded_evidence(self) -> Self:
        if self.claimed_count != self.succeeded_count + self.failed_count:
            raise ValueError("worker claimed count must equal succeeded plus failed")
        inventories = (
            (
                self.claimed_count,
                len(self.executions),
                self.execution_evidence_omitted_count,
            ),
            (
                self.finalized_count,
                len(self.finalized_run_ids),
                self.finalized_id_evidence_omitted_count,
            ),
            (
                self.rejected_count,
                len(self.rejected_run_ids),
                self.rejected_id_evidence_omitted_count,
            ),
            (self.error_count, len(self.errors), self.error_evidence_omitted_count),
        )
        for total, retained, omitted in inventories:
            if retained > self.evidence_limit:
                raise ValueError("worker evidence exceeds its declared bound")
            if total != retained + omitted:
                raise ValueError("worker evidence total disagrees with retained and omitted")
        return self


CliPayload = Annotated[
    RadioListDataV1
    | DoctorDataV1
    | ProfileListDataV1
    | ProfileShowDataV1
    | ProfileShowDataV2
    | ProfileValidationDataV1
    | CaptureDataV1
    | CaptureControlDataV1
    | RunDataV1
    | RunDataV2
    | AcquisitionStatusDataV1
    | ProcessHelpDataV1
    | AcquisitionQualificationReceiptV1
    | CaptureModeCampaignAcceptanceReceiptV2
    | SoakSummaryV1
    | SoakAcceptanceAuditReceiptV1
    | RuntimeContinuityEvidenceV1
    | WriterBenchmarkReceiptV1
    | SessionSearchDataV1
    | SessionDetailDataV1
    | SessionPathsDataV1
    | ReprocessDataV1
    | NativeEvidenceReprocessDataV1
    | CancelRunDataV1
    | StopAndFenceDataV1
    | JobsDataV1
    | HoldDataV1
    | ImportDataV1
    | RetentionDataV1
    | ReconcileDataV1
    | WorkerDataV1
    | CalibrationPredeclareDataV1
    | CalibrationQueueDataV1
    | CalibrationPromoteDataV1
    | CalibrationShowDataV1
    | WP11CreateDataV1
    | WP11ConfigDataV1
    | WP11QueueDataV1
    | WP11LegacyDataV1
    | WP11FinalizeDataV1
    | WP11ShowDataV1
    | ScannerBurstReportV1
    | ScannerBurstReportV2
    | ScannerBurstReportV3
    | ScannerBurstReportV4
    | ScannerReport
    | ScannerReportV2
    | ScannerReportV3
    | ScannerReportV4,
    Field(discriminator="kind"),
]


class CommandResultV1(CliModel):
    schema_version: Literal[1] = 1
    command: str
    ok: bool
    exit_code: int = Field(ge=0, le=255)
    message: str
    payload: CliPayload | None = None

    @model_validator(mode="after")
    def _status_matches_exit_code(self) -> Self:
        if self.ok != (self.exit_code == ExitCode.OK):
            raise ValueError("command ok flag must agree with its exit code")
        return self
