from decimal import Decimal

import pytest

import leo.acquisition.coordinator as coordinator_module
from leo.acquisition.coordinator import AcquisitionCoordinator
from leo.acquisition.models import AcquisitionConfig
from leo.contracts.device_buffer import (
    DDR_RING_EVIDENCE_KEY_V1,
    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2,
    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3,
    DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V4,
    DeviceBufferEvidenceV1,
    DeviceBufferRequestV1,
    DirectAsyncRamDropEvidenceV2,
    DirectAsyncRamDropEvidenceV3,
    DirectAsyncRamDropRequestV2,
    DirectAsyncRamDropRequestV3,
    DirectAsyncRamDropRequestV4,
)
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.recording import DEVICE_AXIS_STORAGE_POLICY_V1, CompressionSettingsV1
from leo.contracts.states import CaptureState, ContinuityPolicy, PeerFailurePolicy, SourceType
from leo.domain.profiles import compile_capture_plan
from leo.radio.fake import FakeRadioSource
from leo.storage import RecordingStore
from leo.storage.writer import DeviceAxisStreamBundleWriter


def _setup(tmp_path, monkeypatch, *, frames=6, queue_capacity=32):
    profile = CaptureProfileV2(
        name="tiny-ring-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=20_000_000,
        bandwidth_hz=20_000_000,
        receivers=(0,),
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        sample_count=frames * 4,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=4,
        refill_queue_capacity=queue_capacity,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile), ["radio-a"], source_type=SourceType.TEST
    )
    request = DeviceBufferRequestV1(
        requested_bytes=32,
        target_frames=frames,
        frame_samples=4,
        requested_device_samples=frames * 4,
    )
    monkeypatch.setattr(coordinator_module, "device_buffer_request_v1", lambda *_: request)
    store = RecordingStore(tmp_path / "bulk")
    coordinator = AcquisitionCoordinator(
        store,
        config=AcquisitionConfig(safety_reserve_bytes=0),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1, target_uncompressed_bytes=1024
        ),
    )
    return coordinator, plan, request


def test_ring_drains_finite_tail_but_publishes_only_requested_device_window(tmp_path, monkeypatch):
    coordinator, plan, request = _setup(tmp_path, monkeypatch)
    radio = FakeRadioSource("radio-a", gaps_before_blocks={2: 8})
    original = DeviceAxisStreamBundleWriter.append

    def append_only_after_radio_drain(self, block):
        assert radio._ring_returned_frames == request.target_frames
        assert radio.lifecycle[-1] == "reset_receive_buffer"
        return original(self, block)

    monkeypatch.setattr(DeviceAxisStreamBundleWriter, "append", append_only_after_radio_drain)
    result = coordinator.capture_once(plan, {"radio-a": radio}, session_id="ring-tail")
    assert result.state is CaptureState.DEGRADED
    assert result.bundle is not None
    stream = result.bundle.manifest.streams[0]
    assert stream.requested_sample_count == stream.logical_sample_count == 24
    assert stream.observed_sample_count == 16
    assert stream.zero_fill_sample_count == 8
    assert stream.continuity.enqueue_failure_count == 0
    reader = coordinator.store.reader(result.bundle, "stream-0")
    first = next(reader.iter_timeline_metadata())
    evidence = DeviceBufferEvidenceV1.model_validate(
        first.hardware_metadata[DDR_RING_EVIDENCE_KEY_V1]
    )
    assert evidence.returned_frames == 6
    assert evidence.returned_device_span_samples == 32
    assert evidence.drained_outside_window_samples == 8
    assert evidence.protected_prefix_bytes == 32
    assert not tuple(result.bundle.path.glob("raw-stage-*"))
    coordinator.store.verify(result.bundle.session_id)


def test_ring_terminal_abi3_gap_persists_readable_v2_header_view(tmp_path, monkeypatch):
    coordinator, plan, _ = _setup(tmp_path, monkeypatch)
    result = coordinator.capture_once(
        plan,
        {"radio-a": FakeRadioSource("radio-a", gaps_before_blocks={5: 8})},
        session_id="ring-terminal-abi3-gap",
    )

    assert result.state is CaptureState.DEGRADED
    bundle = coordinator.store.inspect("ring-terminal-abi3-gap")
    terminal = bundle.manifest.streams[0].continuity.terminal_gap
    assert terminal is not None
    assert terminal.metadata_abi_version == 3
    assert terminal.header.schema_version == 2
    coordinator.store.verify(bundle.session_id)


def test_ring_contiguous_capture_commits_and_admits_double_space(tmp_path, monkeypatch):
    coordinator, plan, _ = _setup(tmp_path, monkeypatch)
    estimate = coordinator.estimate_admission(plan)
    assert (
        estimate.required_free_bytes == 2 * estimate.raw_iq_bytes + estimate.metadata_reserve_bytes
    )
    result = coordinator.capture_once(
        plan, {"radio-a": FakeRadioSource("radio-a")}, session_id="ring-clean"
    )
    assert result.state is CaptureState.COMMITTED
    assert result.bundle is not None
    assert result.bundle.manifest.streams[0].continuity.refill_count == 6


def test_direct_async_ram_drop_uses_one_session_and_persists_queue_closure(tmp_path, monkeypatch):
    profile = CaptureProfileV2(
        name="tiny-direct-ram-drop-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=25_000_000,
        bandwidth_hz=25_000_000,
        receivers=(0,),
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        sample_count=100,
        refill_samples=1_048_576,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=12,
        refill_queue_capacity=4,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    request = DirectAsyncRamDropRequestV2(
        target_frames=1,
        requested_device_samples=100,
    )
    monkeypatch.setattr(coordinator_module, "_device_buffer_request", lambda *_: request)
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1024,
        ),
    )
    radio = FakeRadioSource("radio-a")

    result = coordinator.capture_once(
        plan,
        {"radio-a": radio},
        session_id="direct-ram-drop-clean",
    )

    assert result.state is CaptureState.COMMITTED
    assert radio.lifecycle.count("begin_metadata_capture:1048576:12") == 1
    assert result.bundle is not None
    first = next(coordinator.store.reader(result.bundle, "stream-0").iter_timeline_metadata())
    evidence = DirectAsyncRamDropEvidenceV2.model_validate(
        first.hardware_metadata[DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2]
    )
    assert evidence.segment_count == 1
    assert evidence.returned_frames == 1
    assert evidence.stored_observed_samples == 100
    assert evidence.drained_outside_window_samples == 1_048_476
    assert evidence.status.requested_capacity_iq_bytes == 200_000_000
    assert evidence.status.admitted_capacity_iq_bytes == 197_132_288
    assert evidence.ram_dropped_frames == 0
    coordinator.store.verify(result.bundle.session_id)


def test_qualified_ram_drop_uses_v3_key_and_qualified_geometry(tmp_path, monkeypatch):
    profile = CaptureProfileV2(
        name="tiny-qualified-direct-ram-drop-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=25_000_000,
        bandwidth_hz=25_000_000,
        receivers=(0,),
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        sample_count=100,
        refill_samples=1_048_576,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=11,
        refill_queue_capacity=4,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    request = DirectAsyncRamDropRequestV3(
        target_frames=1,
        requested_device_samples=100,
    )
    monkeypatch.setattr(coordinator_module, "_device_buffer_request", lambda *_: request)
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1024,
        ),
    )
    radio = FakeRadioSource("radio-a")

    result = coordinator.capture_once(
        plan,
        {"radio-a": radio},
        session_id="qualified-direct-ram-drop-clean",
    )

    assert result.state is CaptureState.COMMITTED
    assert radio.lifecycle.count("begin_metadata_capture:1048576:11") == 1
    assert result.bundle is not None
    first = next(coordinator.store.reader(result.bundle, "stream-0").iter_timeline_metadata())
    evidence = DirectAsyncRamDropEvidenceV3.model_validate(
        first.hardware_metadata[DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3]
    )
    assert evidence.request.schema_version == 3
    assert evidence.status.requested_capacity_iq_bytes == 134_217_728
    assert evidence.status.admitted_capacity_iq_bytes == 134_217_728
    assert DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V2 not in first.hardware_metadata
    coordinator.store.verify(result.bundle.session_id)


def test_bounded_ram_drop_collects_terminal_status_from_every_segment(tmp_path, monkeypatch):
    profile = CaptureProfileV2(
        name="tiny-bounded-direct-ram-drop-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=20_000_000,
        bandwidth_hz=20_000_000,
        receivers=(0,),
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        sample_count=20,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=11,
        refill_queue_capacity=8,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    # Production V4 fixes these values at 1,048,576 and 239. A tiny constructed
    # instance exercises the same coordinator state machine without a 1 GiB fixture.
    request = DirectAsyncRamDropRequestV4.model_construct(
        schema_version=4,
        mode="direct_async_ram_drop",
        frame_samples=4,
        maximum_segment_frames=2,
        target_frames=5,
        receiver_count=1,
        requested_device_samples=20,
        requested_ram_bytes=134_217_728,
        drop_backlog_on_overrun=True,
    )
    monkeypatch.setattr(coordinator_module, "_device_buffer_request", lambda *_: request)
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1024,
        ),
    )
    radio = FakeRadioSource("radio-a")

    result = coordinator.capture_once(
        plan,
        {"radio-a": radio},
        session_id="bounded-direct-ram-drop-clean",
    )

    assert result.state is CaptureState.COMMITTED
    assert radio.lifecycle.count("begin_metadata_capture:4:11") == 3
    assert radio.lifecycle.count("reopen_configured:exact") == 2
    assert result.bundle is not None
    first = next(coordinator.store.reader(result.bundle, "stream-0").iter_timeline_metadata())
    payload = first.hardware_metadata[DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V4]
    assert payload["schema_version"] == 4
    assert payload["segment_count"] == 3
    assert len(payload["segment_statuses"]) == 3
    assert [status["state"] for status in payload["segment_statuses"]] == [
        "complete",
        "complete",
        "complete",
    ]
    assert payload["upstream_stream_generations"] == [
        "fake-generation-1",
        "fake-generation-2",
        "fake-generation-3",
    ]
    assert DIRECT_ASYNC_RAM_DROP_EVIDENCE_KEY_V3 not in first.hardware_metadata
    coordinator.store.verify(result.bundle.session_id)


def test_bounded_ram_drop_rejects_identity_change_during_transport_reopen(tmp_path, monkeypatch):
    profile = CaptureProfileV2(
        name="tiny-bounded-direct-ram-drop-identity-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=20_000_000,
        bandwidth_hz=20_000_000,
        receivers=(0,),
        gains=(ReceiverGainV1(receiver_id=0, gain_db=30),),
        sample_count=12,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        kernel_buffers=11,
        refill_queue_capacity=8,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=("TEST",),
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ["radio-a"],
        source_type=SourceType.TEST,
    )
    request = DirectAsyncRamDropRequestV4.model_construct(
        schema_version=4,
        mode="direct_async_ram_drop",
        frame_samples=4,
        maximum_segment_frames=2,
        target_frames=3,
        receiver_count=1,
        requested_device_samples=12,
        requested_ram_bytes=134_217_728,
        drop_backlog_on_overrun=True,
    )
    monkeypatch.setattr(coordinator_module, "_device_buffer_request", lambda *_: request)
    coordinator = AcquisitionCoordinator(
        RecordingStore(tmp_path / "bulk"),
        config=AcquisitionConfig(safety_reserve_bytes=0),
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=1024,
        ),
    )

    class ChangedIdentityRadio(FakeRadioSource):
        def reopen_configured(self, settings, *, exact_readback):
            actual = super().reopen_configured(settings, exact_readback=exact_readback)
            self._identity = self.identity.model_copy(update={"serial": "different-radio"})
            return actual

    result = coordinator.capture_once(
        plan,
        {"radio-a": ChangedIdentityRadio("radio-a")},
        session_id="bounded-direct-ram-drop-identity-change",
    )

    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert any("changed radio identity" in error for error in result.errors)


@pytest.mark.parametrize("gap_block", [0, 1])
def test_ring_prefix_failure_is_never_published(tmp_path, monkeypatch, gap_block):
    coordinator, plan, _ = _setup(tmp_path, monkeypatch)
    # First-frame overflow is authoritative evidence even without a prior counter.
    radio = FakeRadioSource(
        "radio-a", gaps_before_blocks=({1: 4} if gap_block else {}), overflow_blocks={gap_block}
    )
    result = coordinator.capture_once(plan, {"radio-a": radio}, session_id="ring-bad-prefix")
    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert any("protected prefix" in error for error in result.errors)


def test_ring_status_failure_preserves_raw_stage(tmp_path, monkeypatch):
    coordinator, plan, _ = _setup(tmp_path, monkeypatch)

    class BadStatusRadio(FakeRadioSource):
        def ddr_ring_status(self):
            return super().ddr_ring_status().model_copy(update={"error_code": 5})

    result = coordinator.capture_once(
        plan, {"radio-a": BadStatusRadio("radio-a")}, session_id="ring-bad-status"
    )
    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert (
        coordinator.store.spool_root / "ring-bad-status.partial" / "raw-stage-stream-0" / "iq.ci16"
    ).is_file()
    assert (
        coordinator.store.spool_root / "ring-bad-status.partial" / "capture-failure-stream-0.json"
    ).is_file()


def test_raw_stage_compression_failure_remains_unpublished(tmp_path, monkeypatch):
    coordinator, plan, _ = _setup(tmp_path, monkeypatch)

    def fail(self, block):
        raise OSError("injected compression failure")

    monkeypatch.setattr(DeviceAxisStreamBundleWriter, "append", fail)
    result = coordinator.capture_once(
        plan, {"radio-a": FakeRadioSource("radio-a")}, session_id="ring-compress-fail"
    )
    assert result.state is CaptureState.FAILED
    assert result.bundle is None
    assert any("injected compression failure" in error for error in result.errors)
