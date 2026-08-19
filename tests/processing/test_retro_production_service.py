from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from leo.analysis.adapters import (
    production_long_dwell_configuration,
    production_long_dwell_registry,
)
from leo.analysis.graphs import ComputeTier
from leo.analysis.starlink import FixturePreflightStatus, preflight_corpus
from leo.artifacts import AnalysisArtifactStore
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import (
    IqBlockMetadataV1,
    NanosecondIntervalV1,
    RadioIdentityV1,
    RadioSettingsV1,
    ReceiverGainV1,
)
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
    ContinuityStatus,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.processing import ProcessingService, RecordingIqReaderProvider
from leo.storage import RecordingStore

from .conftest import ProcessingDatabase

CORPUS_MANIFEST = Path("corpus/manifest.json").resolve()
CORPUS_ROOT = Path(os.environ.get("LEO_REAL_CORPUS_ROOT", "/srv/bulk/leo/test-corpus"))
RETRO_ID = "retro-positive-68p7"
RETRO_STREAM_ID = "retro-stream"


def _prepare_retro_recording(
    database: ProcessingDatabase,
    bulk_root: Path,
) -> tuple[RecordingStore, AnalysisArtifactStore, str]:
    report = preflight_corpus(CORPUS_MANIFEST, local_corpus_root=CORPUS_ROOT)
    assert report.by_id(RETRO_ID).status is FixturePreflightStatus.READY
    fixture_root = CORPUS_ROOT / RETRO_ID
    fixture = json.loads((fixture_root / "fixture-manifest.json").read_bytes())
    metadata = fixture["metadata"]
    fmt = metadata["format"]
    selection = metadata["selection"]
    sample_count = int(selection["sample_count"])
    sample_rate_hz = int(fmt["sample_rate_hz"])
    samples = np.memmap(
        fixture_root / "recording.ci16",
        dtype="<i2",
        mode="r",
        shape=(sample_count, int(fmt["receiver_count"]), 2),
    )

    center_frequency_hz = 1_709_687_500
    profile = CaptureProfileV1(
        name="protected-retro-production-regression",
        center_frequency_hz=center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30.0),
            ReceiverGainV1(receiver_id=1, gain_db=30.0),
        ),
        sample_count=sample_count,
        storage_policy="test-zstd-v1",
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        ["retro-radio"],
        source_type=SourceType.TEST,
    )
    settings = RadioSettingsV1(
        center_frequency_hz=center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        receiver_ids=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=profile.gains,
    )
    radio = RadioIdentityV1(
        radio_id="retro-radio",
        serial="protected-retro-fixture",
        uri="fixture://retro-positive-68p7",
        transport=RadioTransport.IMPORTED,
    )
    compression = CompressionSettingsV1(
        policy_id="test-zstd-v1",
        level=3,
        target_uncompressed_bytes=sample_count * 8,
    )
    recordings = RecordingStore(bulk_root)
    writer = recordings.begin(RETRO_ID, compression)
    stream_writer = writer.open_stream(RETRO_STREAM_ID, radio, (0, 1))
    instant = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
    stream_writer.append(
        IqBlock(
            samples=np.ascontiguousarray(samples),
            metadata=IqBlockMetadataV1(
                radio_id=radio.radio_id,
                receiver_ids=(0, 1),
                sample_count=sample_count,
                session_sample_start=0,
                host_request_utc_ns=instant,
                host_request_monotonic_ns=instant,
                timing_method=TimingMethod.IMPORTED,
                continuity=ContinuityStatus.CONTIGUOUS,
            ),
        )
    )
    receipt = stream_writer.finalize()
    created_ns = 1_700_000_000_000_000_000
    duration_ns = round(sample_count / sample_rate_hz * 1_000_000_000)
    timing = StreamTimingV1(
        first_sample=TimingEstimateV1(
            estimate_utc_ns=created_ns,
            earliest_utc_ns=created_ns,
            latest_utc_ns=created_ns,
            method=TimingMethod.IMPORTED,
        ),
        last_sample=TimingEstimateV1(
            estimate_utc_ns=created_ns + duration_ns,
            earliest_utc_ns=created_ns + duration_ns,
            latest_utc_ns=created_ns + duration_ns,
            method=TimingMethod.IMPORTED,
        ),
    )
    manifest = RecordingManifestV1(
        session_id=RETRO_ID,
        state=CaptureState.COMMITTED,
        source_type=SourceType.TEST,
        created_utc_ns=created_ns,
        finalized_utc_ns=created_ns + duration_ns,
        capture_plan=plan,
        tags=("TEST",),
        streams=(
            RecordingStreamV1(
                stream_id=RETRO_STREAM_ID,
                radio=radio,
                requested_settings=settings,
                applied_settings=settings,
                state=StreamState.COMPLETE,
                requested_sample_count=sample_count,
                captured_sample_count=sample_count,
                timing=timing,
                chunks=receipt.chunks,
                timeline_relative_path=receipt.timeline_relative_path,
                timeline_sha256=receipt.timeline_sha256,
                continuity=receipt.continuity,
            ),
        ),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=(RETRO_STREAM_ID,),
        ),
        compression=compression,
        host=HostIdentityV1(hostname="protected-fixture", machine_id="test-machine"),
        producer=ProducerV1(name="protected-fixture-import", version="1"),
    )
    published = writer.publish(manifest)
    database.catalog.create_capture_session(
        session_id=RETRO_ID,
        source_type="test",
        state="committed",
        bundle_uri=published.uri,
        manifest_digest=published.manifest_sha256,
        tags=("TEST",),
    )
    return recordings, AnalysisArtifactStore(bulk_root), published.manifest_sha256


def _execute_until_idle(service: ProcessingService) -> None:
    while result := service.run_once(worker_id="retro-production-worker"):
        assert result.succeeded, result.error


def _product_document(
    database: ProcessingDatabase,
    artifacts: AnalysisArtifactStore,
    *,
    run_id: str,
    kind: str,
    stage_key: str,
) -> dict[str, Any]:
    products = [
        item
        for item in database.catalog.run_seal_snapshot(run_id).products
        if item.kind == kind and item.stage_key == stage_key
    ]
    assert len(products) == 1
    return artifacts.read_json(products[0].logical_uri, products[0].digest)


@pytest.mark.real_corpus
def test_protected_retro_full_standard_service_matches_frozen_oracle(
    processing_database: ProcessingDatabase,
    tmp_path: Path,
) -> None:
    recordings, artifacts, manifest_digest = _prepare_retro_recording(
        processing_database,
        tmp_path / "bulk",
    )
    fixture = json.loads((CORPUS_ROOT / RETRO_ID / "fixture-manifest.json").read_bytes())
    expected = fixture["metadata"]["candidate_expectation"]
    release_id = "retro-standard-v1"
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)
    processing_database.catalog.add_pipeline_release(
        release_id=release_id,
        code_revision="protected-retro-adapter-regression",
        environment_digest="sha256:" + "a" * 64,
        graph_digest="sha256:" + "b" * 64,
        configuration=configuration,
    )
    service = ProcessingService(
        catalog=processing_database.catalog,
        artifacts=artifacts,
        registry=production_long_dwell_registry(ComputeTier.STANDARD),
        iq_readers=RecordingIqReaderProvider(recordings),
        lease_for=timedelta(seconds=30),
        heartbeat_interval=timedelta(seconds=1),
    )
    run_id = "retro-standard-run"
    service.create_new_capture_run(
        run_id=run_id,
        session_id=RETRO_ID,
        pipeline_release_id=release_id,
        input_manifest_digest=manifest_digest,
        scope_keys=(RETRO_STREAM_ID,),
    )

    _execute_until_idle(service)
    service.finalize_run(run_id)

    refined = _product_document(
        processing_database,
        artifacts,
        run_id=run_id,
        kind="starlink.refined",
        stage_key="dense-refine",
    )["refined"]
    qam = _product_document(
        processing_database,
        artifacts,
        run_id=run_id,
        kind="qam.presentation",
        stage_key="presentation-overlays",
    )
    for receiver_id in (0, 1):
        receiver_refined = [item for item in refined if item["receiver_id"] == receiver_id]
        oracle_epoch = expected["receiver_epoch_samples"][receiver_id]
        oracle_cfo = expected["receiver_cfo_hz"][receiver_id]
        assert any(
            item["absolute_epoch_sample"] == oracle_epoch
            and item["absolute_cfo_hz"] == pytest.approx(oracle_cfo, abs=35.0)
            for item in receiver_refined
        )
        metrics = next(
            item for item in qam["receiver_metrics"] if item["receiver_key"] == str(receiver_id)
        )
        assert metrics["candidate_epoch_sample"] == oracle_epoch
        assert metrics["baseband_cfo_hz"] == pytest.approx(oracle_cfo, abs=35.0)
        assert metrics["accuracy"] == pytest.approx(
            expected["receiver_hard_symbol_accuracy"][receiver_id],
            abs=1 / 2400,
        )
        assert metrics["tuned_signal_frequency_hz"] == pytest.approx(
            metrics["receiver_tuned_center_hz"] + metrics["baseband_cfo_hz"],
            abs=1e-6,
        )
    assert qam["combined_accuracy"] == pytest.approx(
        expected["historical_combined_hard_symbol_accuracy"],
        abs=1 / 2400,
    )
    assert processing_database.catalog.current_run_id(RETRO_ID) == run_id
    assert qam["candidate_only"] is True
