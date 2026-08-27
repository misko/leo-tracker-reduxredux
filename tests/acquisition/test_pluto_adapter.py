from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.contracts.radio import IqBlockMetadataV2, RadioSettingsV1, ReceiverGainV1
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
        self.metadata_abi = 1
        self.index = 0
        self.closed = False

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
            metadata_abi=1,
            metadata_flags=5,
            overflow_observed=False,
            sample_time_realtime_start_ns=10_000 + self.index,
            sample_time_realtime_end_ns=20_000 + self.index,
            sample_time_monotonic_start_ns=30_000 + self.index,
            sample_time_monotonic_end_ns=40_000 + self.index,
            sample_time_uncertainty_ns=7,
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

    def reset_receive_buffer(self) -> None:
        self.reset_count += 1

    def begin_metadata_capture(self, sample_count: int, *, kernel_buffers: int):
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
    assert expected_metadata_abis == [1]
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

    assert isinstance(first.metadata, IqBlockMetadataV2)
    assert first.metadata.device_sample_counter == 100
    assert first.metadata.source_sequence == 0
    assert first.metadata.stream_generation == "generation-77"
    assert first.metadata.metadata_abi_version == 1
    assert first.metadata.metadata_flags == 5
    assert first.metadata.kernel_buffers == 8
    assert first.metadata.continuity is ContinuityStatus.CONTIGUOUS
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
