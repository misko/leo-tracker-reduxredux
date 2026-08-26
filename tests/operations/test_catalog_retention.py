from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest
from sqlalchemy import text

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.analysis.adapters import production_standard_v2_configuration
from leo.analysis.power import PowerAnalyzer
from leo.analysis.quality import QualityAnalyzer
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import (
    CatalogRepository,
    CurrentSummary,
    ProductConflictError,
    RadioStreamRegistration,
)
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    RadioConfigurationV1,
)
from leo.cli.processing import LocalProcessingBackend, ProcessingServices
from leo.contracts.profile import (
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
    CaptureProfileV2,
)
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingManifestV3,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StarlinkEdge,
    StreamState,
    SynchronizationGrade,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan
from leo.importing import FixtureImporter, RecordingCorpusIngestService
from leo.operations import (
    CatalogHoldService,
    CatalogReconciliationService,
    CatalogRetentionService,
    HoldReceiptStore,
    PurgeExecutor,
    StorageUsage,
    allocated_bytes,
)
from leo.operations.service import CatalogReconcileReport
from leo.pipeline import AnalyzerRegistry
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.radio.fake import FakeRadioSource
from leo.station.authority import (
    CaptureHardwareBindingV1,
    CaptureHardwareBindingV3,
    FixturePathAuthorityV1,
    RadioEndpointEvidenceV1,
    StationRadioTopologyV1,
    StationReceiverAssignmentV1,
    StationReceiverTopologyV1,
)
from leo.station.resolver import ResolvedCaptureAuthority, UnreviewedTestFixtureAuthorityError
from leo.storage import RecordingStore


class InjectedCrash(BaseException):
    pass


def test_processing_reconcile_preserves_nonblocking_historical_report() -> None:
    backend = object.__new__(LocalProcessingBackend)

    result = backend._queue_reconciled(  # noqa: SLF001
        CatalogReconcileReport(
            registered=(),
            existing=(),
            issues=(),
            historical_incompatibilities=("legacy manifest",),
        ),
        restored_purges=(),
        discarded_purges=(),
    )

    assert result.issues == ()
    assert result.historical_incompatibilities == ("legacy manifest",)


def test_v3_reconciliation_registers_observed_count_and_device_axis_authority(
    tmp_path: Path,
) -> None:
    recordings = RecordingStore(tmp_path / "bulk")
    profile = CaptureProfileV2(
        name="operations-device-axis-v3-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=5_000_000,
        bandwidth_hz=2_500_000,
        receivers=(0,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30.0),),
        sample_count=12,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=8,
        refill_queue_capacity=32,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("LIVE",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ("radio-a",),
        source_type=SourceType.LIVE,
    )
    coordinator = AcquisitionCoordinator(
        recordings,
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=32,
        ),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={1: 4})},
        session_id="operations-v3-registration",
    )
    assert result.bundle is not None, result.errors
    assert isinstance(result.bundle.manifest, RecordingManifestV3)
    manifest = result.bundle.manifest
    stream = manifest.streams[0]
    assert stream.observed_sample_count < stream.logical_sample_count

    validity = {
        "valid_from_utc_ns": 1_699_999_000_000_000_000,
        "valid_until_utc_ns": 1_700_001_000_000_000_000,
    }
    topology = StationReceiverTopologyV1.create(
        station_id="operations-v3-station",
        topology_revision="operations-v3-topology-v1",
        radios=(
            StationRadioTopologyV1.create(
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                endpoint_evidence=RadioEndpointEvidenceV1(
                    transport=stream.radio.transport,
                    endpoint=stream.radio.uri,
                    evidence_uri="authority/operations-v3-radio.json",
                    evidence_digest="sha256:" + "d" * 64,
                ),
                receiver_assignments=tuple(
                    StationReceiverAssignmentV1(
                        receiver_id=receiver_id,
                        physical_receiver_id=f"operations-v3-physical-rx{receiver_id}",
                        hardware_epoch_external_id=f"operations-v3-rx{receiver_id}-v1",
                        valid_from_utc_ns=validity["valid_from_utc_ns"],
                        valid_until_utc_ns=validity["valid_until_utc_ns"],
                    )
                    for receiver_id in (0, 1)
                ),
            ),
        ),
        **validity,
    )

    class V3AuthorityResolver:
        def resolve(
            self,
            resolved_manifest: RecordingManifestV1 | RecordingManifestV3,
            *,
            observed_manifest_file_digest: str,
        ) -> ResolvedCaptureAuthority:
            if not isinstance(resolved_manifest, RecordingManifestV3):
                raise TypeError("test resolver requires RecordingManifestV3")
            return ResolvedCaptureAuthority(
                topology=topology,
                path_authority=CaptureHardwareBindingV3.create(
                    resolved_manifest,
                    observed_manifest_file_digest=observed_manifest_file_digest,
                    topology=topology,
                ),
            )

    class RecordingCatalog:
        def __init__(self) -> None:
            self.registered_topology: StationReceiverTopologyV1 | None = None
            self.registration: dict[str, Any] | None = None

        def register_station_topology(self, value: StationReceiverTopologyV1) -> None:
            self.registered_topology = value

        def reconcile_capture_session(self, **values: Any) -> bool:
            self.registration = values
            return True

    catalog = RecordingCatalog()
    service = CatalogReconciliationService(
        cast(CatalogRepository, catalog),
        recordings,
        HoldReceiptStore(recordings.root),
        authority_resolver=V3AuthorityResolver(),
    )

    report = service.run_session(manifest.session_id)

    assert report.registered == (manifest.session_id,)
    assert report.issues == ()
    assert catalog.registered_topology == topology
    assert catalog.registration is not None
    assert isinstance(catalog.registration["path_authority"], CaptureHardwareBindingV3)
    [registration] = catalog.registration["streams"]
    assert registration.captured_sample_count == stream.observed_sample_count
    assert registration.captured_sample_count != stream.logical_sample_count
    assert registration.attributes == {
        "requested_settings": stream.requested_settings.model_dump(mode="json"),
        "applied_settings": stream.applied_settings.model_dump(mode="json"),
        "timing": stream.timing.model_dump(mode="json"),
        "capture_start_utc_ns": stream.timing.first_sample.earliest_utc_ns,
        "capture_end_utc_ns": stream.timing.last_sample.latest_utc_ns + 200,
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
        "validity_inventory_relative_path": stream.validity_inventory_relative_path,
        "validity_inventory_sha256": stream.validity_inventory_sha256,
    }
    assert tuple(chunk.sample_start for chunk in registration.chunks) == tuple(
        chunk.device_sample_start for chunk in stream.chunks
    )


def _publish_bundle(
    recordings: RecordingStore,
    session_id: str,
    *,
    source_type: SourceType = SourceType.LIVE,
    extra_tags: tuple[str, ...] = (),
    failure_injector: Callable[[str], None] | None = None,
) -> tuple[str, str, int]:
    tags = tuple(sorted(({"TEST"} if source_type is SourceType.TEST else set()) | set(extra_tags)))
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        center_frequency_hz=1_700_000_000,
        starlink_channel="ch4",
        starlink_edge=StarlinkEdge.LOWER,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30.0),),
        sample_count=8,
        storage_policy="test-zstd-v1",
        tags=tags,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["radio-a"],
        source_type=source_type,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=profile.center_frequency_hz,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        receiver_ids=(0,),
        gain_mode=profile.gain_mode,
        gains=profile.gains,
    )
    compression = CompressionSettingsV1(
        policy_id="test-zstd-v1", level=1, target_uncompressed_bytes=64
    )
    radio = FakeRadioSource("radio-a", receiver_count=1, seed=19)
    radio.open()
    radio.configure(settings)
    writer = recordings.begin(session_id, compression, failure_injector=failure_injector)
    stream_writer = writer.open_stream("stream-a", radio.identity, (0,))
    stream_writer.append(radio.read_block(8))
    receipt = stream_writer.finalize()
    radio.close()
    timing = StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_000_000_000_000,
            earliest_utc_ns=1_700_000_000_000_000_000,
            latest_utc_ns=1_700_000_000_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=1_700_000_001_000_000_000,
            earliest_utc_ns=1_700_000_000_999_000_000,
            latest_utc_ns=1_700_000_001_001_000_000,
            method=TimingMethod.DEVICE_COUNTER_ANCHORED,
        ),
    )
    manifest = RecordingManifestV1(
        session_id=session_id,
        state=CaptureState.COMMITTED,
        source_type=source_type,
        created_utc_ns=1_700_000_000_000_000_000,
        finalized_utc_ns=1_700_000_002_000_000_000,
        capture_plan=plan,
        tags=tags,
        streams=(
            RecordingStreamV1(
                stream_id="stream-a",
                radio=radio.identity,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=8,
                captured_sample_count=8,
                timing=timing,
                chunks=receipt.chunks,
                timeline_relative_path=receipt.timeline_relative_path,
                timeline_sha256=receipt.timeline_sha256,
                continuity=receipt.continuity,
            ),
        ),
        synchronization=SynchronizationSummaryV1(
            requested_mode=plan.requested_synchronization_mode,
            effective_mode=plan.effective_synchronization_mode,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=("stream-a",),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="operations-test"),
        producer=ProducerV1(name="operations-test", version="1"),
    )
    published = writer.publish(manifest)
    return published.uri, published.manifest_sha256, allocated_bytes(published.path)


def _system(
    database: Any,
    tmp_path: Path,
    *,
    failure_injector=None,
) -> tuple[RecordingStore, HoldReceiptStore, PurgeExecutor, CatalogRetentionService]:
    bulk = tmp_path / "bulk"
    recordings = RecordingStore(bulk)
    holds = HoldReceiptStore(bulk)
    executor = PurgeExecutor(bulk)
    retention = CatalogRetentionService(
        database.catalog,
        recordings,
        holds,
        executor,
        failure_injector=failure_injector,
    )
    return recordings, holds, executor, retention


def _mark_analyzed(database: Any, session_id: str, digest: str) -> None:
    database.catalog.add_pipeline_release(
        release_id="retention-test-release",
        code_revision="test-code",
        environment_digest="sha256:" + "a" * 64,
        graph_digest="sha256:" + "b" * 64,
    )
    run_id = f"accepted-{session_id}"
    database.catalog.create_analysis_run(
        run_id=run_id,
        session_id=session_id,
        pipeline_release_id="retention-test-release",
        input_manifest_digest=digest,
        jobs=(),
    )
    database.catalog.seal_and_promote(
        run_id=run_id,
        manifest_uri=f"bulk://analysis/{session_id}/{run_id}/manifest.json",
        manifest_digest="sha256:" + "c" * 64,
        summary=CurrentSummary(details={"minimum_analysis": True}),
    )


def test_stage_commit_tombstone_then_async_discard(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, _holds, executor, retention = _system(operations_database, tmp_path)
    uri, digest, size = _publish_bundle(recordings, "session-purge")
    operations_database.catalog.create_capture_session(
        session_id="session-purge",
        source_type="live",
        state="committed",
        bundle_uri=uri,
        manifest_digest=digest,
        allocated_bytes=size,
    )
    _mark_analyzed(operations_database, "session-purge", digest)
    result = retention.run(StorageUsage(total_bytes=10_000, used_bytes=7_000))
    assert result.committed == ("session:session-purge",)
    assert len(executor.pending()) == 1
    snapshot = operations_database.catalog.presentation_snapshot("session-purge")
    assert snapshot is not None
    assert snapshot.state == "purged"
    assert snapshot.bundle_uri == uri
    assert "recording_manifest" in snapshot.attributes

    recovery = retention.recover()
    assert recovery.discarded == ("session:session-purge",)
    assert executor.pending() == ()
    with operations_database.engine.connect() as connection:
        reclaimed = connection.execute(
            text(
                "SELECT bytes_reclaimed FROM retention_event "
                "WHERE session_id = 'session-purge' AND event_type = 'trash_discarded'"
            )
        ).scalar_one()
    assert reclaimed > 0


def test_process_death_after_stage_is_recovered_by_restore(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    def crash(point: str) -> None:
        if point == "session:after_stage":
            raise InjectedCrash

    recordings, holds, executor, retention = _system(
        operations_database, tmp_path, failure_injector=crash
    )
    uri, digest, size = _publish_bundle(recordings, "session-crash")
    operations_database.catalog.create_capture_session(
        session_id="session-crash",
        source_type="live",
        state="committed",
        bundle_uri=uri,
        manifest_digest=digest,
        allocated_bytes=size,
    )
    _mark_analyzed(operations_database, "session-crash", digest)
    try:
        retention.run(StorageUsage(total_bytes=10_000, used_bytes=7_000))
    except InjectedCrash:
        pass
    else:
        raise AssertionError("injected process death did not escape")
    assert len(executor.pending()) == 1
    recovered = CatalogRetentionService(
        operations_database.catalog, recordings, holds, executor
    ).recover()
    assert recovered.restored == ("session:session-crash",)
    assert recordings.inspect("session-crash").uri == uri


def test_concurrent_pin_receipt_wins_before_purge_commit(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, executor, _unused = _system(operations_database, tmp_path)
    uri, digest, size = _publish_bundle(recordings, "session-pin")
    operations_database.catalog.create_capture_session(
        session_id="session-pin",
        source_type="live",
        state="committed",
        bundle_uri=uri,
        manifest_digest=digest,
        allocated_bytes=size,
    )
    _mark_analyzed(operations_database, "session-pin", digest)
    hold_service = CatalogHoldService(operations_database.catalog, holds)

    def pin_after_stage(point: str) -> None:
        if point != "session:after_stage":
            return
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(
                hold_service.add,
                session_id="session-pin",
                reason="operator pin",
                actor="operator",
            ).result()

    retention = CatalogRetentionService(
        operations_database.catalog,
        recordings,
        holds,
        executor,
        failure_injector=pin_after_stage,
    )
    result = retention.run(StorageUsage(total_bytes=10_000, used_bytes=7_000))
    assert result.committed == ()
    assert "hold won" in result.failures[0]
    assert recordings.inspect("session-pin").uri == uri
    snapshot = operations_database.catalog.presentation_snapshot("session-pin")
    assert snapshot is not None and snapshot.state == "committed"
    assert snapshot.hold_reason == "operator pin"


def test_reconciliation_registers_only_committed_public_bundles_and_test_hold(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    _publish_bundle(recordings, "session-reconcile", source_type=SourceType.TEST)
    spool = recordings.spool_root / "not-committed.partial"
    spool.mkdir()
    (spool / "manifest.json").write_text("{}")

    report = CatalogReconciliationService(operations_database.catalog, recordings, holds).run()
    assert report.registered == ("session-reconcile",)
    assert report.issues == ()
    assert holds.contains("session-reconcile")
    assert operations_database.catalog.presentation_snapshot("not-committed") is None
    [search_result] = operations_database.catalog.search_sessions()
    snapshot = operations_database.catalog.presentation_snapshot("session-reconcile")
    expected_capture_time = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert search_result.created_at == expected_capture_time
    assert snapshot is not None and snapshot.created_at == expected_capture_time
    second = CatalogReconciliationService(operations_database.catalog, recordings, holds).run()
    assert second.existing == ("session-reconcile",)


def test_reconciliation_scopes_repeated_stream_ids_and_repairs_missing_chunks(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    for session_id in ("repeated-a", "repeated-b"):
        _publish_bundle(recordings, session_id)
    service = CatalogReconciliationService(operations_database.catalog, recordings, holds)

    first = service.run()
    assert first.issues == ()
    with operations_database.engine.begin() as connection:
        streams = connection.execute(
            text(
                "SELECT session_id, id FROM radio_stream "
                "WHERE session_id IN ('repeated-a', 'repeated-b') ORDER BY session_id"
            )
        ).all()
        chunks = connection.execute(
            text(
                "SELECT session_id, stream_id, chunk_index FROM recording_chunk "
                "WHERE session_id IN ('repeated-a', 'repeated-b') ORDER BY session_id, chunk_index"
            )
        ).all()
        connection.execute(
            text(
                "DELETE FROM recording_chunk "
                "WHERE session_id = 'repeated-a' AND stream_id = 'stream-a'"
            )
        )
    assert streams == [("repeated-a", "stream-a"), ("repeated-b", "stream-a")]
    assert {(item[0], item[1]) for item in chunks} == {
        ("repeated-a", "stream-a"),
        ("repeated-b", "stream-a"),
    }

    repaired = service.run_session("repeated-a")
    assert repaired.existing == ("repeated-a",) and repaired.issues == ()
    with operations_database.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT count(*) FROM recording_chunk "
                "WHERE session_id = 'repeated-a' AND stream_id = 'stream-a'"
            )
        ).scalar_one() == len(recordings.inspect("repeated-a").manifest.streams[0].chunks)

    with operations_database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE radio_stream SET captured_sample_count = 7 "
                "WHERE session_id = 'repeated-b' AND id = 'stream-a'"
            )
        )
    conflict = service.run_session("repeated-b")
    assert conflict.registered == () and "conflicts with catalog" in conflict.issues[0]


def test_capture_reconciliation_serializes_first_insert_and_repairs_metadata(
    operations_database: Any,
) -> None:
    catalog = operations_database.catalog
    arguments = dict(
        session_id="concurrent-reconcile",
        source_type="test",
        bundle_uri="bulk://recordings/2026/08/19/concurrent-reconcile",
        manifest_digest="sha256:" + "a" * 64,
        allocated_bytes=100,
        attributes={"reconciled": True},
        tags=("TEST", "ACCEPTANCE"),
        streams=(),
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _index: catalog.reconcile_capture_session(**arguments),
                range(8),
            )
        )
    assert results.count(True) == 1 and results.count(False) == 7
    with operations_database.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM retention_hold WHERE session_id='concurrent-reconcile' "
                    "AND released_at IS NULL"
                )
            ).scalar_one()
            == 1
        )
        assert set(
            connection.execute(
                text("SELECT tag_name FROM session_tag WHERE session_id='concurrent-reconcile'")
            ).scalars()
        ) == {"TEST", "ACCEPTANCE"}

    catalog.create_capture_session(
        session_id="metadata-repair",
        source_type="test",
        state="committed",
        bundle_uri="bulk://recordings/metadata-repair",
        manifest_digest="sha256:" + "b" * 64,
        attributes={"operator_note": "preserve"},
    )
    assert not catalog.reconcile_capture_session(
        session_id="metadata-repair",
        source_type="test",
        bundle_uri="bulk://recordings/metadata-repair",
        manifest_digest="sha256:" + "b" * 64,
        allocated_bytes=200,
        attributes={"reconciled": True},
        tags=("TEST",),
        streams=(),
    )
    with operations_database.engine.connect() as connection:
        attributes = connection.execute(
            text("SELECT attributes FROM capture_session WHERE id='metadata-repair'")
        ).scalar_one()
        assert attributes == {"operator_note": "preserve", "reconciled": True}
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM retention_hold WHERE session_id='metadata-repair' "
                    "AND released_at IS NULL"
                )
            ).scalar_one()
            == 1
        )

    with pytest.raises(Exception, match="conflicts with catalog"):
        catalog.reconcile_capture_session(**{**arguments, "source_type": "live"})
    with pytest.raises(Exception, match="attributes conflict"):
        catalog.reconcile_capture_session(**{**arguments, "attributes": {"reconciled": False}})

    def race_different(source_type: str) -> str:
        try:
            inserted = catalog.reconcile_capture_session(
                **{
                    **arguments,
                    "session_id": "different-reconcile",
                    "source_type": source_type,
                    "bundle_uri": "bulk://recordings/different-reconcile",
                }
            )
        except ProductConflictError:
            return "conflict"
        return f"{source_type}:{inserted}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        raced = list(pool.map(race_different, ("live", "test") * 4))
    winners = [item for item in raced if item != "conflict"]
    assert len([item for item in winners if item.endswith(":True")]) == 1
    assert {item.split(":", 1)[0] for item in winners} in ({"live"}, {"test"})
    assert raced.count("conflict") == 4

    shared_stream = RadioStreamRegistration(
        stream_id="stream-0",
        radio_id="shared-radio",
        radio_serial="shared-serial",
        radio_uri="ip:192.0.2.50",
        radio_transport="ethernet",
        state="complete",
        receiver_ids=(1,),
        sample_rate_hz=2_500_000,
        captured_sample_count=8,
        observed_start_at=None,
        observed_end_at=None,
        attributes={},
        chunks=(),
    )

    def reconcile_shared_radio(index: int) -> bool:
        session_id = f"shared-radio-session-{index}"
        return catalog.reconcile_capture_session(
            session_id=session_id,
            source_type="live",
            bundle_uri=f"bulk://recordings/{session_id}",
            manifest_digest=f"sha256:{index:064x}",
            allocated_bytes=1,
            attributes={"reconciled": True},
            streams=(shared_stream,),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(reconcile_shared_radio, range(8))) == [True] * 8
    with operations_database.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM radio WHERE id='shared-radio'")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM radio_stream WHERE radio_id='shared-radio'")
            ).scalar_one()
            == 8
        )


def test_reconciliation_recovers_publication_interrupted_after_atomic_commit(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)

    def interrupt_after_commit(point: str) -> None:
        if point == "after_session_rename":
            raise RuntimeError("simulated process interruption after atomic commit")

    with pytest.raises(RuntimeError, match="simulated process interruption"):
        _publish_bundle(
            recordings,
            "session-publication-recovery",
            failure_injector=interrupt_after_commit,
        )

    storage_report = recordings.reconcile()
    assert tuple(item.session_id for item in storage_report.committed) == (
        "session-publication-recovery",
    )
    assert storage_report.issues == ()
    assert operations_database.catalog.presentation_snapshot("session-publication-recovery") is None

    catalog_report = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
    ).run()
    assert catalog_report.registered == ("session-publication-recovery",)
    assert catalog_report.issues == ()
    snapshot = operations_database.catalog.presentation_snapshot("session-publication-recovery")
    assert snapshot is not None
    assert snapshot.state == "committed"


def test_targeted_reconciliation_does_not_scan_or_register_other_bundles(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    _publish_bundle(recordings, "soak-target")
    _publish_bundle(recordings, "unrelated-history")
    reconciliation = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
    )

    report = reconciliation.run_session("soak-target")

    assert report.registered == ("soak-target",)
    assert report.existing == ()
    assert report.issues == ()
    assert operations_database.catalog.presentation_snapshot("soak-target") is not None
    assert operations_database.catalog.presentation_snapshot("unrelated-history") is None


def test_archive_reconciliation_reports_legacy_inventory_without_blocking_valid_capture(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    _publish_bundle(recordings, "valid-new-live")
    _publish_bundle(recordings, "historical-unreviewed-test", source_type=SourceType.TEST)
    legacy = recordings.recordings_root / "2023/11/14/historical-pre-contract"
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text("{}", encoding="utf-8")

    class RejectUnreviewedTests:
        def resolve(
            self,
            manifest: RecordingManifestV1,
            *,
            observed_manifest_file_digest: str,
        ) -> None:
            del observed_manifest_file_digest
            if manifest.source_type is SourceType.TEST:
                raise UnreviewedTestFixtureAuthorityError(
                    "TEST manifest has no reviewed digest-pinned fixture authority"
                )

    service = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
        authority_resolver=RejectUnreviewedTests(),  # type: ignore[arg-type]
    )

    report = service.run()

    assert report.registered == ("valid-new-live",)
    assert report.issues == ()
    assert len(report.historical_incompatibilities) == 2
    assert any("historical-pre-contract" in item for item in report.historical_incompatibilities)
    assert any(
        "historical-unreviewed-test" in item and "UnreviewedTestFixtureAuthorityError" in item
        for item in report.historical_incompatibilities
    )
    assert operations_database.catalog.presentation_snapshot("valid-new-live") is not None
    assert operations_database.catalog.presentation_snapshot("historical-unreviewed-test") is None

    targeted = service.run_session("historical-unreviewed-test")
    assert targeted.registered == ()
    assert targeted.historical_incompatibilities == ()
    assert len(targeted.issues) == 1
    assert "UnreviewedTestFixtureAuthorityError" in targeted.issues[0]

    class FailingLiveAuthority:
        def resolve(
            self,
            manifest: RecordingManifestV1,
            *,
            observed_manifest_file_digest: str,
        ) -> None:
            del manifest, observed_manifest_file_digest
            raise RuntimeError("new capture authority unavailable")

    strict_target = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
        authority_resolver=FailingLiveAuthority(),  # type: ignore[arg-type]
    ).run_session("valid-new-live")
    assert strict_target.registered == ()
    assert strict_target.historical_incompatibilities == ()
    assert len(strict_target.issues) == 1
    assert "new capture authority unavailable" in strict_target.issues[0]


def test_archive_reconciliation_quarantines_only_exact_cataloged_legacy_manifest(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    _publish_bundle(recordings, "cataloged-precanonical")
    initial = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
    )
    assert initial.run().registered == ("cataloged-precanonical",)
    _publish_bundle(recordings, "new-precanonical")

    class RejectPrecanonicalManifest:
        def resolve(
            self,
            manifest: RecordingManifestV1,
            *,
            observed_manifest_file_digest: str,
        ) -> None:
            del manifest, observed_manifest_file_digest
            raise ValueError(
                "observed manifest-file digest does not match canonical RecordingManifestV1"
            )

    report = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
        authority_resolver=RejectPrecanonicalManifest(),  # type: ignore[arg-type]
    ).run()

    assert report.registered == ()
    assert report.existing == ()
    assert len(report.historical_incompatibilities) == 1
    assert "cataloged-precanonical" in report.historical_incompatibilities[0]
    assert len(report.issues) == 1
    assert "new-precanonical" in report.issues[0]

    targeted = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
        authority_resolver=RejectPrecanonicalManifest(),  # type: ignore[arg-type]
    ).run_session("cataloged-precanonical")
    assert targeted.historical_incompatibilities == ()
    assert len(targeted.issues) == 1


def test_processing_cli_reconcile_queues_only_new_nonqualification_bundles(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    release_id = "1" * 40
    recordings, holds, executor, retention = _system(operations_database, tmp_path)
    _publish_bundle(recordings, "already-cataloged", source_type=SourceType.TEST)
    reconciliation = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
    )
    assert reconciliation.run().registered == ("already-cataloged",)
    _publish_bundle(recordings, "new-live")
    _publish_bundle(
        recordings,
        "qualification-only",
        extra_tags=("QUALIFICATION",),
    )
    _publish_bundle(recordings, "calibration-only", extra_tags=("CALIBRATION",))
    _publish_bundle(recordings, "acceptance-only", extra_tags=("ACCEPTANCE",))
    legacy = recordings.recordings_root / "2023/11/14/historical-pre-contract"
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text("{}", encoding="utf-8")

    class TestLiveAuthority:
        def resolve(
            self,
            manifest: RecordingManifestV1 | RecordingManifestV3,
            *,
            observed_manifest_file_digest: str,
        ) -> ResolvedCaptureAuthority:
            if manifest.session_id == "already-cataloged":
                raise UnreviewedTestFixtureAuthorityError(
                    "TEST manifest has no reviewed digest-pinned fixture authority"
                )
            if manifest.source_type is SourceType.TEST:
                if isinstance(manifest, RecordingManifestV3):
                    raise UnreviewedTestFixtureAuthorityError(
                        "V3 TEST manifests require a separately reviewed fixture authority"
                    )
                return ResolvedCaptureAuthority(
                    topology=None,
                    path_authority=FixturePathAuthorityV1.create(
                        manifest,
                        observed_manifest_file_digest=observed_manifest_file_digest,
                    ),
                )
            [stream] = manifest.streams
            validity = {
                "valid_from_utc_ns": 1_699_999_000_000_000_000,
                "valid_until_utc_ns": 1_700_001_000_000_000_000,
            }
            radio = StationRadioTopologyV1.create(
                radio_id=stream.radio.radio_id,
                radio_serial=stream.radio.serial,
                endpoint_evidence=RadioEndpointEvidenceV1(
                    transport=stream.radio.transport,
                    endpoint=stream.radio.uri,
                    evidence_uri="authority/test-radio.json",
                    evidence_digest="sha256:" + "c" * 64,
                ),
                receiver_assignments=tuple(
                    StationReceiverAssignmentV1(
                        receiver_id=receiver_id,
                        physical_receiver_id=f"physical-rx{receiver_id}",
                        hardware_epoch_external_id=f"test-rx{receiver_id}-v1",
                        valid_from_utc_ns=validity["valid_from_utc_ns"],
                        valid_until_utc_ns=validity["valid_until_utc_ns"],
                    )
                    for receiver_id in (0, 1)
                ),
            )
            topology = StationReceiverTopologyV1.create(
                station_id="test-station",
                topology_revision="test-topology-v1",
                radios=(radio,),
                **validity,
            )
            return ResolvedCaptureAuthority(
                topology=topology,
                path_authority=(
                    CaptureHardwareBindingV3.create(
                        manifest,
                        observed_manifest_file_digest=observed_manifest_file_digest,
                        topology=topology,
                    )
                    if isinstance(manifest, RecordingManifestV3)
                    else CaptureHardwareBindingV1.create(
                        manifest,
                        observed_manifest_file_digest=observed_manifest_file_digest,
                        topology=topology,
                    )
                ),
            )

    authorized_reconciliation = CatalogReconciliationService(
        operations_database.catalog,
        recordings,
        holds,
        authority_resolver=TestLiveAuthority(),
    )
    operations_database.catalog.add_pipeline_release(
        release_id=release_id,
        code_revision=release_id,
        environment_digest="sha256:" + "a" * 64,
        graph_digest="sha256:" + "b" * 64,
        configuration={
            "display_version": "2.0.0",
            "stages": production_standard_v2_configuration(),
        },
    )
    artifacts = AnalysisArtifactStore(recordings.root)
    processing = ProcessingService(
        catalog=operations_database.catalog,
        artifacts=artifacts,
        registry=AnalyzerRegistry((QualityAnalyzer(), PowerAnalyzer())),
        iq_readers=RecordingIqReaderProvider(
            recordings,
            allow_unpinned_integrity_for_tests=True,
        ),
    )
    backend = LocalProcessingBackend(
        ProcessingServices(
            catalog=operations_database.catalog,
            recordings=recordings,
            artifacts=artifacts,
            processing=processing,
            holds=CatalogHoldService(operations_database.catalog, holds),
            retention=retention,
            reconciliation=authorized_reconciliation,
            importer=FixtureImporter((tmp_path / "corpus").resolve()),
            corpus_ingest=RecordingCorpusIngestService(recordings),
            pipeline_release_id=release_id,
        )
    )

    result = backend.reconcile()

    assert set(result.registered_sessions) == {
        "new-live",
        "qualification-only",
        "calibration-only",
        "acceptance-only",
    }
    assert result.existing_sessions == ()
    assert result.issues == ()
    assert len(result.queued_run_ids) == 1
    assert len(result.historical_incompatibilities) == 2
    assert any("historical-pre-contract" in item for item in result.historical_incompatibilities)
    assert any("already-cataloged" in item for item in result.historical_incompatibilities)
    assert operations_database.catalog.current_run_id("already-cataloged") is None
    search = backend.search_sessions(
        source_type=None,
        state=None,
        tag=None,
        held=None,
        created_after=None,
        created_before=None,
        limit=10,
    )
    by_id = {item.session_id: item for item in search.sessions}
    assert by_id["calibration-only"].held
    assert by_id["acceptance-only"].held
    expected_capture_time = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert by_id["new-live"].created_at == expected_capture_time
    assert backend.show_session("new-live").created_at == expected_capture_time

    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    (profile_root / "automatic.yaml").write_text(
        """\
schema_version: 1
name: automatic
center_frequency_hz: 1700000000
starlink_channel: ch4
starlink_edge: lower
sample_rate_hz: 2500000
bandwidth_hz: 2500000
receivers: [0]
gain_mode: manual
gains:
  - {schema_version: 1, receiver_id: 0, gain_db: 30.0}
sample_count: 8
refill_samples: 4
settle_seconds: 0
prime_refills: 0
continuity_policy: require_contiguous
synchronization_mode: none
peer_failure_policy: keep_survivor
storage_policy: test-zstd-v1
tags: [TEST]
""",
        encoding="utf-8",
    )
    acquisition = LocalAcquisitionBackend(
        CliSettings(
            profile_root=profile_root,
            bulk_root=recordings.root,
            radio_backend="fake",
            radios=(RadioConfigurationV1(radio_id="radio-a", receiver_count=1),),
            safety_reserve_bytes=0,
        ),
        CompositionHooks(
            recording_store_factory=lambda _root: recordings,
            processing_backend_factory=lambda _settings: backend,
        ),
    )

    captured = acquisition.capture_once(
        "automatic",
        radio_ids=("radio-a",),
        session_id="auto-catalog-visible",
        extra_tags=(),
        cancel=Event(),
    )

    assert captured.state is CaptureState.COMMITTED
    assert captured.errors == ()
    assert backend.show_session("auto-catalog-visible").bundle_uri == captured.bundle_uri


def test_hold_crash_windows_remain_fail_safe(
    operations_database: Any,
    tmp_path: Path,
) -> None:
    recordings, holds, _executor, _retention = _system(operations_database, tmp_path)
    uri, digest, size = _publish_bundle(recordings, "session-hold-order")
    operations_database.catalog.create_capture_session(
        session_id="session-hold-order",
        source_type="live",
        state="committed",
        bundle_uri=uri,
        manifest_digest=digest,
        allocated_bytes=size,
    )

    def fail_after_receipt(point: str) -> None:
        if point == "hold:after_receipt":
            raise RuntimeError("database unavailable")

    service = CatalogHoldService(
        operations_database.catalog, holds, failure_injector=fail_after_receipt
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        service.add(session_id="session-hold-order", reason="keep", actor="operator")
    assert holds.contains("session-hold-order")
    snapshot = operations_database.catalog.presentation_snapshot("session-hold-order")
    assert snapshot is not None and snapshot.hold_reason is None

    operations_database.catalog.add_retention_hold(
        session_id="session-hold-order", reason="keep", created_by="operator"
    )

    def fail_after_release(point: str) -> None:
        if point == "hold:after_catalog_release":
            raise RuntimeError("receipt filesystem unavailable")

    service = CatalogHoldService(
        operations_database.catalog, holds, failure_injector=fail_after_release
    )
    with pytest.raises(RuntimeError, match="filesystem unavailable"):
        service.release(session_id="session-hold-order")
    assert holds.contains("session-hold-order")
    snapshot = operations_database.catalog.presentation_snapshot("session-hold-order")
    assert snapshot is not None and snapshot.hold_reason is None
