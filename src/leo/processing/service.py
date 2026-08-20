"""Leased analyzer execution, immutable run sealing, and atomic promotion."""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import signal
import stat
import tempfile
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import JsonValue

from leo.artifacts import (
    AnalysisArtifactStore,
    AnalysisJobReceiptV1,
    AnalysisProductReceiptV1,
    AnalysisRunManifestV2,
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
    RunSubjectBindingRegistration,
    StageResultCommit,
    WorkerReleaseAuthority,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.recording import RecordingManifestV1
from leo.contracts.standard_pipeline import (
    PairTimingEvidenceV1,
    StandardPairInputBindV2,
    StandardPathInputBindV3,
    StreamTimingEvidenceV1,
    resolve_manifest_starlink_tuning,
)
from leo.pipeline import (
    AnalysisContext,
    Analyzer,
    AnalyzerRegistry,
    ExpandedRunPlanV1,
    IqReader,
    ProductSpec,
    PublishedProduct,
    RawIntegrityAttestationV1,
    StageOutcome,
    StageResult,
    compile_standard_run_plan,
)
from leo.pipeline.topology import compile_scope_inventory
from leo.processing.adapters import CatalogArtifactProductReader, IqReaderProvider
from leo.processing.authority import LoadedWorkerRelease
from leo.storage import PinnedLocalRoot

FailureInjector = Callable[[str], None]
AUTOMATIC_JOB_PRIORITY = 0
REPROCESS_JOB_PRIORITY = 100
RESEARCH_JOB_PRIORITY = -100
_DEFAULT_OUTPUT_LIMITS = {
    "streaming": 512 * 1024 * 1024,
    "cpu": 1024 * 1024 * 1024,
    "memory": 2 * 1024 * 1024 * 1024,
    "heavy": 4 * 1024 * 1024 * 1024,
}
_DEFAULT_WALL_LIMITS = {"streaming": 600.0, "cpu": 600.0, "memory": 1200.0, "heavy": 1800.0}
_PROCESS_TERMINATION_GRACE_SECONDS = 2.0
_MAX_ISOLATED_PRODUCT_BYTES = 64 * 1024 * 1024


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

    def __init__(
        self,
        delegate: ArtifactOutputSink,
        *,
        maximum_bytes: int,
        before_publish: Callable[[], None] | None = None,
    ) -> None:
        if maximum_bytes <= 0:
            raise ValueError("output boundary must be positive")
        self._delegate = delegate
        self._maximum_bytes = maximum_bytes
        self._reserved_bytes = 0
        self._before_publish = before_publish

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
        if self._before_publish is not None:
            self._before_publish()
        if self._reserved_bytes + byte_size > self._maximum_bytes:
            raise RunRejectedError("stage exceeded its output-byte boundary")
        self._reserved_bytes += byte_size


@dataclass(frozen=True, slots=True)
class _StagedPublication:
    publication: ProductPublication
    file_name: str
    is_json: bool


class _IsolatedOutputSink:
    """Write child output only to a private retained directory until acceptance."""

    _MAX_PRODUCTS = 256

    def __init__(
        self,
        directory_fd: int,
        *,
        stage_key: str,
        scope_key: str,
        maximum_bytes: int,
        before_stage: Callable[[], None],
    ) -> None:
        self._directory_fd = directory_fd
        self._stage_key = stage_key
        self._scope_key = scope_key
        self._maximum_bytes = maximum_bytes
        self._before_stage = before_stage
        self._reserved_bytes = 0
        self._publications: list[_StagedPublication] = []

    @property
    def publications(self) -> tuple[_StagedPublication, ...]:
        return tuple(self._publications)

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        return self._stage(product, canonical_json_bytes(document), is_json=True)

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        return self._stage(product, payload, is_json=False)

    def _stage(self, product: ProductSpec, payload: bytes, *, is_json: bool) -> PublishedProduct:
        self._before_stage()
        identity = (product.kind, product.schema_version)
        if any(
            (
                item.publication.published.product.kind,
                item.publication.published.product.schema_version,
            )
            == identity
            for item in self._publications
        ):
            raise RunRejectedError(f"job staged product more than once: {identity}")
        if len(self._publications) >= self._MAX_PRODUCTS:
            raise RunRejectedError("stage exceeded its product-count boundary")
        if not payload or len(payload) > _MAX_ISOLATED_PRODUCT_BYTES:
            raise RunRejectedError("stage product is empty or exceeds 64 MiB")
        if self._reserved_bytes + len(payload) > self._maximum_bytes:
            raise RunRejectedError("stage exceeded its output-byte boundary")
        index = len(self._publications)
        file_name = f"product-{index:03d}.staged"
        descriptor = os.open(
            file_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=self._directory_fd,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as target:
                target.write(payload)
                target.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._reserved_bytes += len(payload)
        published = PublishedProduct(
            product=product,
            logical_uri=f"staged://{file_name}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )
        self._publications.append(
            _StagedPublication(
                publication=ProductPublication(
                    stage_key=self._stage_key,
                    scope_key=self._scope_key,
                    published=published,
                ),
                file_name=file_name,
                is_json=is_json,
            )
        )
        return published


class _LocalStagingDirectory:
    """One flat private directory anchored to literal local ``/tmp``.

    TMPDIR is deliberately ignored. Cleanup uses retained directory descriptors
    and never recursively traverses a replacement path.
    """

    def __init__(self) -> None:
        self._parent = PinnedLocalRoot(Path("/tmp"))
        self._name = ""
        self._directory: PinnedLocalRoot | None = None
        try:
            created = Path(
                tempfile.mkdtemp(
                    prefix="leo-analyzer-output-",
                    dir=self._parent.io_root,
                )
            )
            self._name = created.name
            self._directory = self._parent.child(self._name)
        except Exception:
            if self._name:
                with suppress(OSError):
                    os.rmdir(self._name, dir_fd=self._parent.fileno())
            self._parent.close()
            raise

    def __enter__(self) -> PinnedLocalRoot:
        if self._directory is None:
            raise RuntimeError("isolated staging directory is unavailable")
        return self._directory

    def __exit__(self, *_exc: object) -> None:
        directory = self._directory
        self._directory = None
        if directory is not None:
            try:
                for name in os.listdir(directory.fileno()):
                    if name in {"", ".", ".."} or "/" in name:
                        continue
                    try:
                        metadata = os.stat(name, dir_fd=directory.fileno(), follow_symlinks=False)
                        if not stat.S_ISDIR(metadata.st_mode):
                            os.unlink(name, dir_fd=directory.fileno())
                    except FileNotFoundError:
                        pass
            finally:
                directory.close()
        try:
            os.rmdir(self._name, dir_fd=self._parent.fileno())
        except OSError:
            # A replaced name is never traversed or recursively removed. The
            # retained original was emptied through its descriptor above.
            pass
        finally:
            self._parent.close()


def _materialize_staged_publications(
    staged: tuple[_StagedPublication, ...],
    directory: PinnedLocalRoot,
    outputs: _BoundedOutputSink,
) -> tuple[ProductPublication, ...]:
    for item in staged:
        expected = item.publication.published
        descriptor = os.open(
            item.file_name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory.fileno(),
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected.byte_size:
                raise RunRejectedError("isolated stage output identity changed before publication")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                payload = source.read(expected.byte_size + 1)
        finally:
            os.close(descriptor)
        if len(payload) != expected.byte_size or sha256_digest(payload) != expected.digest:
            raise RunRejectedError("isolated stage output digest changed before publication")
        if item.is_json:
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise RunRejectedError("isolated JSON product is not an object")
            outputs.publish_json(expected.product, cast(dict[str, JsonValue], document))
        else:
            outputs.publish_bytes(expected.product, payload)
    return outputs.publications


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
        self._next_renewal = time.monotonic() + self._interval_seconds
        self._renew_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"leo-heartbeat-{lease.job_id}",
            daemon=True,
        )
        self._thread_started = False
        self._error: BaseException | None = None

    def start(self) -> None:
        # The claim transaction already created a complete lease. The first
        # renewal is due only after one heartbeat interval.
        self._thread.start()
        self._thread_started = True

    def renew(self) -> None:
        with self._renew_lock:
            self._renew_locked()

    def renew_if_due(self) -> bool:
        with self._renew_lock:
            if time.monotonic() < self._next_renewal:
                return False
            self._renew_locked()
            return True

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
        while True:
            with self._renew_lock:
                wait_for = max(0.0, self._next_renewal - time.monotonic())
            if self._stop.wait(wait_for):
                return
            try:
                self.renew_if_due()
            except BaseException as error:
                self._error = error
                self._stop.set()
                return

    def _renew_locked(self) -> None:
        self._catalog.heartbeat_job(
            job_id=self._lease.job_id,
            worker_id=self._lease.worker_id,
            lease_for=self._lease_for,
        )
        self._next_renewal = time.monotonic() + self._interval_seconds


def _isolated_analyzer_entry(
    sender: Any,
    analyzer: Analyzer,
    context: AnalysisContext,
    reader: IqReader,
    products: CatalogArtifactProductReader,
    outputs: _IsolatedOutputSink,
) -> None:
    try:
        os.setsid()
        products.after_fork()
        result = analyzer.analyze(context, reader, products, outputs)
        sender.send(("ok", result, outputs.publications, products.consumed_product_ids))
    except WorkerIncompatibleError as error:
        sender.send(("incompatible", f"{type(error).__name__}: {error}"))
    except BaseException as error:
        sender.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        sender.close()


def _run_analyzer_isolated(
    *,
    analyzer: Analyzer,
    context: AnalysisContext,
    reader: IqReader,
    products: CatalogArtifactProductReader,
    outputs: _IsolatedOutputSink,
    timeout_seconds: float,
    heartbeat: _LeaseHeartbeat,
) -> tuple[StageResult, tuple[_StagedPublication, ...], tuple[int, ...]]:
    if timeout_seconds <= 0:
        raise RunRejectedError("isolated-stage wall-time boundary must be positive")
    process_context = multiprocessing.get_context("fork")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_isolated_analyzer_entry,
        args=(sender, analyzer, context, reader, products, outputs),
        name=f"leo-analyzer-{context.job_node_id or context.stage_config}",
        daemon=False,
    )
    process.start()
    sender.close()
    deadline = time.monotonic() + timeout_seconds
    next_heartbeat = time.monotonic() + heartbeat._interval_seconds
    message: tuple[Any, ...] | None = None
    try:
        while message is None:
            now = time.monotonic()
            if now >= deadline:
                _terminate_analyzer_process(process)
                raise RunRejectedError("stage exceeded enforceable wall-time boundary")
            wait_for = min(deadline - now, max(0.0, next_heartbeat - now), 0.25)
            if receiver.poll(wait_for):
                try:
                    message = receiver.recv()
                except EOFError as error:
                    raise ProcessingError("isolated analyzer exited without a receipt") from error
                break
            if not process.is_alive():
                raise ProcessingError("isolated analyzer exited without a receipt")
            now = time.monotonic()
            if now >= next_heartbeat:
                heartbeat.renew()
                heartbeat.ensure_owned()
                next_heartbeat = now + heartbeat._interval_seconds
    finally:
        receiver.close()
        if process.is_alive():
            _terminate_analyzer_process(process)
        process.join(timeout=_PROCESS_TERMINATION_GRACE_SECONDS)
    assert message is not None
    if message[0] == "incompatible":
        raise WorkerIncompatibleError(str(message[1]))
    if message[0] == "error":
        raise ProcessingError(str(message[1]))
    if message[0] != "ok" or len(message) != 4:
        raise ProcessingError("isolated analyzer returned an invalid receipt")
    return (
        cast(StageResult, message[1]),
        cast(tuple[_StagedPublication, ...], message[2]),
        cast(tuple[int, ...], message[3]),
    )


def _terminate_analyzer_process(process: Any) -> None:
    if not process.is_alive():
        return
    pid = process.pid
    if pid is None:
        raise ProcessingError("isolated analyzer has no process identity")
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGTERM)
        else:
            process.terminate()
    except (ProcessLookupError, PermissionError):
        process.terminate()
    process.join(timeout=_PROCESS_TERMINATION_GRACE_SECONDS)
    if process.is_alive():
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.join(timeout=_PROCESS_TERMINATION_GRACE_SECONDS)
    if process.is_alive():
        raise ProcessingError("isolated analyzer process could not be terminated")


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
        lane_registries: dict[PipelineLane, AnalyzerRegistry] | None = None,
    ) -> None:
        if heartbeat_interval <= timedelta(0) or heartbeat_interval >= lease_for:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")
        self.catalog = catalog
        self.artifacts = artifacts
        self.registry = registry
        self._lane_registries = {
            PipelineLane.STANDARD: registry,
            **({} if lane_registries is None else lane_registries),
        }
        if self._lane_registries[PipelineLane.STANDARD] is not registry:
            raise ValueError("Standard lane registry must be the primary registry")
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
        self._loaded_worker_release = loaded_worker_release
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
        claim_authority = (
            self._loaded_worker_release.revalidate_for_claim()
            if self._loaded_worker_release is not None
            else self._live_worker_authority()
        )
        if (
            self._loaded_worker_release is not None
            and claim_authority != self._loaded_worker_release.authority
        ):
            raise WorkerIncompatibleError("loaded worker release changed after composition")
        if claim_authority is not None:
            self.catalog.fail_one_unserviceable_run(
                worker_id=worker_id,
                authority=claim_authority,
            )
        lease = self.catalog.claim_job(
            worker_id=worker_id,
            lease_for=self.lease_for,
            authority=claim_authority,
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
            self._require_live_worker_authority(claim_authority)
            # Every typed Standard node runs behind the enforceable process boundary,
            # including CPU/memory reducers. Legacy jobs retain in-process execution
            # until they adopt the typed node contract.
            isolated = lease.node_id is not None
            if not isolated:
                heartbeat.start()
            execution = self.catalog.run_execution_info(lease.run_id)
            if claim_authority is not None:
                _require_execution_authority(execution, claim_authority)
            lane = PipelineLane(execution.pipeline_lane)
            try:
                lane_registry = self._lane_registries[lane]
            except KeyError as error:
                raise RunRejectedError(
                    f"worker has no registry for pipeline lane: {lane.value}"
                ) from error
            analyzer = lane_registry.get(lease.stage_key)
            context = AnalysisContext(
                session_id=execution.session_id,
                run_id=execution.run_id,
                pipeline_release=execution.pipeline_release_id,
                scope_key=lease.scope_key,
                scope=lease.scope,
                job_node_id=lease.node_id,
                dependency_node_ids=lease.dependency_node_ids,
                stage_config=_stage_config(
                    _lane_configuration(execution.pipeline_configuration, lane),
                    lease.stage_key,
                ),
            )
            reader: IqReader
            self._require_live_worker_authority(claim_authority)
            if lease.iq_access == "none":
                reader = _NoIqReader()
            elif lease.scope is not None:
                reader = self.iq_readers.open_scope(execution, lease.scope)
            else:
                reader = self.iq_readers.open(execution, lease.scope_key)
            self._inject("execution:after_iq_reader_open")
            self._require_live_worker_authority(claim_authority)
            products = CatalogArtifactProductReader(
                self.catalog,
                self.artifacts,
                run_id=lease.run_id,
                scope_key=lease.scope_key,
                job_id=lease.job_id if lease.node_id is not None else None,
                scope=lease.scope,
            )
            output_limit = self._output_byte_limits.get(lease.resource_class)
            if output_limit is None:
                raise RunRejectedError(f"unknown resource class: {lease.resource_class}")
            wall_limit = self._wall_time_limits_seconds.get(lease.resource_class)
            if wall_limit is None or wall_limit <= 0:
                raise RunRejectedError(f"unknown resource class: {lease.resource_class}")
            started = time.monotonic()
            deadline = started + wall_limit
            execution_process_id = os.getpid()

            def require_output_authority() -> None:
                self._require_live_worker_authority(claim_authority)
                if time.monotonic() >= deadline:
                    raise RunRejectedError("stage exceeded enforceable wall-time boundary")
                if os.getpid() == execution_process_id:
                    heartbeat.renew_if_due()

            outputs = _BoundedOutputSink(
                self.artifacts.output_sink(
                    session_id=execution.session_id,
                    run_id=lease.run_id,
                    stage_key=lease.stage_key,
                    scope_key=lease.scope_key,
                ),
                maximum_bytes=output_limit,
                before_publish=require_output_authority,
            )
            try:
                if isolated:
                    with _LocalStagingDirectory() as staging:
                        staged_outputs = _IsolatedOutputSink(
                            staging.fileno(),
                            stage_key=lease.stage_key,
                            scope_key=lease.scope_key,
                            maximum_bytes=output_limit,
                            before_stage=require_output_authority,
                        )
                        result, staged, consumed_product_ids = _run_analyzer_isolated(
                            analyzer=analyzer,
                            context=context,
                            reader=reader,
                            products=products,
                            outputs=staged_outputs,
                            timeout_seconds=wall_limit,
                            heartbeat=heartbeat,
                        )
                        self._inject("execution:after_analyze")
                        validation_publications = tuple(item.publication for item in staged)
                        _validate_result(analyzer, result, validation_publications)
                        require_output_authority()
                        publications = _materialize_staged_publications(
                            staged,
                            staging,
                            outputs,
                        )
                else:
                    result = analyzer.analyze(context, reader, products, outputs)
                    publications = outputs.publications
                    consumed_product_ids = products.consumed_product_ids
                    _validate_result(analyzer, result, publications)
            finally:
                close_reader = getattr(reader, "close", None)
                if close_reader is not None:
                    close_reader()
            elapsed = time.monotonic() - started
            self._require_live_worker_authority(claim_authority)
            if elapsed > wall_limit and not isolated:
                raise RunRejectedError(f"stage exceeded {lease.resource_class} wall-time boundary")
            heartbeat.ensure_owned()
            if not isolated:
                self._inject("execution:after_analyze")

            coverage = _coverage(result)
            registrations = tuple(
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
                    input_product_ids=consumed_product_ids,
                    scope=lease.scope,
                )
                for published in (publication.published for publication in publications)
            )
            if lease.node_id is not None:
                if claim_authority is None:
                    raise WorkerIncompatibleError("typed result lacks worker release authority")
                self._inject("execution:before_product_register")
                self._require_live_worker_authority(claim_authority)
                heartbeat.ensure_owned()
                self._inject("execution:before_job_complete")
                self._require_live_worker_authority(claim_authority)
                self.catalog.commit_stage_result(
                    StageResultCommit(
                        job_id=lease.job_id,
                        worker_id=lease.worker_id,
                        attempt_number=lease.attempt_number,
                        authority=claim_authority,
                        outcome=result.outcome.value,
                        declared_products=tuple(
                            sorted(
                                (item.kind, item.schema_version)
                                for item in analyzer.spec.output_products
                            )
                        ),
                        products=registrations,
                        consumed_product_ids=tuple(sorted(consumed_product_ids)),
                    )
                )
            else:
                for registration in registrations:
                    self.catalog.register_product(registration)
                    self._inject("execution:after_product_register")
                heartbeat.ensure_owned()
        except WorkerIncompatibleError as error:
            heartbeat.stop()
            with suppress(LeaseLostError):
                assert claim_authority is not None
                self.catalog.defer_incompatible_job(
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    authority=claim_authority,
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
        if lease.node_id is not None:
            return WorkerExecution(
                job_id=lease.job_id,
                run_id=lease.run_id,
                stage_key=lease.stage_key,
                scope_key=lease.scope_key,
                succeeded=True,
                outcome=result.outcome,
                error=None,
            )
        try:
            heartbeat.ensure_owned()
            self._require_live_worker_authority(claim_authority)
            self._inject("execution:before_job_complete")
            self.catalog.complete_job(
                job_id=lease.job_id,
                worker_id=lease.worker_id,
                outcome=result.outcome.value,
            )
        except WorkerIncompatibleError as error:
            with suppress(LeaseLostError):
                assert claim_authority is not None
                self.catalog.defer_incompatible_job(
                    job_id=lease.job_id,
                    worker_id=lease.worker_id,
                    authority=claim_authority,
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
        pipeline_lane: PipelineLane | str = PipelineLane.STANDARD,
    ) -> None:
        """Persist a validated typed plan only after full raw verification succeeded."""

        identity = self.catalog.capture_recording_identity(plan.session_id)
        if identity.manifest_digest != plan.manifest_digest:
            raise ValueError("expanded plan manifest disagrees with the catalog")
        capture_authority = self.catalog.capture_path_authority(plan.session_id)
        if capture_authority.evidence_only and PromotionPolicy(promotion_policy) is not (
            PromotionPolicy.EVIDENCE_ONLY
        ):
            raise ValueError("protected TEST capture permits evidence-only analysis")
        integrity = self.iq_readers.verify_integrity(identity)
        if (
            integrity.session_id != plan.session_id
            or integrity.manifest_digest != plan.manifest_digest
        ):
            raise ValueError("integrity authority returned evidence for different raw bytes")
        manifest = self.iq_readers.verified_manifest(integrity.attestation_digest)
        expected_plan = compile_standard_run_plan(
            manifest,
            manifest_digest=plan.manifest_digest,
            pipeline_release_id=plan.pipeline_release_id,
        )
        if plan != expected_plan:
            raise ValueError("expanded plan differs from the manifest-authoritative Standard DAG")
        dependencies: dict[str, list[str]] = {job.node_id: [] for job in plan.jobs}
        for edge in plan.edges:
            dependencies[edge.job_node_id].append(edge.depends_on_job_node_id)
        canonical_lane = PipelineLane(pipeline_lane)
        priority = (
            RESEARCH_JOB_PRIORITY
            if canonical_lane is PipelineLane.RESEARCH
            else REPROCESS_JOB_PRIORITY
            if trigger == "reprocess"
            else AUTOMATIC_JOB_PRIORITY
        )
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
            pipeline_lane=canonical_lane,
            expanded_plan_digest=plan.plan_digest,
            raw_integrity_attestation_digest=integrity.attestation_digest,
            require_integrity_prerequisite=True,
            subject_bindings=_compile_subject_binding_registrations(
                catalog=self.catalog,
                manifest=manifest,
                integrity=integrity,
                plan=plan,
            ),
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
        lane = PipelineLane(snapshot.execution.pipeline_lane)
        try:
            registry = self._lane_registries[lane]
        except KeyError as error:
            raise RunRejectedError(
                f"worker has no registry for pipeline lane: {lane.value}"
            ) from error
        for job in snapshot.jobs:
            analyzer = registry.get(job.stage_key)
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

    def _live_worker_authority(self) -> WorkerReleaseAuthority | None:
        if self._loaded_worker_release is None:
            return self._worker_authority
        current = self._loaded_worker_release.revalidate()
        if current != self._loaded_worker_release.authority:
            raise WorkerIncompatibleError("loaded worker release changed after composition")
        return current

    def _require_live_worker_authority(self, expected: WorkerReleaseAuthority | None) -> None:
        current = self._live_worker_authority()
        if current != expected:
            raise WorkerIncompatibleError("worker release changed across execution boundary")


def _lane_configuration(configuration: dict[str, object], lane: PipelineLane) -> dict[str, object]:
    lanes = configuration.get("pipeline_lanes")
    if lanes is None:
        if lane is not PipelineLane.STANDARD:
            raise ValueError("Research run requires explicit lane-scoped configuration")
        return configuration
    if not isinstance(lanes, dict) or set(lanes) != {"standard", "research"}:
        raise ValueError("pipeline lane configuration must declare exactly Standard and Research")
    selected = lanes.get(lane.value)
    if not isinstance(selected, dict):
        raise ValueError(f"pipeline lane configuration must be an object: {lane.value}")
    return cast(dict[str, object], selected)


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


def _compile_subject_binding_registrations(
    *,
    catalog: CatalogRepository,
    manifest: RecordingManifestV1,
    integrity: RawIntegrityAttestationV1,
    plan: ExpandedRunPlanV1,
) -> tuple[RunSubjectBindingRegistration, ...]:
    """Freeze every manifest-derived path/pair fact before the run can exist."""

    release = catalog.pipeline_release_snapshot(plan.pipeline_release_id)
    topology = compile_scope_inventory(manifest)
    starlink_tuning = resolve_manifest_starlink_tuning(manifest)
    streams = {item.stream_id: item for item in manifest.streams}
    raw_streams = {item.stream_id: item for item in integrity.streams}
    registrations: list[RunSubjectBindingRegistration] = []
    for scope in topology.receiver_paths:
        assert scope.stream_id is not None and scope.receiver_id is not None
        stream = streams[scope.stream_id]
        tuning_intent = starlink_tuning[stream.stream_id]
        raw = raw_streams.get(scope.stream_id)
        if stream.timing is None or raw is None:
            raise ValueError("typed receiver path lacks timing or verified chunk closure")
        settings = stream.applied_settings or stream.requested_settings
        capture_binding = catalog.capture_receiver_binding(scope)
        if (
            capture_binding.radio_id != stream.radio.radio_id
            or capture_binding.radio_serial != stream.radio.serial
            or capture_binding.manifest_digest != plan.manifest_digest
            or capture_binding.profile_revision_digest
            != manifest.capture_plan.profile_revision.revision_digest
        ):
            raise ValueError("manifest and catalog receiver authority disagree")
        timing = StreamTimingEvidenceV1(
            first_estimate_utc_ns=stream.timing.first_sample.estimate_utc_ns,
            first_earliest_utc_ns=stream.timing.first_sample.earliest_utc_ns,
            first_latest_utc_ns=stream.timing.first_sample.latest_utc_ns,
            last_estimate_utc_ns=stream.timing.last_sample.estimate_utc_ns,
            last_earliest_utc_ns=stream.timing.last_sample.earliest_utc_ns,
            last_latest_utc_ns=stream.timing.last_sample.latest_utc_ns,
        )
        frequency_reference = catalog.capture_frequency_reference(
            scope,
            tuned_center_frequency_hz=settings.center_frequency_hz,
        )
        values: dict[str, Any] = {
            "schema_version": 3,
            "algorithm_version": "standard-path-input-bind-v3",
            "session_id": manifest.session_id,
            "stream_id": stream.stream_id,
            "radio_id": stream.radio.radio_id,
            "receiver_id": scope.receiver_id,
            "manifest_digest": plan.manifest_digest,
            "raw_integrity_attestation_digest": integrity.attestation_digest,
            "selected_stream_digest": canonical_digest(stream.model_dump(mode="json")),
            "compressed_chunk_closure_digest": raw.compressed_closure_digest,
            "uncompressed_chunk_closure_digest": raw.uncompressed_closure_digest,
            "synchronization_inventory_digest": topology.synchronization_inventory_digest,
            "profile_revision_digest": capture_binding.profile_revision_digest,
            "capture_plan_digest": manifest.capture_plan.plan_digest,
            "receiver_settings_digest": canonical_digest(settings.model_dump(mode="json")),
            "science_configuration_digest": release.configuration_digest,
            "science_implementation_digest": release.executable_digest,
            "capture_lineage_resolution": capture_binding.lineage_resolution,
            "physical_receiver_id": capture_binding.physical_receiver_id,
            "hardware_epoch_id": capture_binding.hardware_epoch_id,
            "tuned_center_frequency_hz": settings.center_frequency_hz,
            "sample_rate_hz": settings.sample_rate_hz,
            "declared_sample_count": stream.captured_sample_count,
            "starlink_channel": tuning_intent.channel,
            "starlink_edge": tuning_intent.edge.value,
            "starlink_tuning_evidence_source": tuning_intent.evidence_source,
            "timing": timing.model_dump(mode="json"),
            "frequency_reference": frequency_reference.model_dump(mode="json"),
        }
        path_binding = StandardPathInputBindV3.model_validate(
            {**values, "binding_digest": canonical_digest(values)}
        )
        registrations.append(
            RunSubjectBindingRegistration(
                scope=scope,
                document=path_binding.model_dump(mode="json"),
            )
        )

    if topology.paired is not None:
        synchronization = manifest.synchronization
        required = (
            synchronization.estimated_start_skew_ns,
            synchronization.start_skew_uncertainty_ns,
            synchronization.estimated_overlap_start_utc_ns,
            synchronization.estimated_overlap_end_utc_ns,
            synchronization.guaranteed_overlap_ns,
        )
        if any(value is None for value in required) or any(
            stream.timing is None for stream in manifest.streams
        ):
            raise ValueError("paired Standard run lacks authoritative overlap timing")
        stream_timings = tuple(
            cast(Any, stream.timing) for stream in manifest.streams if stream.timing is not None
        )
        pair_timing = PairTimingEvidenceV1(
            synchronization_inventory_digest=topology.synchronization_inventory_digest,
            union_start_utc_ns=min(
                timing.first_sample.estimate_utc_ns for timing in stream_timings
            ),
            union_end_utc_ns=max(timing.last_sample.estimate_utc_ns for timing in stream_timings),
            estimated_overlap_start_utc_ns=cast(int, required[2]),
            estimated_overlap_end_utc_ns=cast(int, required[3]),
            estimated_start_skew_ns=cast(int, required[0]),
            start_skew_uncertainty_ns=cast(int, required[1]),
            guaranteed_overlap_ns=cast(int, required[4]),
            synchronization_grade=synchronization.grade.value,
        )
        values = {
            "schema_version": 2,
            "algorithm_version": "standard-pair-input-bind-v2",
            "session_id": manifest.session_id,
            "manifest_digest": plan.manifest_digest,
            "synchronization_inventory_digest": topology.synchronization_inventory_digest,
            "raw_integrity_attestation_digests": [integrity.attestation_digest],
            "timing": pair_timing.model_dump(mode="json"),
        }
        pair_binding = StandardPairInputBindV2.model_validate(
            {**values, "binding_digest": canonical_digest(values)}
        )
        registrations.append(
            RunSubjectBindingRegistration(
                scope=topology.paired,
                document=pair_binding.model_dump(mode="json"),
            )
        )
    return tuple(sorted(registrations, key=lambda item: item.scope.canonical_digest))


def _coverage(result: StageResult) -> float | None:
    value = result.summary.get("coverage_fraction")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if 0.0 <= numeric <= 1.0 else None


def _manifest_from_snapshot(snapshot: RunSealSnapshot) -> AnalysisRunManifestV2:
    return AnalysisRunManifestV2(
        session_id=snapshot.execution.session_id,
        run_id=snapshot.execution.run_id,
        pipeline_release_id=snapshot.execution.pipeline_release_id,
        input_manifest_digest=snapshot.execution.input_manifest_digest,
        trigger=snapshot.execution.trigger,
        pipeline_lane=cast(Literal["standard", "research"], snapshot.execution.pipeline_lane),
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
