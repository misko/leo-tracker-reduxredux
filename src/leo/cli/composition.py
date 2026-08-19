"""Environment-driven local composition and injectable production hooks."""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Annotated, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from leo.acquisition import (
    AcquisitionApplication,
    AcquisitionConfig,
    AcquisitionCoordinator,
    StorageAdmissionDecision,
)
from leo.acquisition.models import CaptureSessionResult
from leo.cli.backend import (
    CliBackend,
    CliBackendError,
    ProcessingCliBackend,
)
from leo.cli.calibration import CalibrationCliBackend
from leo.cli.models import (
    AcquisitionStatusDataV1,
    CalibrationPredeclareDataV1,
    CalibrationPromoteDataV1,
    CalibrationQueueDataV1,
    CalibrationShowDataV1,
    CancelRunDataV1,
    CaptureDataV1,
    CheckState,
    DoctorCheckV1,
    DoctorDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    JobsDataV1,
    ProfileListDataV1,
    ProfileShowDataV1,
    ProfileValidationDataV1,
    RadioItemV1,
    RadioListDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    WorkerDataV1,
    WP11ConfigDataV1,
    WP11CreateDataV1,
    WP11FinalizeDataV1,
    WP11LegacyDataV1,
    WP11QueueDataV1,
    WP11ShowDataV1,
)
from leo.cli.profiles import ProfileDirectory
from leo.cli.wp11 import WP11CliBackend
from leo.contracts.states import SourceType
from leo.domain.profiles import compile_capture_plan
from leo.qualification import (
    AcquisitionAcceptancePolicyV1,
    AcquisitionQualificationHarness,
    AcquisitionQualificationReceiptV1,
    AcquisitionSoakHarness,
    CaptureModeAcceptanceHarness,
    CaptureModeCampaignAcceptanceReceiptV2,
    CaptureModeExpectationV1,
    FinalSoakAcceptanceAuditor,
    PostCommitObservationV1,
    ProcessingBacklogObservationV1,
    RuntimeContinuityEvidenceV1,
    SoakAcceptanceAuditReceiptV1,
    SoakAcceptancePolicyV1,
    SoakConfigV1,
    SoakSummaryV1,
    WriterBenchmarkConfigV1,
    WriterBenchmarkReceiptV1,
    WriterThroughputBenchmark,
    capture_systemd_runtime_continuity,
    resolve_soak_evidence,
)
from leo.radio import FakeRadioSource, PlutoIioRadioSource, RadioSource
from leo.storage import PublishedBundle, RecordingStore

RadioSourceFactory = Callable[["RadioConfigurationV1"], RadioSource]
RecordingStoreFactory = Callable[[Path], RecordingStore]
CaptureObserver = Callable[[CaptureSessionResult], None]
BackendFactory = Callable[[], CliBackend]
ProcessingBackendFactory = Callable[["CliSettings"], ProcessingCliBackend]
CalibrationBackendFactory = Callable[["CliSettings"], CalibrationCliBackend]
WP11BackendFactory = Callable[["CliSettings"], WP11CliBackend]
_CAPTURE_MODE_RADIO_CONFIG = (
    (
        "radio_pluto_5d4d",
        "1040005e0b100007100010000bf33a5d4d",
        "192.168.1.20",
    ),
    (
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        "192.168.1.21",
    ),
)


class RadioConfigurationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    radio_id: Annotated[str, Field(min_length=1, max_length=128)]
    serial: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    host: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    receiver_count: Literal[1, 2] = 2


@dataclass(frozen=True, slots=True)
class CliSettings:
    profile_root: Path
    bulk_root: Path
    radio_backend: Literal["fake", "pluto"]
    radios: tuple[RadioConfigurationV1, ...]
    safety_reserve_bytes: int = 1 * 1024 * 1024 * 1024
    database_url: str | None = None
    corpus_root: Path | None = None
    pipeline_release_id: str = "standard-v1"
    qualification_root: Path = Path("/srv/bulk/leo/qualification")
    capture_evidence_root: Path = Path("/srv/bulk/leo/qualification/capture")
    legacy_evidence_root: Path = Path("/srv/bulk/leo/qualification/legacy")

    def __post_init__(self) -> None:
        ids = tuple(radio.radio_id for radio in self.radios)
        if len(ids) != len(set(ids)):
            raise ValueError("configured radio IDs must be unique")
        if len(ids) > 2:
            raise ValueError("at most two radios can be configured")
        if self.safety_reserve_bytes < 0:
            raise ValueError("acquisition safety reserve cannot be negative")
        if self.radio_backend == "pluto":
            missing_hosts = tuple(radio.radio_id for radio in self.radios if radio.host is None)
            if missing_hosts:
                raise ValueError(f"Pluto radio hosts are missing: {missing_hosts}")

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> CliSettings:
        values = os.environ if environ is None else environ
        raw_radios = values.get("LEO_RADIOS_JSON", "[]")
        try:
            decoded = json.loads(raw_radios)
            if not isinstance(decoded, list):
                raise ValueError("LEO_RADIOS_JSON must contain a JSON list")
            radios = tuple(RadioConfigurationV1.model_validate(item) for item in decoded)
            backend = values.get("LEO_RADIO_BACKEND", "fake")
            if backend not in {"fake", "pluto"}:
                raise ValueError("LEO_RADIO_BACKEND must be fake or pluto")
            reserve = int(values.get("LEO_ACQUISITION_RESERVE_BYTES", str(1024**3)))
            bulk_root = Path(values.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
            qualification_root = Path(
                values.get("LEO_QUALIFICATION_ROOT", str(bulk_root / "qualification"))
            )
            return cls(
                profile_root=Path(values.get("LEO_PROFILE_ROOT", "profiles")),
                bulk_root=bulk_root,
                radio_backend=cast(Literal["fake", "pluto"], backend),
                radios=radios,
                safety_reserve_bytes=reserve,
                database_url=values.get("LEO_DATABASE_URL"),
                corpus_root=Path(
                    values.get(
                        "LEO_CORPUS_ROOT",
                        str(bulk_root / "test-corpus"),
                    )
                ),
                pipeline_release_id=values.get("LEO_PIPELINE_RELEASE_ID", "standard-v1"),
                qualification_root=qualification_root,
                capture_evidence_root=Path(
                    values.get(
                        "LEO_CAPTURE_EVIDENCE_ROOT",
                        str(qualification_root / "capture"),
                    )
                ),
                legacy_evidence_root=Path(
                    values.get(
                        "LEO_LEGACY_EVIDENCE_ROOT",
                        str(qualification_root / "legacy"),
                    )
                ),
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise CliBackendError(
                f"invalid CLI environment configuration: {error}",
                ExitCode.INVALID_CONFIGURATION,
            ) from error


@dataclass(frozen=True, slots=True)
class CompositionHooks:
    """Replaceable hardware, storage, and catalog-registration boundaries."""

    radio_source_factory: RadioSourceFactory | None = None
    recording_store_factory: RecordingStoreFactory = RecordingStore
    capture_observer: CaptureObserver = lambda _result: None
    processing_backend_factory: ProcessingBackendFactory | None = None
    calibration_backend_factory: CalibrationBackendFactory | None = None
    wp11_backend_factory: WP11BackendFactory | None = None


class LocalAcquisitionBackend:
    def __init__(self, settings: CliSettings, hooks: CompositionHooks | None = None) -> None:
        self.settings = settings
        self.hooks = hooks or CompositionHooks()
        self.profiles = ProfileDirectory(settings.profile_root)
        self._store: RecordingStore | None = None
        self._processing_backend: ProcessingCliBackend | None = None
        self._calibration_backend: CalibrationCliBackend | None = None
        self._wp11_backend: WP11CliBackend | None = None

    def radios(self, *, probe: bool) -> RadioListDataV1:
        items: list[RadioItemV1] = []
        for configuration in self.settings.radios:
            state: Literal["configured", "ready", "error"] = "configured"
            detail = None
            if probe:
                source = self._radio_source(configuration)
                try:
                    identity = source.open()
                    expected_serial = configuration.serial or configuration.radio_id
                    if identity.serial != expected_serial:
                        raise RuntimeError(
                            f"serial readback {identity.serial!r} != {expected_serial!r}"
                        )
                    state = "ready"
                    detail = identity.uri
                except Exception as error:
                    state = "error"
                    detail = f"{type(error).__name__}: {error}"
                finally:
                    try:
                        source.close()
                    except Exception as error:
                        state = "error"
                        detail = f"close failed: {type(error).__name__}: {error}"
            items.append(
                RadioItemV1(
                    radio_id=configuration.radio_id,
                    serial=configuration.serial or configuration.radio_id,
                    backend=self.settings.radio_backend,
                    host=configuration.host,
                    receiver_count=configuration.receiver_count,
                    state=state,
                    detail=detail,
                )
            )
        return RadioListDataV1(radios=tuple(items))

    def doctor(self, *, probe_radios: bool) -> DoctorDataV1:
        checks: list[DoctorCheckV1] = []
        try:
            validation = self.profiles.validate(None)
            checks.append(
                DoctorCheckV1(
                    name="profiles",
                    state=(CheckState.PASS if validation.valid else CheckState.FAIL),
                    detail=f"{len(validation.items)} profile document(s)",
                )
            )
        except Exception as error:
            checks.append(_failed_check("profiles", error))

        try:
            root = self.settings.bulk_root
            root.mkdir(parents=True, exist_ok=True)
            control = root / "control"
            control.mkdir(exist_ok=True)
            probe_path = control / f".doctor-{os.getpid()}-{uuid4().hex}.tmp"
            with probe_path.open("xb") as stream:
                stream.write(b"leo-doctor")
                stream.flush()
                os.fsync(stream.fileno())
            probe_path.unlink()
            free = shutil.disk_usage(root).free
            checks.append(
                DoctorCheckV1(
                    name="bulk_storage",
                    state=CheckState.PASS,
                    detail=f"{root.resolve()} has {free} free bytes",
                )
            )
        except Exception as error:
            checks.append(_failed_check("bulk_storage", error))

        if not self.settings.radios:
            checks.append(
                DoctorCheckV1(
                    name="radios",
                    state=CheckState.FAIL,
                    detail="no acquisition radios are configured",
                )
            )
        else:
            radio_items = self.radios(probe=probe_radios).radios
            failed = tuple(item for item in radio_items if item.state == "error")
            checks.append(
                DoctorCheckV1(
                    name="radios",
                    state=CheckState.FAIL if failed else CheckState.PASS,
                    detail=(
                        f"{len(failed)} of {len(radio_items)} radio probes failed"
                        if failed
                        else f"{len(radio_items)} radio(s) configured"
                    ),
                )
            )
        healthy = all(check.state is not CheckState.FAIL for check in checks)
        return DoctorDataV1(healthy=healthy, checks=tuple(checks))

    def profiles_list(self) -> ProfileListDataV1:
        return self.profiles.list_profiles()

    def profile_show(self, name: str) -> ProfileShowDataV1:
        return self.profiles.show(name)

    def profiles_validate(self, target: str | None) -> ProfileValidationDataV1:
        return self.profiles.validate(target)

    def capture_once(
        self,
        profile_name: str,
        *,
        radio_ids: Sequence[str],
        session_id: str | None,
        extra_tags: tuple[str, ...],
        cancel: Event,
    ) -> CaptureDataV1:
        shown = self.profiles.show(profile_name)
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        selected_ids = tuple(radio_ids) if radio_ids else tuple(configured)
        if not selected_ids:
            raise CliBackendError(
                "no acquisition radios are configured or selected",
                ExitCode.INVALID_CONFIGURATION,
            )
        if len(selected_ids) > 2 or len(set(selected_ids)) != len(selected_ids):
            raise CliBackendError(
                "select one or two unique configured radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        unknown = tuple(radio_id for radio_id in selected_ids if radio_id not in configured)
        if unknown:
            raise CliBackendError(
                f"selected radios are not configured: {unknown}",
                ExitCode.INVALID_CONFIGURATION,
            )
        try:
            source_type = (
                SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
            )
            plan = compile_capture_plan(
                shown.revision,
                selected_ids,
                source_type=source_type,
            )
            store = self._recording_store()
            coordinator = AcquisitionCoordinator(
                store,
                config=AcquisitionConfig(
                    safety_reserve_bytes=self.settings.safety_reserve_bytes,
                ),
                storage_admission=self._capture_storage_admission,
            )
            application = AcquisitionApplication(coordinator)
            sources = {
                radio_id: self._radio_source(configured[radio_id]) for radio_id in selected_ids
            }
            tags = set(extra_tags)
            if source_type is SourceType.TEST:
                tags.add("TEST")
            result = application.once(
                plan,
                sources,
                session_id=session_id,
                cancel=cancel,
                extra_tags=tuple(sorted(tags)),
            )
            self.hooks.capture_observer(result)
            data = _capture_data(profile_name, plan.radio_ids, result)
            if result.bundle is not None:
                warning = self._post_commit_registration()
                if warning is not None:
                    data = data.model_copy(update={"errors": (*data.errors, warning)})
            self._write_last_capture(data)
            return data
        except CliBackendError:
            raise
        except Exception as error:
            raise CliBackendError(
                f"capture setup failed: {type(error).__name__}: {error}",
                ExitCode.CAPTURE_FAILED,
            ) from error

    def status(self) -> AcquisitionStatusDataV1:
        store = self._recording_store()
        reconciliation = store.reconcile()
        return AcquisitionStatusDataV1(
            backend=self.settings.radio_backend,
            bulk_root=str(store.root),
            configured_radio_count=len(self.settings.radios),
            valid_profile_count=self.profiles.count_valid(),
            committed_recording_count=len(reconciliation.committed),
            incomplete_spool_count=sum(1 for _ in store.spool_root.glob("*.partial")),
            reconcile_issue_count=len(reconciliation.issues),
            catalog_registration_warning=self._read_registration_warning(),
            last_capture=self._read_last_capture(),
        )

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
    ) -> AcquisitionQualificationReceiptV1:
        shown = self.profiles.show(profile_name)
        selected, configured = self._selected_radios(radio_ids)
        source_type = SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
        plan = compile_capture_plan(shown.revision, selected, source_type=source_type)
        store = self._recording_store()
        coordinator = AcquisitionCoordinator(
            store,
            config=AcquisitionConfig(
                safety_reserve_bytes=self.settings.safety_reserve_bytes,
            ),
            storage_admission=self._capture_storage_admission,
        )
        identifier = qualification_id or f"qual-{uuid4().hex[:16]}"
        destination = receipt_path or (
            store.root / "qualification" / "acquisition" / f"{identifier}.json"
        )
        harness = AcquisitionQualificationHarness(store, AcquisitionApplication(coordinator))
        receipt = harness.run(
            plan,
            lambda radio_id: self._radio_source(configured[radio_id]),
            qualification_id=identifier,
            trial_count=trial_count,
            receipt_path=destination,
            cancel=cancel,
            policy=policy,
            resume=resume,
        )
        if any(trial.bundle_uri is not None for trial in receipt.trials):
            self._post_commit_registration()
        return receipt

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
    ) -> CaptureModeCampaignAcceptanceReceiptV2:
        expected_ids = tuple(item[0] for item in _CAPTURE_MODE_RADIO_CONFIG)
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        if self.settings.radio_backend != "pluto" or radio_ids != expected_ids:
            raise CliBackendError(
                "capture-mode campaign requires the two fixed production Pluto radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        for radio_id, serial, host in _CAPTURE_MODE_RADIO_CONFIG:
            radio = configured.get(radio_id)
            if (
                radio is None
                or radio.serial != serial
                or radio.host != host
                or radio.receiver_count != 2
            ):
                raise CliBackendError(
                    f"capture-mode campaign configuration does not attest {radio_id}",
                    ExitCode.INVALID_CONFIGURATION,
                )
        shown = self.profiles.show(profile_name)
        expectation = CaptureModeExpectationV1.from_hardware_profile_revision(
            shown.revision,
            radio_ids,
        )
        harness = CaptureModeAcceptanceHarness.open_read_only(self.settings.bulk_root)
        return harness.run_campaign(
            expectation,
            acceptance_id=acceptance_id,
            independent_radio_a_session_ids=independent_radio_a_session_ids,
            independent_radio_b_session_ids=independent_radio_b_session_ids,
            synchronized_pair_session_ids=synchronized_pair_session_ids,
            receipt_path=receipt_path,
        )

    def benchmark_writer(
        self,
        *,
        benchmark_id: str | None,
        receipt_path: Path | None,
        configuration: WriterBenchmarkConfigV1,
        resume: bool,
        cancel: Event,
    ) -> WriterBenchmarkReceiptV1:
        store = self._recording_store()
        identifier = benchmark_id or f"writer-{uuid4().hex[:16]}"
        destination = receipt_path or (
            store.root / "qualification" / "writer" / f"{identifier}.json"
        )
        return WriterThroughputBenchmark(store).run(
            benchmark_id=identifier,
            receipt_path=destination,
            configuration=configuration,
            cancel=cancel,
            resume=resume,
        )

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
    ) -> SoakSummaryV1:
        shown = self.profiles.show(profile_name)
        selected, configured = self._selected_radios(radio_ids)
        source_type = SourceType.TEST if self.settings.radio_backend == "fake" else SourceType.LIVE
        plan = compile_capture_plan(shown.revision, selected, source_type=source_type)
        store = self._recording_store()
        coordinator = AcquisitionCoordinator(
            store,
            config=AcquisitionConfig(
                safety_reserve_bytes=self.settings.safety_reserve_bytes,
            ),
            storage_admission=self._capture_storage_admission,
        )
        identifier = soak_id or f"soak-{uuid4().hex[:16]}"
        harness = AcquisitionSoakHarness(
            store,
            AcquisitionApplication(coordinator),
            output_root=output_root or store.root / "qualification" / "soak",
            backlog_observer=self._soak_backlog_observation,
            post_commit_observer=self._soak_post_commit_observation,
        )
        summary = harness.run(
            plan,
            lambda radio_id: self._radio_source(configured[radio_id]),
            soak_id=identifier,
            configuration=configuration,
            policy=SoakAcceptancePolicyV1(
                maximum_post_commit_failure_count=(
                    0
                    if self.settings.database_url
                    or self.hooks.processing_backend_factory is not None
                    else None
                )
            ),
            cancel=cancel,
            resume=resume,
        )
        if summary.completed_trial_count:
            self._post_commit_registration()
        return summary

    def audit_soak(
        self,
        evidence: str,
        *,
        database_url: str | None,
        receipt_path: Path | None,
        runtime_evidence_path: Path | None,
    ) -> SoakAcceptanceAuditReceiptV1:
        configured_url = database_url or self.settings.database_url
        if configured_url is None:
            raise CliBackendError(
                "soak acceptance audit requires --database-url or LEO_DATABASE_URL",
                ExitCode.INVALID_CONFIGURATION,
            )
        evidence_directory = resolve_soak_evidence(evidence, bulk_root=self.settings.bulk_root)
        auditor = FinalSoakAcceptanceAuditor.from_paths(
            bulk_root=self.settings.bulk_root,
            database_url=configured_url,
            runtime_evidence_path=runtime_evidence_path,
        )
        return auditor.audit(evidence_directory, receipt_path=receipt_path)

    def capture_soak_runtime(
        self, soak_id: str, *, output_path: Path
    ) -> RuntimeContinuityEvidenceV1:
        return capture_systemd_runtime_continuity(soak_id, output_path)

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
    ) -> SessionSearchDataV1:
        return self._processing().search_sessions(
            query=query,
            source_type=source_type,
            state=state,
            tag=tag,
            held=held,
            created_after=created_after,
            created_before=created_before,
            cursor=cursor,
            limit=limit,
        )

    def show_session(self, session_id: str) -> SessionDetailDataV1:
        return self._processing().show_session(session_id)

    def session_paths(self, session_id: str) -> SessionPathsDataV1:
        return self._processing().session_paths(session_id)

    def reprocess(self, session_id: str, *, dry_run: bool = False) -> ReprocessDataV1:
        return self._processing().reprocess(session_id, dry_run=dry_run)

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1:
        return self._processing().cancel_run(run_id, reason=reason)

    def jobs(self) -> JobsDataV1:
        return self._processing().jobs()

    def pin(self, session_id: str, *, reason: str) -> HoldDataV1:
        return self._processing().pin(session_id, reason=reason)

    def unpin(self, session_id: str) -> HoldDataV1:
        return self._processing().unpin(session_id)

    def import_qnap(
        self,
        manifest_path: Path,
        *,
        copy: bool,
        tags: tuple[str, ...],
    ) -> ImportDataV1:
        return self._processing().import_qnap(manifest_path, copy=copy, tags=tags)

    def retention_status(self) -> RetentionDataV1:
        return self._processing().retention_status()

    def storage_admission(self) -> StorageAdmissionDecision:
        return self._processing().storage_admission()

    def retention_run(self, *, dry_run: bool) -> RetentionDataV1:
        return self._processing().retention_run(dry_run=dry_run)

    def reconcile(self) -> ReconcileDataV1:
        return self._processing().reconcile()

    def reconcile_session(self, session_id: str) -> ReconcileDataV1:
        return self._processing().reconcile_session(session_id)

    def worker(
        self,
        *,
        worker_id: str,
        poll_seconds: float,
        maximum_jobs: int | None,
        once: bool,
        cancel: Event,
    ) -> WorkerDataV1:
        return self._processing().worker(
            worker_id=worker_id,
            poll_seconds=poll_seconds,
            maximum_jobs=maximum_jobs,
            once=once,
            cancel=cancel,
        )

    def calibration_predeclare(
        self,
        *,
        plan_id: str,
        radio_id: str,
        scheduled_session_ids: tuple[str, ...],
    ) -> CalibrationPredeclareDataV1:
        return self._calibration().calibration_predeclare(
            plan_id=plan_id,
            radio_id=radio_id,
            scheduled_session_ids=scheduled_session_ids,
        )

    def calibration_queue(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
    ) -> CalibrationQueueDataV1:
        return self._calibration().calibration_queue(
            plan_uri=plan_uri,
            plan_digest=plan_digest,
        )

    def calibration_promote(
        self,
        *,
        plan_uri: str,
        plan_digest: str,
        promotion_id: str,
        calibration_id: str,
        calibration_set_id: str,
        valid_until_utc_ns: int | None,
    ) -> CalibrationPromoteDataV1:
        return self._calibration().calibration_promote(
            plan_uri=plan_uri,
            plan_digest=plan_digest,
            promotion_id=promotion_id,
            calibration_id=calibration_id,
            calibration_set_id=calibration_set_id,
            valid_until_utc_ns=valid_until_utc_ns,
        )

    def calibration_show(self, promotion_id: str) -> CalibrationShowDataV1:
        return self._calibration().calibration_show(promotion_id)

    def wp11_create(
        self,
        *,
        campaign_id: str,
        capture_uri: str,
        capture_digest: str,
        config_path: Path,
    ) -> WP11CreateDataV1:
        return self._wp11().wp11_create(
            campaign_id=campaign_id,
            capture_uri=capture_uri,
            capture_digest=capture_digest,
            config_path=config_path,
        )

    def wp11_config(self, *, output_path: Path) -> WP11ConfigDataV1:
        return self._wp11().wp11_config(output_path=output_path)

    def wp11_queue(self, campaign_id: str) -> WP11QueueDataV1:
        return self._wp11().wp11_queue(campaign_id)

    def wp11_legacy(
        self,
        campaign_id: str,
        *,
        ordinals: tuple[int, ...],
    ) -> WP11LegacyDataV1:
        return self._wp11().wp11_legacy(campaign_id, ordinals=ordinals)

    def wp11_finalize(self, campaign_id: str) -> WP11FinalizeDataV1:
        return self._wp11().wp11_finalize(campaign_id)

    def wp11_show(self, campaign_id: str) -> WP11ShowDataV1:
        return self._wp11().wp11_show(campaign_id)

    def _wp11(self) -> WP11CliBackend:
        if self._wp11_backend is not None:
            return self._wp11_backend
        if self.hooks.wp11_backend_factory is not None:
            self._wp11_backend = self.hooks.wp11_backend_factory(self.settings)
            return self._wp11_backend
        if not self.settings.database_url:
            raise CliBackendError(
                "LEO_DATABASE_URL is required for WP11 commands",
                ExitCode.INVALID_CONFIGURATION,
            )
        from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
        from leo.application.frequency_calibration import (
            NativeReleaseCalibrationEvidenceAdapter,
        )
        from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
        from leo.application.trusted_campaign_production import (
            TrustedCampaignProductionSettings,
            open_trusted_campaign_service,
        )
        from leo.application.trusted_matched_recovery import (
            PostgresAuthoritativeCalibrationScope,
        )
        from leo.application.wp11_legacy import WP11LegacyOracleCampaignRunner
        from leo.application.wp11_operations import WP11Operations
        from leo.application.wp11_production import WP11ProductionWorkflow
        from leo.cli.processing import LocalProcessingBackend
        from leo.qualification.frequency_calibration_store import (
            AuthoritativeCalibrationResolver,
            ImmutableCalibrationPromotionStore,
        )
        from leo.qualification.native_release import _normalized_absolute
        from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
        from leo.storage import PinnedLocalRoot

        processing = self._processing()
        if not isinstance(processing, LocalProcessingBackend):
            raise CliBackendError(
                "WP11 requires concrete PostgreSQL processing services",
                ExitCode.INVALID_CONFIGURATION,
            )
        for label, root in (
            ("bulk", self.settings.bulk_root),
            ("qualification", self.settings.qualification_root),
            ("capture evidence", self.settings.capture_evidence_root),
            ("legacy evidence", self.settings.legacy_evidence_root),
        ):
            _normalized_absolute(root, f"WP11 {label} root")
        qualification = PinnedLocalRoot(self.settings.qualification_root)
        capture_root = PinnedLocalRoot(self.settings.capture_evidence_root)
        legacy_root = PinnedLocalRoot(self.settings.legacy_evidence_root)
        bulk = PinnedLocalRoot(self.settings.bulk_root)
        try:
            plans = ImmutableWP11PlanStore(qualification)
            capture = ImmutableCaptureCampaignAuthority(capture_root)
            spool = bulk.child("spool")
            calibration_root = qualification.child("frequency-calibration-promotions")
        finally:
            qualification.close()
            capture_root.close()
            bulk.close()
        release_settings = TrustedCampaignProductionSettings(
            database_url=self.settings.database_url,
            bulk_root=self.settings.bulk_root,
            qualification_root=self.settings.qualification_root,
            capture_evidence_root=self.settings.capture_evidence_root,
            legacy_evidence_root=self.settings.legacy_evidence_root,
            pipeline_release_id=self.settings.pipeline_release_id,
        )
        releases = NativeReleaseCalibrationEvidenceAdapter(
            self.settings.pipeline_release_id,
            current_link=release_settings.current_release_link,
            deployment_root=release_settings.deployment_root,
        )
        calibration_store = ImmutableCalibrationPromotionStore.open_pinned(calibration_root)
        calibration_root.close()
        calibration_resolver = AuthoritativeCalibrationResolver(
            calibration_store,
            releases,
            allowed_release_ids=(self.settings.pipeline_release_id,),
        )
        scopes = PostgresAuthoritativeCalibrationScope(
            processing.services.catalog,
            processing.services.recordings,
            PostgresCalibrationCatalogAdapter(
                processing.services.catalog,
                calibration_resolver,
            ),
        )
        trusted = open_trusted_campaign_service(release_settings)
        self._wp11_backend = WP11CliBackend(
            WP11Operations(
                WP11ProductionWorkflow(
                    plans=plans,
                    capture=capture,
                    catalog=processing.services.catalog,
                    processing=processing.services.processing,
                    trusted=trusted,
                    pipeline_release_id=self.settings.pipeline_release_id,
                )
            ),
            legacy=WP11LegacyOracleCampaignRunner(
                plans=plans,
                capture=capture,
                scopes=scopes,
                recordings=processing.services.recordings,
                spool=spool,
                evidence_root=legacy_root,
                pipeline_release_id=self.settings.pipeline_release_id,
            ),
            releases=releases,
        )
        spool.close()
        legacy_root.close()
        return self._wp11_backend

    def _calibration(self) -> CalibrationCliBackend:
        if self._calibration_backend is None:
            if self.hooks.calibration_backend_factory is not None:
                self._calibration_backend = self.hooks.calibration_backend_factory(self.settings)
            else:
                if not self.settings.database_url:
                    raise CliBackendError(
                        "LEO_DATABASE_URL is required for calibration commands",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                from leo.cli.calibration import (
                    CalibrationBackendSettings,
                    build_postgres_calibration_backend,
                )
                from leo.cli.processing import LocalProcessingBackend

                processing = self._processing()
                if not isinstance(processing, LocalProcessingBackend):
                    raise CliBackendError(
                        "calibration requires concrete PostgreSQL processing services",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                self._calibration_backend = build_postgres_calibration_backend(
                    CalibrationBackendSettings(
                        qualification_root=self.settings.qualification_root,
                        bulk_root=self.settings.bulk_root,
                        pipeline_release_id=self.settings.pipeline_release_id,
                    ),
                    services=processing.services,
                )
        return self._calibration_backend

    def _processing(self) -> ProcessingCliBackend:
        if self._processing_backend is None:
            if self.hooks.processing_backend_factory is not None:
                self._processing_backend = self.hooks.processing_backend_factory(self.settings)
            else:
                if not self.settings.database_url:
                    raise CliBackendError(
                        "LEO_DATABASE_URL is required for process commands",
                        ExitCode.INVALID_CONFIGURATION,
                    )
                from leo.cli.processing import (
                    ProcessingBackendSettings,
                    build_processing_backend,
                )

                self._processing_backend = build_processing_backend(
                    ProcessingBackendSettings(
                        database_url=self.settings.database_url,
                        bulk_root=self.settings.bulk_root,
                        corpus_root=(
                            self.settings.corpus_root
                            if self.settings.corpus_root is not None
                            else self.settings.bulk_root / "test-corpus"
                        ),
                        pipeline_release_id=self.settings.pipeline_release_id,
                        qualification_root=self.settings.qualification_root,
                        legacy_evidence_root=self.settings.legacy_evidence_root,
                        capture_evidence_root=self.settings.capture_evidence_root,
                    )
                )
        return self._processing_backend

    def _capture_storage_admission(self, _root: Path) -> StorageAdmissionDecision:
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return StorageAdmissionDecision(allowed=True)
        try:
            return self._processing().storage_admission()
        except Exception as error:
            return StorageAdmissionDecision(
                allowed=True,
                warning=True,
                reason=(
                    "catalog-backed retention admission is unavailable; "
                    f"free-byte admission only ({type(error).__name__}: {error})"
                ),
            )

    def _soak_backlog_observation(self) -> ProcessingBacklogObservationV1:
        observed_utc_ns = time.time_ns()
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return ProcessingBacklogObservationV1(
                observed_utc_ns=observed_utc_ns,
                available=False,
                error="processing backlog observer is not configured",
            )
        jobs = self._processing().jobs()
        return ProcessingBacklogObservationV1(
            observed_utc_ns=observed_utc_ns,
            queued=jobs.queued,
            running=jobs.running,
            failed=jobs.failed,
            oldest_queued_seconds=jobs.oldest_queued_seconds,
        )

    def _soak_post_commit_observation(
        self,
        bundle: PublishedBundle,
    ) -> PostCommitObservationV1:
        observed_utc_ns = time.time_ns()
        if "QUALIFICATION" in bundle.manifest.tags:
            raise ValueError(
                "soak recording unexpectedly has QUALIFICATION tag and would be skipped"
            )
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return PostCommitObservationV1(
                observed_utc_ns=observed_utc_ns,
                target_session_id=bundle.session_id,
                attempted=False,
                succeeded=False,
                error="catalog registration is not configured",
            )
        try:
            result = self._processing().reconcile_session(bundle.session_id)
            if result.issues:
                raise RuntimeError("; ".join(result.issues))
            known = (
                bundle.session_id in result.registered_sessions
                or bundle.session_id in result.existing_sessions
            )
            if not known:
                raise RuntimeError("reconciliation did not report the target soak recording")
            if bundle.session_id in result.registered_sessions and not result.queued_run_ids:
                raise RuntimeError("new soak recording did not queue an analysis run")
        except Exception as error:
            warning = (
                "recording committed locally but per-trial catalog registration failed: "
                f"{type(error).__name__}: {error}"
            )
            self._write_registration_warning(warning)
            raise
        self._write_registration_warning(None)
        return PostCommitObservationV1(
            observed_utc_ns=observed_utc_ns,
            target_session_id=bundle.session_id,
            attempted=True,
            succeeded=True,
            registered_session_ids=result.registered_sessions,
            existing_session_ids=result.existing_sessions,
            queued_run_ids=result.queued_run_ids,
        )

    def _post_commit_registration(self) -> str | None:
        if not self.settings.database_url and self.hooks.processing_backend_factory is None:
            return None
        try:
            result = self._processing().reconcile()
            if result.issues:
                raise RuntimeError("; ".join(result.issues))
        except Exception as error:
            warning = (
                "recording committed locally but catalog registration is pending: "
                f"{type(error).__name__}: {error}"
            )
            self._write_registration_warning(warning)
            return warning
        self._write_registration_warning(None)
        return None

    def _registration_warning_path(self) -> Path:
        control = self._recording_store().root / "control"
        control.mkdir(exist_ok=True)
        return control / "catalog-registration-warning.txt"

    def _write_registration_warning(self, warning: str | None) -> None:
        destination = self._registration_warning_path()
        if warning is None:
            destination.unlink(missing_ok=True)
            return
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}-{uuid4().hex}.partial"
        )
        with temporary.open("xb") as stream:
            stream.write(warning.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)

    def _read_registration_warning(self) -> str | None:
        path = self._registration_warning_path()
        try:
            return path.read_text(encoding="utf-8") if path.exists() else None
        except OSError:
            return "catalog registration warning status is unreadable"

    def _recording_store(self) -> RecordingStore:
        if self._store is None:
            self._store = self.hooks.recording_store_factory(self.settings.bulk_root)
        return self._store

    def _radio_source(self, configuration: RadioConfigurationV1) -> RadioSource:
        if self.hooks.radio_source_factory is not None:
            return self.hooks.radio_source_factory(configuration)
        if self.settings.radio_backend == "fake":
            return FakeRadioSource(
                configuration.radio_id,
                receiver_count=configuration.receiver_count,
            )
        assert configuration.host is not None
        return PlutoIioRadioSource(
            configuration.host,
            expected_serial=configuration.serial or configuration.radio_id,
            radio_id=configuration.radio_id,
        )

    def _selected_radios(
        self,
        radio_ids: Sequence[str],
    ) -> tuple[tuple[str, ...], dict[str, RadioConfigurationV1]]:
        configured = {radio.radio_id: radio for radio in self.settings.radios}
        selected = tuple(radio_ids) if radio_ids else tuple(configured)
        if not selected:
            raise CliBackendError(
                "no acquisition radios are configured or selected",
                ExitCode.INVALID_CONFIGURATION,
            )
        if len(selected) > 2 or len(set(selected)) != len(selected):
            raise CliBackendError(
                "select one or two unique configured radio IDs",
                ExitCode.INVALID_CONFIGURATION,
            )
        unknown = tuple(radio_id for radio_id in selected if radio_id not in configured)
        if unknown:
            raise CliBackendError(
                f"selected radios are not configured: {unknown}",
                ExitCode.INVALID_CONFIGURATION,
            )
        return selected, configured

    def _status_path(self) -> Path:
        control = self._recording_store().root / "control"
        control.mkdir(exist_ok=True)
        return control / "last-capture.json"

    def _write_last_capture(self, capture: CaptureDataV1) -> None:
        destination = self._status_path()
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}-{uuid4().hex}.partial"
        )
        payload = capture.model_dump_json().encode("utf-8")
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)

    def _read_last_capture(self) -> CaptureDataV1 | None:
        path = self._status_path()
        if not path.exists():
            return None
        try:
            return CaptureDataV1.model_validate_json(path.read_bytes())
        except (OSError, ValidationError):
            return None


def default_backend_factory() -> CliBackend:
    return LocalAcquisitionBackend(CliSettings.from_environ())


def configured_backend_factory(
    settings: CliSettings,
    hooks: CompositionHooks | None = None,
) -> BackendFactory:
    """Return a lazy factory suitable for tests and production composition roots."""

    return lambda: LocalAcquisitionBackend(settings, hooks)


def _capture_data(
    profile_name: str,
    radio_ids: tuple[str, ...],
    result: CaptureSessionResult,
) -> CaptureDataV1:
    bundle = result.bundle
    return CaptureDataV1(
        session_id=result.session_id,
        state=result.state,
        bundle_uri=None if bundle is None else bundle.uri,
        manifest_sha256=None if bundle is None else bundle.manifest_sha256,
        radio_ids=radio_ids,
        profile_name=profile_name,
        raw_iq_bytes=result.admission.raw_iq_bytes,
        required_free_bytes=result.admission.required_free_bytes,
        available_free_bytes=result.admission.available_free_bytes,
        storage_used_fraction=result.admission.storage_used_fraction,
        storage_warning=result.admission.storage_warning,
        admission_reason=result.admission.policy_reason,
        errors=result.errors,
    )


def _failed_check(name: str, error: Exception) -> DoctorCheckV1:
    return DoctorCheckV1(
        name=name,
        state=CheckState.FAIL,
        detail=f"{type(error).__name__}: {error}",
    )
