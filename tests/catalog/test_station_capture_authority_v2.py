from __future__ import annotations

from sqlalchemy import text

from leo.catalog import RadioStreamRegistration, RecordingChunkRegistration
from leo.contracts.recording import RecordingManifestV2, RecordingManifestV3
from leo.contracts.states import SourceType
from leo.station.authority import (
    CaptureHardwareBindingV2,
    CaptureHardwareBindingV3,
    recording_manifest_canonical_digest,
)
from tests.station.manifest_examples import (
    manifest_example_v2,
    manifest_example_v3,
    topology_for_manifest,
)

from .conftest import CatalogHarness


def _stream_registrations(
    manifest: RecordingManifestV2,
) -> tuple[RadioStreamRegistration, ...]:
    registrations: list[RadioStreamRegistration] = []
    for ordinal, stream in enumerate(
        sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id))
    ):
        assert stream.applied_settings is not None
        registrations.append(
            RadioStreamRegistration(
                stream_id=stream.stream_id,
                manifest_ordinal=ordinal,
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                radio_uri=stream.radio.uri,
                radio_transport=stream.radio.transport.value,
                state=stream.state.value,
                receiver_ids=stream.applied_settings.receiver_ids,
                sample_rate_hz=stream.applied_settings.sample_rate_hz,
                captured_sample_count=stream.captured_sample_count,
                observed_start_at=None,
                observed_end_at=None,
                attributes={
                    "requested_settings": stream.requested_settings.model_dump(mode="json"),
                    "applied_settings": stream.applied_settings.model_dump(mode="json"),
                    "timing": (
                        None if stream.timing is None else stream.timing.model_dump(mode="json")
                    ),
                },
                chunks=tuple(
                    RecordingChunkRegistration(
                        chunk_index=chunk.chunk_index,
                        sample_start=chunk.sample_start,
                        sample_count=chunk.sample_count,
                        logical_uri=f"bulk://unused/{chunk.relative_path}",
                        compressed_digest=chunk.compressed_sha256,
                        uncompressed_digest=chunk.uncompressed_sha256,
                        compressed_bytes=chunk.compressed_bytes,
                        uncompressed_bytes=chunk.uncompressed_bytes,
                    )
                    for chunk in stream.chunks
                ),
            )
        )
    return tuple(registrations)


def _stream_registrations_v3(
    manifest: RecordingManifestV3,
) -> tuple[RadioStreamRegistration, ...]:
    registrations: list[RadioStreamRegistration] = []
    for ordinal, stream in enumerate(
        sorted(manifest.streams, key=lambda item: (item.stream_id, item.radio.radio_id))
    ):
        applied = stream.applied_settings
        sample_ns = (1_000_000_000 + applied.sample_rate_hz - 1) // applied.sample_rate_hz
        registrations.append(
            RadioStreamRegistration(
                stream_id=stream.stream_id,
                manifest_ordinal=ordinal,
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                radio_uri=stream.radio.uri,
                radio_transport=stream.radio.transport.value,
                state=stream.state.value,
                receiver_ids=applied.receiver_ids,
                sample_rate_hz=applied.sample_rate_hz,
                captured_sample_count=stream.observed_sample_count,
                observed_start_at=None,
                observed_end_at=None,
                attributes={
                    "requested_settings": stream.requested_settings.model_dump(mode="json"),
                    "applied_settings": applied.model_dump(mode="json"),
                    "timing": stream.timing.model_dump(mode="json"),
                    "capture_start_utc_ns": stream.timing.first_sample.earliest_utc_ns,
                    "capture_end_utc_ns": (stream.timing.last_sample.latest_utc_ns + sample_ns),
                    "continuity": stream.continuity.model_dump(mode="json"),
                    "timeline_relative_path": stream.timeline_relative_path,
                    "timeline_sha256": stream.timeline_sha256,
                    "logical_sample_count": stream.logical_sample_count,
                    "observed_sample_count": stream.observed_sample_count,
                    "zero_fill_sample_count": stream.zero_fill_sample_count,
                    "observed_iq_sha256": stream.observed_iq_sha256,
                    "logical_iq_sha256": stream.logical_iq_sha256,
                    "gap_map_relative_path": stream.gap_map_relative_path,
                    "gap_map_sha256": stream.gap_map_sha256,
                    "validity_inventory_relative_path": (stream.validity_inventory_relative_path),
                    "validity_inventory_sha256": stream.validity_inventory_sha256,
                },
                chunks=tuple(
                    RecordingChunkRegistration(
                        chunk_index=chunk.chunk_index,
                        sample_start=chunk.device_sample_start,
                        sample_count=chunk.sample_count,
                        logical_uri=f"bulk://unused/{chunk.relative_path}",
                        compressed_digest=chunk.compressed_sha256,
                        uncompressed_digest=chunk.uncompressed_sha256,
                        compressed_bytes=chunk.compressed_bytes,
                        uncompressed_bytes=chunk.uncompressed_bytes,
                    )
                    for chunk in stream.chunks
                ),
            )
        )
    return tuple(registrations)


def test_real_postgres_reconciles_complete_v2_station_authority(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = manifest_example_v2(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    ).model_copy(update={"session_id": "station-authority-v2"})
    digest = recording_manifest_canonical_digest(manifest)
    topology = topology_for_manifest(manifest)
    authority = CaptureHardwareBindingV2.create(
        manifest,
        observed_manifest_file_digest=digest,
        topology=topology,
    )
    catalog_harness.repository.register_station_topology(topology)

    inserted = catalog_harness.repository.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=f"bulk://recordings/{manifest.session_id}",
        manifest_digest=digest,
        allocated_bytes=128,
        attributes={"manifest_digest": digest},
        tags=manifest.tags,
        streams=_stream_registrations(manifest),
        path_authority=authority,
    )

    assert inserted is True
    with catalog_harness.engine.connect() as connection:
        document = connection.execute(
            text(
                "SELECT document FROM capture_path_authority "
                "WHERE session_id='station-authority-v2'"
            )
        ).scalar_one()
    assert document["schema_version"] == 2
    assert document["verified_manifest_snapshot"]["recording_manifest"] == manifest.model_dump(
        mode="json"
    )
    assert catalog_harness.repository.capture_path_authority(
        manifest.session_id
    ).authority_digest == (authority.binding_digest)


def test_real_postgres_reconciles_complete_v3_device_axis_authority(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = manifest_example_v3(
        radio_count=1,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.IMPORT,
    ).model_copy(update={"session_id": "station-authority-v3"})
    digest = recording_manifest_canonical_digest(manifest)
    topology = topology_for_manifest(manifest)
    authority = CaptureHardwareBindingV3.create(
        manifest,
        observed_manifest_file_digest=digest,
        topology=topology,
    )
    catalog_harness.repository.register_station_topology(topology)

    inserted = catalog_harness.repository.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=f"bulk://recordings/{manifest.session_id}",
        manifest_digest=digest,
        allocated_bytes=128,
        attributes={"manifest_digest": digest},
        tags=manifest.tags,
        streams=_stream_registrations_v3(manifest),
        path_authority=authority,
    )

    assert inserted is True
    with catalog_harness.engine.connect() as connection:
        document = connection.execute(
            text(
                "SELECT document FROM capture_path_authority "
                "WHERE session_id='station-authority-v3'"
            )
        ).scalar_one()
    assert document["schema_version"] == 3
    assert document["verified_manifest_snapshot"]["recording_manifest"] == (
        manifest.model_dump(mode="json")
    )
    assert (
        catalog_harness.repository.capture_path_authority(manifest.session_id).authority_digest
        == authority.binding_digest
    )
