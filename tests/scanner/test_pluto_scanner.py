from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import leo.radio.pluto_scanner as scanner_module
from leo.radio.pluto_scanner import PlutoScannerError, PlutoSequentialScanRadio
from leo.scanner import ScannerConfiguration, current_low_band_targets


class RxDevice:
    def __init__(self) -> None:
        self.kernel_buffers_count = 4
        self.writes: list[int] = []

    def set_kernel_buffers_count(self, count):
        self.writes.append(count)
        self.kernel_buffers_count = count
        return 0


class StubPluto:
    def __init__(self) -> None:
        self.ctx = SimpleNamespace(destroy=lambda: None)
        self._rxadc = RxDevice()
        self.rx_enabled_channels: list[int] = []
        self.sample_rate = 0
        self.rx_rf_bandwidth = 0
        self.rx_buffer_size = 0
        self.rx_lo = 0
        self.destroy_count = 0
        self.attribute_writes: list[tuple[str, object]] = []

    def __setattr__(self, name, value):
        if name not in {"attribute_writes"} and "attribute_writes" in self.__dict__:
            self.attribute_writes.append((name, value))
        super().__setattr__(name, value)

    def rx_destroy_buffer(self):
        self.destroy_count += 1

    def rx(self):
        return np.vstack(
            (
                np.arange(self.rx_buffer_size, dtype=np.float32),
                np.arange(self.rx_buffer_size, dtype=np.float32) + 1j,
            )
        )


class StubAdi:
    def __init__(self, device) -> None:
        self.device = device

    def ad9361(self, *, uri):
        assert uri == "ip:192.168.1.20"
        return self.device


def test_pluto_scanner_configures_invariants_once_and_retunes_only_lo(monkeypatch) -> None:
    device = StubPluto()
    monkeypatch.setattr(scanner_module, "_context_facts", lambda _context: {"serial": "serial"})
    radio = PlutoSequentialScanRadio(
        "192.168.1.20",
        expected_serial="serial",
        adi_module=StubAdi(device),
    )
    configuration = ScannerConfiguration(targets=current_low_band_targets())

    radio.open()
    radio.configure_once(configuration)
    invariant_writes = list(device.attribute_writes)
    block = radio.tune_and_read(959_687_500, 200_000)
    second = radio.tune_and_read(1_190_312_500, 200_000)

    assert device._rxadc.writes == [1]
    assert block.samples.shape == (200_000, 2)
    assert second.actual_if_center_hz == 1_190_312_500
    later = device.attribute_writes[len(invariant_writes) :]
    assert [name for name, _value in later] == ["rx_lo", "rx_lo"]
    assert device.destroy_count == 2
    radio.close()


def test_pluto_scanner_refuses_serial_mismatch(monkeypatch) -> None:
    device = StubPluto()
    monkeypatch.setattr(scanner_module, "_context_facts", lambda _context: {"serial": "wrong"})
    radio = PlutoSequentialScanRadio(
        "192.168.1.20",
        expected_serial="expected",
        adi_module=StubAdi(device),
    )

    with pytest.raises(PlutoScannerError, match="expected"):
        radio.open()
