from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.acquisition.mixed_rate_schedule import (
    compile_production_dwell_intent_v2,
    compile_production_dwell_intent_v3,
)
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.api import create_app
from leo.application import (
    CatalogPresentationRepository,
    CatalogStandardNativePresentationRepository,
    CatalogStandardPresentationRepository,
    DefinitionDispatchedStandardPresentationRepository,
    StandardReprocessService,
)
from leo.artifacts import (
    AnalysisArtifactStore,
    AnalysisRunManifestV5,
    AnalysisRunManifestV6,
)
from leo.catalog import CatalogSubjectBindingReader
from leo.contracts.device_buffer import DIRECT_ASYNC_EVIDENCE_KEY_V1, DirectAsyncEvidenceV1
from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClassV2,
    ProductionDwellClassV3,
)
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV5,
    RecordingManifestV6,
)
from leo.contracts.standard_native_terminal import (
    StandardNativePairedReportV7,
    StandardNativeRadioReportV6,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.contracts.states import CaptureState, SourceType
from leo.domain.mixed_rate_capture import (
    compile_production_capture_plan_v4,
    compile_production_capture_plan_v5,
)
from leo.domain.profiles import load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import ScopeIdentityV1
from leo.pipeline import standard_native as standard_native_pipeline
from leo.presentation.standard_native_artifacts import (
    StandardNativePngArtifactInventoryV8,
    StandardNativePngArtifactInventoryV9,
    StandardNativePngArtifactInventoryV10,
    StandardNativePngArtifactInventoryV11,
)
from leo.presentation.standard_native_pipeline import (
    StandardNativePlotViewV5,
    StandardNativePlotViewV6,
    StandardNativeSubjectDetailV5,
    StandardNativeSubjectDetailV6,
    StandardNativeSubjectDetailV7,
    StandardNativeSubjectHierarchyV5,
    StandardNativeSubjectHierarchyV6,
    StandardNativeSubjectHierarchyV7,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV5,
    CaptureHardwareBindingV6,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

from .conftest import ProcessingDatabase

pytestmark = pytest.mark.postgres

_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = "9" * 40
_DURATION = Decimal("0.1048576")
_REFILL_SAMPLES = 65_536
_RADIO_IDS = ("radio-mixed-a", "radio-mixed-b")
_LOW_RATE_HZ = 2_500_000


def _station_topology(
    manifest: RecordingManifestV5 | RecordingManifestV6,
) -> StationReceiverTopologyV1:
    capture_start = min(stream.timing.first_sample.earliest_utc_ns for stream in manifest.streams)
    capture_end = max(stream.timing.last_sample.latest_utc_ns + 1 for stream in manifest.streams)
    valid_from = capture_start - 1_000_000_000
    valid_until = capture_end + 1_000_000_000
    return StationReceiverTopologyV1.create(
        station_id="standard-native-mixed-operational-station",
        topology_revision="standard-native-mixed-operational-topology-v1",
        valid_from_utc_ns=valid_from,
        valid_until_utc_ns=valid_until,
        radios=tuple(
            StationRadioTopologyV1.create(
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                endpoint_evidence=RadioEndpointEvidenceV1(
                    transport=stream.radio.transport,
                    endpoint=stream.radio.uri,
                    evidence_uri=f"authority/{stream.radio.radio_id}.json",
                    evidence_digest=canonical_digest(
                        {"radio_id": stream.radio.radio_id, "endpoint": stream.radio.uri}
                    ),
                ),
                receiver_assignments=tuple(
                    StationReceiverAssignmentV1(
                        receiver_id=receiver_id,
                        physical_receiver_id=f"{stream.radio.radio_id}-physical-rx{receiver_id}",
                        hardware_epoch_external_id=(
                            f"{stream.radio.radio_id}-hardware-rx{receiver_id}-v1"
                        ),
                        valid_from_utc_ns=valid_from,
                        valid_until_utc_ns=valid_until,
                    )
                    for receiver_id in (0, 1)
                ),
            )
            for stream in sorted(manifest.streams, key=lambda item: item.radio.radio_id)
        ),
    )


def _register_bundle(
    database: ProcessingDatabase,
    bundle: PublishedBundle,
    topology: StationReceiverTopologyV1,
) -> None:
    manifest = bundle.manifest
    assert type(manifest) in {RecordingManifestV5, RecordingManifestV6}
    authority = (
        CaptureHardwareBindingV6.create(
            manifest,
            observed_manifest_file_digest=bundle.manifest_sha256,
            topology=topology,
        )
        if type(manifest) is RecordingManifestV6
        else CaptureHardwareBindingV5.create(
            manifest,
            observed_manifest_file_digest=bundle.manifest_sha256,
            topology=topology,
        )
    )
    assert database.catalog.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=bundle.uri,
        manifest_digest=bundle.manifest_sha256,
        allocated_bytes=sum(
            item.stat().st_size for item in bundle.path.rglob("*") if item.is_file()
        ),
        attributes={"presentation": {"title": "bounded mixed native Standard"}},
        tags=manifest.tags,
        streams=_stream_registrations(bundle),
        path_authority=authority,
    )
    capture_authority = database.catalog.capture_path_authority(manifest.session_id)
    assert capture_authority.authority_kind == "station"
    assert capture_authority.current_analysis_eligible is True
    assert capture_authority.promotion_permitted is True


def _bounded_production_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    high_rate_profile_suffix: str,
    dwell_class: ProductionDwellClassV2,
):
    duration = Decimal("0.2") if high_rate_profile_suffix == "ddr-ring-v6" else _DURATION
    specifications = (
        ((2_500_000, (0, 1), False), "starlink-ch4-lower-2p5m-60s-native-bandwidth-v4"),
        ((5_000_000, (0, 1), False), "starlink-ch4-lower-5m-60s-native-bandwidth-v4"),
        ((2_500_000, (0, 1), True), "starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4"),
        ((5_000_000, (0, 1), True), "starlink-ch4-lower-5m-60s-mixed-device-axis-v4"),
        *(
            (
                (rate, (receiver,), True),
                f"starlink-ch4-lower-{rate // 1_000_000}m-60s-rx{receiver}-"
                f"{high_rate_profile_suffix}",
            )
            for rate in (10_000_000, 15_000_000, 20_000_000)
            for receiver in (0, 1)
        ),
    )
    revisions: dict[tuple[int, tuple[int, ...], bool], CaptureProfileRevisionV2] = {}
    for key, profile_name in specifications:
        source = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")
        assert isinstance(source, CaptureProfileRevisionV2)
        profile_values = source.profile.model_dump(mode="python")
        profile_values.update(
            {
                "name": f"test-{profile_name}",
                "duration_seconds": duration,
                "sample_count": None,
                "settle_seconds": Decimal(0),
                "prime_refills": 0,
                "campaign": "bounded-production-native-standard-test",
            }
        )
        revision = CaptureProfileRevisionV2.from_profile(
            CaptureProfileV2.model_validate(profile_values)
        )
        revisions[key] = revision
        monkeypatch.setitem(
            standard_native_pipeline.STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES,
            revision.profile.name,
            (
                revision.profile.sample_rate_hz,
                revision.profile.receivers,
                revision.revision_digest,
                revision.profile.refill_samples,
            ),
        )
    authority = {
        key: (revision.profile.name, revision.revision_digest, revision.profile.refill_samples)
        for key, revision in revisions.items()
    }
    intent = next(
        item
        for ordinal in range(8)
        if (
            item := compile_production_dwell_intent_v2(
                operation_key=f"bounded-production:{ordinal}",
                cadence_ordinal=ordinal,
                radio_ids=_RADIO_IDS,
                profile_authority=authority,
                extra_tags=("operational-vertical",),
            )
        ).dwell_class
        is dwell_class
    )
    selected = {
        leg.radio_id: revisions[(leg.sample_rate_hz, leg.receiver_ids, True)]
        for leg in intent.radio_legs
    }
    return compile_production_capture_plan_v4(
        intent=intent,
        profile_revisions_by_radio=selected,
        source_type=SourceType.LIVE,
    )


def _bounded_direct_async_plan(
    monkeypatch: pytest.MonkeyPatch,
    *,
    high_rate_hz: int,
):
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
        source = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")
        assert isinstance(source, CaptureProfileRevisionV2)
        profile_values = source.profile.model_dump(mode="python")
        profile_values.update(
            {
                "name": f"test-{profile_name}-{high_rate_hz}",
                "duration_seconds": Decimal("0.1"),
                "sample_count": None,
                "settle_seconds": Decimal(0),
                "prime_refills": 0,
                "campaign": "bounded-direct-async-native-standard-test",
            }
        )
        revision = CaptureProfileRevisionV2.from_profile(
            CaptureProfileV2.model_validate(profile_values)
        )
        revisions[key] = revision
        if key[0] == 2_500_000:
            monkeypatch.setitem(
                standard_native_pipeline.STANDARD_NATIVE_PRODUCTION_PROFILE_IDENTITIES,
                revision.profile.name,
                (
                    revision.profile.sample_rate_hz,
                    revision.profile.receivers,
                    revision.revision_digest,
                    revision.profile.refill_samples,
                ),
            )
        else:
            monkeypatch.setitem(
                standard_native_pipeline.STANDARD_NATIVE_DIRECT_ASYNC_PROFILE_IDENTITIES,
                revision.profile.name,
                (
                    revision.profile.sample_rate_hz,
                    revision.profile.receivers,
                    revision.revision_digest,
                ),
            )
    authority = {
        key: (revision.profile.name, revision.revision_digest, revision.profile.refill_samples)
        for key, revision in revisions.items()
    }
    dwell_class = ProductionDwellClassV3(f"mixed_2p5_{high_rate_hz // 1_000_000}")
    intent = next(
        item
        for ordinal in range(6)
        if (
            item := compile_production_dwell_intent_v3(
                operation_key=f"bounded-direct-async:{high_rate_hz}:{ordinal}",
                cadence_ordinal=ordinal,
                radio_ids=_RADIO_IDS,
                profile_authority=authority,
                extra_tags=("operational-vertical",),
            )
        ).dwell_class
        is dwell_class
    )
    selected = {
        leg.radio_id: revisions[(leg.sample_rate_hz, leg.receiver_ids, True)]
        for leg in intent.radio_legs
    }
    return compile_production_capture_plan_v5(
        intent=intent,
        profile_revisions_by_radio=selected,
        source_type=SourceType.LIVE,
    )


@pytest.mark.parametrize(
    ("high_rate_profile_suffix", "dwell_class", "high_rate_hz"),
    (
        ("production-v5", ProductionDwellClassV2.MIXED_2P5_10, 10_000_000),
        ("ddr-ring-v6", ProductionDwellClassV2.MIXED_2P5_10, 10_000_000),
        ("ddr-ring-v6", ProductionDwellClassV2.MIXED_2P5_15, 15_000_000),
        ("ddr-ring-v6", ProductionDwellClassV2.MIXED_2P5_20, 20_000_000),
    ),
)
def test_real_postgres_production_single_rx_all_rate_vertical(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    high_rate_profile_suffix: str,
    dwell_class: ProductionDwellClassV2,
    high_rate_hz: int,
) -> None:
    plan = _bounded_production_plan(
        monkeypatch,
        high_rate_profile_suffix=high_rate_profile_suffix,
        dwell_class=dwell_class,
    )
    assert plan.dwell_class is dwell_class
    bulk_root = tmp_path / "bulk-production"
    coordinator = AcquisitionCoordinator(
        RecordingStore(bulk_root),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            _RADIO_IDS[0]: FakeRadioSource(_RADIO_IDS[0], seed=11),
            _RADIO_IDS[1]: FakeRadioSource(_RADIO_IDS[1], seed=12),
        },
        session_id=f"standard-native-production-{high_rate_hz}-single-rx",
    )
    assert result.state is CaptureState.COMMITTED
    assert type(result.manifest) is RecordingManifestV5
    assert result.bundle is not None
    bundle = result.bundle
    manifest = result.manifest
    assert sorted(stream.applied_settings.sample_rate_hz for stream in manifest.streams) == [
        2_500_000,
        high_rate_hz,
    ]
    assert sorted(len(stream.applied_settings.receiver_ids) for stream in manifest.streams) == [
        1,
        2,
    ]
    assert all(stream.continuity.metadata_abi_version == 3 for stream in manifest.streams)

    topology = _station_topology(manifest)
    processing_database.catalog.register_station_topology(topology)
    _register_bundle(processing_database, bundle, topology)

    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "standard-native-production-operational-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = tmp_path / "production-worker-executable"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned production native worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "real-postgres-production-standard-native"},
        executable_root=executable,
    )
    processing_database.catalog.add_pipeline_release(
        release_id=_RELEASE,
        code_revision=_RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )

    pinned = PinnedLocalRoot(bulk_root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(recordings),
        lease_for=timedelta(seconds=30),
        heartbeat_interval=timedelta(seconds=5),
        loaded_worker_release=loaded,
    )
    try:
        application = StandardReprocessService(
            catalog=processing_database.catalog,
            recordings=recordings,
            processing=service,
            pipeline_release_id=_RELEASE,
        )
        queued = application.queue(manifest.session_id)
        assert queued.queued_job_count == 13
        path_count = sum(len(stream.applied_settings.receiver_ids) for stream in manifest.streams)
        assert path_count == 3

        executions = []
        while execution := service.run_once(worker_id="production-standard-native-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == 13
        published = service.finalize_run(queued.run_id)
        assert isinstance(published.manifest, AnalysisRunManifestV5)
        authority = published.manifest.promotion_authority
        assert authority.dwell_class == dwell_class.value
        assert authority.tuning_branch == "same"
        assert sorted(item.sample_rate_hz for item in authority.stream_authorities) == [
            2_500_000,
            high_rate_hz,
        ]
        high = next(
            item for item in authority.stream_authorities if item.sample_rate_hz == high_rate_hz
        )
        assert len(high.receiver_ids) == 1
        assert high.metadata_abi_version == 3
        assert high.gain_controller_mode in {"tandem_hold", "tandem_auto"}

        seal = processing_database.catalog.run_seal_snapshot(queued.run_id)
        radio_reports = tuple(
            StandardNativeRadioReportV6.model_validate(
                artifacts.read_json(item.logical_uri, item.digest)
            )
            for item in seal.products
            if item.kind == "standard.radio-report"
        )
        assert sorted(len(item.paths) for item in radio_reports) == [1, 2]
        paired_product = next(
            item for item in seal.products if item.kind == "standard.paired-report"
        )
        paired = StandardNativePairedReportV7.model_validate(
            artifacts.read_json(paired_product.logical_uri, paired_product.digest)
        )
        assert sorted(paired.radio_sample_rates_hz) == [2_500_000, high_rate_hz]
        assert sorted(len(item.paths) for item in paired.radios) == [1, 2]

        native_repository = CatalogStandardNativePresentationRepository(
            processing_database.catalog,
            artifacts,
        )
        repository = DefinitionDispatchedStandardPresentationRepository(
            CatalogStandardPresentationRepository(processing_database.catalog, artifacts),
            native_repository,
        )
        hierarchy = repository.subject_hierarchy(manifest.session_id)
        assert isinstance(hierarchy, StandardNativeSubjectHierarchyV5)
        assert hierarchy.eligibility.dwell_class == dwell_class.value
        assert sorted(len(item.receiver_ids) for item in hierarchy.eligibility.legs) == [1, 2]
        paired_subject = hierarchy.rows[0]
        detail = repository.subject_detail(manifest.session_id, paired_subject.subject_id)
        assert isinstance(detail, StandardNativeSubjectDetailV5)
        inventory = repository.subject_png_inventory(
            manifest.session_id,
            paired_subject.subject_id,
        )
        assert isinstance(inventory, StandardNativePngArtifactInventoryV8)
        assert sorted(inventory.sample_rates_hz) == [2_500_000, high_rate_hz]
        waterfall = repository.subject_view(
            manifest.session_id,
            paired_subject.subject_id,
            StandardViewKindV2.WATERFALL,
            maximum_points=64,
        )
        assert isinstance(waterfall, StandardNativePlotViewV5)
        assert sorted(waterfall.sample_rates_hz) == [2_500_000, high_rate_hz]
        assert max(len(axis.frequency_bin_centers_hz) for axis in waterfall.frequency_axes) <= 1024
        assert all(
            len(tile.power_dbfs)
            == len(
                next(
                    axis.frequency_bin_centers_hz
                    for axis in waterfall.frequency_axes
                    if axis.receiver_path_id == tile.receiver_path_id
                )
            )
            for tile in waterfall.waterfall_tiles
        )

        with TestClient(
            create_app(
                CatalogPresentationRepository(
                    processing_database.catalog,
                    recordings,
                    artifacts,
                    bulk_root=bulk_root,
                ),
                artifact_root=bulk_root,
                standard_repository=repository,
            )
        ) as client:
            base = f"/api/v2/recordings/{manifest.session_id}/standard-subjects"
            response = client.get(base)
            assert response.status_code == 200
            assert response.json()["schema_version"] == 5
            response = client.get(f"{base}/{paired_subject.subject_id}/artifacts")
            assert response.status_code == 200
            assert response.json()["schema_version"] == 8
            assert sorted(response.json()["sample_rates_hz"]) == [2_500_000, high_rate_hz]
    finally:
        service.close()
        artifacts.close()
        pinned.close()


@pytest.mark.parametrize("high_rate_hz", (10_000_000, 15_000_000, 25_000_000))
def test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    high_rate_hz: int,
) -> None:
    plan = _bounded_direct_async_plan(monkeypatch, high_rate_hz=high_rate_hz)
    expected_dwell = f"mixed_2p5_{high_rate_hz // 1_000_000}"
    assert plan.dwell_class.value == expected_dwell
    assert len({(leg.starlink_channel, leg.starlink_edge) for leg in plan.radio_plans}) == 1

    bulk_root = tmp_path / f"bulk-direct-{high_rate_hz}"
    coordinator = AcquisitionCoordinator(
        RecordingStore(bulk_root),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            _RADIO_IDS[0]: FakeRadioSource(_RADIO_IDS[0], seed=21),
            _RADIO_IDS[1]: FakeRadioSource(_RADIO_IDS[1], seed=22),
        },
        session_id=f"standard-native-direct-{high_rate_hz}-operational",
    )
    assert result.state is CaptureState.COMMITTED
    assert type(result.manifest) is RecordingManifestV6
    assert result.bundle is not None
    bundle = result.bundle
    manifest = result.manifest
    assert sorted(stream.applied_settings.sample_rate_hz for stream in manifest.streams) == [
        2_500_000,
        high_rate_hz,
    ]
    assert sorted(len(stream.applied_settings.receiver_ids) for stream in manifest.streams) == [
        1,
        2,
    ]
    high_stream = next(
        stream
        for stream in manifest.streams
        if stream.applied_settings.sample_rate_hz == high_rate_hz
    )
    first_metadata = next(
        coordinator.store.reader(bundle, high_stream.stream_id).iter_timeline_metadata()
    )
    evidence = DirectAsyncEvidenceV1.model_validate(
        first_metadata.hardware_metadata[DIRECT_ASYNC_EVIDENCE_KEY_V1]
    )
    assert evidence.request.requested_device_samples == high_stream.logical_sample_count
    assert evidence.stored_observed_samples == high_stream.observed_sample_count
    assert evidence.counter_missing_sample_count == 0
    assert evidence.inter_segment_skipped_samples == 0
    coordinator.store.verify(bundle)

    topology = _station_topology(manifest)
    processing_database.catalog.register_station_topology(topology)
    _register_bundle(processing_database, bundle, topology)

    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "standard-native-direct-async-operational-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = tmp_path / f"direct-worker-executable-{high_rate_hz}"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned direct-async native worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "real-postgres-direct-async-standard-native"},
        executable_root=executable,
    )
    processing_database.catalog.add_pipeline_release(
        release_id=_RELEASE,
        code_revision=_RELEASE,
        environment_digest=loaded.authority.environment_digest,
        graph_digest=loaded.authority.graph_digest,
        configuration=configuration,
        executable_digest=loaded.authority.executable_digest,
    )

    pinned = PinnedLocalRoot(bulk_root)
    recordings = RecordingStore.open_pinned(pinned)
    artifacts = AnalysisArtifactStore.open_pinned(pinned)
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=artifacts,
        registry=registry,
        iq_readers=RecordingIqReaderProvider(recordings),
        lease_for=timedelta(seconds=30),
        heartbeat_interval=timedelta(seconds=5),
        loaded_worker_release=loaded,
    )
    try:
        application = StandardReprocessService(
            catalog=processing_database.catalog,
            recordings=recordings,
            processing=service,
            pipeline_release_id=_RELEASE,
        )
        queued = application.queue(manifest.session_id)
        expected_job_count = 7 if high_rate_hz == 25_000_000 else 13
        assert queued.queued_job_count == expected_job_count
        bindings = CatalogSubjectBindingReader(processing_database.catalog)
        for stream in manifest.streams:
            for receiver_id in stream.applied_settings.receiver_ids:
                scope = ScopeIdentityV1.receiver_path(
                    session_id=manifest.session_id,
                    stream_id=stream.stream_id,
                    receiver_id=receiver_id,
                )
                binding = bindings.receiver_path_native(queued.run_id, scope)
                assert isinstance(binding, StandardPathInputBindV5)
                assert binding.sample_rate_hz == stream.applied_settings.sample_rate_hz

        executions = []
        while execution := service.run_once(worker_id="direct-async-standard-native-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == expected_job_count
        published = service.finalize_run(queued.run_id)
        assert isinstance(published.manifest, AnalysisRunManifestV6)
        authority = published.manifest.promotion_authority
        assert authority.dwell_class == expected_dwell
        assert authority.tuning_branch == "same"
        assert sorted(item.sample_rate_hz for item in authority.stream_authorities) == [
            2_500_000,
            high_rate_hz,
        ]

        seal = processing_database.catalog.run_seal_snapshot(queued.run_id)
        expected_product_count = 59 if high_rate_hz == 25_000_000 else 99
        expected_png_count = 35 if high_rate_hz == 25_000_000 else 60
        assert len(seal.products) == expected_product_count
        assert sum(item.media_type == "image/png" for item in seal.products) == expected_png_count
        assert {
            item.schema_version for item in seal.products if item.kind == "standard.path-report"
        } == {4}
        assert {
            item.schema_version for item in seal.products if item.kind == "standard.radio-report"
        } == {6}
        assert {
            item.schema_version for item in seal.products if item.kind == "standard.paired-report"
        } == (set() if high_rate_hz == 25_000_000 else {7})

        native_repository = CatalogStandardNativePresentationRepository(
            processing_database.catalog,
            artifacts,
        )
        repository = DefinitionDispatchedStandardPresentationRepository(
            CatalogStandardPresentationRepository(processing_database.catalog, artifacts),
            native_repository,
        )
        hierarchy = repository.subject_hierarchy(manifest.session_id)
        assert isinstance(
            hierarchy,
            StandardNativeSubjectHierarchyV7
            if high_rate_hz == 25_000_000
            else StandardNativeSubjectHierarchyV6,
        )
        assert hierarchy.eligibility.dwell_class == expected_dwell
        assert sorted(len(item.receiver_ids) for item in hierarchy.eligibility.legs) == [1, 2]
        if high_rate_hz == 25_000_000:
            assert isinstance(hierarchy, StandardNativeSubjectHierarchyV7)
            low_stream_id = next(
                item.stream_id
                for item in authority.stream_authorities
                if item.sample_rate_hz == 2_500_000
            )
            low_radio_subject_id = f"radio:{low_stream_id}"
            assert hierarchy.analysis_selection.analyzed_stream_ids == (low_stream_id,)
            assert hierarchy.rows[0].subject_id == low_radio_subject_id
            root_subject = hierarchy.rows[0]
            detail = repository.subject_detail(manifest.session_id, root_subject.subject_id)
            assert isinstance(detail, StandardNativeSubjectDetailV7)
            subject_inventory_counts = {
                root_subject.subject_id: 7,
                **{item.subject_id: 14 for item in detail.receiver_path_expansions},
            }
        else:
            assert isinstance(hierarchy, StandardNativeSubjectHierarchyV6)
            low_radio_subject_id = None
            root_subject = hierarchy.rows[0]
            detail = repository.subject_detail(manifest.session_id, root_subject.subject_id)
            assert isinstance(detail, StandardNativeSubjectDetailV6)
            subject_inventory_counts = {
                root_subject.subject_id: 6,
                **{item.subject_id: 14 for item in detail.receiver_path_expansions},
            }
        for subject_id, expected_count in subject_inventory_counts.items():
            inventory = repository.subject_png_inventory(manifest.session_id, subject_id)
            if subject_id == low_radio_subject_id:
                assert isinstance(inventory, StandardNativePngArtifactInventoryV11)
                assert inventory.artifacts[-1].name == "pss-glrt-frame-comparison"
            elif high_rate_hz != 25_000_000 and subject_id == root_subject.subject_id:
                assert isinstance(inventory, StandardNativePngArtifactInventoryV9)
            else:
                assert isinstance(inventory, StandardNativePngArtifactInventoryV10)
            assert len(inventory.artifacts) == expected_count
            assert sorted(inventory.sample_rates_hz) in (
                [2_500_000],
                [high_rate_hz],
                [2_500_000, high_rate_hz],
            )
        waterfall = repository.subject_view(
            manifest.session_id,
            root_subject.subject_id,
            StandardViewKindV2.WATERFALL,
            maximum_points=64,
        )
        assert isinstance(waterfall, StandardNativePlotViewV6)
        assert sorted(waterfall.sample_rates_hz) == (
            [2_500_000] if high_rate_hz == 25_000_000 else [2_500_000, high_rate_hz]
        )

        with TestClient(
            create_app(
                CatalogPresentationRepository(
                    processing_database.catalog,
                    recordings,
                    artifacts,
                    bulk_root=bulk_root,
                ),
                artifact_root=bulk_root,
                standard_repository=repository,
            )
        ) as client:
            base = f"/api/v2/recordings/{manifest.session_id}/standard-subjects"
            response = client.get(base)
            assert response.status_code == 200
            assert response.json()["schema_version"] == (7 if high_rate_hz == 25_000_000 else 6)
            for subject_id, expected_count in subject_inventory_counts.items():
                response = client.get(f"{base}/{subject_id}/artifacts")
                assert response.status_code == 200
                payload = response.json()
                expected_schema_version = (
                    11
                    if subject_id == low_radio_subject_id
                    else (
                        9
                        if high_rate_hz != 25_000_000 and subject_id == root_subject.subject_id
                        else 10
                    )
                )
                assert payload["schema_version"] == expected_schema_version
                assert len(payload["artifacts"]) == expected_count
                for item in payload["artifacts"]:
                    png = client.get(item["href"])
                    assert png.status_code == 200
                    assert png.headers["content-type"] == "image/png"
                    assert png.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        service.close()
        artifacts.close()
        pinned.close()
