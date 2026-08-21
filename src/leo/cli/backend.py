"""Narrow application port used by Typer commands."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Literal, Protocol

from leo.acquisition import StorageAdmissionDecision
from leo.cli.models import (
    AcquisitionStatusDataV1,
    CalibrationPredeclareDataV1,
    CalibrationPromoteDataV1,
    CalibrationQueueDataV1,
    CalibrationShowDataV1,
    CancelRunDataV1,
    CaptureDataV1,
    DoctorDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    JobsDataV1,
    ProfileListDataV1,
    ProfileShowDataV1,
    ProfileValidationDataV1,
    RadioListDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    StopAndFenceDataV1,
    WorkerDataV1,
    WP11ConfigDataV1,
    WP11CreateDataV1,
    WP11FinalizeDataV1,
    WP11LegacyDataV1,
    WP11QueueDataV1,
    WP11ShowDataV1,
)
from leo.qualification import (
    AcquisitionAcceptancePolicyV1,
    AcquisitionQualificationReceiptV1,
    CaptureModeCampaignAcceptanceReceiptV2,
    RuntimeContinuityEvidenceV1,
    SoakAcceptanceAuditReceiptV1,
    SoakConfigV1,
    SoakSummaryV1,
    WriterBenchmarkConfigV1,
    WriterBenchmarkReceiptV1,
)


class CliBackendError(RuntimeError):
    def __init__(self, message: str, exit_code: ExitCode) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class AcquisitionCliBackend(Protocol):
    def radios(self, *, probe: bool) -> RadioListDataV1: ...

    def doctor(self, *, probe_radios: bool) -> DoctorDataV1: ...

    def profiles_list(self) -> ProfileListDataV1: ...

    def profile_show(self, name: str) -> ProfileShowDataV1: ...

    def profiles_validate(self, target: str | None) -> ProfileValidationDataV1: ...

    def capture_once(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        session_id: str | None,
        extra_tags: tuple[str, ...],
        cancel: Event,
    ) -> CaptureDataV1: ...

    def status(self) -> AcquisitionStatusDataV1: ...

    def qualify(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        qualification_id: str | None,
        trial_count: int,
        receipt_path: Path | None,
        policy: AcquisitionAcceptancePolicyV1,
        resume: bool,
        cancel: Event,
    ) -> AcquisitionQualificationReceiptV1: ...

    def accept_capture_modes(
        self,
        profile_name: str,
        *,
        radio_ids: tuple[str, str],
        acceptance_id: str,
        independent_radio_a_session_ids: tuple[str, ...],
        independent_radio_b_session_ids: tuple[str, ...],
        synchronized_pair_session_ids: tuple[str, ...],
        receipt_path: Path | None,
    ) -> CaptureModeCampaignAcceptanceReceiptV2: ...

    def benchmark_writer(
        self,
        *,
        benchmark_id: str | None,
        receipt_path: Path | None,
        configuration: WriterBenchmarkConfigV1,
        resume: bool,
        cancel: Event,
    ) -> WriterBenchmarkReceiptV1: ...

    def soak(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        soak_id: str | None,
        output_root: Path | None,
        configuration: SoakConfigV1,
        resume: bool,
        cancel: Event,
    ) -> SoakSummaryV1: ...

    def audit_soak(
        self,
        evidence: str,
        *,
        database_url: str | None,
        receipt_path: Path | None,
        runtime_evidence_path: Path | None,
    ) -> SoakAcceptanceAuditReceiptV1: ...

    def capture_soak_runtime(
        self, soak_id: str, *, output_path: Path
    ) -> RuntimeContinuityEvidenceV1: ...


class ProcessingCliBackend(Protocol):
    def storage_admission(self) -> StorageAdmissionDecision: ...

    def search_sessions(
        self,
        *,
        query: str | None = None,
        source_type: str | None,
        state: str | None,
        tag: str | None,
        held: bool | None,
        created_after: datetime | None,
        created_before: datetime | None,
        cursor: int = 0,
        limit: int,
    ) -> SessionSearchDataV1: ...

    def show_session(self, session_id: str) -> SessionDetailDataV1: ...

    def session_paths(self, session_id: str) -> SessionPathsDataV1: ...

    def reprocess(self, session_id: str, *, dry_run: bool = False) -> ReprocessDataV1: ...

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1: ...

    def stop_and_fence(
        self,
        *,
        operation_id: str,
        pipeline_release_id: str,
        operator_id: str,
        reason: str,
        expected_run_ids: tuple[str, ...] | None,
        allow_current_release: bool,
    ) -> StopAndFenceDataV1: ...

    def jobs(self) -> JobsDataV1: ...

    def pin(self, session_id: str, *, reason: str) -> HoldDataV1: ...

    def unpin(self, session_id: str) -> HoldDataV1: ...

    def import_qnap(
        self,
        manifest_path: Path,
        *,
        copy: bool,
        tags: tuple[str, ...],
    ) -> ImportDataV1: ...

    def retention_status(self) -> RetentionDataV1: ...

    def retention_run(self, *, dry_run: bool) -> RetentionDataV1: ...

    def reconcile(self) -> ReconcileDataV1: ...

    def reconcile_session(self, session_id: str) -> ReconcileDataV1: ...

    def worker(
        self,
        *,
        worker_id: str,
        poll_seconds: float,
        maximum_jobs: int | None,
        once: bool,
        cancel: Event,
    ) -> WorkerDataV1: ...


class CalibrationProcessingCliBackend(Protocol):
    def calibration_predeclare(
        self,
        *,
        plan_id: str,
        radio_id: str,
        scheduled_session_ids: tuple[str, ...],
        starlink_channel: Literal["ch4"],
        starlink_edge: Literal["lower"],
    ) -> CalibrationPredeclareDataV1: ...

    def calibration_queue(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
    ) -> CalibrationQueueDataV1: ...

    def calibration_promote(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
        promotion_id: str,
        calibration_id: str,
        calibration_set_id: str,
        valid_until_utc_ns: int | None,
    ) -> CalibrationPromoteDataV1: ...

    def calibration_show(self, promotion_id: str) -> CalibrationShowDataV1: ...


class WP11ProcessingCliBackend(Protocol):
    def wp11_config(self, *, output_path: Path) -> WP11ConfigDataV1: ...

    def wp11_create(
        self,
        *,
        campaign_id: str,
        capture_uri: str,
        capture_digest: str,
        config_path: Path,
    ) -> WP11CreateDataV1: ...

    def wp11_queue(self, campaign_id: str) -> WP11QueueDataV1: ...

    def wp11_legacy(self, campaign_id: str, *, ordinals: tuple[int, ...]) -> WP11LegacyDataV1: ...

    def wp11_finalize(self, campaign_id: str) -> WP11FinalizeDataV1: ...

    def wp11_show(self, campaign_id: str) -> WP11ShowDataV1: ...


class CliBackend(
    AcquisitionCliBackend,
    ProcessingCliBackend,
    CalibrationProcessingCliBackend,
    WP11ProcessingCliBackend,
    Protocol,
):
    """One application composition port shared by both operational CLI areas."""
