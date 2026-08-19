"""Isolated production-path E2E server.

Importing this module creates a unique PostgreSQL schema, migrates it, publishes
ordinary compressed RecordingStore bundles, executes the real Standard worker
twice to prove current-run replacement, and finally composes the production
read-only application.  Setup failures are intentionally fatal: CI must never
fall back to presentation fixtures or silently skip this lane.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.analysis.adapters import (
    production_long_dwell_configuration,
    production_long_dwell_registry,
)
from leo.analysis.graphs import ComputeTier
from leo.api import ProductionSettings, create_production_app
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_session_factory
from leo.contracts.digests import canonical_json_bytes, sha256_digest
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
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get(
    "LEO_E2E_DATABASE_URL",
    os.environ.get("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker"),
)
PIPELINE_RELEASE = "e2e-standard-v1"
CURRENT_RUN_ID = "e2e-main-run-v2"
REPLACED_RUN_ID = "e2e-main-run-v1"
MAIN_SESSION_ID = "e2e-main-test-recording"
FAILED_SESSION_ID = "e2e-failed-test-recording"
SAMPLE_RATE_HZ = 2_500_000
SAMPLE_COUNT = 2_048
BASE_UTC_NS = 1_780_000_000_000_000_000


@dataclass(frozen=True, slots=True)
class PublishedInput:
    session_id: str
    manifest_digest: str
    scope_keys: tuple[str, ...]


_temporary_directory = tempfile.TemporaryDirectory(prefix="leo-production-e2e-")
_bulk_root = (Path(_temporary_directory.name) / "bulk").resolve()
_schema = f"leo_e2e_{uuid.uuid4().hex}"
_admin_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_schema_engine: Engine | None = None
_cleaned = False


def _cleanup() -> None:
    global _cleaned
    if _cleaned:
        return
    _cleaned = True
    if _schema_engine is not None:
        _schema_engine.dispose()
    try:
        with _admin_engine.begin() as connection:
            connection.execute(DropSchema(_schema, cascade=True))
    finally:
        _admin_engine.dispose()
        _temporary_directory.cleanup()


atexit.register(_cleanup)


def _isolated_database() -> tuple[Engine, str]:
    try:
        with _admin_engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(CreateSchema(_schema))
    except Exception as error:
        raise RuntimeError(
            f"production E2E requires PostgreSQL at {DATABASE_URL!r}: {error}"
        ) from error
    url = make_url(DATABASE_URL).update_query_dict({"options": f"-csearch_path={_schema}"})
    engine = create_engine(url, pool_pre_ping=True)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine, url.render_as_string(hide_password=False)


def _timing(first_utc_ns: int, duration_ns: int) -> StreamTimingV1:
    return StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=first_utc_ns,
            earliest_utc_ns=first_utc_ns - 10_000,
            latest_utc_ns=first_utc_ns + 10_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=first_utc_ns + duration_ns,
            earliest_utc_ns=first_utc_ns + duration_ns - 10_000,
            latest_utc_ns=first_utc_ns + duration_ns + 10_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )


def _publish_recording(
    catalog: CatalogRepository,
    recordings: RecordingStore,
    *,
    session_id: str,
    paired: bool,
    seed: int,
) -> PublishedInput:
    radio_ids = ("e2e-radio-a", "e2e-radio-b") if paired else ("e2e-radio-failed",)
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        description=(
            "Production E2E paired TEST dwell"
            if paired
            else "Production E2E intentional analysis failure"
        ),
        center_frequency_hz=1_709_687_500,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=2_500_000,
        receivers=(0,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=0, gain_db=34.0),),
        sample_count=SAMPLE_COUNT,
        refill_samples=512,
        settle_seconds=0,
        prime_refills=0,
        synchronization_mode=(
            SynchronizationMode.BEST_EFFORT if paired else SynchronizationMode.NONE
        ),
        storage_policy="e2e-zstd-v1",
        tags=("E2E", "TEST"),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        radio_ids,
        source_type=SourceType.TEST,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    compression = CompressionSettingsV1(
        policy_id=profile.storage_policy,
        level=1,
        target_uncompressed_bytes=SAMPLE_COUNT * 4,
    )
    writer = recordings.begin(session_id, compression)
    streams = []
    for index, radio_id in enumerate(radio_ids):
        radio = FakeRadioSource(radio_id, receiver_count=1, seed=seed + index)
        radio.open()
        radio.configure(settings)
        stream_id = f"stream-{index + 1}"
        stream_writer = writer.open_stream(stream_id, radio.identity, (0,))
        for _ in range(SAMPLE_COUNT // 512):
            stream_writer.append(radio.read_block(512))
        receipt = stream_writer.finalize()
        radio.close()
        first = BASE_UTC_NS + index * 50_000
        duration = round(SAMPLE_COUNT * 1_000_000_000 / SAMPLE_RATE_HZ)
        streams.append(
            RecordingStreamV1(
                stream_id=stream_id,
                radio=radio.identity,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=SAMPLE_COUNT,
                captured_sample_count=SAMPLE_COUNT,
                timing=_timing(first, duration),
                chunks=receipt.chunks,
                timeline_relative_path=receipt.timeline_relative_path,
                timeline_sha256=receipt.timeline_sha256,
                continuity=receipt.continuity,
            )
        )
    duration = round(SAMPLE_COUNT * 1_000_000_000 / SAMPLE_RATE_HZ)
    overlap = duration - 50_000
    synchronization = (
        SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.BEST_EFFORT,
            grade=SynchronizationGrade.BEST_EFFORT_OBSERVED,
            stream_ids=tuple(stream.stream_id for stream in streams),
            release_target_monotonic_ns=1_000_000_000,
            estimated_start_skew_ns=50_000,
            start_skew_uncertainty_ns=20_000,
            estimated_overlap_ns=overlap,
            estimated_overlap_start_utc_ns=BASE_UTC_NS + 50_000,
            estimated_overlap_end_utc_ns=BASE_UTC_NS + duration,
            guaranteed_overlap_ns=overlap - 20_000,
            overlap_fraction=overlap / duration,
        )
        if paired
        else SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.NONE,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=(streams[0].stream_id,),
        )
    )
    manifest = RecordingManifestV1(
        session_id=session_id,
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=BASE_UTC_NS,
        finalized_utc_ns=BASE_UTC_NS + duration + 1_000_000,
        capture_plan=plan,
        tags=profile.tags,
        streams=tuple(streams),
        synchronization=synchronization,
        compression=compression,
        host=HostIdentityV1(hostname="e2e-host", machine_id="e2e-machine"),
        producer=ProducerV1(name="production-e2e", version="1"),
    )
    published = writer.publish(manifest)
    catalog.create_capture_session(
        session_id=session_id,
        source_type="test",
        state="committed",
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        tags=manifest.tags,
        allocated_bytes=sum(
            chunk.compressed_bytes for stream in streams for chunk in stream.chunks
        ),
    )
    return PublishedInput(
        session_id,
        published.manifest_sha256,
        tuple(stream.stream_id for stream in streams),
    )


def _execute_run(
    service: ProcessingService,
    source: PublishedInput,
    *,
    run_id: str,
    reprocess: bool,
    expected_stage_count: int,
) -> None:
    create = service.create_reprocess_run if reprocess else service.create_new_capture_run
    create(
        run_id=run_id,
        session_id=source.session_id,
        pipeline_release_id=PIPELINE_RELEASE,
        input_manifest_digest=source.manifest_digest,
        scope_keys=source.scope_keys,
    )
    executions = []
    while execution := service.run_once(worker_id="production-e2e-worker"):
        executions.append(execution)
        if not execution.succeeded:
            raise RuntimeError(f"production E2E worker failed: {execution.error}")
    expected_jobs = expected_stage_count * len(source.scope_keys)
    if len(executions) != expected_jobs:
        raise RuntimeError(f"production E2E ran {len(executions)} jobs, expected {expected_jobs}")
    service.finalize_run(run_id)


def _prepare() -> tuple[str, Path]:
    global _schema_engine
    _schema_engine, schema_url = _isolated_database()
    catalog = CatalogRepository(create_session_factory(_schema_engine))
    recordings = RecordingStore(_bulk_root)
    artifacts = AnalysisArtifactStore(_bulk_root)
    (_bulk_root / "qualification" / "trusted-campaigns").mkdir(parents=True, exist_ok=True)
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)
    graph = {"stages": [item.model_dump(mode="json") for item in registry.graph().plan()]}
    catalog.add_pipeline_release(
        release_id=PIPELINE_RELEASE,
        code_revision="production-e2e",
        environment_digest=sha256_digest(b"production-e2e-environment"),
        graph_digest=sha256_digest(canonical_json_bytes(graph)),
        configuration={"stages": configuration, "compute_tier": "standard"},
    )
    main = _publish_recording(catalog, recordings, session_id=MAIN_SESSION_ID, paired=True, seed=41)
    failed = _publish_recording(
        catalog,
        recordings,
        session_id=FAILED_SESSION_ID,
        paired=False,
        seed=73,
    )
    service = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(recordings),
    )
    _execute_run(
        service,
        main,
        run_id=REPLACED_RUN_ID,
        reprocess=False,
        expected_stage_count=len(registry.keys),
    )
    _execute_run(
        service,
        main,
        run_id=CURRENT_RUN_ID,
        reprocess=True,
        expected_stage_count=len(registry.keys),
    )
    service.create_new_capture_run(
        run_id="e2e-intentional-failure",
        session_id=failed.session_id,
        pipeline_release_id=PIPELINE_RELEASE,
        input_manifest_digest=failed.manifest_digest,
        scope_keys=failed.scope_keys,
    )
    catalog.fail_analysis_run(
        run_id="e2e-intentional-failure",
        failure="Intentional production E2E analysis failure",
    )
    if catalog.current_run_id(main.session_id) != CURRENT_RUN_ID:
        raise RuntimeError("production E2E failed to atomically replace the current run")
    return schema_url, _bulk_root


_database_url, _prepared_bulk_root = _prepare()
app = create_production_app(
    ProductionSettings(
        database_url=_database_url,
        bulk_root=_prepared_bulk_root,
        static_directory=Path(
            os.environ.get("LEO_E2E_WEB_DIST", str(PROJECT_ROOT / "web" / "dist"))
        ),
        host="127.0.0.1",
        port=8766,
    )
)
app.router.add_event_handler("shutdown", _cleanup)
