"""Production composition for catalog-backed processing and data operations."""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Literal
from uuid import uuid4

from leo import __version__
from leo.acquisition import StorageAdmissionDecision
from leo.analysis.adapters import (
    production_long_dwell_configuration,
    production_long_dwell_registry,
)
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink.acceptance import NATIVE_KNOWN_PILOT_EVIDENCE_STAGE
from leo.application.calibration_catalog import PostgresCalibrationCatalogAdapter
from leo.application.calibration_runtime import ImmutableCalibrationScopeProvider
from leo.application.frequency_calibration import NativeReleaseCalibrationEvidenceAdapter
from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
from leo.application.trusted_matched_recovery import (
    PinnedLegacyOracleAuthority,
    PostgresAuthoritativeCalibrationScope,
)
from leo.application.wp11_dynamic import (
    DynamicWP11Analyzer,
    WP11ProductionDelegateFactory,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import (
    ActiveRunExistsError,
    AnalysisRunState,
    CatalogNotFoundError,
    CatalogRepository,
    InvalidStateError,
    JobState,
    SessionSearch,
    create_catalog_engine,
    create_session_factory,
)
from leo.cli.backend import CliBackendError
from leo.cli.models import (
    AnalysisRunDataV1,
    CancelRunDataV1,
    ExitCode,
    HoldDataV1,
    ImportDataV1,
    ImportFixtureDataV1,
    JobItemDataV1,
    JobsDataV1,
    PathItemDataV1,
    ProductItemDataV1,
    ReconcileDataV1,
    ReprocessDataV1,
    RetentionDataV1,
    SessionDetailDataV1,
    SessionPathsDataV1,
    SessionSearchDataV1,
    SessionSearchItemV1,
    WorkerDataV1,
    WorkerExecutionDataV1,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.importing import (
    RECORDING_INGEST_FILENAME,
    FixtureImporter,
    RecordingCorpusIngestService,
    load_corpus_manifest,
    load_recording_ingest_manifest,
)
from leo.operations import (
    CatalogHoldService,
    CatalogReconcileReport,
    CatalogReconciliationService,
    CatalogRetentionService,
    HoldReceiptStore,
    PurgeExecutor,
    RetentionRunResult,
    StorageUsage,
)
from leo.operations.retention import (
    ADMISSION_STOP_WATERMARK,
    HIGH_WATERMARK,
    LOW_WATERMARK,
    WARNING_WATERMARK,
)
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    RunNotReadyError,
    RunRejectedError,
    derive_deployed_worker_release,
)
from leo.qualification.frequency_calibration_documents import ImmutableCalibrationPlanStore
from leo.qualification.frequency_calibration_stage import CalibrationExtractorAnalyzer
from leo.qualification.frequency_calibration_store import (
    AuthoritativeCalibrationResolver,
    ImmutableCalibrationPromotionStore,
)
from leo.qualification.native_execution import ReleaseLocalNativeEvidenceExecutor
from leo.qualification.native_release import _normalized_absolute
from leo.qualification.trusted_matched_recovery_stage import TRUSTED_MATCHED_RECOVERY_STAGE
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
from leo.storage import PinnedLocalRoot, RecordingStore

logger = logging.getLogger(__name__)
_WORKER_EVIDENCE_LIMIT = 256


@dataclass(frozen=True, slots=True)
class ProcessingBackendSettings:
    database_url: str
    bulk_root: Path
    corpus_root: Path
    pipeline_release_id: str = "standard-v1"
    qualification_root: Path | None = None
    legacy_evidence_root: Path | None = None
    capture_evidence_root: Path | None = None
    current_release_link: Path = Path("/opt/leo-tracker/current")
    deployment_root: Path = Path("/opt/leo-tracker")
    scratch_root: Path = Path("/var/tmp")


@dataclass(frozen=True, slots=True)
class ProcessingServices:
    catalog: CatalogRepository
    recordings: RecordingStore
    artifacts: AnalysisArtifactStore
    processing: ProcessingService
    holds: CatalogHoldService
    retention: CatalogRetentionService
    reconciliation: CatalogReconciliationService
    importer: FixtureImporter
    corpus_ingest: RecordingCorpusIngestService
    pipeline_release_id: str


class _WorkerEvidence:
    """Constant-memory recent evidence plus lifetime counters for one worker run."""

    def __init__(self, limit: int = _WORKER_EVIDENCE_LIMIT) -> None:
        self.limit = limit
        self.executions: deque[WorkerExecutionDataV1] = deque(maxlen=limit)
        self.finalized: deque[str] = deque(maxlen=limit)
        self.rejected: deque[str] = deque(maxlen=limit)
        self.errors: deque[str] = deque(maxlen=limit)
        self.claimed_count = 0
        self.succeeded_count = 0
        self.failed_count = 0
        self.finalized_count = 0
        self.rejected_count = 0
        self.error_count = 0

    def execution(self, item: WorkerExecutionDataV1) -> None:
        self.claimed_count += 1
        self.succeeded_count += int(item.succeeded)
        self.failed_count += int(not item.succeeded)
        self.executions.append(item)
        logger.info(
            "worker job job_id=%s run_id=%s stage=%s scope=%s succeeded=%s outcome=%s error=%s",
            item.job_id,
            item.run_id,
            item.stage_key,
            item.scope_key,
            item.succeeded,
            item.outcome,
            item.error,
        )

    def finalized_run(self, run_id: str) -> None:
        self.finalized_count += 1
        self.finalized.append(run_id)
        logger.info("worker finalized run_id=%s", run_id)

    def rejected_run(self, run_id: str, error: str) -> None:
        self.rejected_count += 1
        self.rejected.append(run_id)
        self.error(error)

    def error(self, error: str) -> None:
        self.error_count += 1
        self.errors.append(error)
        logger.warning("worker error=%s", error)

    def result(
        self,
        worker_id: str,
        stopped_reason: Literal["cancelled", "idle", "maximum_jobs", "error"],
    ) -> WorkerDataV1:
        return WorkerDataV1(
            worker_id=worker_id,
            stopped_reason=stopped_reason,
            claimed_count=self.claimed_count,
            succeeded_count=self.succeeded_count,
            failed_count=self.failed_count,
            evidence_limit=self.limit,
            execution_evidence_omitted_count=(self.claimed_count - len(self.executions)),
            finalized_count=self.finalized_count,
            finalized_id_evidence_omitted_count=(self.finalized_count - len(self.finalized)),
            rejected_count=self.rejected_count,
            rejected_id_evidence_omitted_count=(self.rejected_count - len(self.rejected)),
            error_count=self.error_count,
            error_evidence_omitted_count=self.error_count - len(self.errors),
            finalized_run_ids=tuple(self.finalized),
            rejected_run_ids=tuple(self.rejected),
            executions=tuple(self.executions),
            errors=tuple(self.errors),
        )


class LocalProcessingBackend:
    """Thin CLI adapter; all mutations remain owned by domain services."""

    def __init__(self, services: ProcessingServices) -> None:
        self.services = services

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
        results = self.services.catalog.search_sessions(
            SessionSearch(
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
        )
        return SessionSearchDataV1(
            sessions=tuple(
                SessionSearchItemV1(
                    session_id=item.session_id,
                    source_type=item.source_type,
                    state=item.state,
                    created_at=item.created_at,
                    bundle_uri=item.bundle_uri,
                    held=item.held,
                    tags=item.tags,
                    current_run_id=item.current_run_id,
                )
                for item in results
            )
        )

    def storage_admission(self) -> StorageAdmissionDecision:
        usage = self.services.retention.storage_usage()
        result = self.services.retention.run(usage, dry_run=True)
        decision = result.decision
        if not decision.admission_allowed_after_plan:
            reason = (
                "storage is at or above the 80% admission watermark and retention "
                "cannot reach the 65% target"
            )
        elif decision.warning:
            reason = "storage is at or above the 75% warning watermark"
        elif decision.should_run:
            reason = "storage is at or above the 70% retention watermark"
        else:
            reason = None
        return StorageAdmissionDecision(
            allowed=decision.admission_allowed_after_plan,
            used_fraction=usage.fraction,
            warning=decision.warning,
            reason=reason,
        )

    def show_session(self, session_id: str) -> SessionDetailDataV1:
        snapshot = self.services.catalog.presentation_snapshot(session_id)
        if snapshot is None:
            raise CliBackendError(f"capture session is absent: {session_id}", ExitCode.NOT_FOUND)
        analysis = snapshot.analysis
        return SessionDetailDataV1(
            session_id=snapshot.session_id,
            source_type=snapshot.source_type,
            state=snapshot.state,
            created_at=snapshot.created_at,
            bundle_uri=snapshot.bundle_uri,
            manifest_digest=snapshot.manifest_digest,
            attributes=snapshot.attributes,
            tags=snapshot.tags,
            held=snapshot.hold_reason is not None,
            hold_reason=snapshot.hold_reason,
            analysis=(
                None
                if analysis is None
                else AnalysisRunDataV1(
                    run_id=analysis.run_id,
                    pipeline_release_id=analysis.pipeline_release_id,
                    state=analysis.state,
                    created_at=analysis.created_at,
                    started_at=analysis.started_at,
                    sealed_at=analysis.sealed_at,
                    failure=analysis.failure,
                    input_manifest_digest=analysis.input_manifest_digest,
                    manifest_uri=analysis.manifest_uri,
                    manifest_digest=analysis.manifest_digest,
                    is_current=analysis.is_current,
                    jobs=tuple(
                        JobItemDataV1(
                            job_id=job.job_id,
                            stage_key=job.stage_key,
                            scope_key=job.scope_key,
                            state=job.state,
                            outcome=job.outcome,
                        )
                        for job in analysis.jobs
                    ),
                    products=tuple(
                        ProductItemDataV1(
                            product_id=product.product_id,
                            stage_key=product.stage_key,
                            scope_key=product.scope_key,
                            product_kind=product.kind,
                            schema_version=product.schema_version,
                            role=product.role,
                            status=product.status,
                            media_type=product.media_type,
                            logical_uri=product.logical_uri,
                            digest=product.digest,
                            byte_size=product.byte_size,
                            available=product.available,
                            coverage=product.coverage,
                            summary=product.summary,
                        )
                        for product in analysis.products
                    ),
                )
            ),
        )

    def session_paths(self, session_id: str) -> SessionPathsDataV1:
        detail = self.show_session(session_id)
        items: list[PathItemDataV1] = []
        if detail.bundle_uri is not None:
            items.append(
                self._path_item(
                    "recording_bundle",
                    detail.bundle_uri,
                    detail.manifest_digest,
                )
            )
            bundle = self._resolve(detail.bundle_uri)
            manifest_path = None if bundle is None else bundle / "manifest.json"
            items.append(
                PathItemDataV1(
                    role="recording_manifest",
                    logical_uri=f"{detail.bundle_uri}/manifest.json",
                    physical_path=None if manifest_path is None else str(manifest_path),
                    exists=manifest_path is not None and manifest_path.is_file(),
                    digest=detail.manifest_digest,
                )
            )
        if detail.analysis is not None:
            if detail.analysis.manifest_uri is not None:
                items.append(
                    self._path_item(
                        "analysis_manifest",
                        detail.analysis.manifest_uri,
                        detail.analysis.manifest_digest,
                    )
                )
            items.extend(
                self._path_item(
                    f"product:{product.product_kind}:{product.scope_key}",
                    product.logical_uri,
                    product.digest,
                )
                for product in detail.analysis.products
            )
        return SessionPathsDataV1(session_id=session_id, paths=tuple(items))

    def reprocess(self, session_id: str, *, dry_run: bool = False) -> ReprocessDataV1:
        snapshot = self.services.catalog.presentation_snapshot(session_id)
        if snapshot is None:
            raise CliBackendError(f"capture session is absent: {session_id}", ExitCode.NOT_FOUND)
        if snapshot.bundle_uri is None or snapshot.manifest_digest is None:
            raise CliBackendError(
                f"capture session has no locally available raw recording: {session_id}",
                ExitCode.CONFLICT,
            )
        if (
            dry_run
            and snapshot.analysis is not None
            and snapshot.analysis.state
            in {
                "pending",
                "running",
            }
        ):
            raise CliBackendError(
                f"capture session already has an active analysis run: {snapshot.analysis.run_id}",
                ExitCode.CONFLICT,
            )
        try:
            bundle = self.services.recordings.inspect_uri(snapshot.bundle_uri)
            self.services.recordings.verify(bundle)
        except Exception as error:
            raise CliBackendError(
                f"recording verification failed: {type(error).__name__}: {error}",
                ExitCode.UNHEALTHY,
            ) from error
        if bundle.manifest_sha256 != snapshot.manifest_digest:
            raise CliBackendError(
                "catalog and recording manifest digests disagree",
                ExitCode.UNHEALTHY,
            )
        scope_keys = tuple(
            stream.stream_id
            for stream in bundle.manifest.streams
            if stream.captured_sample_count > 0 and stream.chunks
        )
        if not scope_keys:
            raise CliBackendError("recording has no analyzable IQ streams", ExitCode.CONFLICT)
        run_id = f"reprocess-{uuid4().hex}"
        previous = self.services.catalog.current_run_id(session_id)
        if not dry_run:
            try:
                self.services.processing.create_reprocess_run(
                    run_id=run_id,
                    session_id=session_id,
                    pipeline_release_id=self.services.pipeline_release_id,
                    input_manifest_digest=snapshot.manifest_digest,
                    scope_keys=scope_keys,
                )
            except ActiveRunExistsError as error:
                raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        return ReprocessDataV1(
            session_id=session_id,
            run_id=run_id,
            pipeline_release_id=self.services.pipeline_release_id,
            previous_current_run_id=previous,
            queued_scope_keys=scope_keys,
            state="dry_run" if dry_run else "queued",
        )

    def cancel_run(self, run_id: str, *, reason: str) -> CancelRunDataV1:
        try:
            changed = self.services.catalog.cancel_analysis_run(
                run_id=run_id,
                reason=reason,
            )
            snapshot = self.services.catalog.run_seal_snapshot(run_id)
        except CatalogNotFoundError as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        except InvalidStateError as error:
            raise CliBackendError(str(error), ExitCode.CONFLICT) from error
        return CancelRunDataV1(
            run_id=run_id,
            changed=changed,
            reason=reason.strip(),
            cancelled_job_count=sum(job.state == JobState.CANCELLED.value for job in snapshot.jobs),
            succeeded_job_count=sum(job.state == JobState.SUCCEEDED.value for job in snapshot.jobs),
            failed_job_count=sum(job.state == JobState.FAILED.value for job in snapshot.jobs),
            product_count=len(snapshot.products),
        )

    def jobs(self) -> JobsDataV1:
        backlog = self.services.catalog.backlog_snapshot()
        return JobsDataV1(
            queued=backlog.queued,
            running=backlog.running,
            failed=backlog.failed,
            oldest_queued_seconds=backlog.oldest_queued_seconds,
            ready_to_finalize_run_ids=self.services.catalog.ready_run_ids(),
        )

    def pin(self, session_id: str, *, reason: str) -> HoldDataV1:
        if not reason.strip():
            raise CliBackendError("pin reason cannot be empty", ExitCode.INVALID_CONFIGURATION)
        try:
            self.services.holds.add(session_id=session_id, reason=reason, actor="leo-cli")
        except CatalogNotFoundError as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        return HoldDataV1(session_id=session_id, held=True, changed=True, reason=reason)

    def unpin(self, session_id: str) -> HoldDataV1:
        try:
            changed = self.services.holds.release(session_id=session_id)
        except CatalogNotFoundError as error:
            raise CliBackendError(str(error), ExitCode.NOT_FOUND) from error
        return HoldDataV1(session_id=session_id, held=False, changed=changed)

    def import_qnap(
        self,
        manifest_path: Path,
        *,
        copy: bool,
        tags: tuple[str, ...],
    ) -> ImportDataV1:
        if not copy:
            raise CliBackendError(
                "QNAP imports require explicit --copy; source paths remain read-only",
                ExitCode.INVALID_CONFIGURATION,
            )
        if set(tags) != {"TEST"}:
            raise CliBackendError(
                "QNAP imports require exactly the TEST tag",
                ExitCode.INVALID_CONFIGURATION,
            )
        manifest = load_corpus_manifest(manifest_path)
        qnap_root = Path("/mnt/qnap01")
        for fixture in manifest.required_fixtures():
            for artifact in fixture.artifacts:
                resolved = artifact.source_path.resolve(strict=True)
                if resolved == qnap_root or qnap_root not in resolved.parents:
                    raise CliBackendError(
                        f"import-qnap source is outside /mnt/qnap01: {artifact.source_path}",
                        ExitCode.INVALID_CONFIGURATION,
                    )
        results = self.services.importer.materialize_required(manifest)
        ingest_manifest = load_recording_ingest_manifest(
            manifest_path.parent / RECORDING_INGEST_FILENAME
        )
        recordings = self.services.corpus_ingest.ingest_required(
            manifest,
            results,
            ingest_manifest,
        )
        recording_by_fixture = {item.fixture_id: item for item in recordings}
        reconciled = self.reconcile()
        return ImportDataV1(
            corpus_id=manifest.corpus_id,
            source_manifest=str(manifest_path.resolve(strict=True)),
            local_root=str(self.services.importer.local_corpus_root),
            fixtures=tuple(
                ImportFixtureDataV1(
                    fixture_id=result.fixture_id,
                    directory=str(result.directory),
                    status=recording_by_fixture[result.fixture_id].status,
                    session_id=recording_by_fixture[result.fixture_id].session_id,
                    bundle_uri=recording_by_fixture[result.fixture_id].bundle_uri,
                )
                for result in results
            ),
            queued_run_ids=reconciled.queued_run_ids,
            issues=reconciled.issues,
        )

    def retention_status(self) -> RetentionDataV1:
        usage = self.services.retention.storage_usage()
        return _retention_data(self.services.retention.run(usage, dry_run=True), usage, True)

    def retention_run(self, *, dry_run: bool) -> RetentionDataV1:
        usage = self.services.retention.storage_usage()
        return _retention_data(
            self.services.retention.run(usage, dry_run=dry_run),
            usage,
            dry_run,
        )

    def reconcile(self) -> ReconcileDataV1:
        recovery = self.services.retention.recover()
        catalog = self.services.reconciliation.run()
        return self._queue_reconciled(
            catalog,
            restored_purges=recovery.restored,
            discarded_purges=recovery.discarded,
        )

    def reconcile_session(self, session_id: str) -> ReconcileDataV1:
        """Register and queue one newly committed acquisition bundle."""

        return self._queue_reconciled(
            self.services.reconciliation.run_session(session_id),
            restored_purges=(),
            discarded_purges=(),
        )

    def _queue_reconciled(
        self,
        catalog: CatalogReconcileReport,
        *,
        restored_purges: tuple[str, ...],
        discarded_purges: tuple[str, ...],
    ) -> ReconcileDataV1:
        queued: list[str] = []
        issues = list(catalog.issues)
        # Existing rows are repaired above, but only newly registered bundles are
        # eligible for automatic analysis. A release/schema change must never
        # turn reconciliation into an implicit historical backfill.
        for session_id in catalog.registered:
            try:
                run_id = self._ensure_default_run(session_id)
            except Exception as error:
                issues.append(f"{session_id}: {type(error).__name__}: {error}")
            else:
                if run_id is not None:
                    queued.append(run_id)
        return ReconcileDataV1(
            restored_purges=restored_purges,
            discarded_purges=discarded_purges,
            registered_sessions=catalog.registered,
            existing_sessions=catalog.existing,
            queued_run_ids=tuple(queued),
            issues=tuple(issues),
        )

    def worker(
        self,
        *,
        worker_id: str,
        poll_seconds: float,
        maximum_jobs: int | None,
        once: bool,
        cancel: Event,
    ) -> WorkerDataV1:
        if poll_seconds <= 0:
            raise CliBackendError(
                "worker poll interval must be positive",
                ExitCode.INVALID_CONFIGURATION,
            )
        if maximum_jobs is not None and maximum_jobs <= 0:
            raise CliBackendError("maximum jobs must be positive", ExitCode.INVALID_CONFIGURATION)
        evidence = _WorkerEvidence()
        stopped_reason: Literal["cancelled", "idle", "maximum_jobs", "error"] = (
            "idle" if once else "cancelled"
        )
        while not cancel.is_set():
            self._finalize_ready(evidence)
            if maximum_jobs is not None and evidence.claimed_count >= maximum_jobs:
                stopped_reason = "maximum_jobs"
                break
            execution = self.services.processing.run_once(worker_id=worker_id)
            if execution is None:
                if once:
                    stopped_reason = "idle"
                    break
                cancel.wait(poll_seconds)
                continue
            evidence.execution(
                WorkerExecutionDataV1(
                    job_id=execution.job_id,
                    run_id=execution.run_id,
                    stage_key=execution.stage_key,
                    scope_key=execution.scope_key,
                    succeeded=execution.succeeded,
                    outcome=None if execution.outcome is None else execution.outcome.value,
                    error=execution.error,
                )
            )
            self._finalize_one(execution.run_id, evidence)
            if once:
                stopped_reason = "idle"
                break
        if cancel.is_set():
            stopped_reason = "cancelled"
        return evidence.result(worker_id, stopped_reason)

    def _finalize_ready(
        self,
        evidence: _WorkerEvidence,
    ) -> None:
        for run_id in self.services.catalog.ready_run_ids():
            self._finalize_one(run_id, evidence)

    def _ensure_default_run(self, session_id: str) -> str | None:
        if self.services.catalog.current_run_id(session_id) is not None:
            return None
        snapshot = self.services.catalog.presentation_snapshot(session_id)
        if snapshot is None or snapshot.bundle_uri is None or snapshot.manifest_digest is None:
            return None
        bundle = self.services.recordings.inspect_uri(snapshot.bundle_uri)
        if bundle.manifest_sha256 != snapshot.manifest_digest:
            raise ValueError("catalog and bundle manifest digests disagree")
        scope_keys = tuple(
            stream.stream_id
            for stream in bundle.manifest.streams
            if stream.captured_sample_count > 0 and stream.chunks
        )
        if not scope_keys:
            return None
        if {"QUALIFICATION", "CALIBRATION", "ACCEPTANCE"}.intersection(bundle.manifest.tags):
            return None
        run_id = f"capture-{uuid4().hex}"
        try:
            self.services.processing.create_new_capture_run(
                run_id=run_id,
                session_id=session_id,
                pipeline_release_id=self.services.pipeline_release_id,
                input_manifest_digest=snapshot.manifest_digest,
                scope_keys=scope_keys,
            )
        except ActiveRunExistsError:
            return None
        return run_id

    def _finalize_one(
        self,
        run_id: str,
        evidence: _WorkerEvidence,
    ) -> None:
        try:
            self.services.processing.finalize_run(run_id)
        except RunNotReadyError:
            return
        except RunRejectedError as error:
            detail = f"{run_id}: {type(error).__name__}: {error}"
            evidence.rejected_run(run_id, detail)
        except Exception as error:
            # Another worker may have won the seal/promotion race.
            if self.services.catalog.run_state(run_id) is AnalysisRunState.SUCCEEDED:
                evidence.finalized_run(run_id)
            else:
                evidence.error(f"{run_id}: {type(error).__name__}: {error}")
        else:
            evidence.finalized_run(run_id)

    def _path_item(self, role: str, logical_uri: str, digest: str | None) -> PathItemDataV1:
        path = self._resolve(logical_uri)
        return PathItemDataV1(
            role=role,
            logical_uri=logical_uri,
            physical_path=None if path is None else str(path),
            exists=path is not None and path.exists(),
            digest=digest,
        )

    def _resolve(self, logical_uri: str) -> Path | None:
        try:
            return self.services.recordings.resolver.resolve(logical_uri, must_exist=False)
        except (OSError, ValueError):
            return None


def build_processing_backend(settings: ProcessingBackendSettings) -> LocalProcessingBackend:
    for label, root in (
        ("bulk", settings.bulk_root),
        ("qualification", settings.qualification_root),
        ("legacy evidence", settings.legacy_evidence_root),
        ("capture evidence", settings.capture_evidence_root),
        ("scratch", settings.scratch_root),
    ):
        if root is not None:
            _normalized_absolute(root, f"processing {label} root")
    pinned_bulk = PinnedLocalRoot(settings.bulk_root)
    recordings: RecordingStore | None = None
    try:
        recordings = RecordingStore.open_pinned(pinned_bulk)
        artifacts = AnalysisArtifactStore.open_pinned(pinned_bulk)
    except Exception:
        if recordings is not None:
            recordings.close()
        raise
    finally:
        pinned_bulk.close()
    engine = create_catalog_engine(settings.database_url)
    catalog = CatalogRepository(create_session_factory(engine))
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    default_stage_keys = registry.keys
    if settings.qualification_root is not None:
        plans = ImmutableCalibrationPlanStore(
            settings.qualification_root / "frequency-calibration-plans"
        )
        registry.register(
            CalibrationExtractorAnalyzer(ImmutableCalibrationScopeProvider(plans, recordings))
        )
        if settings.legacy_evidence_root is not None and settings.capture_evidence_root is not None:
            plan_root = PinnedLocalRoot(settings.qualification_root)
            try:
                wp11_plans = ImmutableWP11PlanStore(plan_root)
            finally:
                plan_root.close()
            releases = NativeReleaseCalibrationEvidenceAdapter(
                settings.pipeline_release_id,
                current_link=settings.current_release_link,
                deployment_root=settings.deployment_root,
            )
            calibration_outputs = ImmutableCalibrationPromotionStore(
                settings.qualification_root / "frequency-calibration-promotions"
            )
            calibration_resolver = AuthoritativeCalibrationResolver(
                calibration_outputs,
                releases,
                allowed_release_ids=(settings.pipeline_release_id,),
            )
            scopes = PostgresAuthoritativeCalibrationScope(
                catalog,
                recordings,
                PostgresCalibrationCatalogAdapter(catalog, calibration_resolver),
            )
            delegates = WP11ProductionDelegateFactory(
                scopes=scopes,
                legacy=PinnedLegacyOracleAuthority(settings.legacy_evidence_root),
                releases=releases,
                executor=ReleaseLocalNativeEvidenceExecutor(scratch_root=settings.scratch_root),
                recordings=recordings,
                artifacts=artifacts,
            )
            capture_root = PinnedLocalRoot(settings.capture_evidence_root)
            try:
                capture = ImmutableCaptureCampaignAuthority(capture_root)
            finally:
                capture_root.close()
            registry.register(
                DynamicWP11Analyzer(
                    NATIVE_KNOWN_PILOT_EVIDENCE_STAGE,
                    wp11_plans,
                    capture,
                    settings.pipeline_release_id,
                    delegates,
                )
            )
            registry.register(
                DynamicWP11Analyzer(
                    TRUSTED_MATCHED_RECOVERY_STAGE,
                    wp11_plans,
                    capture,
                    settings.pipeline_release_id,
                    delegates,
                )
            )
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)
    release_configuration: dict[str, object] = {
        "stages": configuration,
        "compute_tier": ComputeTier.STANDARD.value,
    }
    graph_document = {"stages": [item.model_dump(mode="json") for item in registry.graph().plan()]}
    graph_digest = sha256_digest(canonical_json_bytes(graph_document))
    environment_digest = sha256_digest(f"leo-tracker:{__version__}".encode())
    loaded_worker_release = None
    if re.fullmatch(r"[0-9a-f]{40}", settings.pipeline_release_id):
        loaded_worker_release = derive_deployed_worker_release(
            registry=registry,
            configuration=release_configuration,
            current_link=settings.current_release_link,
            deployment_root=settings.deployment_root,
            stage_keys=default_stage_keys,
        )
        if loaded_worker_release.authority.pipeline_release_id != settings.pipeline_release_id:
            raise ValueError("configured typed release is not the validated deployed current SHA")
        code_revision = loaded_worker_release.authority.code_revision
        environment_digest = loaded_worker_release.authority.environment_digest
        graph_digest = loaded_worker_release.authority.graph_digest
        executable_digest = loaded_worker_release.authority.executable_digest
    else:
        code_revision = __version__
        executable_digest = environment_digest
    catalog.add_pipeline_release(
        release_id=settings.pipeline_release_id,
        code_revision=code_revision,
        environment_digest=environment_digest,
        graph_digest=graph_digest,
        configuration=release_configuration,
        executable_digest=executable_digest,
    )
    hold_receipts = HoldReceiptStore(settings.bulk_root)
    services = ProcessingServices(
        catalog=catalog,
        recordings=recordings,
        artifacts=artifacts,
        processing=ProcessingService(
            catalog=catalog,
            artifacts=artifacts,
            registry=registry,
            iq_readers=RecordingIqReaderProvider(recordings),
            default_stage_keys=default_stage_keys,
            loaded_worker_release=loaded_worker_release,
        ),
        holds=CatalogHoldService(catalog, hold_receipts),
        retention=CatalogRetentionService(
            catalog,
            recordings,
            hold_receipts,
            PurgeExecutor(settings.bulk_root),
        ),
        reconciliation=CatalogReconciliationService(catalog, recordings, hold_receipts),
        importer=FixtureImporter(settings.corpus_root),
        corpus_ingest=RecordingCorpusIngestService(recordings),
        pipeline_release_id=settings.pipeline_release_id,
    )
    return LocalProcessingBackend(services)


def _retention_data(
    result: RetentionRunResult,
    usage: StorageUsage,
    dry_run: bool,
) -> RetentionDataV1:
    decision = result.decision
    return RetentionDataV1(
        dry_run=dry_run,
        total_bytes=usage.total_bytes,
        used_bytes=usage.used_bytes,
        used_fraction=usage.fraction,
        high_watermark=HIGH_WATERMARK,
        low_watermark=LOW_WATERMARK,
        warning_watermark=WARNING_WATERMARK,
        admission_stop_watermark=ADMISSION_STOP_WATERMARK,
        should_run=decision.should_run,
        warning=decision.warning,
        admission_allowed_after_plan=decision.admission_allowed_after_plan,
        blocked=decision.blocked,
        selected_ids=decision.selected_session_ids,
        selected_bytes=decision.selected_bytes,
        predicted_used_bytes=decision.predicted_used_bytes,
        target_used_bytes=decision.target_used_bytes,
        committed_ids=result.committed,
        failures=result.failures,
    )
