"""Isolated production-path E2E server.

Importing this module creates a unique PostgreSQL schema, migrates it, publishes
ordinary compressed RecordingStore bundles, executes the real Standard worker
twice to prove current-run replacement, and finally composes the production
operator application. Setup failures are intentionally fatal: CI must never
fall back to presentation fixtures or silently skip this lane.
"""

from __future__ import annotations

import atexit
import base64
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.acquisition.mixed_rate_schedule import compile_production_dwell_intent_v3
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.api import ProductionSettings, create_production_app
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_session_factory
from leo.contracts.digests import sha256_digest
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV6,
)
from leo.contracts.states import CaptureState, SourceType
from leo.domain.mixed_rate_capture import compile_production_capture_plan_v5
from leo.domain.profiles import load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import standard_native as standard_native_pipeline
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerAnalysisMetricsV1,
    ScannerConfiguration,
    ScannerFrameAnalysisV1,
    ScannerIqBundleManifestV1,
    ScannerIqCaptureFailureV1,
    ScannerIqFrameV1,
    ScannerReport,
    current_low_band_targets,
)
from leo.station.authority import (
    CaptureHardwareBindingV6,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import (
    PinnedLocalRoot,
    PublishedBundle,
    RecordingStore,
    ScannerAnalysisStore,
)
from tests.postgres_support import require_safe_test_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = require_safe_test_database_url(("LEO_E2E_DATABASE_URL", "LEO_TEST_DATABASE_URL"))
PIPELINE_RELEASE = "e" * 40
PREVIOUS_PIPELINE_RELEASE = "d" * 40
CURRENT_RUN_ID = "e2e-main-run-v2"
REPLACED_RUN_ID = "e2e-main-run-v1"
MAIN_SESSION_ID = "e2e-main-test-recording"
FAILED_SESSION_ID = "e2e-failed-test-recording"
PENDING_SESSION_ID = "e2e-pending-test-recording"
SCANNER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@dataclass(frozen=True, slots=True)
class PublishedInput:
    bundle: PublishedBundle

    @property
    def session_id(self) -> str:
        return self.bundle.manifest.session_id

    @property
    def manifest_digest(self) -> str:
        return self.bundle.manifest_sha256

    @property
    def manifest(self) -> RecordingManifestV6:
        manifest = self.bundle.manifest
        if type(manifest) is not RecordingManifestV6:
            raise RuntimeError("production E2E input is not RecordingManifestV6")
        return manifest


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


def _bounded_direct_async_plan(session_id: str, radio_ids: tuple[str, str]):
    """Compile a small, current V5 plan without weakening production admission."""

    specifications = (
        ((2_500_000, (0, 1), True), "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4"),
        *(
            (
                (rate, (receiver,), True),
                f"starlink-ch4-lower-{rate // 1_000_000}m-60s-rx{receiver}-direct-async-v7",
            )
            for rate in (10_000_000, 15_000_000, 25_000_000)
            for receiver in (0, 1)
        ),
    )
    revisions: dict[tuple[int, tuple[int, ...], bool], CaptureProfileRevisionV2] = {}
    for key, profile_name in specifications:
        source = load_profile_revision(PROJECT_ROOT / "profiles" / f"{profile_name}.yaml")
        if not isinstance(source, CaptureProfileRevisionV2):
            raise RuntimeError(f"E2E direct-async profile is not V2: {profile_name}")
        values = source.profile.model_dump(mode="python")
        values.update(
            {
                "name": f"e2e-{profile_name}",
                "duration_seconds": Decimal("0.1"),
                "sample_count": None,
                "settle_seconds": Decimal(0),
                "prime_refills": 0,
                "campaign": "bounded-production-e2e",
            }
        )
        revision = CaptureProfileRevisionV2.from_profile(CaptureProfileV2.model_validate(values))
        revisions[key] = revision
        if key[0] == 2_500_000:
            standard_native_pipeline.STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES[
                revision.profile.name
            ] = (
                revision.profile.sample_rate_hz,
                revision.profile.receivers,
                revision.revision_digest,
                revision.profile.refill_samples,
            )
        else:
            standard_native_pipeline.STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES[
                revision.profile.name
            ] = (
                revision.profile.sample_rate_hz,
                (revision.profile.receivers[0],),
                revision.revision_digest,
            )
    authority = {
        key: (revision.profile.name, revision.revision_digest, revision.profile.refill_samples)
        for key, revision in revisions.items()
    }
    intent = compile_production_dwell_intent_v3(
        operation_key=f"production-e2e:{session_id}",
        cadence_ordinal=0,
        radio_ids=radio_ids,
        profile_authority=authority,
        extra_tags=("E2E",),
    )
    return compile_production_capture_plan_v5(
        intent=intent,
        profile_revisions_by_radio={
            leg.radio_id: revisions[(leg.sample_rate_hz, leg.receiver_ids, True)]
            for leg in intent.radio_legs
        },
        source_type=SourceType.LIVE,
    )


def _publish_recording(
    catalog: CatalogRepository,
    recordings: RecordingStore,
    *,
    session_id: str,
    paired: bool,
    seed: int,
) -> PublishedInput:
    stem = "main" if paired else session_id.removeprefix("e2e-").removesuffix("-test-recording")
    radio_ids = (f"e2e-radio-{stem}-a", f"e2e-radio-{stem}-b")
    plan = _bounded_direct_async_plan(session_id, radio_ids)
    compression = CompressionSettingsV1(
        policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
        level=1,
        target_uncompressed_bytes=1_048_576,
    )
    coordinator = AcquisitionCoordinator(
        recordings,
        compression=compression,
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            radio_id: FakeRadioSource(radio_id, seed=seed + index)
            for index, radio_id in enumerate(radio_ids)
        },
        session_id=session_id,
    )
    if result.state is not CaptureState.COMMITTED or result.bundle is None:
        raise RuntimeError(f"production E2E direct-async capture failed: {result.errors}")
    published = result.bundle
    manifest = published.manifest
    if type(manifest) is not RecordingManifestV6:
        raise RuntimeError("production E2E capture did not publish RecordingManifestV6")
    topology = _station_topology(manifest)
    catalog.register_station_topology(topology)
    authority = CaptureHardwareBindingV6.create(
        published.manifest,
        observed_manifest_file_digest=published.manifest_sha256,
        topology=topology,
    )
    catalog.reconcile_capture_session(
        session_id=session_id,
        source_type=manifest.source_type.value,
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        tags=manifest.tags,
        attributes={
            "presentation": {
                "title": (
                    "Production E2E paired live dwell"
                    if paired
                    else "Production E2E intentional analysis failure"
                )
            }
        },
        allocated_bytes=sum(
            item.stat().st_size for item in published.path.rglob("*") if item.is_file()
        ),
        streams=_stream_registrations(published),
        path_authority=authority,
    )
    return PublishedInput(published)


def _station_topology(manifest: RecordingManifestV6) -> StationReceiverTopologyV1:
    """Create explicit synthetic station authority for the generated E2E capture."""

    valid_from = (
        min(stream.timing.first_sample.earliest_utc_ns for stream in manifest.streams)
        - 1_000_000_000
    )
    valid_until = (
        max(stream.timing.last_sample.latest_utc_ns for stream in manifest.streams) + 1_000_000_000
    )
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
    pipeline_release_id: str = PIPELINE_RELEASE,
) -> None:
    compiler = (
        standard_native_pipeline.compile_standard_native_default_run_plan
        if reprocess
        else standard_native_pipeline.compile_standard_native_automatic_run_plan
    )
    plan = compiler(
        source.manifest,
        manifest_digest=source.manifest_digest,
        pipeline_release_id=pipeline_release_id,
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
    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "standard-native-e2e-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = _bulk_root.parent / "worker-executable"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned production E2E executable\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=PIPELINE_RELEASE,
        code_revision=PIPELINE_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "production-e2e-standard-native"},
        executable_root=executable,
    )
    previous_loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=PREVIOUS_PIPELINE_RELEASE,
        code_revision=PREVIOUS_PIPELINE_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "production-e2e-standard-native"},
        executable_root=executable,
    )
    for release_id, worker_release in (
        (PREVIOUS_PIPELINE_RELEASE, previous_loaded),
        (PIPELINE_RELEASE, loaded),
    ):
        catalog.add_pipeline_release(
            release_id=release_id,
            code_revision=release_id,
            environment_digest=worker_release.authority.environment_digest,
            graph_digest=worker_release.authority.graph_digest,
            configuration=configuration,
            executable_digest=worker_release.authority.executable_digest,
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
    previous_service = ProcessingService(
        catalog=catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(pinned_recordings),
        loaded_worker_release=previous_loaded,
    )
    _execute_run(
        previous_service,
        main,
        run_id=REPLACED_RUN_ID,
        reprocess=False,
        pipeline_release_id=PREVIOUS_PIPELINE_RELEASE,
    )
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
        run_id=CURRENT_RUN_ID,
        reprocess=True,
    )
    failed_plan = standard_native_pipeline.compile_standard_native_automatic_run_plan(
        failed.manifest,
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
    pending_plan = standard_native_pipeline.compile_standard_native_automatic_run_plan(
        pending.manifest,
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
                listen_ms=120.0,
                iq_sha256="a" * 64,
                best_margin=(0.25 if index < 6 else None),
                reason=("GLRT64 candidate evidence" if index < 6 else "no GLRT64 hit"),
            )
            for index, target in enumerate(scanner_configuration.targets)
        ),
    )
    scanner_root = _bulk_root / "scanner-reports"
    scanner_root.mkdir()
    scanner_analyses = ScannerAnalysisStore(_bulk_root)
    for minute in range(22):
        historical = scanner_report.model_copy(update={"scan_id": f"scan-e2e-{minute + 1:02d}"})
        captured_at = datetime(2026, 8, 21, 1, minute, tzinfo=UTC)
        captured_ns = int(captured_at.timestamp() * 1_000_000_000)
        target = scanner_configuration.targets[0]
        frame_bytes = (
            scanner_configuration.dwell_samples * len(scanner_configuration.receiver_ids) * 4
        )
        scanner_manifest = ScannerIqBundleManifestV1(
            scan_id=historical.scan_id,
            created_utc_ns=captured_ns,
            finalized_utc_ns=captured_ns + 1,
            radio_id=historical.radio_id,
            radio_serial=historical.radio_serial,
            radio_uri="ip:192.0.2.10",
            configuration=scanner_configuration,
            frames=(
                ScannerIqFrameV1(
                    frame_index=0,
                    target_index=0,
                    target=target,
                    sample_start=0,
                    sample_count=scanner_configuration.dwell_samples,
                    requested_if_center_hz=target.if_center_hz,
                    actual_if_center_hz=target.if_center_hz,
                    actual_rf_center_hz=target.rf_center_hz,
                    tune_ms=1.0,
                    listen_ms=float(scanner_configuration.dwell_ms),
                    host_request_utc_ns_lower=captured_ns,
                    host_request_utc_ns_upper=captured_ns + 1,
                    host_request_monotonic_ns_lower=1,
                    host_request_monotonic_ns_upper=2,
                    uncompressed_bytes=frame_bytes,
                    uncompressed_sha256="sha256:" + "1" * 64,
                ),
            ),
            failures=tuple(
                ScannerIqCaptureFailureV1(
                    target_index=index,
                    target=failed_target,
                    reason="production E2E capture-time fixture",
                )
                for index, failed_target in enumerate(scanner_configuration.targets[1:], start=1)
            ),
            total_sample_count=scanner_configuration.dwell_samples,
            uncompressed_bytes=frame_bytes,
            compressed_bytes=1,
            uncompressed_sha256="sha256:" + "1" * 64,
            compressed_sha256="sha256:" + "2" * 64,
            compression=CompressionSettingsV1(policy_id="zstd-128m-v1"),
        )
        scanner_bundle = (
            _bulk_root
            / "scanner-recordings"
            / f"{captured_at.year:04d}"
            / f"{captured_at.month:02d}"
            / f"{captured_at.day:02d}"
            / historical.scan_id
        )
        scanner_bundle.mkdir(parents=True)
        (scanner_bundle / "manifest.json").write_text(scanner_manifest.model_dump_json())
        (scanner_root / f"starlink-scan-20260821T01{minute:02d}00Z.json").write_text(
            historical.model_dump_json()
        )
        metrics = ScannerAnalysisMetricsV1(
            scan_id=historical.scan_id,
            input_uri=f"bulk://scanner-recordings/{historical.scan_id}",
            input_manifest_sha256="sha256:" + "1" * 64,
            configuration=scanner_configuration,
            frames=tuple(
                ScannerFrameAnalysisV1(
                    status="failed",
                    target_index=index,
                    target=target,
                    source_sample_start=index * scanner_configuration.dwell_samples,
                    sample_count=0,
                    requested_if_center_hz=target.if_center_hz,
                    actual_if_center_hz=None,
                    iq_sha256=None,
                    decision=ScanDecision.INCONCLUSIVE,
                    decision_best_margin=None,
                    full_best_margin=None,
                    first_detection=None,
                    reason="production E2E numerical fixture unavailable",
                    probes=(),
                    waterfalls=(),
                )
                for index, target in enumerate(scanner_configuration.targets)
            ),
        )
        published_analysis = scanner_analyses.publish(
            "standard-scan-analysis-stitched-v2",
            historical,
            metrics,
            waterfall_png=SCANNER_PNG,
            glrt64_png=SCANNER_PNG,
        )
        published_at = datetime(2026, 8, 21, 1, minute, tzinfo=UTC).timestamp()
        os.utime(published_analysis.path, (published_at, published_at))
    catalog.enqueue_acquisition_operation(
        operation_key="e2e-pending-dwell",
        kind="scheduled_recording",
        payload={
            "profile_name": "e2e-live-60s",
            "radio_ids": ["radio-a", "radio-b"],
            "extra_tags": ["E2E"],
        },
        scheduled_for=datetime(2026, 8, 21, 1, 30, tzinfo=UTC),
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
    # Four newer unique element sets let the selected-satellite UI exercise a
    # real five-record comparison. The base record remains the exact snapshot
    # nearest the fixture anchor and therefore the comparison reference.
    for revision in range(1, 5):
        revised_payload = ""
        for index in range(8):
            number = 40_000 + index
            mean_anomaly = (130.0 + index * 0.6 - 2.0 + revision * 0.02) % 360.0
            first = seal(
                f"1 {number:05d}U 26232A   26232.50000000  .00000100  00000-0  10000-4 0  9990"
            )
            second = seal(
                f"2 {number:05d}   0.5000   0.0000 0001000"
                f"  87.0000 {mean_anomaly:8.4f} 15.20000000260120"
            )
            revised_payload += first + "\n" + second + "\n"
        revised_digest = hashlib.sha256(revised_payload.encode()).hexdigest()
        (directory / f"{anchor_ns + revision + 1}-{revised_digest}.tle").write_text(revised_payload)
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
