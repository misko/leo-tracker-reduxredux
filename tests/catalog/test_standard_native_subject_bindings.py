from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CaptureRecordingIdentity, CatalogSubjectBindingReader, PromotionPolicy
from leo.contracts.digests import canonical_digest
from leo.contracts.profile import CapturePlanV2, CaptureProfileRevisionV2
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    ContinuitySummaryV2,
    DeviceAxisRecordingChunkV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV3,
    RecordingStreamV3,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.contracts.states import (
    CaptureState,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    TimingMethod,
)
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
    ValidityRunV1,
)
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.operations.service import _stream_registrations
from leo.pipeline import (
    AnalyzerRegistry,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ScopeIdentityV1,
)
from leo.pipeline.standard_native import compile_standard_native_run_plan
from leo.processing import ProcessingService
from leo.processing.adapters import CatalogArtifactProductReader, IqReaderProvider
from leo.station.authority import (
    CaptureHardwareBindingV3,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
    recording_manifest_canonical_digest,
)
from leo.storage import PublishedBundle

from .conftest import CatalogHarness

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = "1" * 40
_REVISION = "2" * 40
_ENVIRONMENT = canonical_digest({"environment": "native-catalog-test"})
_GRAPH = canonical_digest({"graph": "standard-native-v1"})
_EXECUTABLE = canonical_digest({"executable": "standard-native-v1"})
_OBSERVED_IQ = canonical_digest({"iq": "observed"})
_COMPRESSED_CHUNK = canonical_digest({"chunk": "compressed"})
_TIMELINE = canonical_digest({"timeline": "native"})
_GAP_MAP_FILE = canonical_digest({"gap-map-file": "native"})
_GAP_MAP_CONTENT = canonical_digest({"gap-map-content": "native"})
_FIRST_SAMPLE_COUNTER = 100
_FIRST_UTC_NS = 1_700_000_000_000_000_000


class _VerifiedNativeProvider:
    def __init__(
        self,
        manifest: RecordingManifestV3,
        manifest_digest: str,
        validity: ValidityInventoryV1,
    ) -> None:
        self._manifest = manifest
        self._validity = validity
        stream = manifest.streams[0]
        self._integrity = RawIntegrityAttestationV1(
            session_id=manifest.session_id,
            manifest_digest=manifest_digest,
            streams=(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=len(stream.chunks),
                    compressed_closure_digest=canonical_digest({"closure": "compressed"}),
                    uncompressed_closure_digest=canonical_digest({"closure": "uncompressed"}),
                ),
            ),
            verifier_version="native-catalog-component-v1",
            verified_utc_ns=_FIRST_UTC_NS,
        )

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1:
        assert identity.session_id == self._manifest.session_id
        assert identity.manifest_digest == self._integrity.manifest_digest
        return self._integrity

    def verified_manifest(self, attestation_digest: str) -> RecordingManifestV3:
        assert attestation_digest == self._integrity.attestation_digest
        return self._manifest

    def verified_validity_inventory(
        self,
        attestation_digest: str,
        stream_id: str,
    ) -> ValidityInventoryV1:
        assert attestation_digest == self._integrity.attestation_digest
        assert stream_id == self._validity.stream_id
        return self._validity


def _native_manifest() -> tuple[RecordingManifestV3, ValidityInventoryV1]:
    revision = load_profile_revision(
        _PROJECT_ROOT / "profiles" / "starlink-ch4-lower-3m-60s-device-axis-v3.yaml"
    )
    assert isinstance(revision, CaptureProfileRevisionV2)
    profile = revision.profile
    plan = cast(
        CapturePlanV2,
        compile_capture_plan(
            revision,
            ("radio-native",),
            source_type=SourceType.IMPORT,
        ),
    )
    logical_samples = plan.resolved_sample_count
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=profile.receivers,
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    validity = ValidityInventoryV1(
        stream_id="stream-native",
        timeline_sha256=_TIMELINE,
        gap_map_content_digest=_GAP_MAP_CONTENT,
        first_device_sample_counter=_FIRST_SAMPLE_COUNTER,
        logical_sample_count=logical_samples,
        observed_sample_count=logical_samples,
        missing_sample_count=0,
        continuity_boundary_count=0,
        runs=(
            ValidityRunV1(
                run_index=0,
                device_sample_start=0,
                sample_count=logical_samples,
                content_kind=DeviceAxisContentKind.OBSERVED,
                stored_sample_start=0,
                continuity_segment_index=0,
            ),
        ),
        segments=(
            ContinuitySegmentV1(
                segment_index=0,
                device_sample_start=0,
                device_sample_stop=logical_samples,
                stored_sample_start=0,
                stored_sample_stop=logical_samples,
            ),
        ),
    )
    final_sample_utc_ns = _FIRST_UTC_NS + 60_000_000_000 - 334
    timing = StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=_FIRST_UTC_NS,
            earliest_utc_ns=_FIRST_UTC_NS - 100,
            latest_utc_ns=_FIRST_UTC_NS + 100,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=final_sample_utc_ns,
            earliest_utc_ns=final_sample_utc_ns - 100,
            latest_utc_ns=final_sample_utc_ns + 100,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )
    stream = RecordingStreamV3(
        stream_id=validity.stream_id,
        radio=RadioIdentityV1(
            radio_id="radio-native",
            serial="native-serial",
            uri="ip:192.168.1.10",
            transport=RadioTransport.IIO_IP,
        ),
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=logical_samples,
        logical_sample_count=logical_samples,
        observed_sample_count=logical_samples,
        zero_fill_sample_count=0,
        timing=timing,
        chunks=(
            DeviceAxisRecordingChunkV1(
                chunk_index=0,
                content_kind=DeviceAxisContentKind.OBSERVED,
                continuity_segment_index=0,
                relative_path="streams/stream-native/iq-000000.ci16.zst",
                device_sample_start=0,
                sample_count=logical_samples,
                uncompressed_bytes=logical_samples * len(profile.receivers) * 4,
                compressed_bytes=1,
                uncompressed_sha256=_OBSERVED_IQ,
                compressed_sha256=_COMPRESSED_CHUNK,
            ),
        ),
        observed_iq_sha256=_OBSERVED_IQ,
        logical_iq_sha256=_OBSERVED_IQ,
        timeline_relative_path="streams/stream-native/timeline.jsonl.zst",
        timeline_sha256=_TIMELINE,
        gap_map_relative_path="streams/stream-native/gap-map.json",
        gap_map_sha256=_GAP_MAP_FILE,
        validity_inventory_relative_path=("streams/stream-native/validity-inventory.json"),
        validity_inventory_sha256=validity.inventory_digest,
        continuity=ContinuitySummaryV2(
            refill_count=1,
            segment_count=1,
            sample_loss_observable=True,
            first_source_sequence=0,
            last_source_sequence=0,
            first_device_sample_counter=_FIRST_SAMPLE_COUNTER,
            last_device_sample_counter=_FIRST_SAMPLE_COUNTER + logical_samples - 1,
            observed_sample_count=logical_samples,
            device_span_sample_count=logical_samples,
            kernel_buffers=profile.kernel_buffers,
            metadata_abi_version=1,
            validated_stream_generation="native-catalog-generation",
            queue_capacity_refills=profile.refill_queue_capacity,
            queue_high_water_refills=1,
        ),
    )
    return (
        RecordingManifestV3(
            session_id="native-catalog-session",
            state=CaptureState.COMMITTED,
            source_type=SourceType.IMPORT,
            created_utc_ns=_FIRST_UTC_NS - 1_000_000_000,
            finalized_utc_ns=_FIRST_UTC_NS + 61_000_000_000,
            capture_plan=plan,
            tags=profile.tags,
            streams=(stream,),
            synchronization=SynchronizationSummaryV1(
                requested_mode=plan.requested_synchronization_mode,
                effective_mode=plan.effective_synchronization_mode,
                grade=SynchronizationGrade.NOT_REQUESTED,
                stream_ids=(stream.stream_id,),
            ),
            compression=CompressionSettingsV1(policy_id=DEVICE_AXIS_STORAGE_POLICY_V1),
            host=HostIdentityV1(hostname="native-catalog-test"),
            producer=ProducerV1(name="native-catalog-test", version="1"),
        ),
        validity,
    )


def _register_native_capture(
    harness: CatalogHarness,
    manifest: RecordingManifestV3,
    manifest_digest: str,
    tmp_path: Path,
) -> None:
    stream = manifest.streams[0]
    topology_start = _FIRST_UTC_NS - 1_000_000_000
    topology_end = _FIRST_UTC_NS + 61_000_000_000
    topology = StationReceiverTopologyV1.create(
        station_id="native-catalog-station",
        topology_revision="native-catalog-topology-v1",
        valid_from_utc_ns=topology_start,
        valid_until_utc_ns=topology_end,
        radios=(
            StationRadioTopologyV1.create(
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                endpoint_evidence=RadioEndpointEvidenceV1(
                    transport=stream.radio.transport,
                    endpoint=stream.radio.uri,
                    evidence_uri="authority/native-radio.json",
                    evidence_digest=canonical_digest({"radio": "native"}),
                ),
                receiver_assignments=tuple(
                    StationReceiverAssignmentV1(
                        receiver_id=receiver_id,
                        physical_receiver_id=f"native-physical-rx{receiver_id}",
                        hardware_epoch_external_id=f"native-hardware-rx{receiver_id}-v1",
                        valid_from_utc_ns=topology_start,
                        valid_until_utc_ns=topology_end,
                    )
                    for receiver_id in (0, 1)
                ),
            ),
        ),
    )
    authority = CaptureHardwareBindingV3.create(
        manifest,
        observed_manifest_file_digest=manifest_digest,
        topology=topology,
    )
    harness.repository.register_station_topology(topology)
    bundle_uri = f"bulk://recordings/{manifest.session_id}"
    harness.repository.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=bundle_uri,
        manifest_digest=manifest_digest,
        allocated_bytes=1,
        attributes={"manifest_digest": manifest_digest},
        tags=manifest.tags,
        streams=_stream_registrations(
            PublishedBundle(
                session_id=manifest.session_id,
                path=tmp_path / manifest.session_id,
                uri=bundle_uri,
                manifest=manifest,
                manifest_sha256=manifest_digest,
            )
        ),
        path_authority=authority,
    )


def test_real_postgres_native_expanded_run_persists_and_reads_v5_binding(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    manifest, validity = _native_manifest()
    manifest_digest = recording_manifest_canonical_digest(manifest)
    _register_native_capture(catalog_harness, manifest, manifest_digest, tmp_path)
    catalog_harness.repository.add_pipeline_release(
        release_id=_RELEASE,
        code_revision=_REVISION,
        environment_digest=_ENVIRONMENT,
        graph_digest=_GRAPH,
        executable_digest=_EXECUTABLE,
    )
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    service = ProcessingService(
        catalog=catalog_harness.repository,
        artifacts=cast(AnalysisArtifactStore, object()),
        registry=AnalyzerRegistry(()),
        iq_readers=cast(
            IqReaderProvider,
            _VerifiedNativeProvider(manifest, manifest_digest, validity),
        ),
    )

    service.create_expanded_run(
        run_id="native-catalog-run",
        plan=plan,
        trigger="reprocess",
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
    )

    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=manifest.streams[0].stream_id,
        receiver_id=0,
    )
    reader = CatalogSubjectBindingReader(catalog_harness.repository)
    binding = reader.receiver_path_native("native-catalog-run", scope)
    assert isinstance(binding, StandardPathInputBindV5)
    assert binding.validity_inventory == validity
    assert binding.declared_sample_count == manifest.streams[0].logical_sample_count
    assert binding.observed_sample_count == manifest.streams[0].observed_sample_count

    # This is the exact subject-document route used by a native worker.
    products = CatalogArtifactProductReader(
        catalog_harness.repository,
        cast(AnalysisArtifactStore, object()),
        run_id="native-catalog-run",
        scope_key=scope.canonical_digest,
        scope=scope,
    )
    assert StandardPathInputBindV5.model_validate(products.read_subject_binding()) == binding

    # The frozen Standard reader remains fail-closed for device-axis V4 input.
    with pytest.raises(ValidationError):
        reader.receiver_path("native-catalog-run", scope)

    with catalog_harness.engine.connect() as connection:
        job_count = connection.execute(
            text("SELECT count(*) FROM processing_job WHERE run_id='native-catalog-run'")
        ).scalar_one()
        binding_versions = tuple(
            connection.execute(
                text(
                    "SELECT document->>'schema_version' FROM run_subject_binding "
                    "WHERE run_id='native-catalog-run' ORDER BY scope_id"
                )
            ).scalars()
        )
    assert job_count == len(plan.jobs) == 5
    assert binding_versions == ("5", "5")
