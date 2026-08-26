from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.application import StandardReprocessService
from leo.artifacts import AnalysisArtifactStore, AnalysisRunManifestV3
from leo.catalog import CatalogSubjectBindingReader
from leo.contracts.digests import canonical_digest
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    RecordingManifestV3,
)
from leo.contracts.standard_native import (
    NativeWindowDisposition,
    StandardNativeNumericalWaterfallV3,
    StandardNativePowerTimelineV3,
    StandardNativeQualityV2,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_native_alternate_tracks import (
    NativeAlternateTrackProjectionDispositionV1,
    StandardNativeAlternateCfoTrackBankV4,
)
from leo.contracts.standard_native_glrt import StandardNativeFullCaptureGlrt20msV1
from leo.contracts.standard_native_path_report import StandardNativePathReportV3
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentDispositionV2,
    StandardNativeStatefulPathV2,
)
from leo.contracts.standard_native_terminal import (
    StandardNativePairedReportV4,
    StandardNativeRadioReportV4,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import CaptureState, SourceType, StreamState
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import ScopeIdentityV1, StageOutcome
from leo.pipeline import standard_native as standard_native_pipeline
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    RunRejectedError,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV3,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

from .conftest import ProcessingDatabase

pytestmark = pytest.mark.postgres

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = "7" * 40
_SECOND_RELEASE = "8" * 40
_PROFILE_NAME = "test-reviewed-standard-native-3m-device-axis-v3"
_SAMPLE_RATE_HZ = 3_000_000
_SAMPLE_COUNT = 262_144
_REFILL_SAMPLES = 65_536
_GAP_START = _REFILL_SAMPLES
_GAP_STOP = 2 * _REFILL_SAMPLES
_RADIO_IDS = ("radio-native-a", "radio-native-b")
_SESSION_LOSSLESS = "standard-native-operational-lossless"
_SESSION_GAPPED = "standard-native-operational-gapped"


def _bounded_profile_revision() -> CaptureProfileRevisionV2:
    production = load_profile_revision(
        _PROJECT_ROOT / "profiles/starlink-ch4-lower-3m-60s-device-axis-v3.yaml"
    )
    assert isinstance(production, CaptureProfileRevisionV2)
    values = production.profile.model_dump(mode="python")
    values.update(
        {
            "name": _PROFILE_NAME,
            "duration_seconds": None,
            "sample_count": _SAMPLE_COUNT,
            "refill_samples": _REFILL_SAMPLES,
            "settle_seconds": Decimal(0),
            "prime_refills": 0,
            "campaign": "bounded-native-standard-test",
        }
    )
    return CaptureProfileRevisionV2.from_profile(CaptureProfileV2.model_validate(values))


def _capture_plan(revision: CaptureProfileRevisionV2) -> CapturePlanV2:
    return cast(
        CapturePlanV2,
        compile_capture_plan(revision, _RADIO_IDS, source_type=SourceType.LIVE),
    )


def _capture_bundle(
    coordinator: AcquisitionCoordinator,
    plan: CapturePlanV2,
    *,
    session_id: str,
    gapped_radio_id: str | None = None,
) -> PublishedBundle:
    sources = {
        radio_id: FakeRadioSource(
            radio_id,
            seed=index,
            gaps_before_blocks=({1: _REFILL_SAMPLES} if radio_id == gapped_radio_id else None),
        )
        for index, radio_id in enumerate(_RADIO_IDS)
    }
    result = coordinator.capture_once(plan, sources, session_id=session_id)
    assert result.state is (
        CaptureState.DEGRADED if gapped_radio_id is not None else CaptureState.COMMITTED
    )
    assert isinstance(result.manifest, RecordingManifestV3)
    assert result.bundle is not None
    assert result.bundle.manifest == result.manifest
    coordinator.store.verify(result.bundle)
    return result.bundle


def _station_topology(manifest: RecordingManifestV3) -> StationReceiverTopologyV1:
    capture_start = min(stream.timing.first_sample.earliest_utc_ns for stream in manifest.streams)
    capture_end = max(stream.timing.last_sample.latest_utc_ns + 1 for stream in manifest.streams)
    valid_from = capture_start - 1_000_000_000
    valid_until = capture_end + 1_000_000_000
    return StationReceiverTopologyV1.create(
        station_id="standard-native-operational-station",
        topology_revision="standard-native-operational-topology-v1",
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
    assert isinstance(manifest, RecordingManifestV3)
    authority = CaptureHardwareBindingV3.create(
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
        attributes={
            "presentation": {
                "title": f"bounded native Standard {manifest.session_id}",
                "duration_seconds": _SAMPLE_COUNT / _SAMPLE_RATE_HZ,
            }
        },
        tags=manifest.tags,
        streams=_stream_registrations(bundle),
        path_authority=authority,
    )
    capture_authority = database.catalog.capture_path_authority(manifest.session_id)
    assert capture_authority.authority_kind == "station"
    assert capture_authority.evidence_only is False
    assert capture_authority.current_analysis_eligible is True
    assert capture_authority.promotion_permitted is True


def _assert_physical_zero_gap(store: RecordingStore, bundle: PublishedBundle) -> None:
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV3)
    gapped = next(stream for stream in manifest.streams if stream.radio.radio_id == _RADIO_IDS[0])
    clean = next(stream for stream in manifest.streams if stream.radio.radio_id == _RADIO_IDS[1])
    assert gapped.state is StreamState.PARTIAL
    assert gapped.logical_sample_count == _SAMPLE_COUNT
    assert gapped.observed_sample_count == _SAMPLE_COUNT - _REFILL_SAMPLES
    assert gapped.zero_fill_sample_count == _REFILL_SAMPLES
    assert clean.state is StreamState.COMPLETE
    assert clean.observed_sample_count == clean.logical_sample_count == _SAMPLE_COUNT
    reader = store.reader(bundle, gapped.stream_id)
    validity = reader.validity_inventory()
    assert validity.missing_sample_count == _REFILL_SAMPLES
    assert len(validity.segments) == 2
    span = reader.read_device_span(0, _SAMPLE_COUNT)
    assert span.valid_samples[:_GAP_START].all()
    assert not span.valid_samples[_GAP_START:_GAP_STOP].any()
    assert span.valid_samples[_GAP_STOP:].all()
    assert not span.samples[_GAP_START:_GAP_STOP].any()


def _assert_v4_bindings(
    database: ProcessingDatabase,
    run_id: str,
    manifest: RecordingManifestV3,
) -> None:
    reader = CatalogSubjectBindingReader(database.catalog)
    for stream in manifest.streams:
        for receiver_id in stream.applied_settings.receiver_ids:
            scope = ScopeIdentityV1.receiver_path(
                session_id=manifest.session_id,
                stream_id=stream.stream_id,
                receiver_id=receiver_id,
            )
            binding = reader.receiver_path_native(run_id, scope)
            assert isinstance(binding, StandardPathInputBindV4)
            assert binding.sample_rate_hz == _SAMPLE_RATE_HZ
            assert binding.logical_sample_count == stream.logical_sample_count
            assert binding.observed_sample_count == stream.observed_sample_count
            assert binding.missing_sample_count == stream.zero_fill_sample_count
            assert binding.validity_inventory.inventory_digest == (stream.validity_inventory_sha256)
            with pytest.raises(ValidationError):
                reader.receiver_path(run_id, scope)


def _assert_native_products(
    database: ProcessingDatabase,
    artifacts: AnalysisArtifactStore,
    seal: object,
    manifest: RecordingManifestV3,
    *,
    gapped_radio_id: str | None,
) -> None:
    products = seal.products  # type: ignore[attr-defined]
    assert len(products) == 40
    assert Counter(item.kind for item in products) == {
        "quality.summary": 4,
        "standard.power-timeline": 4,
        "standard.numerical-waterfall": 4,
        "standard.probe-schedule": 4,
        "standard.native-stateful-path": 4,
        "standard.full-capture-glrt20ms": 4,
        "standard.path-report": 4,
        "standard.alternate-cfo-track-bank": 4,
        "standard.alternate-cfo-tracks-png": 4,
        "standard.radio-report": 2,
        "standard.paired-report": 1,
        "standard.waterfall-png": 1,
    }
    json_models = {
        "quality.summary": StandardNativeQualityV2,
        "standard.power-timeline": StandardNativePowerTimelineV3,
        "standard.numerical-waterfall": StandardNativeNumericalWaterfallV3,
        "standard.probe-schedule": StandardProbeScheduleV3,
        "standard.native-stateful-path": StandardNativeStatefulPathV2,
        "standard.full-capture-glrt20ms": StandardNativeFullCaptureGlrt20msV1,
        "standard.alternate-cfo-track-bank": StandardNativeAlternateCfoTrackBankV4,
        "standard.path-report": StandardNativePathReportV3,
        "standard.radio-report": StandardNativeRadioReportV4,
        "standard.paired-report": StandardNativePairedReportV4,
    }
    streams = {stream.radio.radio_id: stream for stream in manifest.streams}
    stateful_documents: list[StandardNativeStatefulPathV2] = []
    for product in products:
        if product.media_type == "image/png":
            assert artifacts.read_bytes(product.logical_uri, product.digest).startswith(b"\x89PNG")
            if product.kind == "standard.alternate-cfo-tracks-png":
                dependencies = database.catalog.product_direct_dependencies(product.product_id)
                assert len(dependencies) == 1
                assert dependencies[0].kind == "standard.native-stateful-path"
                assert dependencies[0].scope_key == product.scope_key
            continue
        model = json_models[product.kind]
        document = model.model_validate(artifacts.read_json(product.logical_uri, product.digest))
        if hasattr(document, "source"):
            source = document.source
            stream = streams[source.radio_id]
            assert source.sample_rate_hz == _SAMPLE_RATE_HZ
            assert source.logical_sample_count == _SAMPLE_COUNT
            assert source.observed_sample_count == stream.observed_sample_count
            assert source.missing_sample_count == stream.zero_fill_sample_count
            expected_coverage = stream.observed_sample_count / _SAMPLE_COUNT
            assert product.coverage == pytest.approx(expected_coverage)
        if isinstance(document, StandardNativeStatefulPathV2):
            stateful_documents.append(document)
        if isinstance(document, StandardNativeFullCaptureGlrt20msV1):
            assert product.scope is not None
            binding = CatalogSubjectBindingReader(database.catalog).receiver_path_native(
                seal.execution.run_id,  # type: ignore[attr-defined]
                product.scope,
            )
            assert document.source == StandardNativeSourceV1.from_path_binding(binding)
            assert len(document.opportunities) == document.accounting.scheduled_count == 7
            expected_valid = 3 if document.source.radio_id == gapped_radio_id else 7
            expected_gap_excluded = 4 if document.source.radio_id == gapped_radio_id else 0
            assert document.accounting.valid_count == expected_valid
            assert document.accounting.analyzed_count == expected_valid
            assert document.accounting.gap_excluded_count == expected_gap_excluded
            assert document.accounting.continuity_boundary_excluded_count == 0
            assert document.accounting.outside_span_count == 0
            assert document.accounting.passing_count <= expected_valid
            assert sum(len(item.windows) for item in document.segments) == expected_valid
            assert tuple(item.continuity_segment for item in document.segments) == (
                document.source.continuity_segments
            )
            dispositions = tuple(item.validity.disposition for item in document.opportunities)
            assert dispositions.count(NativeWindowDisposition.VALID) == expected_valid
            assert dispositions.count(NativeWindowDisposition.GAP_OVERLAP) == expected_gap_excluded
            assert document.native_evidence_only is True
            assert document.current_eligible is False
        if isinstance(document, StandardNativePathReportV3):
            assert product.scope is not None
            same_scope = {
                item.kind: item
                for item in products
                if item.scope_key == product.scope_key
                and item.kind
                in {
                    "quality.summary",
                    "standard.power-timeline",
                    "standard.numerical-waterfall",
                    "standard.probe-schedule",
                    "standard.native-stateful-path",
                    "standard.full-capture-glrt20ms",
                }
            }
            assert document.products.quality_product_digest == same_scope["quality.summary"].digest
            assert (
                document.products.power_timeline_product_digest
                == same_scope["standard.power-timeline"].digest
            )
            assert (
                document.products.numerical_waterfall_product_digest
                == same_scope["standard.numerical-waterfall"].digest
            )
            assert (
                document.products.probe_schedule_product_digest
                == same_scope["standard.probe-schedule"].digest
            )
            assert (
                document.products.stateful_path_product_digest
                == same_scope["standard.native-stateful-path"].digest
            )
            assert (
                document.products.full_capture_glrt20ms_product_digest
                == same_scope["standard.full-capture-glrt20ms"].digest
            )
            assert document.schedule_execution.accounting.analyzed_count == (
                document.schedule_execution.accounting.valid_count
            )
            assert document.qam_statistics.qam_result_count == 0
            assert document.scientific_disposition.value == "insufficient"
            assert document.cross_segment_association_permitted is False
        if isinstance(document, StandardNativeAlternateCfoTrackBankV4):
            assert product.scope is not None
            binding = CatalogSubjectBindingReader(database.catalog).receiver_path_native(
                seal.execution.run_id,  # type: ignore[attr-defined]
                product.scope,
            )
            assert document.source == StandardNativeSourceV1.from_path_binding(binding)
            dependencies = database.catalog.product_direct_dependencies(product.product_id)
            assert len(dependencies) == 1
            stateful_product = dependencies[0]
            assert stateful_product.kind == "standard.native-stateful-path"
            assert stateful_product.scope_key == product.scope_key
            assert document.source_stateful_product_digest == stateful_product.digest
            stateful = StandardNativeStatefulPathV2.model_validate(
                artifacts.read_json(stateful_product.logical_uri, stateful_product.digest)
            )
            assert document.source_stateful_path_digest == stateful.stateful_path_digest
            assert document.science_configuration_digest == stateful.science_configuration_digest
            assert tuple(item.continuity_segment for item in document.segments) == (
                document.source.continuity_segments
            )
            assert tuple(item.stateful_segment_digest for item in document.segments) == tuple(
                item.segment_digest for item in stateful.segments
            )
            assert document.projection_status == "insufficient_data"
            assert document.source_observation_count == 0
            assert document.detected_track_count == document.returned_track_count == 0
            assert document.truncated_track_count == 0
            assert all(
                item.projection_disposition
                is NativeAlternateTrackProjectionDispositionV1.NO_STATEFUL_SCIENCE
                for item in document.segments
            )
            assert document.native_evidence_only is True
            assert document.current_eligible is False
            assert document.cross_segment_association_permitted is False
        if isinstance(document, (StandardNativeRadioReportV4, StandardNativePairedReportV4)):
            assert document.native_evidence_only is True
            assert document.current_eligible is False
            assert document.aggregate_qam_statistics.qam_result_count == 0
            assert document.aggregate_terminal_tracks.returned_trajectory_count == 0
            assert document.scientific_disposition.value == "insufficient"

    assert len(stateful_documents) == 4
    if gapped_radio_id is None:
        assert {item.stateful_science_status for item in stateful_documents} == {"complete"}
        assert all(
            item.native_evidence_only and not item.current_eligible for item in stateful_documents
        )
    else:
        clean = tuple(
            item for item in stateful_documents if item.source.radio_id != gapped_radio_id
        )
        gapped = tuple(
            item for item in stateful_documents if item.source.radio_id == gapped_radio_id
        )
        assert len(clean) == len(gapped) == 2
        assert {item.stateful_science_status for item in clean} == {"complete"}
        assert {item.stateful_science_status for item in gapped} == {"partial_coverage"}
        assert all(item.analyzed_outer_window_count == 0 for item in gapped)
        assert all(
            segment.disposition is NativeStatefulSegmentDispositionV2.NO_VALID_GLOBAL_PROBE
            and segment.local_science is None
            for item in gapped
            for segment in item.segments
        )
        assert all(item.native_evidence_only and not item.current_eligible for item in gapped)


def _run_manual_native_evidence(
    database: ProcessingDatabase,
    artifacts: AnalysisArtifactStore,
    service: ProcessingService,
    application: StandardReprocessService,
    bundle: PublishedBundle,
    *,
    gapped_radio_id: str | None,
) -> str:
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV3)
    assert database.catalog.active_run_id(manifest.session_id) is None
    previous_current = database.catalog.current_run_id(manifest.session_id)
    result = application.queue_native_evidence(manifest.session_id)
    assert result.pipeline_family == "standard-native-evidence-v1"
    assert result.promotion_policy == "evidence_only"
    assert result.previous_current_run_id == previous_current
    assert result.queued_job_count == 12
    _assert_v4_bindings(database, result.run_id, manifest)

    executions = []
    while execution := service.run_once(worker_id="standard-native-operational-worker"):
        executions.append(execution)
        assert execution.succeeded, execution.error
    assert len(executions) == 12
    service.finalize_run(result.run_id)
    seal = database.catalog.run_seal_snapshot(result.run_id)
    assert len(seal.jobs) == 12
    assert {item.state for item in seal.jobs} == {"succeeded"}
    outcomes = Counter(item.outcome for item in seal.jobs)
    if gapped_radio_id is None:
        assert outcomes == {StageOutcome.COMPLETE.value: 8, StageOutcome.INSUFFICIENT_DATA.value: 4}
    else:
        assert outcomes == {
            StageOutcome.COMPLETE.value: 3,
            StageOutcome.PARTIAL_COVERAGE.value: 5,
            StageOutcome.INSUFFICIENT_DATA.value: 4,
        }
    assert seal.execution.trigger == "reprocess"
    assert seal.execution.promotion_policy == "evidence_only"
    assert seal.execution.pipeline_lane == "standard"
    _assert_native_products(
        database,
        artifacts,
        seal,
        manifest,
        gapped_radio_id=gapped_radio_id,
    )
    assert database.catalog.current_run_id(manifest.session_id) == previous_current
    assert database.catalog.active_run_id(manifest.session_id) is None
    return result.run_id


def _run_native_current(
    database: ProcessingDatabase,
    artifacts: AnalysisArtifactStore,
    service: ProcessingService,
    application: StandardReprocessService,
    bundle: PublishedBundle,
    *,
    gapped_radio_id: str | None,
) -> str:
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV3)
    previous_current = database.catalog.current_run_id(manifest.session_id)
    result = application.queue(manifest.session_id)
    assert result.previous_current_run_id == previous_current
    assert result.queued_job_count == 12
    _assert_v4_bindings(database, result.run_id, manifest)
    assert database.catalog.current_run_id(manifest.session_id) == previous_current

    executions = []
    while execution := service.run_once(worker_id="standard-native-current-worker"):
        executions.append(execution)
        assert execution.succeeded, execution.error
    assert len(executions) == 12
    published = service.finalize_run(result.run_id)
    assert isinstance(published.manifest, AnalysisRunManifestV3)
    authority = published.manifest.promotion_authority
    capture_authority = database.catalog.capture_path_authority(manifest.session_id)
    assert authority.source_manifest_digest == bundle.manifest_sha256
    assert authority.pipeline_release_id == _RELEASE
    assert authority.pipeline_definition_id == authority.pipeline_definition.definition_id
    assert authority.pipeline_definition.automatic_eligible is True
    assert authority.pipeline_definition.promotion_allowed is True
    assert (
        authority.expanded_plan_digest
        == database.catalog.run_execution_info(result.run_id).expanded_plan_digest
    )
    assert authority.profile_revision_digest == (
        manifest.capture_plan.profile_revision.revision_digest
    )
    assert authority.sample_rate_hz == _SAMPLE_RATE_HZ
    assert authority.capture_plan_digest == manifest.capture_plan.plan_digest
    assert authority.capture_hardware_binding_digest == capture_authority.authority_digest
    assert len(authority.terminal_products) == 7
    assert Counter(item.kind for item in authority.terminal_products) == {
        "standard.path-report": 4,
        "standard.radio-report": 2,
        "standard.paired-report": 1,
    }
    assert published.manifest.trigger == "reprocess"
    assert published.manifest.promotion_policy == "current"
    assert published.manifest.processing_status == "succeeded"

    seal = database.catalog.run_seal_snapshot(result.run_id)
    _assert_native_products(
        database,
        artifacts,
        seal,
        manifest,
        gapped_radio_id=gapped_radio_id,
    )
    assert database.catalog.current_run_id(manifest.session_id) == result.run_id
    assert database.catalog.active_run_id(manifest.session_id) is None
    return result.run_id


def test_real_postgres_standard_native_operational_vertical(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _bounded_profile_revision()
    assert _PROFILE_NAME not in standard_native_pipeline.STANDARD_NATIVE_PROFILE_RATE_HZ
    assert _PROFILE_NAME not in standard_native_pipeline.STANDARD_NATIVE_PROFILE_REVISION_DIGESTS
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
    lossless = _capture_bundle(
        coordinator,
        plan,
        session_id=_SESSION_LOSSLESS,
    )
    gapped = _capture_bundle(
        coordinator,
        plan,
        session_id=_SESSION_GAPPED,
        gapped_radio_id=_RADIO_IDS[0],
    )
    _assert_physical_zero_gap(recording_store, gapped)

    assert isinstance(lossless.manifest, RecordingManifestV3)
    topology = _station_topology(lossless.manifest)
    processing_database.catalog.register_station_topology(topology)
    _register_bundle(processing_database, lossless, topology)
    _register_bundle(processing_database, gapped, topology)
    with processing_database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM analysis_run")).scalar_one() == 0

    registry = production_standard_native_evidence_registry()
    native_stage_configuration = production_standard_native_evidence_configuration()
    native_path_spec = registry.get("path-standard-native").spec
    assert native_path_spec.algorithm_version == "standard-native-evidence-v7"
    assert native_path_spec.configuration_schema == "path-standard-native.evidence.v6"
    assert "probes" not in native_stage_configuration["path-standard-native"]
    configuration: dict[str, object] = {
        "display_version": "standard-native-operational-v1",
        "stages": native_stage_configuration,
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "standard-native.txt").write_text("pinned native worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "real-postgres-standard-native-operational"},
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

    for bundle in (lossless, gapped):
        manifest = bundle.manifest
        assert isinstance(manifest, RecordingManifestV3)
        native_plan = standard_native_pipeline.compile_standard_native_run_plan(
            manifest,
            manifest_digest=bundle.manifest_sha256,
            pipeline_release_id=_RELEASE,
        )
        assert (len(native_plan.jobs), len(native_plan.edges)) == (12, 14)
        assert {item.stage_key for item in native_plan.jobs} == set(
            standard_native_pipeline.STANDARD_NATIVE_STAGE_KEYS
        )
        assert all("resampl" not in item.stage_key for item in native_plan.jobs)
        assert all(
            item.iq_access.value == "receiver_path"
            for item in native_plan.jobs
            if item.stage_key == "path-standard-native"
        )
        assert all(
            item.iq_access.value == "none"
            for item in native_plan.jobs
            if item.stage_key == "path-alternate-tracks-native"
        )
        alternate_nodes = tuple(
            item for item in native_plan.jobs if item.stage_key == "path-alternate-tracks-native"
        )
        assert {
            (edge.job_node_id, edge.depends_on_job_node_id)
            for edge in native_plan.edges
            if edge.job_node_id in {item.node_id for item in alternate_nodes}
        } == {
            (
                item.node_id,
                item.node_id.replace("-alternate-tracks-native", "-standard-native"),
            )
            for item in alternate_nodes
        }

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
        current_run_ids = (
            _run_native_current(
                processing_database,
                artifacts,
                service,
                application,
                lossless,
                gapped_radio_id=None,
            ),
            _run_native_current(
                processing_database,
                artifacts,
                service,
                application,
                gapped,
                gapped_radio_id=_RADIO_IDS[0],
            ),
        )
        evidence_run_id = _run_manual_native_evidence(
            processing_database,
            artifacts,
            service,
            application,
            gapped,
            gapped_radio_id=_RADIO_IDS[0],
        )
        with processing_database.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    text(
                        "SELECT id, trigger, promotion_policy, pipeline_lane, state "
                        "FROM analysis_run ORDER BY session_id"
                    )
                )
            )
        assert {row.id for row in rows} == {*current_run_ids, evidence_run_id}
        assert {
            (row.trigger, row.promotion_policy, row.pipeline_lane, row.state) for row in rows
        } == {
            ("reprocess", "current", "standard", "succeeded"),
            ("reprocess", "evidence_only", "standard", "succeeded"),
        }
        assert processing_database.catalog.current_run_id(_SESSION_LOSSLESS) == (current_run_ids[0])
        assert processing_database.catalog.current_run_id(_SESSION_GAPPED) == current_run_ids[1]

        second_executable = tmp_path / "worker-executable-second-release"
        second_executable.mkdir()
        (second_executable / "standard-native.txt").write_text("second pinned native worker\n")
        second_loaded = derive_loaded_worker_release_for_tests(
            pipeline_release_id=_SECOND_RELEASE,
            code_revision=_SECOND_RELEASE,
            registry=registry,
            configuration=configuration,
            environment_document={"name": "native-plan-tamper-regression"},
            executable_root=second_executable,
        )
        processing_database.catalog.add_pipeline_release(
            release_id=_SECOND_RELEASE,
            code_revision=_SECOND_RELEASE,
            environment_digest=second_loaded.authority.environment_digest,
            graph_digest=second_loaded.authority.graph_digest,
            configuration=configuration,
            executable_digest=second_loaded.authority.executable_digest,
        )
        second_service = ProcessingService(
            catalog=processing_database.catalog,
            artifacts=artifacts,
            registry=registry,
            iq_readers=RecordingIqReaderProvider(recordings),
            lease_for=timedelta(seconds=30),
            heartbeat_interval=timedelta(seconds=5),
            loaded_worker_release=second_loaded,
        )
        second_application = StandardReprocessService(
            catalog=processing_database.catalog,
            recordings=recordings,
            processing=second_service,
            pipeline_release_id=_SECOND_RELEASE,
        )
        try:
            candidate = second_application.queue(_SESSION_GAPPED)
            assert candidate.previous_current_run_id == current_run_ids[1]
            while execution := second_service.run_once(worker_id="native-tamper-worker"):
                assert execution.succeeded, execution.error
            with processing_database.engine.begin() as connection:
                connection.execute(
                    text("UPDATE analysis_run SET expanded_plan_digest=:digest WHERE id=:run_id"),
                    {
                        "digest": canonical_digest({"tampered": "expanded-plan"}),
                        "run_id": candidate.run_id,
                    },
                )
            with pytest.raises(RunRejectedError, match="expanded-plan authority changed"):
                second_service.finalize_run(candidate.run_id)
            assert processing_database.catalog.current_run_id(_SESSION_GAPPED) == current_run_ids[1]
        finally:
            second_service.close()
    finally:
        service.close()
        artifacts.close()
        pinned.close()
