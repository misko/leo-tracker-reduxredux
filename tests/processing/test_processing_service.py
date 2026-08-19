from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from leo.analysis.power import PowerAnalyzer
from leo.analysis.quality import QualityAnalyzer
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import AnalysisRunState, AttemptState, InvalidStateError, PromotionPolicy
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.pipeline import (
    AnalyzerRegistry,
    MissingDependencyError,
    ProductRequirement,
    ProductSpec,
    StageOutcome,
    StageResult,
    StageSpec,
)
from leo.processing import ProcessingService, RecordingIqReaderProvider, RunRejectedError
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore

from .conftest import ProcessingDatabase

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


@dataclass(frozen=True, slots=True)
class PreparedSystem:
    recordings: RecordingStore
    artifacts: AnalysisArtifactStore
    session_id: str
    manifest_digest: str


def _prepare_recording(
    database: ProcessingDatabase,
    root: Path,
    session_id: str,
) -> PreparedSystem:
    recordings = RecordingStore(root)
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=30.0),
        ),
        sample_count=8,
        storage_policy="test-zstd-v1",
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=GainMode.MANUAL,
        gains=profile.gains,
    )
    compression = CompressionSettingsV1(
        policy_id="test-zstd-v1",
        level=3,
        target_uncompressed_bytes=64,
    )
    radio = FakeRadioSource("radio-a", receiver_count=2, seed=23)
    radio.open()
    radio.configure(settings)
    writer = recordings.begin(session_id, compression)
    stream_writer = writer.open_stream("stream-a", radio.identity, (0, 1))
    for _ in range(2):
        stream_writer.append(radio.read_block(4))
    receipt = stream_writer.finalize()
    radio.close()
    timing = StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_000_000_000_000,
            earliest_utc_ns=1_700_000_000_000_000_000,
            latest_utc_ns=1_700_000_000_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_001_000_000_000,
            earliest_utc_ns=1_700_000_000_999_000_000,
            latest_utc_ns=1_700_000_001_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )
    manifest = RecordingManifestV1(
        session_id=session_id,
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=("TEST",),
        streams=(
            RecordingStreamV1(
                stream_id="stream-a",
                radio=radio.identity,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=8,
                captured_sample_count=8,
                timing=timing,
                chunks=receipt.chunks,
                timeline_relative_path=receipt.timeline_relative_path,
                timeline_sha256=receipt.timeline_sha256,
                continuity=receipt.continuity,
            ),
        ),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="processing-test", machine_id="test-machine"),
        producer=ProducerV1(name="processing-test", version="1"),
    )
    published = writer.publish(manifest)
    database.catalog.create_capture_session(
        session_id=session_id,
        source_type="test",
        state="committed",
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        tags=("TEST",),
    )
    return PreparedSystem(
        recordings=recordings,
        artifacts=AnalysisArtifactStore(root),
        session_id=session_id,
        manifest_digest=published.manifest_sha256,
    )


def _add_release(
    database: ProcessingDatabase,
    release_id: str,
    *,
    configuration: dict | None = None,
) -> None:
    database.catalog.add_pipeline_release(
        release_id=release_id,
        code_revision=f"code-{release_id}",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration={} if configuration is None else configuration,
    )


def _baseline_service(
    database: ProcessingDatabase,
    system: PreparedSystem,
    *,
    failure_injector=None,
) -> ProcessingService:
    return ProcessingService(
        catalog=database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((QualityAnalyzer(), PowerAnalyzer())),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=5),
        heartbeat_interval=timedelta(seconds=1),
        failure_injector=failure_injector,
    )


def _execute_until_idle(service: ProcessingService) -> tuple:
    executions = []
    while execution := service.run_once(worker_id="worker-a"):
        executions.append(execution)
    return tuple(executions)


def test_real_recording_quality_power_run_seals_and_promotes(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-baseline")
    _add_release(
        processing_database,
        "release-baseline",
        configuration={
            "stages": {
                "quality": {"block_samples": 3},
                "power": {"block_samples": 3},
            }
        },
    )
    service = _baseline_service(processing_database, system)
    service.create_new_capture_run(
        run_id="run-baseline",
        session_id=system.session_id,
        pipeline_release_id="release-baseline",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )

    executions = _execute_until_idle(service)
    published = service.finalize_run("run-baseline")
    snapshot = processing_database.catalog.run_seal_snapshot("run-baseline")

    assert [item.stage_key for item in executions] == ["quality", "power"]
    assert all(item.succeeded for item in executions)
    assert {item.kind for item in snapshot.products} == {"quality.summary", "power.summary"}
    assert all(item.status == "complete" for item in snapshot.products)
    assert snapshot.execution.promotion_policy == PromotionPolicy.CURRENT.value
    assert published.path.name == "manifest.json"
    assert processing_database.catalog.current_run_id(system.session_id) == "run-baseline"
    assert processing_database.catalog.run_state("run-baseline") is AnalysisRunState.SUCCEEDED


def test_evidence_only_stage_plan_seals_product_without_replacing_standard(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-evidence")
    _add_release(processing_database, "release-standard")
    service = _baseline_service(processing_database, system)
    service.create_new_capture_run(
        run_id="run-standard",
        session_id=system.session_id,
        pipeline_release_id="release-standard",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )
    _execute_until_idle(service)
    service.finalize_run("run-standard")

    _add_release(processing_database, "release-wp11")
    service.create_reprocess_run(
        run_id="run-wp11",
        session_id=system.session_id,
        pipeline_release_id="release-wp11",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
        stage_keys=("quality",),
    )
    executions = _execute_until_idle(service)
    published = service.finalize_run("run-wp11")
    snapshot = processing_database.catalog.run_seal_snapshot("run-wp11")

    assert [execution.stage_key for execution in executions] == ["quality"]
    assert [product.kind for product in snapshot.products] == ["quality.summary"]
    assert published.manifest.products[0].kind == "quality.summary"
    assert snapshot.execution.pipeline_release_id == "release-wp11"
    assert snapshot.execution.promotion_policy == PromotionPolicy.EVIDENCE_ONLY.value
    assert processing_database.catalog.run_state("run-wp11") is AnalysisRunState.SUCCEEDED
    assert processing_database.catalog.current_run_id(system.session_id) == "run-standard"


def test_invalid_policy_and_incomplete_explicit_graph_create_no_run(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-fail-closed")
    _add_release(processing_database, "release-fail-closed")
    service = _baseline_service(processing_database, system)

    with pytest.raises(ValueError, match="unknown analysis-run promotion policy"):
        service.create_reprocess_run(
            run_id="run-invalid-policy",
            session_id=system.session_id,
            pipeline_release_id="release-fail-closed",
            input_manifest_digest=system.manifest_digest,
            scope_keys=("stream-a",),
            promotion_policy="unsafe",
        )
    with pytest.raises(MissingDependencyError, match="missing pipeline dependencies: quality"):
        service.create_reprocess_run(
            run_id="run-invalid-graph",
            session_id=system.session_id,
            pipeline_release_id="release-fail-closed",
            input_manifest_digest=system.manifest_digest,
            scope_keys=("stream-a",),
            stage_keys=("power",),
        )

    assert processing_database.catalog.current_run_id(system.session_id) is None


def test_reprocess_retry_and_seal_recovery_atomically_replace_current(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-reprocess")
    _add_release(processing_database, "release-reprocess")
    initial = _baseline_service(processing_database, system)
    initial.create_new_capture_run(
        run_id="run-old",
        session_id=system.session_id,
        pipeline_release_id="release-reprocess",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )
    _execute_until_idle(initial)
    initial.finalize_run("run-old")

    failed_product_once = False
    failed_seal_once = False

    def inject(point: str) -> None:
        nonlocal failed_product_once, failed_seal_once
        if point == "execution:before_job_complete" and not failed_product_once:
            failed_product_once = True
            raise RuntimeError("injected crash after idempotent product registration")
        if point == "execution:after_manifest_publish" and not failed_seal_once:
            failed_seal_once = True
            raise RuntimeError("injected crash before atomic catalog promotion")

    retrying = _baseline_service(processing_database, system, failure_injector=inject)
    retrying.create_reprocess_run(
        run_id="run-new",
        session_id=system.session_id,
        pipeline_release_id="release-reprocess",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )
    first = retrying.run_once(worker_id="worker-retry")
    assert first is not None and first.succeeded is False
    assert processing_database.catalog.current_run_id(system.session_id) == "run-old"

    executions = _execute_until_idle(retrying)
    assert [item.stage_key for item in executions] == ["quality", "power"]
    assert processing_database.catalog.attempt_states(first.job_id) == (
        AttemptState.FAILED,
        AttemptState.SUCCEEDED,
    )
    snapshot = processing_database.catalog.run_seal_snapshot("run-new")
    assert len(snapshot.products) == 2

    with pytest.raises(RuntimeError, match="before atomic catalog promotion"):
        retrying.finalize_run("run-new")
    assert processing_database.catalog.current_run_id(system.session_id) == "run-old"

    retrying.finalize_run("run-new")
    assert processing_database.catalog.current_run_id(system.session_id) == "run-new"


def test_run_creation_pins_the_catalog_recording_manifest(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-pinned")
    _add_release(processing_database, "release-pinned")
    service = _baseline_service(processing_database, system)

    with pytest.raises(InvalidStateError, match="input digest disagrees"):
        service.create_reprocess_run(
            run_id="run-wrong-input",
            session_id=system.session_id,
            pipeline_release_id="release-pinned",
            input_manifest_digest=DIGEST_A,
            scope_keys=("stream-a",),
        )


def test_explicit_reprocess_jobs_precede_automatic_capture_backlog(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    old = _prepare_recording(processing_database, tmp_path / "bulk", "session-old")
    new = _prepare_recording(processing_database, tmp_path / "bulk", "session-new")
    _add_release(processing_database, "release-priority")
    service = _baseline_service(processing_database, old)

    service.create_new_capture_run(
        run_id="run-old-current",
        session_id=old.session_id,
        pipeline_release_id="release-priority",
        input_manifest_digest=old.manifest_digest,
        scope_keys=("stream-a",),
    )
    _execute_until_idle(service)
    service.finalize_run("run-old-current")
    service.create_new_capture_run(
        run_id="run-automatic",
        session_id=new.session_id,
        pipeline_release_id="release-priority",
        input_manifest_digest=new.manifest_digest,
        scope_keys=("stream-a",),
    )
    service.create_reprocess_run(
        run_id="run-explicit",
        session_id=old.session_id,
        pipeline_release_id="release-priority",
        input_manifest_digest=old.manifest_digest,
        scope_keys=("stream-a",),
    )

    execution = service.run_once(worker_id="priority-worker")

    assert execution is not None
    assert execution.run_id == "run-explicit"
    assert execution.stage_key == "quality"


class _SemanticAnalyzer:
    def __init__(self, key: str, outcome: StageOutcome, *, delay: float = 0.0) -> None:
        self.spec = StageSpec(
            key=key,
            algorithm_version="1.0.0",
            configuration_schema=f"{key}.v1",
            accepted_outcomes=(outcome,),
        )
        self._outcome = outcome
        self._delay = delay

    def analyze(self, *args, **kwargs) -> StageResult:
        if self._delay:
            time.sleep(self._delay)
        return StageResult(outcome=self._outcome, summary={"coverage_fraction": 0.5})


class _FailingAnalyzer:
    spec = StageSpec(
        key="failing",
        algorithm_version="1.0.0",
        configuration_schema="failing.v1",
    )

    def analyze(self, *args, **kwargs) -> StageResult:
        raise RuntimeError("injected analyzer failure")


_V2_VERTICAL_PRODUCT = ProductSpec(kind="science.native-evidence", schema_version=2)
_V2_CONSUMER_PRODUCT = ProductSpec(kind="science.consumer-result", schema_version=1)


class _V2EvidenceProducer:
    spec = StageSpec(
        key="v2-producer",
        algorithm_version="2.0.0",
        configuration_schema="v2-producer.v2",
        output_products=(_V2_VERTICAL_PRODUCT,),
    )

    def analyze(self, _context, _iq, _products, outputs) -> StageResult:
        published = outputs.publish_json(
            _V2_VERTICAL_PRODUCT,
            {"schema_version": 2, "sealed": True},
        )
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


class _V2EvidenceConsumer:
    spec = StageSpec(
        key="v2-consumer",
        algorithm_version="1.0.0",
        configuration_schema="v2-consumer.v1",
        dependencies=("v2-producer",),
        input_products=(
            ProductRequirement(
                kind=_V2_VERTICAL_PRODUCT.kind,
                accepted_schema_versions=(2,),
            ),
        ),
        output_products=(_V2_CONSUMER_PRODUCT,),
    )

    def __init__(self) -> None:
        self.observed = False

    def analyze(self, _context, _iq, products, outputs) -> StageResult:
        document = products.read_json(self.spec.input_products[0])
        self.observed = document == {"schema_version": 2, "sealed": True}
        if not self.observed:
            raise ValueError("actual artifact reader did not return selected V2 evidence")
        published = outputs.publish_json(
            _V2_CONSUMER_PRODUCT,
            {"schema_version": 1, "consumed": True},
        )
        return StageResult(outcome=StageOutcome.COMPLETE, products=(published,))


def test_selected_dag_reads_registered_v2_artifact_through_real_product_reader(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-v2-reader")
    _add_release(processing_database, "release-v2-reader")
    consumer = _V2EvidenceConsumer()
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((_V2EvidenceProducer(), consumer)),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=200),
    )
    service.create_reprocess_run(
        run_id="run-v2-reader",
        session_id=system.session_id,
        pipeline_release_id="release-v2-reader",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
        stage_keys=("v2-producer", "v2-consumer"),
    )

    executions = _execute_until_idle(service)
    assert [item.stage_key for item in executions] == ["v2-producer", "v2-consumer"]
    assert consumer.observed is True
    with processing_database.engine.connect() as connection:
        dependency = connection.execute(
            text(
                "SELECT output.kind, input.kind "
                "FROM product_dependency dependency "
                "JOIN analysis_product output ON output.id = dependency.product_id "
                "JOIN analysis_product input ON input.id = dependency.input_product_id"
            )
        ).one()
    assert dependency == (_V2_CONSUMER_PRODUCT.kind, _V2_VERTICAL_PRODUCT.kind)


@pytest.mark.parametrize(
    "outcome",
    [StageOutcome.PARTIAL_COVERAGE, StageOutcome.NO_RESULT],
)
def test_accepted_semantic_partial_and_no_result_can_seal(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    outcome: StageOutcome,
) -> None:
    session_id = f"session-{outcome.value}"
    run_id = f"run-{outcome.value}"
    release_id = f"release-{outcome.value}"
    system = _prepare_recording(processing_database, tmp_path / outcome.value, session_id)
    _add_release(processing_database, release_id)
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((_SemanticAnalyzer("semantic", outcome),)),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=200),
    )
    service.create_new_capture_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id=release_id,
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )

    execution = service.run_once(worker_id="worker-semantic")
    published = service.finalize_run(run_id)

    assert execution is not None and execution.outcome is outcome
    assert published.manifest.jobs[0].outcome == outcome.value
    assert published.manifest.products == ()


def test_terminal_failed_run_never_replaces_current(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-failure")
    _add_release(processing_database, "release-good")
    good = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((_SemanticAnalyzer("good", StageOutcome.COMPLETE),)),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=200),
    )
    good.create_new_capture_run(
        run_id="run-good",
        session_id=system.session_id,
        pipeline_release_id="release-good",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )
    execution = good.run_once(worker_id="worker-good")
    assert execution is not None and execution.succeeded
    good.finalize_run("run-good")

    _add_release(processing_database, "release-failing")
    failing = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((_FailingAnalyzer(),)),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=2),
        heartbeat_interval=timedelta(milliseconds=200),
    )
    failing.create_reprocess_run(
        run_id="run-failing",
        session_id=system.session_id,
        pipeline_release_id="release-failing",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )
    for _ in range(3):
        execution = failing.run_once(worker_id="worker-failing")
        assert execution is not None and execution.succeeded is False

    with pytest.raises(RunRejectedError, match="failed or cancelled"):
        failing.finalize_run("run-failing")
    assert processing_database.catalog.current_run_id(system.session_id) == "run-good"
    assert processing_database.catalog.run_state("run-failing") is AnalysisRunState.FAILED


def test_heartbeat_keeps_slow_stage_lease_live(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    system = _prepare_recording(processing_database, tmp_path / "bulk", "session-heartbeat")
    _add_release(processing_database, "release-heartbeat")
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=system.artifacts,
        # Keep the stage longer than the initial lease while leaving enough wall-clock
        # margin for a loaded PostgreSQL CI host to schedule the heartbeat thread.
        registry=AnalyzerRegistry((_SemanticAnalyzer("slow", StageOutcome.COMPLETE, delay=2.0),)),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=1),
        heartbeat_interval=timedelta(milliseconds=100),
    )
    service.create_new_capture_run(
        run_id="run-heartbeat",
        session_id=system.session_id,
        pipeline_release_id="release-heartbeat",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-a",),
    )

    execution = service.run_once(worker_id="worker-slow")
    assert execution is not None and execution.succeeded is True
    service.finalize_run("run-heartbeat")
