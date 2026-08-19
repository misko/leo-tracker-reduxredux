from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.analysis.adapters import (
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.application import CatalogStandardPresentationRepository
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_session_factory
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

    configuration: dict[str, object] = {
        "display_version": "2.0.0",
        "stages": production_standard_v2_configuration(),
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "standard-v2.txt").write_text("pinned test executable\n")
    registry = production_standard_v2_registry()
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=RELEASE,
        code_revision=RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "bounded-real-pg-standard-v2"},
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
    plan = compile_standard_run_plan(
        published.manifest,
        manifest_digest=published.manifest_sha256,
        pipeline_release_id=RELEASE,
    )
    assert (len(plan.jobs), len(plan.edges)) == (43, 94)

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
    )
    try:
        service.create_expanded_run(run_id="standard-v2-operational-run", plan=plan)
        executions = []
        while execution := service.run_once(worker_id="standard-v2-test-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == 43
        service.finalize_run("standard-v2-operational-run")

        seal = catalog.run_seal_snapshot("standard-v2-operational-run")
        assert len(seal.jobs) == 43
        assert len(seal.products) == 47
        assert catalog.current_run_id(SESSION) == "standard-v2-operational-run"
        with engine.connect() as connection:
            dependency_count = connection.execute(
                text("SELECT count(*) FROM processing_job_dependency")
            ).scalar_one()
            product_dependency_count = connection.execute(
                text("SELECT count(*) FROM product_dependency")
            ).scalar_one()
        assert dependency_count == 94
        assert product_dependency_count == 110
        paired = next(item for item in seal.products if item.kind == "standard.paired-report")
        closure = catalog.product_dependency_closure(paired.product_id)
        assert len(closure) == 43
        assert {item.kind for item in closure} == {
            "standard.path-input-bind",
            "quality.summary",
            "standard.power-timeline",
            "standard.numerical-waterfall",
            "standard.probe-schedule",
            "standard.pilot-scan",
            "standard.trajectory-bank",
            "standard.trajectory-feedback",
            "standard.glrt64-trajectory-table",
            "standard.path-report",
            "standard.radio-report",
            "standard.paired-report",
        }

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
    finally:
        service.close()
        artifacts.close()
        pinned.close()


def _publish_four_path_recording(
    recordings: RecordingStore,
    topology: StationReceiverTopologyV1,
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
        sample_count=SAMPLE_RATE,
        storage_policy="test-zstd-v1",
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
        for _ in range(10):
            stream_writer.append(source.read_block(SAMPLE_RATE // 10))
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
                estimate_utc_ns=START_NS + 999_999_600,
                earliest_utc_ns=START_NS + 999_999_600,
                latest_utc_ns=START_NS + 999_999_600,
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
                requested_sample_count=SAMPLE_RATE,
                captured_sample_count=SAMPLE_RATE,
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
            estimated_overlap_ns=999_999_600,
            estimated_overlap_start_utc_ns=START_NS,
            estimated_overlap_end_utc_ns=START_NS + 999_999_600,
            guaranteed_overlap_ns=999_999_600,
            overlap_fraction=1.0,
        ),
        compression=compression,
        host=HostIdentityV1(hostname="standard-v2-test"),
        producer=ProducerV1(name="standard-v2-operational-test", version="1"),
    )
    return writer.publish(manifest)
