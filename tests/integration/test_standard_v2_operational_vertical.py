from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema
from typer.testing import CliRunner

from leo.analysis.adapters import (
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.analysis.research import (
    production_research_v1_configuration,
    production_research_v1_registry,
    research_pipeline_definition_id,
)
from leo.application import CatalogStandardPresentationRepository, StandardReprocessService
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_session_factory
from leo.cli.app import create_cli
from leo.cli.composition import BackendFactory
from leo.cli.processing import LocalProcessingBackend, ProcessingServices
from leo.contracts.pipeline_lanes import PipelineLane
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
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
    RadioTransport,
    SourceType,
    StarlinkEdge,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.operations.service import _stream_registrations
from leo.pipeline import compile_standard_run_plan
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import CaptureHardwareBindingV1, StationReceiverTopologyV1
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE = "2" * 40
SESSION = "standard-v2-operational-2x2"
START_NS = 1_786_600_000_000_000_000
SAMPLE_RATE = 2_500_000
pytestmark = pytest.mark.postgres
runner = CliRunner()


@pytest.fixture
def standard_database(tmp_path: Path) -> Iterator[tuple[CatalogRepository, Engine, Path]]:
    base_url = os.environ.get("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker")
    schema = f"leo_standard_vertical_{uuid.uuid4().hex}"
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
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield CatalogRepository(create_session_factory(engine)), engine, tmp_path / "bulk"
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_standard_v2_four_path_operational_vertical(
    standard_database: tuple[CatalogRepository, Engine, Path],
    tmp_path: Path,
) -> None:
    catalog, engine, bulk_root = standard_database
    topology = StationReceiverTopologyV1.model_validate_json(
        (PROJECT_ROOT / "deploy/station/gauss-four-path-postreboot-20260816-v1.json").read_bytes()
    )
    recordings = RecordingStore(bulk_root)
    published = _publish_four_path_recording(recordings, topology)
    catalog.register_station_topology(topology)
    authority = CaptureHardwareBindingV1.create(
        published.manifest,
        observed_manifest_file_digest=published.manifest_sha256,
        topology=topology,
    )
    assert catalog.reconcile_capture_session(
        session_id=SESSION,
        source_type=SourceType.IMPORT.value,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        allocated_bytes=sum(
            item.stat().st_size for item in published.path.rglob("*") if item.is_file()
        ),
        attributes={"presentation": {"title": "bounded Standard-v2 2x2", "duration_seconds": 1.0}},
        streams=_stream_registrations(published),
        path_authority=authority,
    )

    standard_configuration = production_standard_v2_configuration()
    research_configuration = production_research_v1_configuration()
    research_definition_id = research_pipeline_definition_id(
        pipeline_release_id=RELEASE,
        configuration=research_configuration,
    )
    configuration: dict[str, object] = {
        "display_version": "2.0.0",
        "pipeline": "standard-research-v1",
        "research_definition_id": research_definition_id,
        "pipeline_lanes": {
            "standard": {"stages": standard_configuration},
            "research": {"stages": research_configuration},
        },
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "standard-v2.txt").write_text("pinned test executable\n")
    registry = production_standard_v2_registry()
    research_registry = production_research_v1_registry(research_definition_id)
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=RELEASE,
        code_revision=RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "bounded-real-pg-standard-v2"},
        executable_root=executable,
        lane_registries={"standard": registry, "research": research_registry},
    )
    catalog.add_pipeline_release(
        release_id=RELEASE,
        code_revision=RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )
    plan = compile_standard_run_plan(
        published.manifest,
        manifest_digest=published.manifest_sha256,
        pipeline_release_id=RELEASE,
    )
    assert (len(plan.jobs), len(plan.edges)) == (8, 10)

    pinned = PinnedLocalRoot(bulk_root)
    pinned_recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    service = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(pinned_recordings),
        lease_for=timedelta(seconds=30),
        heartbeat_interval=timedelta(seconds=5),
        loaded_worker_release=loaded,
        lane_registries={PipelineLane.RESEARCH: research_registry},
    )
    try:
        service.create_expanded_run(run_id="standard-v2-operational-run", plan=plan)
        queued = catalog.active_jobs(limit=200)
        assert len(queued) == 8
        assert {item.state for item in queued} == {"pending"}
        assert {item.session_id for item in queued} == {SESSION}
        path_job = next(item for item in queued if item.stage_key == "path-standard")
        assert path_job.stream_id in {"stream-0", "stream-1"}
        assert path_job.radio_id in {"radio_pluto_5d4d", "radio_pluto_19f2"}
        assert path_job.receiver_id in {0, 1}
        executions = []
        while execution := service.run_once(worker_id="standard-v2-test-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == 8
        service.finalize_run("standard-v2-operational-run")

        seal = catalog.run_seal_snapshot("standard-v2-operational-run")
        assert len(seal.jobs) == 8
        expected_product_count = sum(
            len(registry.get(job.stage_key).spec.output_products) for job in plan.jobs
        )
        assert expected_product_count == 98
        assert len(seal.products) == expected_product_count
        assert catalog.current_run_id(SESSION) == "standard-v2-operational-run"
        with engine.connect() as connection:
            dependency_count = connection.execute(
                text("SELECT count(*) FROM processing_job_dependency")
            ).scalar_one()
            product_dependency_count = connection.execute(
                text("SELECT count(*) FROM product_dependency")
            ).scalar_one()
        assert dependency_count == 10
        assert product_dependency_count >= len(plan.edges)
        paired = next(item for item in seal.products if item.kind == "standard.paired-report")
        closure = catalog.product_dependency_closure(paired.product_id)
        assert len(closure) >= 11
        assert {
            "standard.path-report",
            "standard.path-presentation",
            "standard.radio-report",
            "standard.paired-report",
        }.issubset({item.kind for item in closure})
        paired_pngs = tuple(
            item
            for item in seal.products
            if item.scope is not None
            and item.scope.kind.value == "paired"
            and item.media_type == "image/png"
        )
        assert {item.kind for item in paired_pngs} == {
            "standard.waterfall-png",
            "standard.pilot-methods-png",
            "standard.cfo-trajectories-png",
            "standard.cfo-trajectories-dealiased-png",
            "standard.cfo-trajectories-final-png",
        }
        assert all(
            artifacts.read_bytes(item.logical_uri, item.digest).startswith(b"\x89PNG")
            for item in paired_pngs
        )

        presentation = CatalogStandardPresentationRepository(catalog, artifacts)
        hierarchy = presentation.subject_hierarchy(SESSION)
        assert hierarchy is not None
        assert len(hierarchy.rows) == 3
        assert sum(len(item.receiver_paths) for item in hierarchy.rows[1:]) == 4
        paired_subject = next(
            item for item in hierarchy.rows if item.subject_kind.value == "paired"
        )
        detail = presentation.subject_detail(SESSION, paired_subject.subject_id)
        assert detail is not None
        assert {item.view_kind for item in detail.views} == set(StandardViewKindV2)
        for view_kind in StandardViewKindV2:
            view = presentation.subject_view(
                SESSION, paired_subject.subject_id, view_kind, maximum_points=2048
            )
            assert view is not None
            assert view.view_kind is view_kind

        service.create_expanded_run(
            run_id="research-v1-operational-run",
            plan=plan,
            pipeline_lane=PipelineLane.RESEARCH,
        )
        research_executions = []
        while execution := service.run_once(worker_id="research-v1-test-worker"):
            research_executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(research_executions) == 8
        service.finalize_run("research-v1-operational-run")

        research_seal = catalog.run_seal_snapshot("research-v1-operational-run")
        assert len(research_seal.products) == expected_product_count
        assert all(item.kind.startswith("research.") for item in research_seal.products)
        assert catalog.current_run_id(SESSION) == "standard-v2-operational-run"
        assert (
            catalog.current_run_id(SESSION, PipelineLane.RESEARCH) == "research-v1-operational-run"
        )
        research_manifest_reference = catalog.run_manifest_reference("research-v1-operational-run")
        research_manifest = artifacts.read_json(
            research_manifest_reference.logical_uri,
            research_manifest_reference.digest,
        )
        assert research_manifest["schema_version"] == 2
        assert research_manifest["pipeline_lane"] == "research"
        research_presentation = CatalogStandardPresentationRepository(
            catalog, artifacts, pipeline_lane=PipelineLane.RESEARCH
        )
        research_hierarchy = research_presentation.subject_hierarchy(SESSION)
        assert research_hierarchy is not None
        research_pair = next(
            item for item in research_hierarchy.rows if item.subject_kind.value == "paired"
        )
        research_detail = research_presentation.subject_detail(SESSION, research_pair.subject_id)
        assert research_detail is not None
        assert {item.view_kind for item in research_detail.views} == set(StandardViewKindV2)
        for view_kind in StandardViewKindV2:
            assert (
                research_presentation.subject_view(
                    SESSION,
                    research_pair.subject_id,
                    view_kind,
                    maximum_points=2048,
                )
                is not None
            )
    finally:
        service.close()
        artifacts.close()
        pinned.close()


def test_cli_reprocess_uses_typed_plan_and_dry_run_is_read_only(
    standard_database: tuple[CatalogRepository, Engine, Path],
    tmp_path: Path,
) -> None:
    catalog, engine, bulk_root = standard_database
    topology = StationReceiverTopologyV1.model_validate_json(
        (PROJECT_ROOT / "deploy/station/gauss-four-path-postreboot-20260816-v1.json").read_bytes()
    )
    recordings = RecordingStore(bulk_root)
    published = _publish_four_path_recording(recordings, topology, sample_count=16)
    catalog.register_station_topology(topology)
    authority = CaptureHardwareBindingV1.create(
        published.manifest,
        observed_manifest_file_digest=published.manifest_sha256,
        topology=topology,
    )
    assert catalog.reconcile_capture_session(
        session_id=SESSION,
        source_type=SourceType.IMPORT.value,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        allocated_bytes=sum(
            item.stat().st_size for item in published.path.rglob("*") if item.is_file()
        ),
        attributes={"presentation": {"title": "typed reprocess", "duration_seconds": 0.0}},
        streams=_stream_registrations(published),
        path_authority=authority,
    )
    configuration: dict[str, object] = {
        "display_version": "2.0.0",
        "stages": production_standard_v2_configuration(),
    }
    executable = tmp_path / "reprocess-worker"
    executable.mkdir()
    (executable / "standard-v2.txt").write_text("pinned typed reprocess executable\n")
    registry = production_standard_v2_registry()
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=RELEASE,
        code_revision=RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "typed-reprocess-real-pg"},
        executable_root=executable,
    )
    catalog.add_pipeline_release(
        release_id=RELEASE,
        code_revision=RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )
    pinned = PinnedLocalRoot(bulk_root)
    pinned_recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    processing = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(pinned_recordings),
        lease_for=timedelta(seconds=30),
        heartbeat_interval=timedelta(seconds=5),
        loaded_worker_release=loaded,
    )
    services = ProcessingServices(
        catalog=catalog,
        recordings=pinned_recordings,
        artifacts=artifacts,
        processing=processing,
        holds=cast(Any, None),
        retention=cast(Any, None),
        reconciliation=cast(Any, None),
        importer=cast(Any, None),
        corpus_ingest=cast(Any, None),
        pipeline_release_id=RELEASE,
    )
    backend = LocalProcessingBackend(services)
    app = create_cli(cast(BackendFactory, lambda: backend))
    counted_tables = (
        "analysis_run",
        "processing_job",
        "processing_job_dependency",
        "raw_integrity_attestation",
        "run_subject_binding",
    )
    try:
        with engine.connect() as connection:
            before = tuple(
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in counted_tables
            )
        dry = runner.invoke(
            app,
            ["process", "reprocess", SESSION, "--dry-run", "--json"],
        )
        assert dry.exit_code == 0, dry.stdout
        assert json.loads(dry.stdout)["payload"]["state"] == "dry_run"
        with engine.connect() as connection:
            after = tuple(
                connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in counted_tables
            )
        assert after == before

        queued = runner.invoke(app, ["process", "reprocess", SESSION, "--json"])
        assert queued.exit_code == 0, queued.stdout
        payload = json.loads(queued.stdout)["payload"]
        assert payload["pipeline_release_id"] == RELEASE
        assert payload["state"] == "queued"
        with engine.connect() as connection:
            job_count = connection.execute(text("SELECT count(*) FROM processing_job")).scalar_one()
            edge_count = connection.execute(
                text("SELECT count(*) FROM processing_job_dependency")
            ).scalar_one()
            subject_count = connection.execute(
                text("SELECT count(*) FROM run_subject_binding")
            ).scalar_one()
            assert (job_count, edge_count, subject_count) == (8, 10, 5)
        assert catalog.active_run_id(SESSION) == payload["run_id"]
        refused = runner.invoke(
            app,
            ["process", "reprocess", SESSION, "--dry-run", "--json"],
        )
        assert refused.exit_code != 0
        assert "already has an active analysis run" in json.loads(refused.stdout)["message"]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM analysis_run")).scalar_one() == 1

        assert catalog.cancel_analysis_run(run_id=payload["run_id"], reason="exercise API service")
        api_result = StandardReprocessService(
            catalog=catalog,
            recordings=pinned_recordings,
            processing=processing,
            pipeline_release_id=RELEASE,
        ).queue(SESSION)
        assert api_result.previous_current_run_id is None
        assert api_result.queued_job_count == 8
        assert catalog.active_run_id(SESSION) == api_result.run_id
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM analysis_run")).scalar_one() == 2
            assert (
                connection.execute(text("SELECT count(*) FROM processing_job")).scalar_one() == 16
            )
    finally:
        processing.close()
        artifacts.close()
        pinned.close()


def _publish_four_path_recording(
    recordings: RecordingStore,
    topology: StationReceiverTopologyV1,
    *,
    sample_count: int = SAMPLE_RATE,
) -> PublishedBundle:
    radio_ids = tuple(radio.radio_id for radio in topology.radios)
    gains = (
        ReceiverGainV1(receiver_id=0, gain_db=30.0),
        ReceiverGainV1(receiver_id=1, gain_db=30.0),
    )
    profile = CaptureProfileV1(
        name="standard-v2-operational",
        center_frequency_hz=1_709_687_500,
        sample_rate_hz=SAMPLE_RATE,
        bandwidth_hz=SAMPLE_RATE,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=gains,
        sample_count=sample_count,
        storage_policy="test-zstd-v1",
        starlink_channel="ch4",
        starlink_edge=StarlinkEdge.LOWER,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile), radio_ids, source_type=SourceType.IMPORT
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=SAMPLE_RATE,
        bandwidth_hz=SAMPLE_RATE,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=gains,
    )
    compression = CompressionSettingsV1(
        policy_id="test-zstd-v1", level=3, target_uncompressed_bytes=4_000_000
    )
    writer = recordings.begin(SESSION, compression)
    streams = []
    for ordinal, radio in enumerate(topology.radios):
        identity = RadioIdentityV1(
            radio_id=radio.radio_id,
            serial=radio.radio_serial,
            uri=radio.endpoint_evidence.endpoint,
            transport=RadioTransport.IIO_IP,
        )
        source = FakeRadioSource(radio.radio_id, seed=31 + ordinal, utc_origin_ns=START_NS)
        source.open()
        source.configure(settings)
        stream_id = f"stream-{ordinal}"
        stream_writer = writer.open_stream(stream_id, identity, (0, 1))
        remaining = sample_count
        while remaining:
            block_samples = min(remaining, SAMPLE_RATE // 10)
            stream_writer.append(source.read_block(block_samples))
            remaining -= block_samples
        receipt = stream_writer.finalize()
        source.close()
        timing = StreamTimingV1(
            first_sample=TimingEstimateV1(
                estimate_utc_ns=START_NS,
                earliest_utc_ns=START_NS,
                latest_utc_ns=START_NS,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
            last_sample=TimingEstimateV1(
                estimate_utc_ns=START_NS + (sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
                earliest_utc_ns=START_NS + (sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
                latest_utc_ns=START_NS + (sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
                method=TimingMethod.DEVICE_COUNTER_ANCHORED,
            ),
        )
        streams.append(
            RecordingStreamV1(
                stream_id=stream_id,
                radio=identity,
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
            )
        )
    manifest = RecordingManifestV1(
        session_id=SESSION,
        state=CaptureState.COMMITTED,
        source_type=SourceType.IMPORT,
        created_utc_ns=START_NS,
        finalized_utc_ns=START_NS + 2_000_000_000,
        capture_plan=plan,
        tags=(),
        streams=tuple(streams),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.BEST_EFFORT,
            grade=SynchronizationGrade.BEST_EFFORT_OBSERVED,
            stream_ids=tuple(item.stream_id for item in streams),
            estimated_start_skew_ns=0,
            start_skew_uncertainty_ns=0,
            estimated_overlap_ns=(sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
            estimated_overlap_start_utc_ns=START_NS,
            estimated_overlap_end_utc_ns=START_NS
            + (sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
            guaranteed_overlap_ns=(sample_count - 1) * 1_000_000_000 // SAMPLE_RATE,
            overlap_fraction=1.0,
        ),
        compression=compression,
        host=HostIdentityV1(hostname="standard-v2-test"),
        producer=ProducerV1(name="standard-v2-operational-test", version="1"),
    )
    return writer.publish(manifest)
