"""Narrow application port used by Typer commands."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Protocol

from leo.acquisition import StorageAdmissionDecision
from leo.cli.models import (
    AcquisitionStatusDataV1,
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
    WorkerDataV1,
)
from leo.qualification import (
    AcquisitionAcceptancePolicyV1,
    AcquisitionQualificationReceiptV1,
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


class ProcessingCliBackend(Protocol):
    def storage_admission(self) -> StorageAdmissionDecision: ...

    def search_sessions(
        self,
        *,
        source_type: str | None,
        state: str | None,
        tag: str | None,
        held: bool | None,
        created_after: datetime | None,
        created_before: datetime | None,
        limit: int,
    ) -> SessionSearchDataV1: ...

    def show_session(self, session_id: str) -> SessionDetailDataV1: ...

    def session_paths(self, session_id: str) -> SessionPathsDataV1: ...

    def reprocess(self, session_id: str) -> ReprocessDataV1: ...

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1: ...

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


class CliBackend(AcquisitionCliBackend, ProcessingCliBackend, Protocol):
    """One application composition port shared by both operational CLI areas."""
