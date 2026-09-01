from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.contracts.device_buffer import (
    DeviceBufferRequestV1,
    DirectAsyncRamDropRequestV2,
    DirectAsyncRamDropRequestV3,
    DirectAsyncRamDropRequestV4,
    DirectAsyncRamStatusV2,
    DirectAsyncRequestV1,
)
from leo.contracts.gain_control import GainControllerMode, GainControllerPolicyV1
from leo.contracts.radio import IqBlockMetadataV3, RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import ContinuityStatus, GainMode, RadioTransport
from leo.radio.pluto_adapter import PlutoAdapterError, PlutoIioRadioSource


class StubDevice:
    def __init__(self, uri: str, *, serial: str, radio_id: str) -> None:
        self.constructor_args = (uri, serial, radio_id)
        self.closed = False
        self.identity = SimpleNamespace(
            radio_id=radio_id,
            serial=serial,
            uri=uri,
            transport="iio_ip",
            model="Stub Pluto+",
            firmware_version="stub-fw",
        )
        self.capabilities = SimpleNamespace(
            receiver_channels=(0, 1),
            minimum_sample_rate_hz=520_833,
            maximum_sample_rate_hz=30_720_000,
        )
        self.settings: Any = None

    def open(self) -> None:
        pass

    def apply_settings(self, settings):
        self.settings = settings
        return settings

    def read_settings(self):
        return self.settings

    def read_block(self, sample_count: int):
        receivers = len(self.settings.channels)
        values = np.empty((receivers, sample_count), dtype=np.complex64)
        for receiver in range(receivers):
            values[receiver] = (
                np.arange(sample_count, dtype=np.float32)
                + receiver * 100
                + 1j * (np.arange(sample_count, dtype=np.float32) * -1)
            )
        return SimpleNamespace(utc_ns=1234, samples=values)

    def close(self) -> None:
        self.closed = True


class StubMetadataSession:
    def __init__(self, device: StubDevice, sample_count: int, kernel_buffers: int) -> None:
        self.device = device
        self.sample_count = sample_count
        self.kernel_buffers = kernel_buffers
        self.metadata_abi = 3
        self.index = 0
        self.closed = False
        self.tandem_state_name = "ARMED_HOLD"
        self.tandem_fault_flags = 0

    def read_block(self):
        samples = self.device.read_block(self.sample_count).samples
        starts = (100, 108)
        result = SimpleNamespace(
            utc_ns=1234,
            samples=samples,
            sample_count=self.sample_count,
            stream_id=77,
            stream_generation="generation-77",
            buffer_sequence=(0, 2)[self.index],
            first_sample_sequence=starts[self.index],
            metadata_abi=3,
            metadata_flags=5,
            overflow_observed=False,
            sample_time_realtime_start_ns=10_000 + self.index,
            sample_time_realtime_end_ns=20_000 + self.index,
            sample_time_monotonic_start_ns=30_000 + self.index,
            sample_time_monotonic_end_ns=40_000 + self.index,
            sample_time_uncertainty_ns=7,
            tandem_metadata=SimpleNamespace(
                tandem_state=SimpleNamespace(name=self.tandem_state_name),
                tandem_fault_flags=self.tandem_fault_flags,
                gain_events=(),
                ownership_epoch=9,
                tandem_transition_count=0,
                gain_table_id=2,
                threshold_provenance=0x30313A14,
                minimum_gain_db=0,
                maximum_gain_db=62,
                initial_gain_db=30,
                minimum_gain_index=0,
                maximum_gain_index=76,
                rx1_gain_index=30,
                rx2_gain_index=30,
                ad9361_temperature_mdeg_c=43_000,
            ),
        )
        self.index += 1
        return result

    def close(self) -> None:
        self.closed = True


class StubMetadataDevice(StubDevice):
    def __init__(self, uri: str, *, serial: str, radio_id: str) -> None:
        super().__init__(uri, serial=serial, radio_id=radio_id)
        self.capabilities.supports_device_sample_counter = True
        self.capabilities.supports_continuity_sequence = True
        self.reset_count = 0
        self.session: StubMetadataSession | None = None
        self.tandem_request = None

    def reset_receive_buffer(self) -> None:
        self.reset_count += 1

    def begin_metadata_capture(self, sample_count: int, *, kernel_buffers: int, tandem_request):
        self.tandem_request = tandem_request
        self.session = StubMetadataSession(self, sample_count, kernel_buffers)
        return self.session


def _settings(
    receiver_ids: tuple[int, ...],
    *,
    sample_rate_hz: int = 2_500_000,
) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=2_500_000,
        receiver_ids=receiver_ids,
        gain_mode=GainMode.MANUAL,
        gains=tuple(
            ReceiverGainV1(receiver_id=receiver, gain_db=30.0) for receiver in receiver_ids
        ),
    )


def _upstream_settings(**kwargs):
    return SimpleNamespace(**kwargs)


@pytest.mark.parametrize("receiver_ids", [(0,), (0, 1)])
def test_adapter_maps_one_or_two_rx_without_leaking_upstream_models(receiver_ids) -> None:
    constructed: list[StubDevice] = []
    expected_metadata_abis: list[int] = []

    def factory(
        uri: str,
        *,
        serial: str,
        radio_id: str,
        expected_metadata_abi: int,
    ) -> StubDevice:
        expected_metadata_abis.append(expected_metadata_abi)
        device = StubDevice(uri, serial=serial, radio_id=radio_id)
        constructed.append(device)
        return device

    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=factory,
        settings_factory=_upstream_settings,
        utc_ns=iter((100, 200)).__next__,
        monotonic_ns=iter((1_000, 2_000)).__next__,
    )

    identity = adapter.open()
    actual = adapter.configure(_settings(receiver_ids))
    block = adapter.read_block(4)

    assert identity.radio_id == "radio-a"
    assert identity.serial == "serial-123"
    assert identity.transport is RadioTransport.IIO_IP
    assert constructed[0].constructor_args == (
        "ip:192.168.2.1",
        "serial-123",
        "radio-a",
    )
    assert expected_metadata_abis == [3]
    assert isinstance(actual, RadioSettingsV1)
    assert block.samples.shape == (4, len(receiver_ids), 2)
    assert block.samples.dtype == np.dtype("<i2")
    assert block.samples[3, 0].tolist() == [3, -3]
    assert block.metadata.hardware_metadata["upstream_utc_ns"] == 1234
    assert block.metadata.host_request_utc_ns.lower_ns == 100
    assert block.metadata.host_request_utc_ns.upper_ns == 200
    adapter.close()
    assert constructed[0].closed


@pytest.mark.parametrize("sample_rate_hz", (3_000_000, 5_000_000))
def test_adapter_applies_and_attests_exact_rate_modes(sample_rate_hz: int) -> None:
    device = StubDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()

    actual = adapter.configure(_settings((0, 1), sample_rate_hz=sample_rate_hz))

    assert device.settings.sample_rate_hz == float(sample_rate_hz)
    assert device.settings.bandwidth_hz == 2_500_000.0
    assert actual.sample_rate_hz == sample_rate_hz
    assert actual.bandwidth_hz == 2_500_000


def test_adapter_rejects_rate_mode_readback_coercion() -> None:
    class CoercingDevice(StubDevice):
        def apply_settings(self, settings):
            self.settings = settings
            return SimpleNamespace(**{**vars(settings), "sample_rate_hz": 2_500_000.0})

    device = CoercingDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()

    with pytest.raises(PlutoAdapterError, match="sample_rate_hz readback mismatch"):
        adapter.configure(_settings((0, 1), sample_rate_hz=3_000_000))


def test_adapter_exact_configuration_uses_bounded_ppu_lo_search() -> None:
    class QuantizedDevice(StubDevice):
        def __init__(self, uri: str, *, serial: str, radio_id: str) -> None:
            super().__init__(uri, serial=serial, radio_id=radio_id)
            self.requests: list[int] = []

        def apply_settings(self, settings):
            request = round(settings.center_frequency_hz)
            self.requests.append(request)
            desired = 1_700_000_000
            if request == desired:
                readback = desired - 2
            elif request == desired + 2:
                readback = desired
            else:
                readback = request + 100
            self.settings = settings.model_copy(update={"center_frequency_hz": float(readback)})
            return self.settings

    device = QuantizedDevice("ip:192.168.1.20", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.1.20",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
    )
    adapter.open()

    actual = adapter.configure_exact(_settings((0, 1)))

    assert actual.center_frequency_hz == 1_700_000_000
    assert device.requests == [
        1_700_000_000,
        1_700_000_001,
        1_699_999_999,
        1_700_000_002,
    ]


def test_adapter_closes_device_when_serial_attestation_disagrees() -> None:
    device = StubDevice("ip:192.168.2.1", serial="wrong", radio_id="radio-a")

    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="expected",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )

    with pytest.raises(PlutoAdapterError, match="expected"):
        adapter.open()
    assert device.closed


def test_adapter_rejects_unrepresentable_independent_manual_gains() -> None:
    device = StubDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    settings = _settings((0, 1)).model_copy(
        update={
            "gains": (
                ReceiverGainV1(receiver_id=0, gain_db=20.0),
                ReceiverGainV1(receiver_id=1, gain_db=30.0),
            )
        }
    )

    with pytest.raises(PlutoAdapterError, match="common manual gain"):
        adapter.configure(settings)


def test_adapter_applies_and_attests_slow_attack_without_manual_gain() -> None:
    device = StubDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    requested = _settings((0, 1)).model_copy(
        update={"gain_mode": GainMode.SLOW_ATTACK, "gains": ()}
    )

    actual = adapter.configure(requested)

    assert device.settings.gain_mode == "slow_attack"
    assert device.settings.gain_db is None
    assert actual.gain_mode is GainMode.SLOW_ATTACK
    assert actual.gains == ()


def test_constructor_is_lazy_and_needs_no_hardware_dependency() -> None:
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
    )

    assert adapter.identity.serial == "serial-123"
    assert adapter.identity.uri == "ip:192.168.2.1"


def test_metadata_session_maps_exact_header_and_derives_gap() -> None:
    device = StubMetadataDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    ticks = iter((100, 200, 300, 400, 500, 600, 700, 800))
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
        utc_ns=ticks.__next__,
        monotonic_ns=ticks.__next__,
    )
    adapter.open()
    adapter.reset_receive_buffer()
    adapter.configure(_settings((0, 1)))

    assert adapter.begin_metadata_capture(4, kernel_buffers=8) == 8
    first = adapter.read_block(4)
    second = adapter.read_block(4)

    assert isinstance(first.metadata, IqBlockMetadataV3)
    assert first.metadata.device_sample_counter == 100
    assert first.metadata.source_sequence == 0
    assert first.metadata.stream_generation == "generation-77"
    assert first.metadata.metadata_abi_version == 3
    assert first.metadata.metadata_flags == 5
    assert first.metadata.kernel_buffers == 8
    assert first.metadata.continuity is ContinuityStatus.CONTIGUOUS
    assert first.metadata.tandem.tandem_state == "armed_hold"
    assert first.metadata.tandem.ownership_epoch == 9
    assert device.tandem_request is not None
    assert device.tandem_request.mode.name == "HOLD"
    assert second.metadata.continuity is ContinuityStatus.GAP_BEFORE
    assert second.metadata.missing_samples_before == 4
    assert second.metadata.hardware_metadata["stream_id"] == 77
    assert second.metadata.hardware_metadata["stream_generation"] == "generation-77"
    assert second.metadata.hardware_metadata["first_sample_sequence"] == 108
    assert device.reset_count == 1
    adapter.close()
    assert device.session is not None and device.session.closed


def test_metadata_capture_fails_closed_without_capability_attestation() -> None:
    device = StubDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0, 1)))

    with pytest.raises(PlutoAdapterError, match="does not attest"):
        adapter.begin_metadata_capture(4, kernel_buffers=8)


def test_gain_controller_covers_v2_first_refill_arm_window() -> None:
    controller = GainControllerPolicyV1.create(
        GainControllerMode.TANDEM_AUTO,
        sample_count=1_048_576,
    )

    assert controller.cooldown_periods == 31


class StubRingDevice(StubMetadataDevice):
    def __init__(self):
        super().__init__("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
        self.identity.firmware_version = "v0.44-plutoplus-spf-ddr-ring-prefill-v1"
        self.ring_kwargs = None
        self.ring_capable = True
        self.admitted_bytes = 200_000_000

    def diagnostic_facts(self):
        return {
            "buffer_metadata_abi": 3,
            "buffer_ddr_ring": self.ring_capable,
            "buffer_ddr_ring_modes_raw": "finite,continuous",
            "buffer_metadata_status": True,
            "buffer_ddr_ring_max_iq_bytes": 200_000_000,
        }

    def begin_metadata_capture(self, sample_count, *, kernel_buffers, tandem_request, **kwargs):
        self.ring_kwargs = kwargs
        session = super().begin_metadata_capture(
            sample_count, kernel_buffers=kernel_buffers, tandem_request=tandem_request
        )
        session.ddr_ring_enabled = True
        session.ddr_ring_requested_bytes = kwargs["ddr_ring_bytes"]
        session.ddr_ring_admitted_bytes = self.admitted_bytes
        session.ddr_ring_capacity_frames = 50
        session.ddr_ring_capture_frames = kwargs["ddr_ring_frames"]
        session.ddr_ring_continuous = False
        return session


@pytest.mark.parametrize("failure", [None, "capability", "firmware", "admission"])
def test_ring_adapter_exact_request_and_fail_closed_readback(failure):
    device = StubRingDevice()
    if failure == "capability":
        device.ring_capable = False
    if failure == "firmware":
        device.identity.firmware_version = "v0.43-plutoplus-spf-ddr-ring-v1"
    if failure == "admission":
        device.admitted_bytes = 196_000_000
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=20_000_000))
    request = DeviceBufferRequestV1(
        requested_bytes=200_000_000,
        target_frames=400,
        frame_samples=1_000_000,
        requested_device_samples=400_000_000,
    )
    try:
        if failure:
            with pytest.raises(PlutoAdapterError):
                adapter.begin_metadata_capture(1_000_000, kernel_buffers=4, device_buffer=request)
            if failure in ("capability", "firmware"):
                assert device.ring_kwargs is None
            else:
                assert device.session.closed
        else:
            assert (
                adapter.begin_metadata_capture(1_000_000, kernel_buffers=4, device_buffer=request)
                == 4
            )
            assert device.ring_kwargs == {
                "ddr_ring_bytes": 200_000_000,
                "ddr_ring_frames": 400,
                "ddr_ring_continuous": False,
            }
    finally:
        adapter.close()


class StubDirectAsyncDevice(StubMetadataDevice):
    def __init__(self):
        super().__init__("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
        self.identity.firmware_version = "v0.46-plutoplus-spf-iq-direct-async-ring-v1"
        self.direct_capable = True
        self.direct_kwargs = None

    def diagnostic_facts(self):
        return {
            "buffer_metadata_abi": 3,
            "buffer_direct_async": self.direct_capable,
        }

    def begin_metadata_capture(self, sample_count, *, kernel_buffers, tandem_request, **kwargs):
        self.direct_kwargs = kwargs
        session = super().begin_metadata_capture(
            sample_count, kernel_buffers=kernel_buffers, tandem_request=tandem_request
        )
        session.direct_async_frames = kwargs["direct_async_frames"]
        session.direct_async_ring_extension = False
        session.ddr_ring_requested_bytes = 0
        session.ddr_ring_admitted_bytes = 0
        session.ddr_ring_capacity_frames = 0
        session.ddr_ring_capture_frames = 0
        session.ddr_ring_continuous = False
        return session


class StubRamDropDevice(StubMetadataDevice):
    def __init__(self):
        super().__init__("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
        self.identity.firmware_version = "v0.47-plutoplus-spf-iq-direct-async-v2"
        self.direct_kwargs = None

    def diagnostic_facts(self):
        return {
            "buffer_metadata_abi": 3,
            "buffer_metadata_status": True,
            "buffer_ddr_ring_max_iq_bytes": 200_000_000,
            "buffer_direct_async": True,
            "buffer_direct_async_ring": True,
            "buffer_direct_async_overrun_policies": (
                "drop-backlog",
                "preserve-backlog",
            ),
            "buffer_direct_async_default_overrun_policy": "drop-backlog",
        }

    def begin_metadata_capture(self, sample_count, *, kernel_buffers, tandem_request, **kwargs):
        self.direct_kwargs = kwargs
        session = super().begin_metadata_capture(
            sample_count, kernel_buffers=kernel_buffers, tandem_request=tandem_request
        )
        session.direct_async_frames = kwargs["direct_async_frames"]
        session.direct_async_ring_extension = True
        session.drop_backlog_on_overrun = kwargs["drop_backlog_on_overrun"]
        session.ddr_ring_requested_bytes = kwargs["ddr_ring_bytes"]
        frame_bytes = sample_count * 4
        session.ddr_ring_capacity_frames = kwargs["ddr_ring_bytes"] // frame_bytes
        session.ddr_ring_admitted_bytes = session.ddr_ring_capacity_frames * frame_bytes
        session.ddr_ring_capture_frames = kwargs["ddr_ring_frames"]
        session.ddr_ring_continuous = kwargs["ddr_ring_continuous"]
        session.ddr_ring_status = lambda: {
            "version": 1,
            "state": "complete",
            "terminal_reason": "target_complete",
            "error_code": 0,
            "requested_capacity_iq_bytes": kwargs["ddr_ring_bytes"],
            "admitted_capacity_iq_bytes": session.ddr_ring_admitted_bytes,
            "target_frames": 0,
            "produced_frames": 12,
            "consumed_frames": 7,
            "high_water_frames": 10,
            "wrap_count": 1,
            "producer_position": 12,
            "consumer_position": 7,
            "last_contiguous_sample_sequence": None,
            "first_unavailable_sample_sequence": 123,
            "failure_frame_index": None,
            "failure_sample_sequence": None,
        }
        return session


def test_ram_drop_adapter_attests_v047_policy_ram_and_status() -> None:
    device = StubRamDropDevice()
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=25_000_000))
    request = DirectAsyncRamDropRequestV2(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )
    try:
        assert (
            adapter.begin_metadata_capture(
                1_048_576,
                kernel_buffers=12,
                device_buffer=request,
                direct_async_frames=1431,
            )
            == 12
        )
        assert device.direct_kwargs == {
            "direct_async_frames": 1431,
            "ddr_ring_bytes": 200_000_000,
            "ddr_ring_frames": 0,
            "ddr_ring_continuous": False,
            "drop_backlog_on_overrun": True,
        }
        status = adapter.ddr_ring_status()
        assert isinstance(status, DirectAsyncRamStatusV2)
        assert status.produced_frames == 12
        assert status.consumed_frames == 7
    finally:
        adapter.close()


def test_qualified_ram_drop_adapter_uses_exact_128_mib_geometry() -> None:
    device = StubRamDropDevice()
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=25_000_000))
    request = DirectAsyncRamDropRequestV3(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )
    try:
        assert (
            adapter.begin_metadata_capture(
                1_048_576,
                kernel_buffers=11,
                device_buffer=request,
                direct_async_frames=1431,
            )
            == 11
        )
        assert device.direct_kwargs == {
            "direct_async_frames": 1431,
            "ddr_ring_bytes": 134_217_728,
            "ddr_ring_frames": 0,
            "ddr_ring_continuous": False,
            "drop_backlog_on_overrun": True,
        }
        status = adapter.ddr_ring_status()
        assert status.requested_capacity_iq_bytes == 134_217_728
        assert status.admitted_capacity_iq_bytes == 134_217_728
    finally:
        adapter.close()


def test_bounded_ram_drop_adapter_arms_one_64_frame_session() -> None:
    device = StubRamDropDevice()
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=25_000_000))
    request = DirectAsyncRamDropRequestV4(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )
    try:
        assert (
            adapter.begin_metadata_capture(
                1_048_576,
                kernel_buffers=11,
                device_buffer=request,
                direct_async_frames=64,
            )
            == 11
        )
        assert device.direct_kwargs == {
            "direct_async_frames": 64,
            "ddr_ring_bytes": 134_217_728,
            "ddr_ring_frames": 0,
            "ddr_ring_continuous": False,
            "drop_backlog_on_overrun": True,
        }
        assert isinstance(adapter.ddr_ring_status(), DirectAsyncRamStatusV2)
    finally:
        adapter.close()


def test_ram_drop_refill_failure_retains_terminal_firmware_status() -> None:
    device = StubRamDropDevice()
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=25_000_000))
    request = DirectAsyncRamDropRequestV4(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )
    adapter.begin_metadata_capture(
        1_048_576,
        kernel_buffers=11,
        device_buffer=request,
        direct_async_frames=64,
    )
    assert device.session is not None
    device.session.read_block = lambda: (_ for _ in ()).throw(OSError(61, "No data available"))

    try:
        with pytest.raises(PlutoAdapterError) as captured:
            adapter.read_block(1_048_576)
        message = str(captured.value)
        assert "[Errno 61] No data available" in message
        assert 'terminal_status={"admitted_capacity_iq_bytes":134217728' in message
        assert '"state":"complete"' in message
        assert '"terminal_reason":"target_complete"' in message
    finally:
        adapter.close()


def test_direct_async_adapter_exposes_device_diagnostic_facts() -> None:
    device = StubDirectAsyncDevice()
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()

    assert adapter.diagnostic_facts() == {
        "buffer_metadata_abi": 3,
        "buffer_direct_async": True,
    }


@pytest.mark.parametrize("failure", [None, "capability", "firmware", "admission"])
def test_direct_async_adapter_exact_segment_and_fail_closed_readback(failure):
    device = StubDirectAsyncDevice()
    if failure == "capability":
        device.direct_capable = False
    if failure == "firmware":
        device.identity.firmware_version = "v0.44-plutoplus-spf-ddr-ring-prefill-v1"
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.configure(_settings((0,), sample_rate_hz=25_000_000))
    request = DirectAsyncRequestV1(
        target_frames=1431,
        requested_device_samples=1_500_000_000,
    )
    try:
        if failure == "admission":
            original = device.begin_metadata_capture

            def wrong_admission(*args, **kwargs):
                session = original(*args, **kwargs)
                session.direct_async_frames -= 1
                return session

            device.begin_metadata_capture = wrong_admission  # type: ignore[method-assign]
        if failure:
            with pytest.raises(PlutoAdapterError):
                adapter.begin_metadata_capture(
                    1_048_576,
                    kernel_buffers=15,
                    device_buffer=request,
                    direct_async_frames=64,
                )
            if failure in ("capability", "firmware"):
                assert device.direct_kwargs is None
            else:
                assert device.session is not None and device.session.closed
        else:
            assert (
                adapter.begin_metadata_capture(
                    1_048_576,
                    kernel_buffers=15,
                    device_buffer=request,
                    direct_async_frames=64,
                )
                == 15
            )
            assert device.direct_kwargs == {"direct_async_frames": 64}
    finally:
        adapter.close()


def test_metadata_session_maps_explicit_auto_controller_and_rejects_faults() -> None:
    device = StubMetadataDevice("ip:192.168.2.1", serial="serial-123", radio_id="radio-a")
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
        radio_id="radio-a",
        device_factory=lambda *_args, **_kwargs: device,
        settings_factory=_upstream_settings,
    )
    adapter.open()
    adapter.reset_receive_buffer()
    adapter.configure(_settings((0, 1)))
    controller = GainControllerPolicyV1.create(
        GainControllerMode.TANDEM_AUTO,
        sample_count=4,
    )

    adapter.begin_metadata_capture(4, kernel_buffers=8, gain_controller=controller)
    assert device.session is not None
    device.session.tandem_state_name = "ARMED_AUTO"
    block = adapter.read_block(4)

    assert block.metadata.tandem.mode is GainControllerMode.TANDEM_AUTO
    assert device.tandem_request.mode.name == "AUTO"
    device.session.tandem_fault_flags = 1
    with pytest.raises(PlutoAdapterError, match="fault"):
        adapter.read_block(4)
