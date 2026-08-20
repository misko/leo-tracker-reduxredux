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
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.analysis.power import PowerAnalyzer
from leo.analysis.quality import QualityAnalyzer
from leo.api import ProductionSettings, create_app, create_production_app
from leo.application import CatalogPresentationRepository, CatalogStandardPresentationRepository
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, JobDefinition, create_session_factory
from leo.contracts.digests import sha256_digest
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
from leo.operations.service import _stream_registrations
from leo.pipeline import AnalyzerRegistry, compile_standard_run_plan
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
STANDARD_RELEASE = "d" * 40


@dataclass(frozen=True, slots=True)
class ReadSystem:
    catalog: CatalogRepository
    engine: Engine
    bulk_root: Path
    recordings: RecordingStore
    artifacts: AnalysisArtifactStore
    bundle: PublishedBundle
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
        bundle = _publish_test_recording(catalog, recordings)
        yield ReadSystem(
            catalog=catalog,
            engine=engine,
            bulk_root=bulk_root,
            recordings=recordings,
            artifacts=artifacts,
            bundle=bundle,
            manifest_digest=bundle.manifest_sha256,
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _publish_test_recording(
    catalog: CatalogRepository,
    recordings: RecordingStore,
    *,
    session_id: str = "session-read-vertical",
    radio_id: str = "radio-read",
    source_type: SourceType = SourceType.TEST,
    sample_count: int = 16,
) -> PublishedBundle:
    imported = source_type is SourceType.IMPORT
    profile = CaptureProfileV1(
        name="read-vertical",
        description="Imported read vertical" if imported else "TEST read vertical",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=31.0),
        ),
        sample_count=sample_count,
        refill_samples=min(sample_count, 512),
        settle_seconds=Decimal(0),
        prime_refills=0,
        storage_policy="test-zstd-v1",
        tags=("READ",) if imported else ("TEST",),
        starlink_channel="ch4" if imported else None,
        starlink_edge=StarlinkEdge.LOWER if imported else None,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        [radio_id],
        source_type=source_type,
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
        target_uncompressed_bytes=sample_count * 4,
    )
    radio = FakeRadioSource(radio_id, receiver_count=2, seed=37)
    radio.open()
    radio.configure(settings)
    writer = recordings.begin(session_id, compression)
    stream_writer = writer.open_stream("stream-read", radio.identity, (0, 1))
    refill_samples = min(sample_count, 512)
    for _ in range(sample_count // refill_samples):
        stream_writer.append(radio.read_block(refill_samples))
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
        source_type=source_type,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=profile.tags,
        streams=(
            RecordingStreamV1(
                stream_id="stream-read",
                radio=radio.identity,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=sample_count,
                captured_sample_count=sample_count,
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
    attributes = {
        "presentation": {
            "title": profile.description,
            "profile_name": profile.name,
            "duration_seconds": manifest.capture_plan.resolved_sample_count
            / profile.sample_rate_hz,
        }
    }
    if imported:
        topology = _station_topology(published.manifest)
        catalog.register_station_topology(topology)
        authority = CaptureHardwareBindingV1.create(
            published.manifest,
            observed_manifest_file_digest=published.manifest_sha256,
            topology=topology,
        )
        assert catalog.reconcile_capture_session(
            session_id=manifest.session_id,
            source_type=source_type.value,
            bundle_uri=published.uri,
            manifest_digest=published.manifest_sha256,
            allocated_bytes=sum(
                item.stat().st_size for item in published.path.rglob("*") if item.is_file()
            ),
            attributes=attributes,
            tags=manifest.tags,
            streams=_stream_registrations(published),
            path_authority=authority,
        )
    else:
        catalog.create_capture_session(
            session_id=manifest.session_id,
            source_type=source_type.value,
            state="committed",
            bundle_uri=published.uri,
            manifest_digest=published.manifest_sha256,
            attributes=attributes,
            tags=manifest.tags,
        )
    return published


def _station_topology(manifest: RecordingManifestV1) -> StationReceiverTopologyV1:
    timings = tuple(stream.timing for stream in manifest.streams)
    assert all(timing is not None for timing in timings)
    valid_from = min(timing.first_sample.earliest_utc_ns for timing in timings if timing) - 1
    valid_until = max(timing.last_sample.latest_utc_ns for timing in timings if timing) + 1_000_000
    radios = tuple(
        StationRadioTopologyV1.create(
            radio_id=stream.radio.radio_id,
            radio_serial=stream.radio.serial,
            endpoint_evidence=RadioEndpointEvidenceV1(
                transport=stream.radio.transport,
                endpoint=stream.radio.uri,
                evidence_uri=f"test://{manifest.session_id}/{stream.radio.radio_id}",
                evidence_digest=sha256_digest(
                    f"{manifest.session_id}:{stream.radio.radio_id}".encode()
                ),
            ),
            receiver_assignments=tuple(
                StationReceiverAssignmentV1(
                    receiver_id=receiver_id,
                    physical_receiver_id=f"test-{stream.radio.radio_id}-rx{receiver_id}",
                    hardware_epoch_external_id=(
                        f"test-{stream.radio.radio_id}-rx{receiver_id}-epoch-v1"
                    ),
                    valid_from_utc_ns=valid_from,
                    valid_until_utc_ns=valid_until,
                )
                for receiver_id in (0, 1)
            ),
        )
        for stream in manifest.streams
    )
    return StationReceiverTopologyV1.create(
        station_id=f"test-{manifest.session_id}",
        topology_revision=f"{manifest.session_id}-v1",
        valid_from_utc_ns=valid_from,
        valid_until_utc_ns=valid_until,
        radios=radios,
    )


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


def _process_standard(
    system: ReadSystem,
    bundle: PublishedBundle,
    *,
    run_id: str,
) -> None:
    configuration: dict[str, object] = {
        "display_version": "2.0.0",
        "stages": production_standard_v2_configuration(),
    }
    registry = production_standard_v2_registry()
    executable = system.bulk_root.parent / f"{run_id}-worker"
    executable.mkdir()
    (executable / "standard-v2.txt").write_text("pinned integration worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=STANDARD_RELEASE,
        code_revision=STANDARD_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "read-vertical-standard-v2"},
        executable_root=executable,
    )
    system.catalog.add_pipeline_release(
        release_id=STANDARD_RELEASE,
        code_revision=STANDARD_RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )
    pinned = PinnedLocalRoot(system.bulk_root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    service = ProcessingService(
        catalog=system.catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(recordings),
        lease_for=timedelta(seconds=5),
        heartbeat_interval=timedelta(seconds=1),
        loaded_worker_release=loaded,
    )
    plan = compile_standard_run_plan(
        bundle.manifest,
        manifest_digest=bundle.manifest_sha256,
        pipeline_release_id=STANDARD_RELEASE,
    )
    try:
        service.create_expanded_run(run_id=run_id, plan=plan, trigger="new_capture")
        executions = []
        while execution := service.run_once(worker_id="standard-v2-worker"):
            executions.append(execution)
        assert len(executions) == len(plan.jobs)
        assert all(item.succeeded for item in executions)
        service.finalize_run(run_id)
    finally:
        service.close()
        artifacts.close()
        pinned.close()


def test_whole_dwell_processing_promotes_one_bounded_presentation_run(
    read_system: ReadSystem,
) -> None:
    session_id = "session-read-vertical-standard"
    bundle = _publish_test_recording(
        read_system.catalog,
        read_system.recordings,
        session_id=session_id,
        radio_id="radio-read-standard",
        source_type=SourceType.IMPORT,
        sample_count=2_048,
    )
    _process_standard(
        read_system,
        bundle,
        run_id="read-whole-dwell-run-v1",
    )
    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    standard_repository = CatalogStandardPresentationRepository(
        read_system.catalog,
        read_system.artifacts,
    )
    client = TestClient(
        create_app(
            repository,
            artifact_root=read_system.bulk_root,
            standard_repository=standard_repository,
        )
    )

    detail = client.get(f"/api/v1/recordings/{session_id}").json()
    run_id = detail["analysis"]["current_run"]["run_id"]
    assert run_id == "read-whole-dwell-run-v1"
    assert detail["provenance"]["analysis_run_id"] == run_id
    assert {item["analysis_run_id"] for item in detail["products"]} == {run_id}
    hierarchy = client.get(f"/api/v2/recordings/{session_id}/standard-subjects").json()
    assert len(hierarchy["rows"]) == 1
    assert len(hierarchy["rows"][0]["receiver_paths"]) == 2
    subject_id = hierarchy["rows"][0]["receiver_paths"][0]["subject_id"]
    quality = client.get(
        f"/api/v2/recordings/{session_id}/standard-subjects/{subject_id}/views/quality",
        params={"maximum_points": 512},
    )
    assert quality.status_code == 200, quality.text
    assert quality.json()["returned_point_count"] <= 512


def test_two_radio_single_rx1_capture_storage_standard_and_presentation_vertical(
    read_system: ReadSystem,
) -> None:
    profile = CaptureProfileV1(
        name="generated-ch4-lower-single-rx1",
        description="Generated two-radio single-RX1 imported dwell",
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
        sample_count=2_048,
        refill_samples=512,
        settle_seconds=Decimal(0),
        prime_refills=0,
        storage_policy="generated-rx1-zstd-v1",
        tags=("READ",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ("generated-radio-a", "generated-radio-b"),
        source_type=SourceType.IMPORT,
    )
    coordinator = AcquisitionCoordinator(
        read_system.recordings,
        compression=CompressionSettingsV1(
            policy_id=profile.storage_policy,
            target_uncompressed_bytes=2_048,
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
        assert reader.sample_count == 2_048
        assert reader.read(0, 2_048).shape == (2_048, 1, 2)

    topology = _station_topology(bundle.manifest)
    read_system.catalog.register_station_topology(topology)
    authority = CaptureHardwareBindingV1.create(
        bundle.manifest,
        observed_manifest_file_digest=bundle.manifest_sha256,
        topology=topology,
    )
    assert read_system.catalog.reconcile_capture_session(
        session_id=bundle.session_id,
        source_type=SourceType.IMPORT.value,
        bundle_uri=bundle.uri,
        manifest_digest=bundle.manifest_sha256,
        allocated_bytes=sum(
            item.stat().st_size for item in bundle.path.rglob("*") if item.is_file()
        ),
        attributes={"presentation": {"title": profile.description}},
        tags=bundle.manifest.tags,
        streams=_stream_registrations(bundle),
        path_authority=authority,
    )
    _process_standard(
        read_system,
        bundle,
        run_id="generated-rx1-run-v1",
    )

    repository = CatalogPresentationRepository(
        read_system.catalog,
        read_system.recordings,
        read_system.artifacts,
        bulk_root=read_system.bulk_root,
    )
    client = TestClient(
        create_app(
            repository,
            artifact_root=read_system.bulk_root,
            standard_repository=CatalogStandardPresentationRepository(
                read_system.catalog,
                read_system.artifacts,
            ),
        )
    )
    detail = client.get("/api/v1/recordings/generated-two-radio-rx1").json()
    assert detail["profile"]["receiver_count_per_radio"] == 1
    assert [radio["receiver_labels"] for radio in detail["radios"]] == [["rx1"], ["rx1"]]
    assert len(detail["stream_analyses"]) == 2
    assert [item["receiver_labels"] for item in detail["stream_analyses"]] == [
        ["rx1"],
        ["rx1"],
    ]
    assert {item["analysis_run_id"] for item in detail["products"]} == {"generated-rx1-run-v1"}
    hierarchy = client.get("/api/v2/recordings/generated-two-radio-rx1/standard-subjects")
    assert hierarchy.status_code == 200, hierarchy.text
    assert len(hierarchy.json()["rows"]) == 3


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
