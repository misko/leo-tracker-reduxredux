from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
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
from leo.artifacts import AnalysisArtifactStore, AnalysisRunManifestV4
from leo.catalog import CatalogSubjectBindingReader
from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV4,
)
from leo.contracts.standard_native_path_report import StandardNativePathReportV3
from leo.contracts.standard_native_terminal import StandardNativePairedReportV5
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.starlink_frequency import (
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import CaptureState, SourceType, StarlinkEdge
from leo.domain.mixed_rate_capture import compile_mixed_rate_capture_plan_v3
from leo.domain.profiles import load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import ScopeIdentityV1
from leo.pipeline import standard_native as standard_native_pipeline
from leo.presentation.standard_native_artifacts import StandardNativePngArtifactInventoryV5
from leo.presentation.standard_native_pipeline import (
    StandardNativePlotViewV4,
    StandardNativeSubjectDetailV4,
    StandardNativeSubjectHierarchyV4,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV4,
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


def _bounded_revisions(high_rate_hz: int) -> dict[str, CaptureProfileRevisionV2]:
    revisions: dict[str, CaptureProfileRevisionV2] = {}
    for radio_id, rate in zip(_RADIO_IDS, (_LOW_RATE_HZ, high_rate_hz), strict=True):
        rate_label = {2_500_000: "2p5", 5_000_000: "5", 10_000_000: "10"}[rate]
        source = load_profile_revision(
            _ROOT / "profiles" / f"starlink-ch4-lower-{rate_label}m-60s-mixed-device-axis-v4.yaml"
        )
        assert isinstance(source, CaptureProfileRevisionV2)
        values = source.profile.model_dump(mode="python")
        values.update(
            {
                "name": f"test-reviewed-mixed-{rate}-device-axis-v4",
                "duration_seconds": _DURATION,
                "sample_count": None,
                "refill_samples": _REFILL_SAMPLES,
                "settle_seconds": Decimal(0),
                "prime_refills": 0,
                "campaign": "bounded-mixed-native-standard-test",
            }
        )
        revisions[radio_id] = CaptureProfileRevisionV2.from_profile(
            CaptureProfileV2.model_validate(values)
        )
    return revisions


def _capture_bundle(
    coordinator: AcquisitionCoordinator,
    revisions: dict[str, CaptureProfileRevisionV2],
    *,
    dwell_class: ProductionDwellClass,
    session_id: str,
) -> PublishedBundle:
    plan = compile_mixed_rate_capture_plan_v3(
        dwell_class=dwell_class,
        radio_ids=_RADIO_IDS,
        profile_revisions_by_radio=revisions,
        starlink_channel=3,
        starlink_edge=StarlinkEdge.LOWER,
        source_type=SourceType.LIVE,
    )
    result = coordinator.capture_once(
        plan,
        {
            _RADIO_IDS[0]: FakeRadioSource(
                _RADIO_IDS[0],
                seed=1,
                gaps_before_blocks={1: _REFILL_SAMPLES},
            ),
            _RADIO_IDS[1]: FakeRadioSource(_RADIO_IDS[1], seed=2),
        },
        session_id=session_id,
    )
    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV4)
    assert result.bundle is not None
    coordinator.store.verify(result.bundle)
    return result.bundle


def _station_topology(manifest: RecordingManifestV4) -> StationReceiverTopologyV1:
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
    assert isinstance(manifest, RecordingManifestV4)
    authority = CaptureHardwareBindingV4.create(
        manifest,
        observed_manifest_file_digest=bundle.manifest_sha256,
        topology=topology,
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


@pytest.mark.parametrize(
    ("high_rate_hz", "dwell_class"),
    (
        (5_000_000, ProductionDwellClass.MIXED_2P5_5),
        (10_000_000, ProductionDwellClass.MIXED_2P5_10),
    ),
)
def test_real_postgres_mixed_capture_standard_png_and_browser_vertical(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    high_rate_hz: int,
    dwell_class: ProductionDwellClass,
) -> None:
    rates = (_LOW_RATE_HZ, high_rate_hz)
    session_id = f"standard-native-{dwell_class.value}-operational"
    revisions = _bounded_revisions(high_rate_hz)
    for radio_id, rate in zip(_RADIO_IDS, rates, strict=True):
        revision = revisions[radio_id]
        monkeypatch.setitem(
            standard_native_pipeline.STANDARD_NATIVE_MIXED_PROFILE_NAMES,
            rate,
            revision.profile.name,
        )
        monkeypatch.setitem(
            standard_native_pipeline.STANDARD_NATIVE_MIXED_PROFILE_REVISION_DIGESTS,
            rate,
            revision.revision_digest,
        )
    monkeypatch.setattr(
        standard_native_pipeline,
        "STANDARD_NATIVE_MIXED_REFILL_SAMPLES",
        _REFILL_SAMPLES,
    )

    bulk_root = tmp_path / "bulk"
    recording_store = RecordingStore(bulk_root)
    coordinator = AcquisitionCoordinator(
        recording_store,
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    bundle = _capture_bundle(
        coordinator,
        revisions,
        dwell_class=dwell_class,
        session_id=session_id,
    )
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV4)
    assert tuple(stream.applied_settings.sample_rate_hz for stream in manifest.streams) == rates
    assert tuple(stream.applied_settings.bandwidth_hz for stream in manifest.streams) == rates
    assert tuple(stream.logical_sample_count for stream in manifest.streams) == (
        262_144,
        int(_DURATION * high_rate_hz),
    )
    assert manifest.capture_plan.starlink_channel == 3
    assert manifest.capture_plan.starlink_edge is StarlinkEdge.LOWER
    assert all(
        leg.requested_settings.center_frequency_hz
        == starlink_maximum_coverage_if_center_frequency_hz(
            manifest.capture_plan.starlink_channel,
            manifest.capture_plan.starlink_edge,
            bandwidth_hz=leg.requested_settings.bandwidth_hz,
        )
        for leg in manifest.capture_plan.radio_plans
    )

    topology = _station_topology(manifest)
    processing_database.catalog.register_station_topology(topology)
    _register_bundle(processing_database, bundle, topology)

    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "standard-native-mixed-operational-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned mixed native worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "real-postgres-mixed-standard-native"},
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
    application = StandardReprocessService(
        catalog=processing_database.catalog,
        recordings=recordings,
        processing=service,
        pipeline_release_id=_RELEASE,
    )
    try:
        queued = application.queue(manifest.session_id)
        assert queued.queued_job_count == 12
        plan = standard_native_pipeline.compile_standard_native_run_plan(
            manifest,
            manifest_digest=bundle.manifest_sha256,
            pipeline_release_id=_RELEASE,
        )
        assert (len(plan.jobs), len(plan.edges)) == (12, 15)
        assert all("resampl" not in item.stage_key for item in plan.jobs)

        binding_reader = CatalogSubjectBindingReader(processing_database.catalog)
        binding_rates: list[int] = []
        for stream in manifest.streams:
            for receiver_id in stream.applied_settings.receiver_ids:
                scope = ScopeIdentityV1.receiver_path(
                    session_id=manifest.session_id,
                    stream_id=stream.stream_id,
                    receiver_id=receiver_id,
                )
                binding = binding_reader.receiver_path_native(queued.run_id, scope)
                assert isinstance(binding, StandardPathInputBindV4)
                assert binding.sample_rate_hz == stream.applied_settings.sample_rate_hz
                assert binding.rf_bandwidth_hz == binding.sample_rate_hz
                assert binding.starlink_channel == 3
                assert binding.starlink_edge is StarlinkEdge.LOWER
                binding_rates.append(binding.sample_rate_hz)
        assert Counter(binding_rates) == {_LOW_RATE_HZ: 2, high_rate_hz: 2}

        executions = []
        while execution := service.run_once(worker_id="mixed-standard-native-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == 12
        published = service.finalize_run(queued.run_id)
        assert isinstance(published.manifest, AnalysisRunManifestV4)
        authority = published.manifest.promotion_authority
        assert authority.dwell_class == dwell_class.value
        assert tuple(item.sample_rate_hz for item in authority.stream_authorities) == rates
        assert all(
            item.rf_bandwidth_hz == item.sample_rate_hz
            and item.starlink_channel == 3
            and item.starlink_edge == "lower"
            and item.channel_if_start_hz <= item.captured_if_start_hz
            and item.captured_if_stop_hz <= item.channel_if_stop_hz
            and item.captured_if_start_hz
            <= item.pilot_if_center_frequency_hz
            <= item.captured_if_stop_hz
            for item in authority.stream_authorities
        )

        seal = processing_database.catalog.run_seal_snapshot(queued.run_id)
        assert len(seal.products) == 98
        assert sum(item.media_type == "image/png" for item in seal.products) == 59
        assert processing_database.catalog.current_run_id(manifest.session_id) == queued.run_id
        path_reports = tuple(
            StandardNativePathReportV3.model_validate(
                artifacts.read_json(item.logical_uri, item.digest)
            )
            for item in seal.products
            if item.kind == "standard.path-report"
        )
        assert Counter(item.source.sample_rate_hz for item in path_reports) == {
            _LOW_RATE_HZ: 2,
            high_rate_hz: 2,
        }
        paired_product = next(
            item for item in seal.products if item.kind == "standard.paired-report"
        )
        paired = StandardNativePairedReportV5.model_validate(
            artifacts.read_json(paired_product.logical_uri, paired_product.digest)
        )
        assert paired.radio_sample_rates_hz == rates
        assert paired.resampling_permitted is False

        native_repository = CatalogStandardNativePresentationRepository(
            processing_database.catalog,
            artifacts,
        )
        repository = DefinitionDispatchedStandardPresentationRepository(
            CatalogStandardPresentationRepository(processing_database.catalog, artifacts),
            native_repository,
        )
        hierarchy = repository.subject_hierarchy(manifest.session_id)
        assert isinstance(hierarchy, StandardNativeSubjectHierarchyV4)
        assert {
            (item.sample_rate_hz, item.rf_bandwidth_hz) for item in hierarchy.eligibility.legs
        } == {
            (_LOW_RATE_HZ, _LOW_RATE_HZ),
            (high_rate_hz, high_rate_hz),
        }
        assert {
            (item.starlink_channel, item.starlink_edge) for item in hierarchy.eligibility.legs
        } == {(3, "lower")}
        paired_subject = hierarchy.rows[0]
        detail = repository.subject_detail(manifest.session_id, paired_subject.subject_id)
        assert isinstance(detail, StandardNativeSubjectDetailV4)
        inventory = repository.subject_png_inventory(
            manifest.session_id,
            paired_subject.subject_id,
        )
        assert isinstance(inventory, StandardNativePngArtifactInventoryV5)
        assert inventory.sample_rates_hz == rates
        assert len(inventory.artifacts) == 5
        waterfall = repository.subject_view(
            manifest.session_id,
            paired_subject.subject_id,
            StandardViewKindV2.WATERFALL,
            maximum_points=64,
        )
        assert isinstance(waterfall, StandardNativePlotViewV4)
        assert waterfall.sample_rates_hz == rates
        assert {item.receiver_path_id for item in waterfall.frequency_axes} == {
            path.path_id for path in paired_subject.receiver_paths
        }

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
            assert response.json()["schema_version"] == 4
            assert response.json()["eligibility"]["resampled"] is False
            assert {
                (item["starlink_channel"], item["starlink_edge"])
                for item in response.json()["eligibility"]["legs"]
            } == {(3, "lower")}
            response = client.get(f"{base}/{paired_subject.subject_id}/artifacts")
            assert response.status_code == 200
            assert response.json()["schema_version"] == 5
            assert response.json()["sample_rates_hz"] == list(rates)
            for artifact in response.json()["artifacts"]:
                png = client.get(artifact["href"])
                assert png.status_code == 200
                assert png.headers["content-type"] == "image/png"
                assert png.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        service.close()
        artifacts.close()
        pinned.close()
