"""Leased analyzer execution, immutable run sealing, and atomic promotion."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from leo.artifacts.store import ArtifactOutputSink
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
    RawIntegrityAttestationRegistration,
    RunExecutionInfo,
    RunSealSnapshot,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_json_bytes
from leo.pipeline import (
    AnalysisContext,
    Analyzer,
    AnalyzerRegistry,
    ExpandedRunPlanV1,
    IqReader,
    ProductSpec,
    PublishedProduct,
    StageOutcome,
    StageResult,
    compile_standard_run_plan,
)
from leo.processing.adapters import CatalogArtifactProductReader, IqReaderProvider
from leo.processing.authority import LoadedWorkerRelease

FailureInjector = Callable[[str], None]
AUTOMATIC_JOB_PRIORITY = 0
REPROCESS_JOB_PRIORITY = 100
_DEFAULT_OUTPUT_LIMITS = {
    "streaming": 512 * 1024 * 1024,
    "cpu": 1024 * 1024 * 1024,
    "memory": 2 * 1024 * 1024 * 1024,
    "heavy": 4 * 1024 * 1024 * 1024,
}
_DEFAULT_WALL_LIMITS = {"streaming": 600.0, "cpu": 600.0, "memory": 1200.0, "heavy": 1800.0}


class ProcessingError(RuntimeError):
    pass


class RunNotReadyError(ProcessingError):
    pass


class RunRejectedError(ProcessingError):
    pass


class WorkerIncompatibleError(ProcessingError):
    """Operational release mismatch; it is not a scientific job attempt."""


class _NoIqReader:
    """Reducer sentinel: any attempted IQ access is a contract violation."""

    @property
    def sample_rate_hz(self) -> int:
        raise RunRejectedError("product-only job attempted to read IQ metadata")

    @property
    def center_frequency_hz(self) -> int:
        raise RunRejectedError("product-only job attempted to read IQ metadata")

    @property
    def sample_count(self) -> int:
        raise RunRejectedError("product-only job attempted to read IQ metadata")

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        raise RunRejectedError("product-only job attempted to read IQ metadata")

    def iter_blocks(self, *, block_samples: int) -> Iterable[Any]:
        del block_samples
        raise RunRejectedError("product-only job attempted to read IQ")


class _BoundedOutputSink:
    """Reject oversized stage output before any bytes reach artifact storage."""

    def __init__(self, delegate: ArtifactOutputSink, *, maximum_bytes: int) -> None:
        if maximum_bytes <= 0:
            raise ValueError("output boundary must be positive")
        self._delegate = delegate
        self._maximum_bytes = maximum_bytes
        self._reserved_bytes = 0

    @property
    def publications(self) -> tuple[ProductPublication, ...]:
        return self._delegate.publications

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        self._reserve(len(canonical_json_bytes(document)))
        return self._delegate.publish_json(product, document)

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        self._reserve(len(payload))
        return self._delegate.publish_bytes(product, payload)

    def _reserve(self, byte_size: int) -> None:
        if self._reserved_bytes + byte_size > self._maximum_bytes:
            raise RunRejectedError("stage exceeded its output-byte boundary")
        self._reserved_bytes += byte_size


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
        default_stage_keys: Iterable[str] | None = None,
        worker_authority: WorkerReleaseAuthority | None = None,
        loaded_worker_release: LoadedWorkerRelease | None = None,
        worker_resource_classes: tuple[str, ...] | None = None,
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
        self._default_stage_keys = None if default_stage_keys is None else tuple(default_stage_keys)
        if worker_authority is not None and loaded_worker_release is not None:
            raise ValueError("choose either test authority or loaded runtime authority")
        self._worker_authority = (
            worker_authority if loaded_worker_release is None else loaded_worker_release.authority
        )
        self._worker_resource_classes = worker_resource_classes
        self._output_byte_limits = _DEFAULT_OUTPUT_LIMITS
        self._wall_time_limits_seconds = _DEFAULT_WALL_LIMITS

    @property
    def default_stage_keys(self) -> tuple[str, ...] | None:
        return self._default_stage_keys

    def close(self) -> None:
        close = getattr(self.iq_readers, "close", None)
        if close is not None:
            close()

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
        lease = self.catalog.claim_job(
            worker_id=worker_id,
            lease_for=self.lease_for,
            authority=self._worker_authority,
            resource_classes=self._worker_resource_classes,
        )
        if lease is None:
            if self._worker_authority is not None:
                self.catalog.record_pending_worker_incompatibility(
                    worker_id=worker_id, authority=self._worker_authority
                )
            return None
        heartbeat = _LeaseHeartbeat(
            self.catalog,
            lease,
            lease_for=self.lease_for,
            interval=self.heartbeat_interval,
        )
        try:
            self._inject("execution:after_claim")
            heartbeat.start()
            execution = self.catalog.run_execution_info(lease.run_id)
            if self._worker_authority is not None:
                _require_execution_authority(execution, self._worker_authority)
            analyzer = self.registry.get(lease.stage_key)
            context = AnalysisContext(
                session_id=execution.session_id,
                run_id=execution.run_id,
                pipeline_release=execution.pipeline_release_id,
                scope_key=lease.scope_key,
                scope=lease.scope,
                job_node_id=lease.node_id,
                stage_config=_stage_config(
                    execution.pipeline_configuration,
                    lease.stage_key,
                ),
            )
            reader: IqReader
            if lease.iq_access == "none":
                reader = _NoIqReader()
            elif lease.scope is not None:
                reader = self.iq_readers.open_scope(execution, lease.scope)
            else:
                reader = self.iq_readers.open(execution, lease.scope_key)
            products = CatalogArtifactProductReader(
                self.catalog,
                self.artifacts,
                run_id=lease.run_id,
                scope_key=lease.scope_key,
                job_id=lease.job_id if lease.node_id is not None else None,
            )
            output_limit = self._output_byte_limits.get(lease.resource_class)
            if output_limit is None:
                raise RunRejectedError(f"unknown resource class: {lease.resource_class}")
            outputs = _BoundedOutputSink(
                self.artifacts.output_sink(
                    session_id=execution.session_id,
                    run_id=lease.run_id,
                    stage_key=lease.stage_key,
                    scope_key=lease.scope_key,
                ),
                maximum_bytes=output_limit,
            )
            started = time.monotonic()
            result = analyzer.analyze(context, reader, products, outputs)
            elapsed = time.monotonic() - started
            _validate_result(analyzer, result, outputs.publications)
            wall_limit = self._wall_time_limits_seconds.get(lease.resource_class)
            if wall_limit is None or elapsed > wall_limit:
                raise RunRejectedError(f"stage exceeded {lease.resource_class} wall-time boundary")
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
                        input_product_ids=products.consumed_product_ids,
                        scope=lease.scope,
                    )
                )
                self._inject("execution:after_product_register")
            heartbeat.ensure_owned()
        except WorkerIncompatibleError as error:
            heartbeat.stop()
            with suppress(LeaseLostError):
                assert self._worker_authority is not None
                self.catalog.defer_incompatible_job(
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    authority=self._worker_authority,
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

    def create_expanded_run(
        self,
        *,
        run_id: str,
        plan: ExpandedRunPlanV1,
        trigger: Literal["new_capture", "reprocess"] = "reprocess",
        promotion_policy: PromotionPolicy | str = PromotionPolicy.CURRENT,
    ) -> None:
        """Persist a validated typed plan only after full raw verification succeeded."""

        identity = self.catalog.capture_recording_identity(plan.session_id)
        if identity.manifest_digest != plan.manifest_digest:
            raise ValueError("expanded plan manifest disagrees with the catalog")
        integrity = self.iq_readers.verify_integrity(identity)
        if (
            integrity.session_id != plan.session_id
            or integrity.manifest_digest != plan.manifest_digest
        ):
            raise ValueError("integrity authority returned evidence for different raw bytes")
        expected_plan = compile_standard_run_plan(
            self.iq_readers.verified_manifest(integrity.attestation_digest),
            manifest_digest=plan.manifest_digest,
            pipeline_release_id=plan.pipeline_release_id,
        )
        if plan != expected_plan:
            raise ValueError("expanded plan differs from the manifest-authoritative Standard DAG")
        dependencies: dict[str, list[str]] = {job.node_id: [] for job in plan.jobs}
        for edge in plan.edges:
            dependencies[edge.job_node_id].append(edge.depends_on_job_node_id)
        priority = REPROCESS_JOB_PRIORITY if trigger == "reprocess" else AUTOMATIC_JOB_PRIORITY
        jobs = tuple(
            JobDefinition(
                node_id=job.node_id,
                stage_key=job.stage_key,
                scope=job.scope,
                depends_on_node_ids=tuple(sorted(dependencies[job.node_id])),
                priority=priority,
                resource_class=job.resource_class,
                iq_access=job.iq_access.value,
            )
            for job in plan.jobs
        )
        self.catalog.register_raw_integrity_attestation(
            RawIntegrityAttestationRegistration(
                session_id=integrity.session_id,
                manifest_digest=integrity.manifest_digest,
                attestation_digest=integrity.attestation_digest,
                document=integrity.model_dump(mode="json"),
                verified_at=(
                    datetime.fromtimestamp(
                        integrity.verified_utc_ns // 1_000_000_000,
                        tz=UTC,
                    )
                    + timedelta(microseconds=(integrity.verified_utc_ns % 1_000_000_000) // 1_000)
                ),
            )
        )
        self.catalog.create_analysis_run(
            run_id=run_id,
            session_id=plan.session_id,
            pipeline_release_id=plan.pipeline_release_id,
            input_manifest_digest=plan.manifest_digest,
            jobs=jobs,
            trigger=trigger,
            promotion_policy=promotion_policy,
            expanded_plan_digest=plan.plan_digest,
            raw_integrity_attestation_digest=integrity.attestation_digest,
            require_integrity_prerequisite=True,
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
        selected_stage_keys = self._default_stage_keys if stage_keys is None else tuple(stage_keys)
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


def _require_execution_authority(
    execution: RunExecutionInfo, authority: WorkerReleaseAuthority
) -> None:
    expected = (
        authority.pipeline_release_id,
        authority.code_revision,
        authority.environment_digest,
        authority.graph_digest,
        authority.configuration_digest,
        authority.executable_digest,
    )
    actual = (
        execution.pipeline_release_id,
        execution.code_revision,
        execution.environment_digest,
        execution.graph_digest,
        execution.configuration_digest,
        execution.executable_digest,
    )
    if actual != expected:
        raise WorkerIncompatibleError("claimed job release authority changed before execution")


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
