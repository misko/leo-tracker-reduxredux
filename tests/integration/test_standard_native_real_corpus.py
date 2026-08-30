from __future__ import annotations

import os
from pathlib import Path

import pytest

from leo.analysis.standard.configuration import production_receiver_standard_config
from leo.analysis.standard.native_stateful import (
    NativeScheduledProbeInput,
    detect_standard_native_probe_outcome,
)
from leo.analysis.standard.native_windows import (
    NativeWindowPurpose,
    NativeWindowRequest,
    StandardNativeWindowAdapter,
    native_window_evidence,
)
from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.catalog import CaptureRecordingIdentity, RunExecutionInfo
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.recording import RecordingManifestV2, parse_recording_manifest_json
from leo.contracts.standard_native import NativeProbeWindowV3
from leo.contracts.standard_pipeline import ProbeWindowV2
from leo.contracts.states import SourceType, StarlinkEdge
from leo.pipeline import ScopeIdentityV1
from leo.pipeline.standard_native import (
    STANDARD_NATIVE_STAGE_KEYS,
    compile_standard_native_run_plan,
)
from leo.processing import RecordingIqReaderProvider
from leo.storage import PinnedLocalRoot, RecordingStore

pytestmark = pytest.mark.real_corpus

_DEFAULT_CORPUS_ROOT = Path("/srv/bulk/leo/recordings/2026/08/25")
_RELEASE = "1" * 40
_ADMITTED = (
    (
        "cap-20260825T212100-f5e627722c6c",
        "starlink-ch4-lower-2p5m-60s-continuity-v2",
        2_500_000,
    ),
    (
        "cap-20260825T213600-dd352bd0e4fc",
        "starlink-ch4-lower-3m-60s-capture-v2",
        3_000_000,
    ),
    (
        "cap-20260825T214800-edc045ea9a07",
        "starlink-ch4-lower-5m-60s-segmented-v2",
        5_000_000,
    ),
)
_TRUNCATED = "cap-20260825T211500-642ccf40a8c1"
_FIVE_M_SESSION = "cap-20260825T214800-edc045ea9a07"
_EXECUTABLE_REAL_IQ_SESSIONS = (
    "cap-20260825T213600-dd352bd0e4fc",
    _FIVE_M_SESSION,
)
_FIVE_M_MANIFEST_DIGEST = "sha256:9ba64b81c7c7521e9967eb4d78ad348e6091ffde873d22b3c7d03a92422b0824"
_FIVE_M_STREAM_ORACLE = {
    "radio_pluto_5d4d": {
        "stream_id": "stream-0",
        "selected_stream_digest": (
            "sha256:274769ddcbf4b7fd8817591b76ab19ae9ba8dfcfe791c0c6ad7118153cbc02b4"
        ),
        "uncompressed_chunk_closure_digest": (
            "sha256:5504d5cfefb91952f3a681639212ab2b8b093cd186a330deb60d7aa229d67ed3"
        ),
        "validity_inventory_digest": (
            "sha256:7344372282c28fa79df9f4587c908d3637ce9f7c23ee52199f436c1828333f45"
        ),
        "observed_iq_digest": (
            "sha256:653949aeaf55931443c436c9c2ad4584eca0516bb71449feee9c471bb63a52cc"
        ),
        "logical_iq_digest": (
            "sha256:e7d996913dabfce183d97bb7d727b535c0b757793fd99f0d0c124d0df79573c4"
        ),
    },
    "radio_pluto_19f2": {
        "stream_id": "stream-1",
        "selected_stream_digest": (
            "sha256:4df538f7f71b37e54b015410024f0d3deb255c713f68c179760509e060bfc4fd"
        ),
        "uncompressed_chunk_closure_digest": (
            "sha256:39e3a8eb364035d0b72d60f3180bce5e6660014a06b27148b1a066ef225f5260"
        ),
        "validity_inventory_digest": (
            "sha256:400908b8c72e44a7778ef56709435c00db9252a661aa1392f0fdea6699bcf680"
        ),
        "observed_iq_digest": (
            "sha256:d65372899c7b2b83e349048fa0d7691eb550ee8dc1a828aee62041ef7827bbb9"
        ),
        "logical_iq_digest": (
            "sha256:38355ae3d9ac86f7c63156f5dc2d1f9a290c771b84b6416926dbb07d607b4643"
        ),
    },
}


def _require_explicit_real_corpus(request: pytest.FixtureRequest) -> None:
    if "real_corpus" not in request.config.option.markexpr:
        pytest.skip("historical native corpus admission requires explicit `pytest -m real_corpus`")


def _corpus_root() -> Path:
    configured = Path(os.environ.get("LEO_NATIVE_REAL_CORPUS_ROOT", str(_DEFAULT_CORPUS_ROOT)))
    try:
        root = configured.resolve(strict=True)
    except OSError as error:
        pytest.fail(f"configured read-only native corpus root is unavailable: {error}")
    if not root.is_dir():
        pytest.fail(f"configured read-only native corpus root is not a directory: {root}")
    return root


def _manifest(session_id: str) -> tuple[RecordingManifestV2, bytes]:
    manifest_path = _corpus_root() / session_id / "manifest.json"
    if not manifest_path.is_file():
        pytest.fail(f"required read-only historical recording is absent: {manifest_path}")
    payload = manifest_path.read_bytes()
    manifest = parse_recording_manifest_json(payload)
    assert isinstance(manifest, RecordingManifestV2)
    assert manifest.session_id == session_id
    return manifest, payload


def test_exact_named_historical_v2_sessions_are_native_admissible(
    request: pytest.FixtureRequest,
) -> None:
    _require_explicit_real_corpus(request)

    for session_id, profile_name, sample_rate_hz in _ADMITTED:
        manifest, payload = _manifest(session_id)
        assert manifest.source_type is SourceType.LIVE
        assert manifest.capture_plan.profile_revision.profile.name == profile_name
        assert manifest.capture_plan.profile_revision.profile.sample_rate_hz == sample_rate_hz
        assert len(manifest.streams) == 2
        plan = compile_standard_native_run_plan(
            manifest,
            manifest_digest=sha256_digest(payload),
            pipeline_release_id=_RELEASE,
        )
        assert (len(plan.jobs), len(plan.edges)) == (12, 15)
        assert {item.stage_key for item in plan.jobs} == set(STANDARD_NATIVE_STAGE_KEYS)
        assert all("resampl" not in item.stage_key for item in plan.jobs)


def test_plan_exact_five_m_session_rebuilds_deterministic_native_digest_closure(
    request: pytest.FixtureRequest,
) -> None:
    _require_explicit_real_corpus(request)
    manifest, payload = _manifest(_FIVE_M_SESSION)
    assert sha256_digest(payload) == _FIVE_M_MANIFEST_DIGEST
    assert set(_FIVE_M_STREAM_ORACLE) == {stream.radio.radio_id for stream in manifest.streams}
    for stream in manifest.streams:
        assert stream.requested_sample_count == 300_000_000
        assert stream.continuity.device_span_sample_count == 300_000_000
        assert stream.captured_sample_count == 284_795_648
        assert stream.continuity.observed_sample_count == 284_795_648
        assert stream.continuity.missing_sample_count == 15_204_352
        assert stream.continuity.gap_count == 58
        assert stream.continuity.segment_count == 59

    corpus_root = _corpus_root()
    recordings_namespace = corpus_root.parents[2]
    if recordings_namespace.name != "recordings":
        pytest.fail(
            "LEO_NATIVE_REAL_CORPUS_ROOT must identify one YYYY/MM/DD directory beneath "
            "a recording-store recordings namespace"
        )
    pinned = PinnedLocalRoot(recordings_namespace.parent)
    recordings = RecordingStore.open_pinned(pinned)
    provider = RecordingIqReaderProvider(recordings)
    try:
        bundle = recordings.inspect(_FIVE_M_SESSION)
        assert bundle.manifest_sha256 == _FIVE_M_MANIFEST_DIGEST
        attestation = provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=_FIVE_M_SESSION,
                bundle_uri=bundle.uri,
                manifest_digest=bundle.manifest_sha256,
            )
        )
        raw_by_stream = {item.stream_id: item for item in attestation.streams}
        for stream in manifest.streams:
            oracle = _FIVE_M_STREAM_ORACLE[stream.radio.radio_id]
            assert stream.stream_id == oracle["stream_id"]
            evidence = provider.verified_historical_v2_native_stream_evidence(
                attestation.attestation_digest,
                stream.stream_id,
            )
            assert evidence.raw_integrity_attestation_digest == attestation.attestation_digest
            assert evidence.selected_stream_digest == canonical_digest(
                stream.model_dump(mode="json")
            )
            assert evidence.selected_stream_digest == oracle["selected_stream_digest"]
            assert evidence.uncompressed_chunk_closure_digest == (
                raw_by_stream[stream.stream_id].uncompressed_closure_digest
            )
            assert (
                evidence.uncompressed_chunk_closure_digest
                == (oracle["uncompressed_chunk_closure_digest"])
            )
            assert evidence.validity_inventory == provider.verified_validity_inventory(
                attestation.attestation_digest,
                stream.stream_id,
            )
            assert evidence.validity_inventory.logical_sample_count == 300_000_000
            assert evidence.validity_inventory.observed_sample_count == 284_795_648
            assert evidence.validity_inventory.missing_sample_count == 15_204_352
            assert evidence.validity_inventory.continuity_boundary_count == 58
            assert len(evidence.validity_inventory.segments) == 59
            assert (
                evidence.validity_inventory.inventory_digest
                == (oracle["validity_inventory_digest"])
            )
            assert evidence.observed_iq_digest == oracle["observed_iq_digest"]
            assert evidence.logical_iq_digest == oracle["logical_iq_digest"]
            assert evidence.observed_iq_digest != evidence.logical_iq_digest
    finally:
        provider.close()
        recordings.close()
        pinned.close()


def test_truncated_named_historical_v2_session_is_native_rejected(
    request: pytest.FixtureRequest,
) -> None:
    _require_explicit_real_corpus(request)
    manifest, payload = _manifest(_TRUNCATED)
    assert any(
        stream.continuity.device_span_sample_count < stream.requested_sample_count
        and stream.continuity.enqueue_failure_count == 1
        for stream in manifest.streams
    )

    with pytest.raises(ValueError, match="complete counter-proven span"):
        compile_standard_native_run_plan(
            manifest,
            manifest_digest=sha256_digest(payload),
            pipeline_release_id=_RELEASE,
        )


@pytest.mark.parametrize("session_id", _EXECUTABLE_REAL_IQ_SESSIONS)
def test_real_iq_executes_production_native_probe_without_crossing_a_gap(
    request: pytest.FixtureRequest,
    session_id: str,
) -> None:
    """Exercise the production detector on real 3M and gapped 5M IQ bytes."""

    _require_explicit_real_corpus(request)
    manifest, _payload = _manifest(session_id)
    stream = min(manifest.streams, key=lambda item: item.stream_id)
    settings = stream.applied_settings
    assert settings is not None
    receiver_id = min(settings.receiver_ids)
    probe_samples = settings.sample_rate_hz * 20 // 1_000
    assert probe_samples * 1_000 == settings.sample_rate_hz * 20

    recordings_namespace = _corpus_root().parents[2]
    if recordings_namespace.name != "recordings":
        pytest.fail(
            "LEO_NATIVE_REAL_CORPUS_ROOT must identify one YYYY/MM/DD directory beneath "
            "a recording-store recordings namespace"
        )
    pinned = PinnedLocalRoot(recordings_namespace.parent)
    recordings = RecordingStore.open_pinned(pinned)
    provider = RecordingIqReaderProvider(recordings)
    reader = None
    try:
        bundle = recordings.inspect(session_id)
        attestation = provider.verify_integrity(
            CaptureRecordingIdentity(
                session_id=session_id,
                bundle_uri=bundle.uri,
                manifest_digest=bundle.manifest_sha256,
            )
        )
        reader = provider.open_validity_scope(
            RunExecutionInfo(
                run_id=f"real-iq-native-{session_id}",
                session_id=session_id,
                pipeline_release_id=_RELEASE,
                pipeline_configuration={},
                input_manifest_digest=bundle.manifest_sha256,
                trigger="qualification",
                bundle_uri=bundle.uri,
                raw_integrity_attestation_digest=attestation.attestation_digest,
                raw_integrity_attestation=attestation.model_dump(mode="json"),
            ),
            ScopeIdentityV1.receiver_path(
                session_id=session_id,
                stream_id=stream.stream_id,
                receiver_id=receiver_id,
            ),
        )
        adapter = StandardNativeWindowAdapter(reader)
        request_window = NativeWindowRequest(
            opportunity_index=0,
            purpose=NativeWindowPurpose.PROBE_20MS,
            device_sample_start=0,
            sample_count=probe_samples,
        )
        decision = adapter.decide((request_window,))[0]
        assert decision.eligible
        window_items = tuple(adapter.iter_valid_windows((decision,)))
        assert len(window_items) == 1
        _decision, window = window_items[0]
        segment_index = decision.classification.continuity_segment_index
        assert segment_index is not None
        segment = reader.validity_inventory.segments[segment_index]
        assert (
            segment.device_sample_start
            <= window.global_device_sample_start
            < window.global_device_sample_stop
            <= segment.device_sample_stop
        )
        opportunity = NativeProbeWindowV3(
            probe=ProbeWindowV2(
                probe_id=canonical_digest(
                    {
                        "session_id": session_id,
                        "stream_id": stream.stream_id,
                        "receiver_id": receiver_id,
                        "sample_start": window.global_device_sample_start,
                        "sample_count": window.sample_count,
                        "gate": "standard-native-real-iq-probe-v1",
                    }
                ),
                coarse_window_index=0,
                subwindow_index=0,
                probe_offset_ms=0,
                sample_start=window.global_device_sample_start,
                sample_count=window.sample_count,
                time_s=window.global_device_sample_start / settings.sample_rate_hz,
            ),
            validity=native_window_evidence(decision.classification),
        )
        config = production_receiver_standard_config(
            sample_rate_hz=settings.sample_rate_hz
        ).feedback
        frequency_reference = compile_pilot_search_geometry(
            receiver_id=receiver_id,
            starlink_channel=1,
            edge=StarlinkEdge.LOWER,
            tuned_center_frequency_hz=settings.center_frequency_hz,
            sample_rate_hz=settings.sample_rate_hz,
            rf_bandwidth_hz=settings.bandwidth_hz,
            residual_cfo_min_hz=config.cfo_search_min_hz,
            residual_cfo_max_hz=config.cfo_search_max_hz,
        ).frequency_reference
        scheduled = NativeScheduledProbeInput(
            opportunity_index=0,
            opportunity=opportunity,
            segment=segment,
            iq=window,
            continuity_segment_index=segment_index,
            global_device_sample_start=window.global_device_sample_start,
            global_device_sample_stop=window.global_device_sample_stop,
            segment_local_sample_start=(
                window.global_device_sample_start - segment.device_sample_start
            ),
            frequency_reference=frequency_reference,
        )
        outcome = detect_standard_native_probe_outcome(
            scheduled,
            config,
            StarlinkEdge.LOWER,
        )
        detection = outcome.detection
        assert detection.sample_start == scheduled.segment_local_sample_start
        assert detection.time_s == pytest.approx(
            scheduled.segment_local_sample_start / settings.sample_rate_hz
        )
        assert bool(detection.local_epoch_sample is not None) is bool(
            outcome.primary_qam_result is not None
        )
        if outcome.primary_qam_result is not None:
            assert outcome.primary_qam_result.known_symbols_only
            assert outcome.primary_qam_result.candidate_only
    finally:
        if reader is not None:
            reader.close()
        provider.close()
        recordings.close()
        pinned.close()
