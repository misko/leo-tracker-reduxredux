from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import text

from leo.catalog import InvalidStateError, ProductConflictError
from leo.contracts.digests import canonical_digest
from leo.contracts.recording import RecordingManifestV1
from leo.contracts.states import SourceType
from leo.operations.service import _stream_registrations
from leo.pipeline import ScopeIdentityV1
from leo.station.authority import (
    CaptureHardwareBindingV1,
    FixturePathAuthorityV1,
    StationReceiverTopologyV1,
    recording_manifest_canonical_digest,
)
from leo.storage import PublishedBundle
from tests.station.manifest_examples import manifest_example, topology_for_manifest

from .conftest import CatalogHarness

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _manifest(
    session_id: str,
    *,
    radio_count: int,
    receiver_ids: tuple[int, ...] = (0, 1),
    second_receiver_ids: tuple[int, ...] | None = None,
    source_type: SourceType = SourceType.IMPORT,
) -> RecordingManifestV1:
    manifest = manifest_example(
        radio_count=radio_count,
        applied_receiver_ids=receiver_ids,
        requested_receiver_ids=(0, 1),
        source_type=source_type,
    ).model_copy(update={"session_id": session_id})
    if second_receiver_ids is not None:
        assert len(manifest.streams) == 2
        second = manifest.streams[1]
        assert second.applied_settings is not None
        gains = tuple(
            gain
            for gain in second.applied_settings.gains
            if gain.receiver_id in second_receiver_ids
        )
        applied = second.applied_settings.model_copy(
            update={"receiver_ids": second_receiver_ids, "gains": gains}
        )
        chunks = tuple(
            chunk.model_copy(update={"uncompressed_bytes": 4 * len(second_receiver_ids)})
            for chunk in second.chunks
        )
        second = second.model_copy(update={"applied_settings": applied, "chunks": chunks})
        manifest = manifest.model_copy(update={"streams": (manifest.streams[0], second)})
    return RecordingManifestV1.model_validate(manifest.model_dump(mode="json"))


def _reconcile(
    harness: CatalogHarness,
    manifest: RecordingManifestV1,
) -> tuple[CaptureHardwareBindingV1 | FixturePathAuthorityV1, bool]:
    digest = recording_manifest_canonical_digest(manifest)
    bundle_uri = f"bulk://recordings/{manifest.session_id}"
    bundle = PublishedBundle(
        session_id=manifest.session_id,
        path=Path("/tmp/station-authority-unused"),
        uri=bundle_uri,
        manifest=manifest,
        manifest_sha256=digest,
    )
    if manifest.source_type is SourceType.TEST:
        authority: CaptureHardwareBindingV1 | FixturePathAuthorityV1 = (
            FixturePathAuthorityV1.create(
                manifest,
                observed_manifest_file_digest=digest,
            )
        )
    else:
        topology = topology_for_manifest(manifest)
        harness.repository.register_station_topology(topology)
        authority = CaptureHardwareBindingV1.create(
            manifest,
            observed_manifest_file_digest=digest,
            topology=topology,
        )
    inserted = harness.repository.reconcile_capture_session(
        session_id=manifest.session_id,
        source_type=manifest.source_type.value,
        bundle_uri=bundle_uri,
        manifest_digest=digest,
        allocated_bytes=128,
        attributes={"manifest_digest": digest},
        tags=manifest.tags,
        streams=_stream_registrations(bundle),
        path_authority=authority,
    )
    return authority, inserted


@pytest.mark.parametrize(
    ("radio_count", "receiver_ids", "second_receiver_ids", "expected_paths"),
    (
        (1, (0,), None, 1),
        (1, (0, 1), None, 2),
        (2, (0,), None, 2),
        (2, (0, 1), (0,), 3),
        (2, (0, 1), None, 4),
    ),
)
def test_real_postgres_reconciles_exact_station_topology_shapes(
    catalog_harness: CatalogHarness,
    radio_count: int,
    receiver_ids: tuple[int, ...],
    second_receiver_ids: tuple[int, ...] | None,
    expected_paths: int,
) -> None:
    manifest = _manifest(
        f"station-{radio_count}-{expected_paths}",
        radio_count=radio_count,
        receiver_ids=receiver_ids,
        second_receiver_ids=second_receiver_ids,
    )

    authority, inserted = _reconcile(catalog_harness, manifest)

    assert isinstance(authority, CaptureHardwareBindingV1)
    assert inserted is True
    with catalog_harness.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT count(*), count(physical_receiver_id), "
                "count(station_assignment_id), count(DISTINCT capture_authority_session_id) "
                "FROM capture_receiver_lineage WHERE session_id=:session"
            ),
            {"session": manifest.session_id},
        ).one()
    assert row == (expected_paths, expected_paths, expected_paths, 1)
    for path in authority.paths:
        scope = ScopeIdentityV1.receiver_path(
            session_id=manifest.session_id,
            stream_id=path.stream_id,
            receiver_id=path.receiver_id,
        )
        binding = catalog_harness.repository.capture_receiver_binding(scope)
        assert binding.physical_receiver_id == path.physical_receiver_id
        assert binding.hardware_epoch_id == path.hardware_epoch_external_id
        assert binding.capture_start_utc_ns == path.capture_start_utc_ns
        assert binding.capture_end_utc_ns == path.capture_end_utc_ns
        reference = catalog_harness.repository.capture_frequency_reference(
            scope,
            tuned_center_frequency_hz=1_700_000_000,
        )
        assert reference.reference.value == "uncalibrated_prior"
        assert reference.calibration_digest is None


def test_deployed_four_path_topology_registers_in_real_postgres(
    catalog_harness: CatalogHarness,
) -> None:
    topology = StationReceiverTopologyV1.model_validate_json(
        (
            _PROJECT_ROOT
            / "deploy/station/gauss-four-path-postreboot-20260816-v1.json"
        ).read_bytes()
    )

    receipt = catalog_harness.repository.register_station_topology(topology)

    assert receipt.topology_digest == topology.topology_digest
    assert receipt.assignment_count == 4


def test_reconciliation_rejects_manifest_inventory_and_radio_substitution(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = _manifest("station-substitution", radio_count=2)
    authority, _inserted = _reconcile(catalog_harness, manifest)
    digest = recording_manifest_canonical_digest(manifest)
    bundle = PublishedBundle(
        session_id=manifest.session_id,
        path=Path("/tmp/station-authority-unused"),
        uri=f"bulk://recordings/{manifest.session_id}",
        manifest=manifest,
        manifest_sha256=digest,
    )
    streams = _stream_registrations(bundle)
    changed_applied = dict(streams[0].attributes)
    changed_applied["applied_settings"] = {
        **changed_applied["applied_settings"],
        "center_frequency_hz": 1_700_000_001,
    }
    variants = (
        streams[:-1],
        streams + (replace(streams[0], stream_id="invented-stream"),),
        (replace(streams[0], receiver_ids=(0,)),) + streams[1:],
        (replace(streams[0], radio_serial="substituted-serial"),) + streams[1:],
        (replace(streams[0], radio_uri="ip:203.0.113.99"),) + streams[1:],
        (replace(streams[0], attributes=changed_applied),) + streams[1:],
    )
    for variant in variants:
        with pytest.raises((InvalidStateError, ProductConflictError, ValueError)):
            catalog_harness.repository.reconcile_capture_session(
                session_id=manifest.session_id,
                source_type=manifest.source_type.value,
                bundle_uri=bundle.uri,
                manifest_digest=digest,
                allocated_bytes=128,
                attributes={"manifest_digest": digest},
                streams=variant,
                path_authority=authority,
            )


def test_repeated_local_stream_ids_are_isolated_by_capture_session(
    catalog_harness: CatalogHarness,
) -> None:
    first = _manifest("station-repeat-a", radio_count=1)
    second = _manifest("station-repeat-b", radio_count=1)

    _reconcile(catalog_harness, first)
    _reconcile(catalog_harness, second)

    with catalog_harness.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT session_id, stream_id, count(*) FROM capture_receiver_lineage "
                "WHERE session_id LIKE 'station-repeat-%' "
                "GROUP BY session_id, stream_id ORDER BY session_id"
            )
        ).all()
    assert rows == [
        ("station-repeat-a", "stream-0", 2),
        ("station-repeat-b", "stream-0", 2),
    ]


def test_protected_test_fixture_is_unresolved_evidence_only_and_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = _manifest(
        "station-protected-test",
        radio_count=2,
        source_type=SourceType.TEST,
    )

    authority, inserted = _reconcile(catalog_harness, manifest)
    record = catalog_harness.repository.capture_path_authority(manifest.session_id)

    assert isinstance(authority, FixturePathAuthorityV1)
    assert inserted is True
    assert record.evidence_only is True
    assert record.current_analysis_eligible is False
    assert record.physical_association_permitted is False
    assert record.calibration_association_permitted is False
    assert record.promotion_permitted is False
    with catalog_harness.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT bool_and(lineage_status='unresolved'), "
                "count(physical_receiver_id), count(hardware_epoch_external_id) "
                "FROM capture_receiver_lineage WHERE session_id=:session"
            ),
            {"session": manifest.session_id},
        ).one() == (True, 0, 0)
    for statement in (
        "UPDATE capture_path_authority SET promotion_permitted=true "
        "WHERE session_id='station-protected-test'",
        "DELETE FROM capture_path_authority WHERE session_id='station-protected-test'",
        "UPDATE capture_receiver_lineage SET physical_receiver_id='fabricated' "
        "WHERE session_id='station-protected-test'",
    ):
        with (
            catalog_harness.engine.connect() as connection,
            connection.begin(),
            pytest.raises(Exception, match="immutable"),
        ):
            connection.execute(text(statement))


def test_eight_concurrent_identical_reconciliations_are_idempotent(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = _manifest("station-concurrent", radio_count=2)

    def reconcile(_index: int) -> bool:
        _authority, inserted = _reconcile(catalog_harness, manifest)
        return inserted

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(reconcile, range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7
    with catalog_harness.engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT count(*) FROM capture_receiver_lineage "
                "WHERE session_id='station-concurrent'"
            )
        ) == 4
        assert connection.scalar(
            text(
                "SELECT count(DISTINCT authority_digest) FROM capture_path_authority "
                "WHERE session_id='station-concurrent'"
            )
        ) == 1


def test_topology_and_assignment_inventory_are_sql_immutable(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = _manifest("station-immutable", radio_count=2)
    authority, _inserted = _reconcile(catalog_harness, manifest)
    assert isinstance(authority, CaptureHardwareBindingV1)

    statements = (
        "UPDATE station_topology SET topology_revision='retargeted'",
        "DELETE FROM station_topology",
        "UPDATE station_receiver_assignment SET radio_serial='retargeted'",
        "DELETE FROM station_receiver_assignment",
        "INSERT INTO station_receiver_assignment "
        "(topology_digest, radio_id, radio_serial, radio_transport, radio_endpoint, "
        "endpoint_evidence_uri, endpoint_evidence_digest, receiver_id, "
        "physical_receiver_id, hardware_epoch_external_id, valid_from_utc_ns, "
        "valid_until_utc_ns, receiver_path_id, hardware_epoch_id) "
        "SELECT topology_digest, radio_id, radio_serial, radio_transport, radio_endpoint, "
        "endpoint_evidence_uri, endpoint_evidence_digest, receiver_id, "
        "physical_receiver_id, hardware_epoch_external_id, valid_from_utc_ns, "
        "valid_until_utc_ns, receiver_path_id, hardware_epoch_id "
        "FROM station_receiver_assignment LIMIT 1",
    )
    for statement in statements:
        with (
            catalog_harness.engine.connect() as connection,
            connection.begin(),
            pytest.raises(Exception, match="immutable|sealed"),
        ):
            connection.execute(text(statement))


def test_capture_binding_digest_is_stable_after_live_profile_state_changes(
    catalog_harness: CatalogHarness,
) -> None:
    manifest = _manifest("station-snapshot", radio_count=1)
    authority, _inserted = _reconcile(catalog_harness, manifest)
    assert isinstance(authority, CaptureHardwareBindingV1)
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id="stream-0",
        receiver_id=0,
    )
    before = catalog_harness.repository.capture_receiver_binding(scope)
    with catalog_harness.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE capture_profile_revision SET document=jsonb_set(document, "
                "'{profile,description}', to_jsonb('later metadata'::text), true)"
            )
        )
    after = catalog_harness.repository.capture_receiver_binding(scope)
    assert after == before
    assert canonical_digest(authority.model_dump(mode="json")) == canonical_digest(
        authority.model_dump(mode="json")
    )
