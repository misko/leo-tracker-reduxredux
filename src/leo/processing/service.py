"""Leased analyzer execution, immutable run sealing, and atomic promotion."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast

from pydantic import JsonValue

from leo.artifacts import (
    AnalysisArtifactStore,
    AnalysisJobReceiptV1,
    AnalysisProductReceiptV1,
    AnalysisRunManifestV1,
    ProductPublication,
    PublishedRunManifest,
)
from leo.catalog import (
    AnalysisRunState,
    CatalogRepository,
    CurrentSummary,
    JobDefinition,
    JobLease,
    JobState,
    LeaseLostError,
    ProductRegistration,
    PromotionPolicy,
    RunSealSnapshot,
)
from leo.pipeline import AnalysisContext, Analyzer, AnalyzerRegistry, StageOutcome, StageResult
from leo.processing.adapters import CatalogArtifactProductReader, IqReaderProvider

FailureInjector = Callable[[str], None]
AUTOMATIC_JOB_PRIORITY = 0
REPROCESS_JOB_PRIORITY = 100


class ProcessingError(RuntimeError):
    pass


class RunNotReadyError(ProcessingError):
    pass


class RunRejectedError(ProcessingError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerExecution:
    job_id: int
    run_id: str
    stage_key: str
    scope_key: str
    succeeded: bool
    outcome: StageOutcome | None
    error: str | None


class _LeaseHeartbeat:
    def __init__(
        self,
        catalog: CatalogRepository,
        lease: JobLease,
        *,
        lease_for: timedelta,
        interval: timedelta,
    ) -> None:
        if interval <= timedelta(0) or interval >= lease_for:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")
        self._catalog = catalog
        self._lease = lease
        self._lease_for = lease_for
        self._interval_seconds = interval.total_seconds()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"leo-heartbeat-{lease.job_id}",
            daemon=True,
        )
        self._thread_started = False
        self._error: BaseException | None = None

    def start(self) -> None:
        # Renew synchronously before handing responsibility to the scheduler.  This
        # closes the small but real gap between a successful claim and the first
        # background wake-up on a busy worker host.
        self._catalog.heartbeat_job(
            job_id=self._lease.job_id,
            worker_id=self._lease.worker_id,
            lease_for=self._lease_for,
        )
        self._thread.start()
        self._thread_started = True

    def stop(self) -> None:
        self._stop.set()
        if self._thread_started:
            self._thread.join()

    def ensure_owned(self) -> None:
        if self._error is not None:
            raise LeaseLostError(
                f"heartbeat lost lease for job {self._lease.job_id}: {self._error}"
            ) from self._error

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._catalog.heartbeat_job(
                    job_id=self._lease.job_id,
                    worker_id=self._lease.worker_id,
                    lease_for=self._lease_for,
                )
            except BaseException as error:
                self._error = error
                self._stop.set()
                return


class ProcessingService:
    def __init__(
        self,
        *,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        registry: AnalyzerRegistry,
        iq_readers: IqReaderProvider,
        lease_for: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta = timedelta(minutes=1),
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if heartbeat_interval <= timedelta(0) or heartbeat_interval >= lease_for:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")
        self.catalog = catalog
        self.artifacts = artifacts
        self.registry = registry
        self.iq_readers = iq_readers
        self.lease_for = lease_for
        self.heartbeat_interval = heartbeat_interval
        self._failure_injector = failure_injector

    def create_new_capture_run(
        self,
        *,
        run_id: str,
        session_id: str,
        pipeline_release_id: str,
        input_manifest_digest: str,
        scope_keys: Iterable[str],
        promotion_policy: PromotionPolicy | str = PromotionPolicy.CURRENT,
        stage_keys: Iterable[str] | None = None,
    ) -> None:
        self._create_run(
            run_id=run_id,
            session_id=session_id,
            pipeline_release_id=pipeline_release_id,
            input_manifest_digest=input_manifest_digest,
            scope_keys=scope_keys,
            trigger="new_capture",
            promotion_policy=promotion_policy,
            stage_keys=stage_keys,
        )

    def create_reprocess_run(
        self,
        *,
        run_id: str,
        session_id: str,
        pipeline_release_id: str,
        input_manifest_digest: str,
        scope_keys: Iterable[str],
        promotion_policy: PromotionPolicy | str = PromotionPolicy.CURRENT,
        stage_keys: Iterable[str] | None = None,
    ) -> None:
        self._create_run(
            run_id=run_id,
            session_id=session_id,
            pipeline_release_id=pipeline_release_id,
            input_manifest_digest=input_manifest_digest,
            scope_keys=scope_keys,
            trigger="reprocess",
            promotion_policy=promotion_policy,
            stage_keys=stage_keys,
        )

    def run_once(self, *, worker_id: str) -> WorkerExecution | None:
        lease = self.catalog.claim_job(worker_id=worker_id, lease_for=self.lease_for)
        if lease is None:
            return None
        heartbeat = _LeaseHeartbeat(
            self.catalog,
            lease,
            lease_for=self.lease_for,
            interval=self.heartbeat_interval,
        )
        try:
            heartbeat.start()
            execution = self.catalog.run_execution_info(lease.run_id)
            analyzer = self.registry.get(lease.stage_key)
            context = AnalysisContext(
                session_id=execution.session_id,
                run_id=execution.run_id,
                pipeline_release=execution.pipeline_release_id,
                scope_key=lease.scope_key,
                stage_config=_stage_config(
                    execution.pipeline_configuration,
                    lease.stage_key,
                ),
            )
            reader = self.iq_readers.open(execution, lease.scope_key)
            products = CatalogArtifactProductReader(
                self.catalog,
                self.artifacts,
                run_id=lease.run_id,
                scope_key=lease.scope_key,
            )
            outputs = self.artifacts.output_sink(
                session_id=execution.session_id,
                run_id=lease.run_id,
                stage_key=lease.stage_key,
                scope_key=lease.scope_key,
            )
            result = analyzer.analyze(context, reader, products, outputs)
            _validate_result(analyzer, result, outputs.publications)
            heartbeat.ensure_owned()
            self._inject("execution:after_analyze")

            coverage = _coverage(result)
            for publication in outputs.publications:
                self._inject("execution:before_product_register")
                published = publication.published
                self.catalog.register_product(
                    ProductRegistration(
                        run_id=lease.run_id,
                        stage_key=lease.stage_key,
                        scope_key=lease.scope_key,
                        kind=published.product.kind,
                        schema_version=published.product.schema_version,
                        role=published.product.role.value,
                        status=result.outcome.value,
                        media_type=published.product.media_type,
                        logical_uri=published.logical_uri,
                        digest=published.digest,
                        byte_size=published.byte_size,
                        coverage=coverage,
                        summary=result.summary,
                    )
                )
                self._inject("execution:after_product_register")
            heartbeat.ensure_owned()
        except Exception as error:
            heartbeat.stop()
            with suppress(LeaseLostError):
                self.catalog.fail_job(
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    error=f"{type(error).__name__}: {error}",
                    retryable=True,
                )
            return WorkerExecution(
                job_id=lease.job_id,
                run_id=lease.run_id,
                stage_key=lease.stage_key,
                scope_key=lease.scope_key,
                succeeded=False,
                outcome=None,
                error=f"{type(error).__name__}: {error}",
            )

        heartbeat.stop()
        try:
            heartbeat.ensure_owned()
            self._inject("execution:before_job_complete")
            self.catalog.complete_job(
                job_id=lease.job_id,
                worker_id=lease.worker_id,
                outcome=result.outcome.value,
            )
        except Exception as error:
            with suppress(LeaseLostError):
                self.catalog.fail_job(
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    error=f"{type(error).__name__}: {error}",
                    retryable=True,
                )
            return WorkerExecution(
                job_id=lease.job_id,
                run_id=lease.run_id,
                stage_key=lease.stage_key,
                scope_key=lease.scope_key,
                succeeded=False,
                outcome=None,
                error=f"{type(error).__name__}: {error}",
            )
        return WorkerExecution(
            job_id=lease.job_id,
            run_id=lease.run_id,
            stage_key=lease.stage_key,
            scope_key=lease.scope_key,
            succeeded=True,
            outcome=result.outcome,
            error=None,
        )

    def finalize_run(self, run_id: str) -> PublishedRunManifest:
        snapshot = self.catalog.run_seal_snapshot(run_id)
        failed = [
            job
            for job in snapshot.jobs
            if job.state in {JobState.FAILED.value, JobState.CANCELLED.value}
        ]
        if failed:
            if self.catalog.run_state(run_id) in {
                AnalysisRunState.PENDING,
                AnalysisRunState.RUNNING,
            }:
                self.catalog.fail_analysis_run(
                    run_id=run_id,
                    failure=f"{len(failed)} processing jobs failed or were cancelled",
                )
            raise RunRejectedError(f"analysis run has {len(failed)} failed or cancelled jobs")
        unfinished = [job for job in snapshot.jobs if job.state != JobState.SUCCEEDED.value]
        if unfinished:
            raise RunNotReadyError(f"analysis run has {len(unfinished)} unfinished jobs")
        self._validate_terminal_outcomes(snapshot)

        manifest = _manifest_from_snapshot(snapshot)
        published = self.artifacts.seal_run(manifest)
        self._inject("execution:after_manifest_publish")
        summary = _current_summary(snapshot, self.artifacts)
        self.catalog.seal_and_promote(
            run_id=run_id,
            manifest_uri=published.logical_uri,
            manifest_digest=published.digest,
            summary=summary,
        )
        return published

    def _create_run(
        self,
        *,
        run_id: str,
        session_id: str,
        pipeline_release_id: str,
        input_manifest_digest: str,
        scope_keys: Iterable[str],
        trigger: str,
        promotion_policy: PromotionPolicy | str,
        stage_keys: Iterable[str] | None,
    ) -> None:
        scopes = tuple(sorted(set(scope_keys)))
        if not scopes:
            raise ValueError("analysis run requires at least one IQ scope")
        selected_stage_keys = None if stage_keys is None else tuple(stage_keys)
        plan = self.registry.graph(selected_stage_keys).plan()
        if not plan:
            raise ValueError("analysis run requires at least one pipeline stage")
        jobs = tuple(
            JobDefinition(
                stage_key=stage.key,
                scope_key=scope,
                dependencies=stage.dependencies,
                priority=(
                    REPROCESS_JOB_PRIORITY if trigger == "reprocess" else AUTOMATIC_JOB_PRIORITY
                ),
            )
            for scope in scopes
            for stage in plan
        )
        self.catalog.create_analysis_run(
            run_id=run_id,
            session_id=session_id,
            pipeline_release_id=pipeline_release_id,
            input_manifest_digest=input_manifest_digest,
            jobs=jobs,
            trigger=trigger,
            promotion_policy=promotion_policy,
        )

    def _validate_terminal_outcomes(self, snapshot: RunSealSnapshot) -> None:
        for job in snapshot.jobs:
            analyzer = self.registry.get(job.stage_key)
            if job.outcome is None:
                raise RunRejectedError(f"successful job has no outcome: {job.job_id}")
            try:
                outcome = StageOutcome(job.outcome)
            except ValueError as error:
                raise RunRejectedError(
                    f"job {job.job_id} has unknown semantic outcome: {job.outcome}"
                ) from error
            if outcome not in analyzer.spec.accepted_outcomes:
                raise RunRejectedError(
                    f"stage {job.stage_key} does not accept terminal outcome {outcome.value}"
                )

    def _inject(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)


def _stage_config(configuration: dict[str, object], stage_key: str) -> dict[str, JsonValue]:
    stages = configuration.get("stages", configuration)
    if not isinstance(stages, dict):
        raise ValueError("pipeline release configuration stages must be an object")
    value = stages.get(stage_key, {})
    if not isinstance(value, dict):
        raise ValueError(f"pipeline stage configuration must be an object: {stage_key}")
    return cast(dict[str, JsonValue], value)


def _validate_result(
    analyzer: Analyzer,
    result: StageResult,
    publications: tuple[ProductPublication, ...],
) -> None:
    if result.outcome not in analyzer.spec.accepted_outcomes:
        raise RunRejectedError(
            f"stage {analyzer.spec.key} returned unaccepted outcome {result.outcome.value}"
        )
    declared = {(product.kind, product.schema_version) for product in analyzer.spec.output_products}
    returned = {
        (product.product.kind, product.product.schema_version) for product in result.products
    }
    published = {
        (
            publication.published.product.kind,
            publication.published.product.schema_version,
        )
        for publication in publications
    }
    if returned != published or published != declared:
        raise RunRejectedError(
            f"stage {analyzer.spec.key} products do not match its declared output contract"
        )


def _coverage(result: StageResult) -> float | None:
    value = result.summary.get("coverage_fraction")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if 0.0 <= numeric <= 1.0 else None


def _manifest_from_snapshot(snapshot: RunSealSnapshot) -> AnalysisRunManifestV1:
    return AnalysisRunManifestV1(
        session_id=snapshot.execution.session_id,
        run_id=snapshot.execution.run_id,
        pipeline_release_id=snapshot.execution.pipeline_release_id,
        input_manifest_digest=snapshot.execution.input_manifest_digest,
        trigger=snapshot.execution.trigger,
        jobs=tuple(
            AnalysisJobReceiptV1(
                job_id=job.job_id,
                stage_key=job.stage_key,
                scope_key=job.scope_key,
                outcome=job.outcome or "",
            )
            for job in sorted(snapshot.jobs, key=lambda item: (item.stage_key, item.scope_key))
        ),
        products=tuple(
            AnalysisProductReceiptV1(
                product_id=product.product_id,
                stage_key=product.stage_key,
                scope_key=product.scope_key,
                kind=product.kind,
                product_schema_version=product.schema_version,
                role=cast(Literal["scientific", "presentation"], product.role),
                status=product.status,
                media_type=product.media_type,
                logical_uri=product.logical_uri,
                digest=product.digest,
                byte_size=product.byte_size,
                coverage=product.coverage,
            )
            for product in snapshot.products
        ),
    )


def _current_summary(
    snapshot: RunSealSnapshot,
    artifacts: AnalysisArtifactStore,
) -> CurrentSummary:
    linear_powers: list[float] = []
    qam_values: list[float] = []
    cfo_values: list[float] = []
    doppler_values: list[float] = []
    candidate_counts: list[int] = []
    whole_dwell_details: dict[str, Any] = {}
    coverages = [product.coverage for product in snapshot.products if product.coverage is not None]
    for product in snapshot.products:
        if product.kind != "power.summary":
            if product.kind.endswith(".presentation"):
                summary = product.summary
                _append_number(qam_values, summary.get("best_qam_accuracy"))
                _append_number(cfo_values, summary.get("best_cfo_hz"))
                _append_number(doppler_values, summary.get("doppler_slope_hz_s"))
                candidate = summary.get("candidate_count")
                if (
                    isinstance(candidate, int)
                    and not isinstance(candidate, bool)
                    and candidate >= 0
                ):
                    candidate_counts.append(candidate)
                for key in ("compute_tier", "scientific_confidence"):
                    value = summary.get(key)
                    if isinstance(value, str):
                        whole_dwell_details[key] = value
            continue
        document = artifacts.read_json(product.logical_uri, product.digest)
        receivers = document.get("receivers")
        if isinstance(receivers, list):
            for receiver in receivers:
                if not isinstance(receiver, dict):
                    continue
                value = receiver.get("mean_power_full_scale_squared")
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    linear_powers.append(float(value))
    mean_power_dbfs = None
    if linear_powers:
        linear_mean = sum(linear_powers) / len(linear_powers)
        if linear_mean > 0:
            mean_power_dbfs = 10.0 * math.log10(linear_mean)
    return CurrentSummary(
        mean_power_dbfs=mean_power_dbfs,
        best_qam_accuracy=max(qam_values, default=None),
        best_cfo_hz=max(cfo_values, default=None),
        doppler_slope_hz_s=(doppler_values[0] if doppler_values else None),
        candidate_count=max(candidate_counts, default=None),
        coverage=min(coverages) if coverages else None,
        details={
            **whole_dwell_details,
            "stage_outcomes": {
                f"{job.stage_key}@{job.scope_key}": job.outcome for job in snapshot.jobs
            },
        },
    )


def _append_number(values: list[float], value: object) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            values.append(numeric)
