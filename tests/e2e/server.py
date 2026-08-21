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
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.api import ProductionSettings, create_production_app
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_session_factory
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
from leo.pipeline import compile_standard_run_plan
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
    current_low_band_targets,
)
from leo.station.authority import (
    CaptureHardwareBindingV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get(
    "LEO_E2E_DATABASE_URL",
    os.environ.get("LEO_TEST_DATABASE_URL", "postgresql+psycopg:///leo_tracker"),
)
PIPELINE_RELEASE = "e" * 40
CURRENT_RUN_ID = "e2e-main-run-v2"
REPLACED_RUN_ID = "e2e-main-run-v1"
MAIN_SESSION_ID = "e2e-main-test-recording"
FAILED_SESSION_ID = "e2e-failed-test-recording"
PENDING_SESSION_ID = "e2e-pending-test-recording"
SAMPLE_RATE_HZ = 2_500_000
SAMPLE_COUNT = 2_048
BASE_UTC_NS = 1_780_000_000_000_000_000


@dataclass(frozen=True, slots=True)
class PublishedInput:
    bundle: PublishedBundle

    @property
    def session_id(self) -> str:
        return self.bundle.manifest.session_id

    @property
    def manifest_digest(self) -> str:
        return self.bundle.manifest_sha256


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
    receiver_ids = (0, 1) if paired else (0,)
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        description=(
            "Production E2E paired imported dwell"
            if paired
            else "Production E2E intentional analysis failure"
        ),
        center_frequency_hz=1_709_687_500,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=2_500_000,
        receivers=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=receiver_id, gain_db=34.0) for receiver_id in receiver_ids
        ),
        sample_count=SAMPLE_COUNT,
        refill_samples=512,
        settle_seconds=0,
        prime_refills=0,
        synchronization_mode=(
            SynchronizationMode.BEST_EFFORT if paired else SynchronizationMode.NONE
        ),
        storage_policy="e2e-zstd-v1",
        tags=("E2E",),
        starlink_channel="ch4",
        starlink_edge=StarlinkEdge.LOWER,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        radio_ids,
        source_type=SourceType.IMPORT,
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
        radio = FakeRadioSource(
            radio_id,
            receiver_count=len(receiver_ids),
            seed=seed + index,
        )
        radio.open()
        radio.configure(settings)
        stream_id = f"stream-{index + 1}"
        stream_writer = writer.open_stream(stream_id, radio.identity, receiver_ids)
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
        source_type=SourceType.IMPORT,
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
    topology = _station_topology(published.manifest)
    catalog.register_station_topology(topology)
    authority = CaptureHardwareBindingV1.create(
        published.manifest,
        observed_manifest_file_digest=published.manifest_sha256,
        topology=topology,
    )
    catalog.reconcile_capture_session(
        session_id=session_id,
        source_type="import",
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        tags=manifest.tags,
        attributes={"presentation": {"title": profile.description}},
        allocated_bytes=sum(
            chunk.compressed_bytes for stream in streams for chunk in stream.chunks
        ),
        streams=_stream_registrations(published),
        path_authority=authority,
    )
    return PublishedInput(published)


def _station_topology(manifest: RecordingManifestV1) -> StationReceiverTopologyV1:
    """Create explicit synthetic station authority for the generated E2E capture."""

    valid_from = manifest.created_utc_ns - 1_000_000_000
    valid_until = manifest.finalized_utc_ns + 1_000_000_000
    radios = tuple(
        StationRadioTopologyV1.create(
            radio_id=stream.radio.radio_id,
            radio_serial=stream.radio.serial,
            endpoint_evidence=RadioEndpointEvidenceV1(
                transport=stream.radio.transport,
                endpoint=stream.radio.uri,
                evidence_uri=f"e2e://{manifest.session_id}/{stream.radio.radio_id}",
                evidence_digest=sha256_digest(
                    f"{manifest.session_id}:{stream.radio.radio_id}".encode()
                ),
            ),
            receiver_assignments=tuple(
                StationReceiverAssignmentV1(
                    receiver_id=receiver_id,
                    physical_receiver_id=f"e2e-{stream.radio.radio_id}-rx{receiver_id}",
                    hardware_epoch_external_id=(
                        f"e2e-{stream.radio.radio_id}-rx{receiver_id}-epoch-v1"
                    ),
                    valid_from_utc_ns=valid_from,
                    valid_until_utc_ns=valid_until,
                )
                # Station authority describes the complete physical radio,
                # including the RX path not selected by this capture.
                for receiver_id in (0, 1)
            ),
        )
        for stream in manifest.streams
    )
    return StationReceiverTopologyV1.create(
        station_id="e2e-station",
        topology_revision=f"{manifest.session_id}-v1",
        valid_from_utc_ns=valid_from,
        valid_until_utc_ns=valid_until,
        radios=radios,
    )


def _execute_run(
    service: ProcessingService,
    source: PublishedInput,
    *,
    run_id: str,
    reprocess: bool,
) -> None:
    plan = compile_standard_run_plan(
        source.bundle.manifest,
        manifest_digest=source.manifest_digest,
        pipeline_release_id=PIPELINE_RELEASE,
    )
    service.create_expanded_run(
        run_id=run_id,
        plan=plan,
        trigger="reprocess" if reprocess else "new_capture",
    )
    executions = []
    while execution := service.run_once(worker_id="production-e2e-worker"):
        executions.append(execution)
        if not execution.succeeded:
            raise RuntimeError(f"production E2E worker failed: {execution.error}")
    if len(executions) != len(plan.jobs):
        raise RuntimeError(f"production E2E ran {len(executions)} jobs, expected {len(plan.jobs)}")
    service.finalize_run(run_id)


def _prepare() -> tuple[str, Path]:
    global _schema_engine
    _schema_engine, schema_url = _isolated_database()
    catalog = CatalogRepository(create_session_factory(_schema_engine))
    recordings = RecordingStore(_bulk_root)
    (_bulk_root / "qualification" / "trusted-campaigns").mkdir(parents=True, exist_ok=True)
    registry = production_standard_v2_registry()
    configuration: dict[str, object] = {
        "display_version": "2.0.0",
        "stages": production_standard_v2_configuration(),
    }
    executable = _bulk_root.parent / "worker-executable"
    executable.mkdir()
    (executable / "standard-v2.txt").write_text("pinned production E2E executable\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=PIPELINE_RELEASE,
        code_revision=PIPELINE_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "production-e2e-standard-v2"},
        executable_root=executable,
    )
    catalog.add_pipeline_release(
        release_id=PIPELINE_RELEASE,
        code_revision=PIPELINE_RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )
    main = _publish_recording(catalog, recordings, session_id=MAIN_SESSION_ID, paired=True, seed=41)
    failed = _publish_recording(
        catalog,
        recordings,
        session_id=FAILED_SESSION_ID,
        paired=False,
        seed=73,
    )
    pending = _publish_recording(
        catalog,
        recordings,
        session_id=PENDING_SESSION_ID,
        paired=False,
        seed=91,
    )
    bulk_pin = PinnedLocalRoot(_bulk_root)
    try:
        pinned_recordings = RecordingStore.open_pinned(bulk_pin)
        artifacts = AnalysisArtifactStore.open_pinned(bulk_pin)
    finally:
        bulk_pin.close()
    service = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(pinned_recordings),
        loaded_worker_release=loaded,
    )
    _execute_run(
        service,
        main,
        run_id=REPLACED_RUN_ID,
        reprocess=False,
    )
    _execute_run(
        service,
        main,
        run_id=CURRENT_RUN_ID,
        reprocess=True,
    )
    failed_plan = compile_standard_run_plan(
        failed.bundle.manifest,
        manifest_digest=failed.manifest_digest,
        pipeline_release_id=PIPELINE_RELEASE,
    )
    service.create_expanded_run(
        run_id="e2e-intentional-failure",
        plan=failed_plan,
        trigger="new_capture",
    )
    catalog.fail_analysis_run(
        run_id="e2e-intentional-failure",
        failure="Intentional production E2E analysis failure",
    )
    pending_plan = compile_standard_run_plan(
        pending.bundle.manifest,
        manifest_digest=pending.manifest_digest,
        pipeline_release_id=PIPELINE_RELEASE,
    )
    service.create_expanded_run(
        run_id="e2e-pending-run",
        plan=pending_plan,
        trigger="new_capture",
    )
    if catalog.current_run_id(main.session_id) != CURRENT_RUN_ID:
        raise RuntimeError("production E2E failed to atomically replace the current run")
    scanner_configuration = ScannerConfiguration(targets=current_low_band_targets())
    scanner_report = ScannerReport(
        scan_id="scan-e2e-latest",
        radio_id="radio_pluto_5d4d",
        radio_serial="e2e-radio-serial",
        configuration=scanner_configuration,
        capture_elapsed_ms=1_557.0,
        analysis_elapsed_ms=16_799.0,
        results=tuple(
            ScanEdgeResult(
                target=target,
                decision=(ScanDecision.ACTIVE if index < 6 else ScanDecision.NO_DETECTION),
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=2.0,
                listen_ms=80.0,
                iq_sha256="a" * 64,
                best_margin=(0.25 if index < 6 else None),
                reason=("GLRT64 candidate evidence" if index < 6 else "no GLRT64 hit"),
            )
            for index, target in enumerate(scanner_configuration.targets)
        ),
    )
    scanner_root = _bulk_root / "scanner-reports"
    scanner_root.mkdir()
    (scanner_root / "starlink-scan-20260821T010000Z.json").write_text(
        scanner_report.model_dump_json()
    )
    return schema_url, _bulk_root


def _prepare_tle_archive(root: Path) -> Path:
    """Stage one deterministic element-set snapshot for the sky views.

    Near-equatorial orbits placed over the equator at the anchor, so the sky
    view has something to draw from the fixture position.
    """

    import hashlib

    from leo.sky.propagation import element_line_checksum

    def seal(line: str) -> str:
        return f"{line[:68]}{element_line_checksum(line)}"

    anchor_ns = 1_787_238_197_000_000_000
    payload = ""
    hugging_face_payload = ""
    for index in range(8):
        number = 40_000 + index
        mean_anomaly = (130.0 + index * 0.6 - 2.0) % 360.0
        first = seal(
            f"1 {number:05d}U 26232A   26232.50000000  .00000100  00000-0  10000-4 0  9990"
        )
        second = seal(
            f"2 {number:05d}   0.5000   0.0000 0001000"
            f"  87.0000 {mean_anomaly:8.4f} 15.20000000260120"
        )
        payload += first + "\n" + second + "\n"
        # The live Hugging Face archive uses an unprefixed name line.  Keep
        # this exact provider dialect in the browser fixture so a parser drift
        # cannot pass API units while breaking the real globe.
        hugging_face_payload += f"STARLINK-{number}\n" + first + "\n" + second + "\n"
    directory = root / "tle" / "archive" / "space-track"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{anchor_ns}-{digest}.tle").write_text(payload)
    hf_directory = root / "tle" / "archive" / "huggingface"
    hf_directory.mkdir(parents=True, exist_ok=True)
    hf_digest = hashlib.sha256(hugging_face_payload.encode()).hexdigest()
    (hf_directory / f"{anchor_ns + 1}-{hf_digest}.tle").write_text(hugging_face_payload)
    return root / "tle"


_database_url, _prepared_bulk_root = _prepare()
_tle_root = _prepare_tle_archive(_prepared_bulk_root)
app = create_production_app(
    ProductionSettings(
        database_url=_database_url,
        bulk_root=_prepared_bulk_root,
        static_directory=Path(
            os.environ.get("LEO_E2E_WEB_DIST", str(PROJECT_ROOT / "web" / "dist"))
        ),
        host="127.0.0.1",
        port=8766,
        tle_root=_tle_root,
        scanner_report_root=_prepared_bulk_root / "scanner-reports",
    )
)
app.router.add_event_handler("shutdown", _cleanup)
