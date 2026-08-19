from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode, RadioTransport
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


def _settings(receiver_ids: tuple[int, ...]) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
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

    def factory(uri: str, *, serial: str, radio_id: str) -> StubDevice:
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
    assert isinstance(actual, RadioSettingsV1)
    assert block.samples.shape == (4, len(receiver_ids), 2)
    assert block.samples.dtype == np.dtype("<i2")
    assert block.samples[3, 0].tolist() == [3, -3]
    assert block.metadata.hardware_metadata["upstream_utc_ns"] == 1234
    assert block.metadata.host_request_utc_ns.lower_ns == 100
    assert block.metadata.host_request_utc_ns.upper_ns == 200
    adapter.close()
    assert constructed[0].closed


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


def test_constructor_is_lazy_and_needs_no_hardware_dependency() -> None:
    adapter = PlutoIioRadioSource(
        "192.168.2.1",
        expected_serial="serial-123",
    )

    assert adapter.identity.serial == "serial-123"
    assert adapter.identity.uri == "ip:192.168.2.1"
