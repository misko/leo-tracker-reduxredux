from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.analysis.adapters import (
    production_long_dwell_configuration,
    production_long_dwell_registry,
)
from leo.analysis.graphs import ComputeTier
from leo.analysis.power import PowerAnalyzer
from leo.analysis.quality import QualityAnalyzer
from leo.api import ProductionSettings, create_app, create_production_app
from leo.application import CatalogPresentationRepository
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, JobDefinition, create_session_factory
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
    StarlinkEdge,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.pipeline import AnalyzerRegistry
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


@dataclass(frozen=True, slots=True)
class ReadSystem:
    catalog: CatalogRepository
    engine: Engine
    bulk_root: Path
    recordings: RecordingStore
    artifacts: AnalysisArtifactStore
    manifest_digest: str


@pytest.fixture
def read_system(tmp_path: Path) -> Iterator[ReadSystem]:
    base_url = os.environ.get(
        "LEO_TEST_DATABASE_URL",
        "postgresql+psycopg:///leo_tracker",
    )
    schema = f"leo_read_{uuid.uuid4().hex}"
    admin = create_engine(base_url, pool_pre_ping=True)
    try:
        with admin.begin() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(CreateSchema(schema))
    except Exception as error:
        admin.dispose()
        pytest.fail(
            f"real PostgreSQL test database is required at {base_url!r}: {error}",
            pytrace=False,
        )
    url = make_url(base_url).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(url, pool_pre_ping=True)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    bulk_root = (tmp_path / "bulk").resolve()
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        catalog = CatalogRepository(create_session_factory(engine))
        recordings = RecordingStore(bulk_root)
        artifacts = AnalysisArtifactStore(bulk_root)
        manifest_digest = _publish_test_recording(catalog, recordings)
        yield ReadSystem(
            catalog=catalog,
            engine=engine,
            bulk_root=bulk_root,
            recordings=recordings,
            artifacts=artifacts,
            manifest_digest=manifest_digest,
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _publish_test_recording(catalog: CatalogRepository, recordings: RecordingStore) -> str:
    profile = CaptureProfileV1(
        name="read-vertical",
        description="TEST read vertical",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=31.0),
        ),
        sample_count=16,
        storage_policy="test-zstd-v1",
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["radio-read"],
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
        policy_id="test-zstd-v1",
        level=3,
        target_uncompressed_bytes=64,
    )
    radio = FakeRadioSource("radio-read", receiver_count=2, seed=37)
    radio.open()
    radio.configure(settings)
    writer = recordings.begin("session-read-vertical", compression)
    stream_writer = writer.open_stream("stream-read", radio.identity, (0, 1))
    for _ in range(4):
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
        session_id="session-read-vertical",
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=("TEST",),
        streams=(
            RecordingStreamV1(
                stream_id="stream-read",
                radio=radio.identity,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=16,
                captured_sample_count=16,
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
            stream_ids=("stream-read",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="read-test", machine_id="read-test-machine"),
        producer=ProducerV1(name="read-integration", version="1"),
    )
    published = writer.publish(manifest)
    catalog.create_capture_session(
        session_id=manifest.session_id,
        source_type="test",
        state="committed",
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        attributes={
            "presentation": {
                "title": profile.description,
                "profile_name": profile.name,
                "duration_seconds": manifest.capture_plan.resolved_sample_count
                / profile.sample_rate_hz,
            }
        },
        tags=manifest.tags,
    )
    return published.manifest_sha256


def _process(system: ReadSystem) -> None:
    system.catalog.add_pipeline_release(
        release_id="read-release-v1",
        code_revision="read-code-v1",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration={
            "stages": {
                "quality": {"block_samples": 3},
                "power": {"block_samples": 3},
            }
        },
    )
    service = ProcessingService(
        catalog=system.catalog,
        artifacts=system.artifacts,
        registry=AnalyzerRegistry((QualityAnalyzer(), PowerAnalyzer())),
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=5),
        heartbeat_interval=timedelta(seconds=1),
    )
    service.create_new_capture_run(
        run_id="read-run-v1",
        session_id="session-read-vertical",
        pipeline_release_id="read-release-v1",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-read",),
    )
    while service.run_once(worker_id="read-worker") is not None:
        pass
    service.finalize_run("read-run-v1")


def _process_whole_dwell(system: ReadSystem) -> None:
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)
    system.catalog.add_pipeline_release(
        release_id="read-whole-dwell-v1",
        code_revision="read-code-whole-dwell-v1",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration={"stages": configuration},
    )
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    service = ProcessingService(
        catalog=system.catalog,
        artifacts=system.artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(system.recordings),
        lease_for=timedelta(seconds=5),
        heartbeat_interval=timedelta(seconds=1),
    )
    service.create_new_capture_run(
        run_id="read-whole-dwell-run-v1",
        session_id="session-read-vertical",
        pipeline_release_id="read-whole-dwell-v1",
        input_manifest_digest=system.manifest_digest,
        scope_keys=("stream-read",),
    )
    executions = []
    while execution := service.run_once(worker_id="whole-dwell-worker"):
        executions.append(execution)
    assert len(executions) == len(registry.keys)
    assert all(item.succeeded for item in executions)
    service.finalize_run("read-whole-dwell-run-v1")


def test_whole_dwell_processing_promotes_one_bounded_presentation_run(
    read_system: ReadSystem,
) -> None:
    _process_whole_dwell(read_system)
    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    client = TestClient(create_app(repository, artifact_root=read_system.bulk_root))

    detail = client.get("/api/v1/recordings/session-read-vertical").json()
    run_id = detail["analysis"]["current_run"]["run_id"]
    assert run_id == "read-whole-dwell-run-v1"
    assert detail["analysis"]["state"] == "partial"
    assert detail["whole_dwell"]["compute_tier"] == "standard"
    assert detail["whole_dwell"]["confidence"] == "insufficient"
    assert detail["whole_dwell"]["analysis_run_id"] == run_id
    assert detail["provenance"]["analysis_run_id"] == run_id
    assert {item["analysis_run_id"] for item in detail["products"]} == {run_id}
    assert {item["kind"] for item in detail["products"]} == {
        "quality",
        "power",
        "waterfall",
        "detection",
        "qam",
        "doppler",
        "controls",
        "overlays",
        "provenance",
    }
    waterfall = next(item for item in detail["products"] if item["kind"] == "waterfall")
    content = client.get(f"/api/v1/products/{waterfall['product_id']}/content").json()
    assert content["analysis_run_id"] == run_id
    assert len(content["points"]) <= 512


def test_two_radio_single_rx1_capture_storage_standard_and_presentation_vertical(
    read_system: ReadSystem,
) -> None:
    profile = CaptureProfileV1(
        name="generated-ch4-lower-single-rx1",
        description="Generated two-radio single-RX1 TEST dwell",
        center_frequency_hz=1_709_687_500,
        rf_center_frequency_hz=11_459_687_500,
        lnb_lo_hz=9_750_000_000,
        starlink_channel="ch4",
        starlink_edge=StarlinkEdge.LOWER,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(1,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=1, gain_db=40.0),),
        sample_count=16,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        storage_policy="generated-rx1-zstd-v1",
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ("generated-radio-a", "generated-radio-b"),
        source_type=SourceType.TEST,
    )
    coordinator = AcquisitionCoordinator(
        read_system.recordings,
        compression=CompressionSettingsV1(
            policy_id=profile.storage_policy,
            target_uncompressed_bytes=16,
        ),
        config=AcquisitionConfig(
            release_lead_ns=0,
            readiness_timeout_seconds=2,
            safety_reserve_bytes=0,
            metadata_bytes_per_refill=128,
        ),
    )
    result = coordinator.capture_once(
        plan,
        {
            "generated-radio-a": FakeRadioSource("generated-radio-a", receiver_count=2, seed=71),
            "generated-radio-b": FakeRadioSource("generated-radio-b", receiver_count=2, seed=73),
        },
        session_id="generated-two-radio-rx1",
    )
    assert result.bundle is not None, result.errors
    bundle = result.bundle
    read_system.recordings.verify(bundle)
    assert (
        bundle.manifest.capture_plan.effective_synchronization_mode
        is SynchronizationMode.BEST_EFFORT
    )
    assert len(bundle.manifest.streams) == 2
    for stream in bundle.manifest.streams:
        reader = read_system.recordings.reader(bundle, stream.stream_id)
        assert reader.receiver_ids == (1,)
        assert reader.sample_count == 16
        assert reader.read(0, 16).shape == (16, 1, 2)

    read_system.catalog.create_capture_session(
        session_id=bundle.session_id,
        source_type="test",
        state="committed",
        bundle_uri=bundle.uri,
        manifest_digest=bundle.manifest_sha256,
        tags=bundle.manifest.tags,
    )
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)
    read_system.catalog.add_pipeline_release(
        release_id="generated-rx1-standard-v1",
        code_revision="generated-rx1-code-v1",
        environment_digest=DIGEST_A,
        graph_digest=DIGEST_B,
        configuration={"stages": configuration},
    )
    registry = production_long_dwell_registry(ComputeTier.STANDARD)
    processing = ProcessingService(
        catalog=read_system.catalog,
        artifacts=read_system.artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(read_system.recordings),
        lease_for=timedelta(seconds=5),
        heartbeat_interval=timedelta(seconds=1),
    )
    processing.create_new_capture_run(
        run_id="generated-rx1-run-v1",
        session_id=bundle.session_id,
        pipeline_release_id="generated-rx1-standard-v1",
        input_manifest_digest=bundle.manifest_sha256,
        scope_keys=tuple(stream.stream_id for stream in bundle.manifest.streams),
    )
    executions = []
    while execution := processing.run_once(worker_id="generated-rx1-worker"):
        executions.append(execution)
    assert len(executions) == len(registry.keys) * len(bundle.manifest.streams)
    assert all(item.succeeded for item in executions)
    processing.finalize_run("generated-rx1-run-v1")

    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    detail = (
        TestClient(create_app(repository, artifact_root=read_system.bulk_root))
        .get("/api/v1/recordings/generated-two-radio-rx1")
        .json()
    )
    assert detail["profile"]["receiver_count_per_radio"] == 1
    assert [radio["receiver_labels"] for radio in detail["radios"]] == [["rx1"], ["rx1"]]
    assert len(detail["stream_analyses"]) == 2
    assert [item["receiver_labels"] for item in detail["stream_analyses"]] == [
        ["rx1"],
        ["rx1"],
    ]
    assert {item["analysis_run_id"] for item in detail["products"]} == {"generated-rx1-run-v1"}


def test_catalog_artifact_api_vertical_uses_one_current_run(read_system: ReadSystem) -> None:
    _process(read_system)
    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    client = TestClient(create_app(repository, artifact_root=read_system.bulk_root))

    assert client.get("/api/v1/recordings").json()["total"] == 0
    search = client.get(
        "/api/v1/recordings",
        params={"include_test": True, "query": "read vertical", "held": True},
    ).json()
    assert search["total"] == 1
    assert search["items"][0]["session_id"] == "session-read-vertical"
    assert search["items"][0]["source_type"] == "TEST"

    response = client.get("/api/v1/recordings/session-read-vertical")
    assert response.status_code == 200
    detail = response.json()
    assert detail["analysis"]["current_run"]["run_id"] == "read-run-v1"
    assert detail["stage_matrix"]["analysis_run_id"] == "read-run-v1"
    assert detail["stage_matrix"]["source_stage_count"] == 2
    assert [item["stage_key"] for item in detail["stage_matrix"]["stages"]] == [
        "power",
        "quality",
    ]
    assert {item["state"] for item in detail["stage_matrix"]["stages"]} == {"succeeded"}
    assert detail["analysis"]["current_run"]["pipeline_release"] == "read-release-v1"
    assert detail["analysis"]["state"] == "complete"
    assert detail["analysis"]["coverage"]["analyzed_fraction"] == 1.0
    assert detail["hold"] == {
        "held": True,
        "reason": "automatic TEST corpus hold",
    }
    assert detail["tags"] == ["TEST"]
    assert detail["profile"]["sample_rate_hz"] == 2_500_000
    assert detail["radios"][0]["radio_id"] == "radio-read"
    assert detail["radios"][0]["gain_db"] == [30.0, 31.0]
    assert detail["synchronization"]["mode"] == "none"
    assert Path(detail["paths"]["recording_root"]).is_relative_to(read_system.bulk_root)
    assert Path(detail["paths"]["analysis_root"]).is_relative_to(read_system.bulk_root)
    assert detail["quality"]["state"] == "complete"
    assert len(detail["power"]) == 2

    current = read_system.catalog.run_seal_snapshot("read-run-v1")
    expected_paths = {
        str(read_system.artifacts.resolver.resolve(item.logical_uri, must_exist=True))
        for item in current.products
    }
    assert {item["kind"] for item in detail["products"]} == {"quality", "power"}
    assert {item["artifact_path"] for item in detail["products"]} == expected_paths
    assert {item["analysis_run_id"] for item in detail["products"]} == {"read-run-v1"}
    for product in detail["products"]:
        registered = client.get(f"/api/v1/products/{product['product_id']}")
        assert registered.status_code == 200
        assert registered.json() == product

    status = client.get("/api/v1/status").json()
    filesystem = os.statvfs(read_system.bulk_root)
    assert status["storage"]["total_bytes"] == filesystem.f_frsize * filesystem.f_blocks
    assert status["storage"]["retention_high_watermark"] == 0.7
    assert status["backlog"] == {
        "queued": 0,
        "running": 0,
        "failed": 0,
        "oldest_queued_seconds": None,
    }

    source = read_system.catalog.presentation_snapshot("session-read-vertical")
    assert source is not None and source.bundle_uri is not None
    read_system.catalog.create_capture_session(
        session_id="session-backlog",
        source_type="live",
        state="committed",
        bundle_uri=source.bundle_uri,
        manifest_digest=read_system.manifest_digest,
    )
    read_system.catalog.create_analysis_run(
        run_id="run-backlog",
        session_id="session-backlog",
        pipeline_release_id="read-release-v1",
        input_manifest_digest=read_system.manifest_digest,
        jobs=(JobDefinition(stage_key="quality"),),
    )
    queued = client.get("/api/v1/status").json()["backlog"]
    assert queued["queued"] == 1
    assert queued["oldest_queued_seconds"] is not None
    lease = read_system.catalog.claim_job(
        worker_id="backlog-worker",
        lease_for=timedelta(seconds=5),
    )
    assert lease is not None
    running = client.get("/api/v1/status").json()["backlog"]
    assert running["queued"] == 0
    assert running["running"] == 1
    read_system.catalog.fail_job(
        job_id=lease.job_id,
        worker_id=lease.worker_id,
        error="intentional status probe",
        retryable=False,
    )
    failed = client.get("/api/v1/status").json()["backlog"]
    assert failed["running"] == 0
    assert failed["failed"] == 1

    with read_system.engine.begin() as connection:
        connection.execute(
            text("UPDATE capture_session SET state = 'purged' WHERE id = 'session-read-vertical'")
        )
    purged = client.get("/api/v1/recordings/session-read-vertical").json()
    assert purged["storage_state"] == "purged"
    assert all(item["raw_path"] is None for item in purged["radios"])
    assert client.post("/api/v1/recordings", json={"operation": "forbidden"}).status_code == 405


def test_production_composition_serves_compiled_ui_and_catalog(read_system: ReadSystem) -> None:
    _process(read_system)
    (read_system.bulk_root / "qualification" / "trusted-campaigns").mkdir(parents=True)
    settings = ProductionSettings(
        database_url=read_system.engine.url.render_as_string(hide_password=False),
        bulk_root=read_system.bulk_root,
        static_directory=PROJECT_ROOT / "web" / "dist",
    )
    app = create_production_app(settings)
    try:
        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            detail = client.get("/api/v1/recordings/session-read-vertical").json()
            assert detail["analysis"]["current_run"]["run_id"] == "read-run-v1"
            standard = client.get(
                "/api/v2/recordings/session-read-vertical/standard-subjects",
                params={"include_test": True},
            )
            assert standard.status_code == 503
            assert standard.json()["detail"] == "Standard-v2 presentation is unavailable"
            assert app.state.production_settings.host == "0.0.0.0"
    finally:
        app.state.catalog_engine.dispose()


def test_recording_list_pages_521_rows_without_opening_bundles(
    read_system: ReadSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    with read_system.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO capture_session
                    (id, source_type, state, bundle_uri, manifest_digest, attributes,
                     allocated_bytes, raw_available, observed_start_at, observed_end_at)
                SELECT
                    'bulk-page-' || n, 'live', 'committed',
                    'bulk://recordings/2030/01/01/bulk-page-' || n, :digest,
                    jsonb_build_object('presentation', jsonb_build_object(
                        'title', 'Bulk page recording ' || n,
                        'profile_name', 'standard-60s', 'duration_seconds', 60.0)),
                    1, true, now() - make_interval(secs => n),
                    now() - make_interval(secs => n) + interval '60 seconds'
                FROM generate_series(1, 521) AS n
                """
            ),
            {"digest": DIGEST_A},
        )
    monkeypatch.setattr(
        read_system.recordings,
        "inspect_uri",
        lambda *_args, **_kwargs: pytest.fail("list request opened a recording bundle"),
    )
    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    client = TestClient(create_app(repository, artifact_root=read_system.bulk_root))

    started = time.perf_counter()
    response = client.get(
        "/api/v1/recordings",
        params={"query": "bulk-page-", "cursor": 20, "limit": 25},
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 521
    assert len(payload["items"]) == 25
    assert payload["next_cursor"] == 45
    assert elapsed < 0.75


def test_recording_list_filters_current_analysis_without_opening_products(
    read_system: ReadSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    _process(read_system)
    monkeypatch.setattr(
        read_system.recordings,
        "inspect_uri",
        lambda *_args, **_kwargs: pytest.fail("list request opened a recording bundle"),
    )
    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )

    response = TestClient(create_app(repository, artifact_root=read_system.bulk_root)).get(
        "/api/v1/recordings",
        params={"include_test": True, "analysis_state": "complete"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["analysis"]["state"] == "complete"
    assert payload["items"][0]["analysis"]["coverage"]["analyzed_fraction"] == 1.0
