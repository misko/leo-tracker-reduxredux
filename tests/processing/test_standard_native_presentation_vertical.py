from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
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
from leo.artifacts import AnalysisArtifactStore
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
)
from leo.contracts.standard_native import StandardNativeNumericalWaterfallV4
from leo.contracts.standard_native_terminal import StandardNativePairedReportV7
from leo.pipeline import standard_native as standard_native_pipeline
from leo.presentation.standard_native_artifacts import (
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8,
    STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10,
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactInventoryV8,
    StandardNativePngArtifactInventoryV10,
)
from leo.presentation.standard_native_pipeline import (
    StandardNativePlotViewV3,
    StandardNativeSubjectDetailV3,
    StandardNativeSubjectHierarchyV3,
)
from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.storage import PinnedLocalRoot, RecordingStore

from .conftest import ProcessingDatabase
from .test_standard_native_operational_vertical import (
    _PROFILE_NAME,
    _RADIO_IDS,
    _RELEASE,
    _SAMPLE_RATE_HZ,
    _bounded_profile_revision,
    _capture_bundle,
    _capture_plan,
    _register_bundle,
    _run_native_current,
    _station_topology,
)

pytestmark = pytest.mark.postgres


def test_real_postgres_promoted_gapped_native_run_is_presented_as_current_partial(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _bounded_profile_revision()
    monkeypatch.setitem(
        standard_native_pipeline.STANDARD_NATIVE_PROFILE_RATE_HZ,
        _PROFILE_NAME,
        _SAMPLE_RATE_HZ,
    )
    monkeypatch.setitem(
        standard_native_pipeline.STANDARD_NATIVE_PROFILE_REVISION_DIGESTS,
        _PROFILE_NAME,
        revision.revision_digest,
    )
    plan = _capture_plan(revision)
    bulk_root = tmp_path / "bulk"
    coordinator = AcquisitionCoordinator(
        RecordingStore(bulk_root),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    bundle = _capture_bundle(
        coordinator,
        plan,
        session_id="standard-native-presentation-gapped",
        gapped_radio_id=_RADIO_IDS[0],
    )
    topology = _station_topology(bundle.manifest)
    processing_database.catalog.register_station_topology(topology)
    _register_bundle(processing_database, bundle, topology)

    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "standard-native-presentation-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned presentation worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "real-postgres-standard-native-presentation"},
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
        run_id = _run_native_current(
            processing_database,
            artifacts,
            service,
            application,
            bundle,
            gapped_radio_id=_RADIO_IDS[0],
        )
        native = CatalogStandardNativePresentationRepository(
            processing_database.catalog,
            artifacts,
        )
        repository = DefinitionDispatchedStandardPresentationRepository(
            CatalogStandardPresentationRepository(processing_database.catalog, artifacts),
            native,
        )

        hierarchy = repository.subject_hierarchy(bundle.manifest.session_id)
        assert isinstance(hierarchy, StandardNativeSubjectHierarchyV3)
        assert hierarchy.eligibility.sample_rate_hz == _SAMPLE_RATE_HZ
        assert hierarchy.eligibility.capture_state == "degraded"
        assert hierarchy.eligibility.capture_committed is False
        assert [row.subject_kind.value for row in hierarchy.rows] == [
            "paired",
            "radio",
            "radio",
        ]
        paired = hierarchy.rows[0]
        assert paired.state.value == "current"
        assert paired.coverage_status == "partial_coverage"

        seal = processing_database.catalog.run_seal_snapshot(run_id)
        paired_product = next(
            product for product in seal.products if product.kind == "standard.paired-report"
        )
        paired_report = StandardNativePairedReportV7.model_validate(
            artifacts.read_json(paired_product.logical_uri, paired_product.digest)
        )
        expected_samples = sum(
            path.source.logical_sample_count
            for radio in paired_report.radios
            for path in radio.paths
        )
        terminal = paired.terminal
        assert terminal.expected_complex_sample_count == expected_samples
        assert terminal.valid_complex_sample_count == (
            paired_report.aggregate_statistics.valid_complex_sample_count
        )
        assert terminal.sufficient_statistics == paired_report.aggregate_statistics
        assert terminal.terminal_opportunities == (paired_report.aggregate_terminal_opportunities)
        assert terminal.qam_statistics == paired_report.aggregate_qam_statistics
        assert terminal.terminal_tracks == paired_report.aggregate_terminal_tracks
        assert terminal.valid_utc_intervals == paired_report.valid_utc_intervals
        assert terminal.scientific_disposition == paired_report.scientific_disposition
        assert terminal.valid_samples_only is True
        assert terminal.cross_gap_operation_permitted is False

        detail = repository.subject_detail(bundle.manifest.session_id, paired.subject_id)
        assert isinstance(detail, StandardNativeSubjectDetailV3)
        assert detail.subject.state.value == "current"
        assert detail.subject.coverage_status == "partial_coverage"
        assert detail.available_artifacts == ("waterfall",)
        assert all(item.invalid_zero_fill_excluded for item in detail.receiver_path_evidence)
        paired_inventory = repository.subject_png_inventory(
            bundle.manifest.session_id,
            paired.subject_id,
        )
        assert isinstance(paired_inventory, StandardNativePngArtifactInventoryV8)
        assert tuple(item.name for item in paired_inventory.artifacts) == (
            STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8
        )
        path_subject = detail.receiver_path_expansions[0]
        path_inventory = repository.subject_png_inventory(
            bundle.manifest.session_id,
            path_subject.subject_id,
        )
        assert isinstance(path_inventory, StandardNativePngArtifactInventoryV10)
        assert tuple(item.name for item in path_inventory.artifacts) == (
            STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10
        )

        # Simulate an already sealed pre-V9 Current run.  The API upgrade must
        # continue to inventory and serve its immutable schema-3 pilot PNGs.
        projection = native._load(bundle.manifest.session_id)
        assert projection is not None
        legacy_projection = replace(
            projection,
            products=tuple(
                replace(product, schema_version=3)
                if product.kind
                in {
                    "standard.pilot-doppler-segments-png",
                    "standard.pilot-carrier-tracking-png",
                    "standard.pilot-segment-rates-png",
                }
                and product.schema_version == 4
                else product
                for product in projection.products
                if product.kind
                not in {
                    "standard.doppler-waterfall-png",
                    "standard.glrt-epoch-timing-png",
                    "standard.glrt-epoch-rate-png",
                }
            ),
        )
        legacy_native = CatalogStandardNativePresentationRepository(
            processing_database.catalog,
            artifacts,
        )
        monkeypatch.setattr(
            legacy_native,
            "_load",
            lambda _session_id: legacy_projection,
        )
        legacy_inventory = legacy_native.subject_png_inventory(
            bundle.manifest.session_id,
            path_subject.subject_id,
        )
        assert isinstance(legacy_inventory, StandardNativePngArtifactInventoryV4)
        assert tuple(
            item.product_schema_version
            for item in legacy_inventory.artifacts
            if item.name in {"pilot-doppler", "pilot-carrier-tracking", "pilot-segment-rates"}
        ) == (3, 3, 3)
        legacy_pilot_png = legacy_native.subject_named_png_artifact(
            bundle.manifest.session_id,
            path_subject.subject_id,
            "pilot-doppler",
        )
        assert legacy_pilot_png is not None
        assert legacy_pilot_png.startswith(b"\x89PNG\r\n\x1a\n")

        waterfall = repository.subject_view(
            bundle.manifest.session_id,
            paired.subject_id,
            StandardViewKindV2.WATERFALL,
            maximum_points=64,
        )
        assert isinstance(waterfall, StandardNativePlotViewV3)
        assert waterfall.sample_rate_hz == _SAMPLE_RATE_HZ
        assert waterfall.state.value == "partial"
        raw_waterfall_count = sum(
            len(
                StandardNativeNumericalWaterfallV4.model_validate(
                    artifacts.read_json(product.logical_uri, product.digest)
                ).waterfall.tiles
            )
            for product in seal.products
            if product.kind == "standard.numerical-waterfall"
        )
        assert waterfall.source_point_count == raw_waterfall_count
        assert waterfall.returned_point_count == raw_waterfall_count
        assert waterfall.truncated is False
        invalid = tuple(item for item in waterfall.waterfall_tiles if not item.valid)
        assert invalid
        assert all(item.transform_count == 0 for item in invalid)
        assert all(all(value is None for value in item.power_dbfs) for item in invalid)
        assert repository.subject_png_artifact(
            bundle.manifest.session_id,
            paired.subject_id,
            StandardViewKindV2.WATERFALL,
        ).startswith(b"\x89PNG")

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
            response = client.get(f"/api/v1/recordings/{bundle.manifest.session_id}")
            assert response.status_code == 200
            assert response.json()["session_id"] == bundle.manifest.session_id
            assert response.json()["capture_health"] == "partial"
            base = f"/api/v2/recordings/{bundle.manifest.session_id}/standard-subjects"
            response = client.get(base)
            assert response.status_code == 200
            assert response.json()["schema_version"] == 3
            assert response.json()["rows"][0]["state"] == "current"
            assert response.json()["rows"][0]["coverage_status"] == "partial_coverage"
            response = client.get(f"{base}/{paired.subject_id}/views/waterfall")
            assert response.status_code == 200
            assert response.json()["sample_rate_hz"] == _SAMPLE_RATE_HZ
            assert any(not item["valid"] for item in response.json()["waterfall_tiles"])
            response = client.get(f"{base}/{paired.subject_id}/views/waterfall.png")
            assert response.status_code == 200
            assert response.content.startswith(b"\x89PNG")
            for subject, expected_names in (
                (paired, STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V8),
                (path_subject, STANDARD_NATIVE_PATH_ARTIFACT_NAMES_V10),
            ):
                inventory_path = f"{base}/{subject.subject_id}/artifacts"
                response = client.get(inventory_path)
                assert response.status_code == 200
                assert tuple(item["name"] for item in response.json()["artifacts"]) == (
                    expected_names
                )
                assert client.head(inventory_path).status_code == 200
                inventory = response.json()["artifacts"]
                for item in inventory:
                    response = client.get(item["href"])
                    assert response.status_code == 200
                    assert response.headers["content-type"] == "image/png"
                    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
                    head = client.head(item["href"])
                    assert head.status_code == 200
                    assert head.headers["content-type"] == "image/png"

            for name in ("cfo-alternate", "trajectory-accounting", "pilot-doppler"):
                response = client.get(f"{base}/{paired.subject_id}/artifacts/{name}.png")
                assert response.status_code == 404
    finally:
        service.close()
        artifacts.close()
        pinned.close()
