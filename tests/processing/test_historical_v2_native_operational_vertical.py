from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_configuration,
    production_standard_native_evidence_registry,
)
from leo.application import StandardReprocessError, StandardReprocessService
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogSubjectBindingReader
from leo.contracts.digests import canonical_digest
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import RadioSettingsV1
from leo.contracts.recording import CompressionSettingsV1, RecordingManifestV2
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import CaptureState, SourceType, StreamState
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import ScopeIdentityV1, StageOutcome
from leo.pipeline import standard_native as standard_native_pipeline
from leo.pipeline.standard_native import HistoricalV2NativeAdmission
from leo.processing import (
    ProcessingService,
    RecordingIqReaderProvider,
    derive_loaded_worker_release_for_tests,
)
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV2,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.storage import PinnedLocalRoot, PublishedBundle, RecordingStore

from .conftest import ProcessingDatabase

pytestmark = pytest.mark.postgres

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = "8" * 40
_PROFILE_NAME = "test-reviewed-historical-v2-native-5m"
_SAMPLE_RATE_HZ = 5_000_000
_SAMPLE_COUNT = 262_144
_REFILL_SAMPLES = 65_536
_RADIO_IDS = ("radio-historical-a", "radio-historical-b")
_SESSION_ID = "historical-v2-native-operational-gapped"


def _bounded_profile_revision() -> CaptureProfileRevisionV2:
    production = load_profile_revision(
        _PROJECT_ROOT / "profiles/starlink-ch4-lower-5m-60s-segmented-v2.yaml"
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
            "campaign": "bounded-historical-v2-native-test",
        }
    )
    return CaptureProfileRevisionV2.from_profile(CaptureProfileV2.model_validate(values))


def _capture_bundle(
    tmp_path: Path, revision: CaptureProfileRevisionV2
) -> tuple[
    RecordingStore,
    PublishedBundle,
]:
    plan = compile_capture_plan(revision, _RADIO_IDS, source_type=SourceType.LIVE)
    assert isinstance(plan, CapturePlanV2)
    store = RecordingStore(tmp_path / "bulk")
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id="zstd-128m-v1",
            target_uncompressed_bytes=1_048_576,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            _RADIO_IDS[0]: FakeRadioSource(
                _RADIO_IDS[0],
                seed=31,
                gaps_before_blocks={1: _REFILL_SAMPLES},
            ),
            _RADIO_IDS[1]: FakeRadioSource(_RADIO_IDS[1], seed=37),
        },
        session_id=_SESSION_ID,
        extra_tags=(
            "gain_mode:stream-0:manual",
            "gain_mode:stream-1:manual",
            "tuning:stream-0:ch1:lower",
            "tuning:stream-1:ch1:lower",
            "tuning_policy:same",
        ),
        requested_settings_by_radio=dict.fromkeys(
            _RADIO_IDS,
            RadioSettingsV1(
                center_frequency_hz=959_687_500,
                sample_rate_hz=revision.profile.sample_rate_hz,
                bandwidth_hz=revision.profile.bandwidth_hz,
                receiver_ids=revision.profile.receivers,
                gain_mode=revision.profile.gain_mode,
                gains=revision.profile.gains,
            ),
        ),
    )
    assert result.state is CaptureState.DEGRADED
    assert isinstance(result.manifest, RecordingManifestV2)
    assert result.bundle is not None
    store.verify(result.bundle)
    return store, result.bundle


def _station_topology(manifest: RecordingManifestV2) -> StationReceiverTopologyV1:
    timings = tuple(stream.timing for stream in manifest.streams)
    assert all(item is not None for item in timings)
    capture_start = min(item.first_sample.earliest_utc_ns for item in timings if item is not None)
    capture_end = max(item.last_sample.latest_utc_ns + 1 for item in timings if item is not None)
    valid_from = capture_start - 1_000_000_000
    valid_until = capture_end + 1_000_000_000
    return StationReceiverTopologyV1.create(
        station_id="historical-v2-native-operational-station",
        topology_revision="historical-v2-native-operational-topology-v1",
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
            for stream in manifest.streams
        ),
    )


def _register_bundle(
    database: ProcessingDatabase,
    bundle: PublishedBundle,
    topology: StationReceiverTopologyV1,
) -> None:
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV2)
    authority = CaptureHardwareBindingV2.create(
        manifest,
        observed_manifest_file_digest=bundle.manifest_sha256,
        topology=topology,
    )
    database.catalog.register_station_topology(topology)
    assert database.catalog.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=bundle.uri,
        manifest_digest=bundle.manifest_sha256,
        allocated_bytes=sum(
            item.stat().st_size for item in bundle.path.rglob("*") if item.is_file()
        ),
        attributes={"presentation": {"title": "bounded historical V2 native evidence"}},
        tags=manifest.tags,
        streams=_stream_registrations(bundle),
        path_authority=authority,
    )


def test_real_postgres_historical_v2_runs_through_native_v4_graph(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _bounded_profile_revision()
    assert _PROFILE_NAME not in standard_native_pipeline.STANDARD_NATIVE_V2_PROFILE_ADMISSIONS
    monkeypatch.setitem(
        standard_native_pipeline.STANDARD_NATIVE_V2_PROFILE_ADMISSIONS,
        _PROFILE_NAME,
        HistoricalV2NativeAdmission(
            revision_digest=revision.revision_digest,
            sample_rate_hz=_SAMPLE_RATE_HZ,
            expected_sample_count=_SAMPLE_COUNT,
            counter_gaps_allowed=True,
        ),
    )
    recording_store, bundle = _capture_bundle(tmp_path, revision)
    manifest = bundle.manifest
    assert isinstance(manifest, RecordingManifestV2)
    gapped = next(item for item in manifest.streams if item.radio.radio_id == _RADIO_IDS[0])
    clean = next(item for item in manifest.streams if item.radio.radio_id == _RADIO_IDS[1])
    assert gapped.state is StreamState.PARTIAL
    assert gapped.continuity.device_span_sample_count == _SAMPLE_COUNT
    assert gapped.captured_sample_count == _SAMPLE_COUNT - _REFILL_SAMPLES
    assert gapped.continuity.missing_sample_count == _REFILL_SAMPLES
    assert clean.state is StreamState.COMPLETE
    assert clean.captured_sample_count == _SAMPLE_COUNT

    _register_bundle(processing_database, bundle, _station_topology(manifest))
    registry = production_standard_native_evidence_registry()
    configuration: dict[str, object] = {
        "display_version": "historical-v2-native-operational-v1",
        "stages": production_standard_native_evidence_configuration(),
    }
    executable = tmp_path / "worker-executable"
    executable.mkdir()
    (executable / "historical-v2-native.txt").write_text("pinned historical V2 worker\n")
    loaded = derive_loaded_worker_release_for_tests(
        pipeline_release_id=_RELEASE,
        code_revision=_RELEASE,
        registry=registry,
        configuration=configuration,
        environment_document={"name": "historical-v2-native-operational"},
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

    plan = standard_native_pipeline.compile_standard_native_run_plan(
        manifest,
        manifest_digest=bundle.manifest_sha256,
        pipeline_release_id=_RELEASE,
    )
    assert (len(plan.jobs), len(plan.edges)) == (16, 15)
    assert all("resampl" not in item.stage_key for item in plan.jobs)
    expected_product_kinds = Counter(
        product.kind
        for job in plan.jobs
        for product in registry.get(job.stage_key).spec.output_products
    )

    bulk_root = tmp_path / "bulk"
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
        with pytest.raises(StandardReprocessError, match="separately versioned"):
            application.queue(manifest.session_id)
        result = application.queue_native_evidence(manifest.session_id)
        assert result.promotion_policy == "evidence_only"
        assert result.previous_current_run_id is None
        assert result.queued_job_count == 16

        subject_reader = CatalogSubjectBindingReader(processing_database.catalog)
        for stream in manifest.streams:
            assert stream.applied_settings is not None
            for receiver_id in stream.applied_settings.receiver_ids:
                scope = ScopeIdentityV1.receiver_path(
                    session_id=manifest.session_id,
                    stream_id=stream.stream_id,
                    receiver_id=receiver_id,
                )
                binding = subject_reader.receiver_path_native(result.run_id, scope)
                assert isinstance(binding, StandardPathInputBindV4)
                assert binding.raw_integrity_attestation_digest
                assert binding.selected_stream_digest == canonical_digest(
                    stream.model_dump(mode="json")
                )
                assert binding.logical_sample_count == _SAMPLE_COUNT
                assert binding.observed_sample_count == stream.captured_sample_count
                assert binding.missing_sample_count == stream.continuity.missing_sample_count
                assert binding.validity_inventory.inventory_digest == (
                    binding.validity_inventory_sha256
                )
                assert (binding.logical_iq_digest == binding.observed_iq_digest) is (
                    binding.missing_sample_count == 0
                )
                with pytest.raises(ValidationError):
                    subject_reader.receiver_path(result.run_id, scope)

        executions = []
        while execution := service.run_once(worker_id="historical-v2-native-worker"):
            executions.append(execution)
            assert execution.succeeded, execution.error
        assert len(executions) == 16
        service.finalize_run(result.run_id)
        seal = processing_database.catalog.run_seal_snapshot(result.run_id)
        assert {item.state for item in seal.jobs} == {"succeeded"}
        assert Counter(item.outcome for item in seal.jobs) == {
            StageOutcome.COMPLETE.value: 5,
            StageOutcome.PARTIAL_COVERAGE.value: 7,
            StageOutcome.INSUFFICIENT_DATA.value: 4,
        }
        assert Counter(item.kind for item in seal.products) == expected_product_kinds
        assert len(seal.products) == 125
        assert sum(item.media_type == "image/png" for item in seal.products) == 74
        for product in seal.products:
            if product.scope is None or product.scope.kind.value != "receiver_path":
                continue
            binding = subject_reader.receiver_path_native(result.run_id, product.scope)
            expected_coverage = binding.observed_sample_count / binding.logical_sample_count
            assert product.coverage == pytest.approx(expected_coverage)
        assert seal.execution.trigger == "reprocess"
        assert seal.execution.promotion_policy == "evidence_only"
        assert seal.execution.pipeline_lane == "standard"
        assert processing_database.catalog.current_run_id(manifest.session_id) is None
        assert processing_database.catalog.active_run_id(manifest.session_id) is None
    finally:
        service.close()
        artifacts.close()
        pinned.close()
