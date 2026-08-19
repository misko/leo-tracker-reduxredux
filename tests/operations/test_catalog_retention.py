from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from sqlalchemy import text

from leo.analysis.power import PowerAnalyzer
from leo.analysis.quality import QualityAnalyzer
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CurrentSummary
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    RadioConfigurationV1,
)
from leo.cli.processing import LocalProcessingBackend, ProcessingServices
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    SourceType,
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
from leo.pipeline import AnalyzerRegistry
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore


class InjectedCrash(BaseException):
    pass


def _publish_bundle(
    recordings: RecordingStore,
    session_id: str,
    *,
    source_type: SourceType = SourceType.LIVE,
    extra_tags: tuple[str, ...] = (),
) -> tuple[str, str, int]:
    tags = tuple(sorted(({"TEST"} if source_type is SourceType.TEST else set()) | set(extra_tags)))
    profile = CaptureProfileV1(
        name=f"profile-{session_id}",
        center_frequency_hz=1_700_000_000,
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
    writer = recordings.begin(session_id, compression)
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


def test_processing_cli_reconcile_queues_only_new_nonqualification_bundles(
    operations_database: Any,
    tmp_path: Path,
) -> None:
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
    operations_database.catalog.add_pipeline_release(
        release_id="cli-standard-v1",
        code_revision="test-code",
        environment_digest="sha256:" + "a" * 64,
        graph_digest="sha256:" + "b" * 64,
        configuration={},
    )
    artifacts = AnalysisArtifactStore(recordings.root)
    processing = ProcessingService(
        catalog=operations_database.catalog,
        artifacts=artifacts,
        registry=AnalyzerRegistry((QualityAnalyzer(), PowerAnalyzer())),
        iq_readers=RecordingIqReaderProvider(recordings),
    )
    backend = LocalProcessingBackend(
        ProcessingServices(
            catalog=operations_database.catalog,
            recordings=recordings,
            artifacts=artifacts,
            processing=processing,
            holds=CatalogHoldService(operations_database.catalog, holds),
            retention=retention,
            reconciliation=reconciliation,
            importer=FixtureImporter((tmp_path / "corpus").resolve()),
            corpus_ingest=RecordingCorpusIngestService(recordings),
            pipeline_release_id="cli-standard-v1",
        )
    )

    result = backend.reconcile()

    assert set(result.registered_sessions) == {"new-live", "qualification-only"}
    assert result.existing_sessions == ("already-cataloged",)
    assert len(result.queued_run_ids) == 1
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
