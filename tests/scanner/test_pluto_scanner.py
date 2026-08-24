from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from leo.radio.pluto_scanner import PlutoScannerError, PlutoSequentialScanRadio
from leo.scanner import ScannerConfigurationV2, current_low_band_targets


class MetadataSession:
    def __init__(
        self,
        device: StubDevice,
        sample_count: int,
        kernel_buffers: int,
        *,
        readback: int | None = None,
        missing: int = 0,
        overflow: bool = False,
    ) -> None:
        self.device = device
        self.sample_count = sample_count
        self.kernel_buffers = kernel_buffers if readback is None else readback
        self.missing = missing
        self.overflow = overflow

    def __enter__(self):
        self.device.events.append(("session-enter", self.kernel_buffers))
        return self

    def read_block(self):
        self.device.events.append(("read", self.sample_count))
        episode = self.device.session_count
        samples = np.vstack(
            (
                np.arange(self.sample_count, dtype=np.float32),
                np.arange(self.sample_count, dtype=np.float32) + 1j,
            )
        ).astype(np.complex64)
        return SimpleNamespace(
            samples=samples,
            metadata_abi=self.device.metadata_abi,
            stream_id=100 + episode,
            stream_generation=100 + episode,
            buffer_sequence=0,
            first_sample_sequence=1_000_000 * episode,
            metadata_flags=0x200013,
            missing_samples_before=self.missing,
            overflow_observed=self.overflow,
            sample_time_realtime_start_ns=1_700_000_000_000_000_000 + episode * 1_000_000,
            sample_time_realtime_end_ns=1_700_000_000_120_000_000 + episode * 1_000_000,
            sample_time_monotonic_start_ns=1_000_000_000 + episode * 1_000_000,
            sample_time_monotonic_end_ns=1_120_000_000 + episode * 1_000_000,
            sample_time_uncertainty_ns=25_000,
        )

    def __exit__(self, *_args):
        self.device.events.append("session-close")


class StubDevice:
    def __init__(
        self,
        *,
        serial: str = "serial",
        metadata_abi: int | None = 1,
        kernel_readback: int | None = None,
        missing: int = 0,
        overflow: bool = False,
        tune_offset_hz: int = 0,
    ) -> None:
        self.serial = serial
        self.metadata_abi = metadata_abi
        self.kernel_readback = kernel_readback
        self.missing = missing
        self.overflow = overflow
        self.tune_offset_hz = tune_offset_hz
        self.events: list[object] = []
        self.factory_arguments: tuple[tuple[object, ...], dict[str, object]] | None = None
        self.session_count = 0

    @property
    def identity(self):
        return SimpleNamespace(serial=self.serial)

    def open(self):
        self.events.append("open")

    def diagnostic_facts(self):
        self.events.append("facts")
        return {"buffer_metadata_abi": self.metadata_abi}

    def apply_settings(self, settings):
        self.events.append(("apply", settings.center_frequency_hz))
        return settings

    def reset_receive_buffer(self):
        self.events.append("reset")

    def tune_center_frequency(self, value):
        self.events.append(("tune", round(value)))
        return value + self.tune_offset_hz

    def begin_metadata_capture(self, sample_count, *, kernel_buffers):
        self.session_count += 1
        self.events.append(("begin", sample_count, kernel_buffers))
        return MetadataSession(
            self,
            sample_count,
            kernel_buffers,
            readback=self.kernel_readback,
            missing=self.missing,
            overflow=self.overflow,
        )

    def close(self):
        self.events.append("close")


def settings_factory(**values):
    return SimpleNamespace(**values)


def radio_for(device: StubDevice, sleeps: list[float]) -> PlutoSequentialScanRadio:
    def device_factory(*args, **kwargs):
        device.factory_arguments = (args, kwargs)
        return device

    return PlutoSequentialScanRadio(
        "192.168.1.20",
        expected_serial="serial",
        device_factory=device_factory,
        settings_factory=settings_factory,
        sleep=sleeps.append,
        utc_ns=iter((10, 20, 30, 40)).__next__,
        monotonic_ns=iter((100, 200, 300, 400)).__next__,
    )


def test_pluto_scanner_resets_retunes_settles_and_arms_fresh_k8_buffer_per_target() -> None:
    device = StubDevice(metadata_abi=1)
    sleeps: list[float] = []
    radio = radio_for(device, sleeps)
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())

    radio.open()
    radio.configure_once(configuration)
    first = radio.tune_and_read(959_687_500, configuration.dwell_samples)
    second = radio.tune_and_read(1_190_312_500, configuration.dwell_samples)
    radio.close()

    assert first.metadata_abi_version == 1
    assert device.factory_arguments == (
        ("ip:192.168.1.20",),
        {
            "serial": "serial",
            "radio_id": "scanner-pluto",
            "expected_metadata_abi": 1,
        },
    )
    assert first.kernel_buffers_requested == first.kernel_buffers_readback == 8
    assert first.reset_episode == 1
    assert first.first_sample_sequence == 1_000_000
    assert first.last_sample_sequence_exclusive == 1_300_000
    assert second.stream_id != first.stream_id
    assert second.reset_episode == 2
    assert sleeps == [0.00025, 0.00025]
    assert device.events == [
        "open",
        "facts",
        ("apply", 959_687_500.0),
        "reset",
        "reset",
        ("tune", 959_687_500),
        ("begin", 300_000, 8),
        ("session-enter", 8),
        ("read", 300_000),
        "session-close",
        "reset",
        ("tune", 1_190_312_500),
        ("begin", 300_000, 8),
        ("session-enter", 8),
        ("read", 300_000),
        "session-close",
        "reset",
        "close",
    ]


@pytest.mark.parametrize("metadata_abi", [None, 0, 2, 3])
def test_pluto_scanner_fails_closed_without_supported_metadata_abi(metadata_abi) -> None:
    device = StubDevice(metadata_abi=metadata_abi)
    radio = radio_for(device, [])

    with pytest.raises(PlutoScannerError, match="metadata ABI"):
        radio.open()

    assert device.events[-1] == "close"


def test_pluto_scanner_refuses_serial_mismatch() -> None:
    device = StubDevice(serial="wrong")
    radio = radio_for(device, [])

    with pytest.raises(PlutoScannerError, match="expected 'serial'"):
        radio.open()

    assert device.events[-1] == "close"


def test_pluto_scanner_rejects_kernel_buffer_readback_mismatch() -> None:
    device = StubDevice(kernel_readback=4)
    radio = radio_for(device, [])
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())
    radio.open()
    radio.configure_once(configuration)

    with pytest.raises(PlutoScannerError, match="readback is 4, expected 8"):
        radio.tune_and_read(959_687_500, configuration.dwell_samples)


@pytest.mark.parametrize(
    ("device", "message"),
    [
        (StubDevice(missing=131_072), "missing samples"),
        (StubDevice(overflow=True), "RX overflow"),
    ],
)
def test_pluto_scanner_rejects_discontinuous_or_overflowed_frame(device, message) -> None:
    radio = radio_for(device, [])
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())
    radio.open()
    radio.configure_once(configuration)

    with pytest.raises(PlutoScannerError, match=message):
        radio.tune_and_read(959_687_500, configuration.dwell_samples)


def test_pluto_scanner_accepts_bounded_lo_quantization() -> None:
    device = StubDevice(tune_offset_hz=-2)
    radio = radio_for(device, [])
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())
    radio.open()
    radio.configure_once(configuration)

    block = radio.tune_and_read(959_687_500, configuration.dwell_samples)

    assert block.actual_if_center_hz == 959_687_498
