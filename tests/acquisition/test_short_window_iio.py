"""Owned provider tests; no radio or optional PPU dependency is required."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from leo.acquisition.short_window_iio import (
    IioShortWindowSource,
    ShortWindowIioError,
    Tx2ToneOwner,
    complex_block_to_ci16,
)
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowConfiguration,
    ShortWindowTarget,
    ValidityAuthority,
)


class FakePpu:
    def __init__(self) -> None:
        self.identity = SimpleNamespace(serial="dev-serial", uri="ip:192.168.1.15")
        self.calls: list[tuple] = []
        self.active = None
        self.frequency = 2_400_000_000
        self.original = object()
        self.slots = {slot: (slot,) * 16 for slot in range(8)}
        self.original_slots = dict(self.slots)
        self.fail_restore = False
        self.fail_read = False
        self.corrupt_active = False

    def open(self):
        self.calls.append(("open",))

    def close(self):
        self.calls.append(("close",))

    def reset_receive_buffer(self):
        self.calls.append(("reset",))

    def read_receiver_settings_readback(self):
        return self.original

    def read_active_rx_fastlock_profile(self):
        return 7 if self.corrupt_active else self.active

    def save_rx_fastlock_profile(self, slot):
        return self.slots[slot]

    def configure_source_locked_receiver_geometry(self, **values):
        self.calls.append(("geometry", values))

    def configure_kernel_buffers(self, count):
        self.calls.append(("kernel_buffers", count))
        return count

    def write_center_frequency_bufferless(self, frequency):
        self.frequency = frequency
        self.calls.append(("ordinary_tune", frequency))

    def read_center_frequency(self):
        return self.frequency

    def store_rx_fastlock_profile(self, slot):
        self.slots[slot] = (100 + slot,) * 16
        return self.slots[slot]

    def recall_rx_fastlock_profile(self, slot):
        self.active = slot
        self.calls.append(("recall", slot))

    def read_device_sample_counter_low32(self):
        return 123456

    def read_block(self, count):
        if self.fail_read:
            raise RuntimeError("injected USB timeout")
        self.calls.append(("read", count))
        return SimpleNamespace(samples=np.full((2, count), 123 - 99j, dtype=np.complex64))

    def load_rx_fastlock_profile(self, slot, registers):
        self.slots[slot] = registers
        self.calls.append(("load", slot))

    def restore_receiver_settings_readback(self, snapshot):
        assert snapshot is self.original
        self.calls.append(("restore",))
        if self.fail_restore:
            raise RuntimeError("injected restoration error")

    def mute_transmit(self):
        self.calls.append(("mute",))


def configuration():
    return ShortWindowConfiguration(
        targets=(
            ShortWindowTarget("lower", 959_687_500),
            ShortWindowTarget("upper", 1_190_312_500),
        )
    )


def source(radio):
    return IioShortWindowSource(
        "ip:192.168.1.15",
        expected_serial="dev-serial",
        guard_ms=0,
        profile_settle_ms=0,
        radio_factory=lambda uri, serial: radio,
    )


def test_capture_uses_real_profile_recall_preserves_codes_and_truthful_authority():
    radio = FakePpu()
    provider = source(radio)
    config = configuration()
    provider.configure_once(config)
    ordinary_count = sum(call[0] == "ordinary_tune" for call in radio.calls)
    window = provider.capture(config.targets[0], config.window_samples)
    assert window.samples.shape == (50_000, 2, 2)
    np.testing.assert_array_equal(window.samples[0], [[123, -99], [123, -99]])
    assert not window.samples.flags.writeable
    assert window.counter_authority is CounterAuthority.SOFTWARE_DELIVERY_ORDINAL
    assert window.validity_authority is ValidityAuthority.DIAGNOSTIC_HOST_GUARD
    assert window.sample_start_utc_ns is None
    assert window.generation == 1
    assert window.sample_start == 0
    assert not window.contiguous_with_previous
    assert ("recall", 0) in radio.calls
    assert sum(call[0] == "ordinary_tune" for call in radio.calls) == ordinary_count
    receipt = json.loads(window.retune_receipt)
    assert receipt["counter_bracket_authority"] == "register_reads_only_no_iq_boundary"
    provider.close()
    assert radio.slots == radio.original_slots
    assert radio.calls[-1] == ("close",)
    assert provider.restoration_receipt["receiver_settings_restored"]
    assert not provider.restoration_receipt["fastlock_initialized_flags_restorable"]


def test_serial_mismatch_closes_before_configuration():
    radio = FakePpu()
    radio.identity.serial = "other"
    provider = source(radio)
    with pytest.raises(ShortWindowIioError, match="URI/serial"):
        provider.configure_once(configuration())
    assert not any(call[0] == "geometry" for call in radio.calls)
    assert radio.calls[-1] == ("close",)


def test_configuration_once_and_exact_window_only():
    radio = FakePpu()
    provider = source(radio)
    config = configuration()
    provider.configure_once(config)
    provider.configure_once(config)
    assert sum(call[0] == "geometry" for call in radio.calls) == 1
    with pytest.raises(ValueError, match="50,000"):
        provider.capture(config.targets[0], 49_999)
    with pytest.raises(ValueError, match="outside"):
        provider.capture(ShortWindowTarget("unknown", 915_000_000), 50_000)
    provider.close()


def test_restore_failure_does_not_prevent_tx_off_or_context_close():
    radio = FakePpu()
    provider = source(radio)
    provider.configure_once(configuration())
    radio.fail_restore = True
    with pytest.raises(ShortWindowIioError, match="restoration error"):
        provider.close()
    assert ("mute",) in radio.calls
    assert radio.calls[-1] == ("close",)
    assert not provider.restoration_receipt["receiver_settings_restored"]
    provider.close()


def test_cancelled_capture_never_reads_and_always_allows_restore():
    radio = FakePpu()
    provider = source(radio)
    provider.configure_once(configuration())
    provider.cancel()
    with pytest.raises(ShortWindowIioError, match="cancelled"):
        provider.capture(configuration().targets[0], 50_000)
    assert not any(call[0] == "read" for call in radio.calls)
    provider.close()


def test_failed_refill_or_unacknowledged_recall_never_produces_window():
    radio = FakePpu()
    provider = source(radio)
    provider.configure_once(configuration())
    radio.fail_read = True
    with pytest.raises(RuntimeError, match="USB timeout"):
        provider.capture(configuration().targets[0], 50_000)
    radio.fail_read = False
    radio.corrupt_active = True
    with pytest.raises(ShortWindowIioError, match="acknowledged"):
        provider.capture(configuration().targets[0], 50_000)
    provider.close()


@pytest.mark.parametrize("value", [32768 + 0j, -32769 + 0j, 0.5 + 0j, np.nan + 0j])
def test_ci16_conversion_refuses_saturation_rounding_or_nonfinite(value):
    with pytest.raises(ShortWindowIioError):
        complex_block_to_ci16(np.full((2, 1), value), 2, 1)


@pytest.mark.parametrize("uri", ["usb:", "ip:", "", "ip:192.168.1.15 "])
def test_implicit_radio_selection_is_rejected(uri):
    with pytest.raises(ValueError, match="explicit"):
        IioShortWindowSource(uri, expected_serial="dev-serial")


class FakeTx:
    def __init__(self):
        self.powerdown = SimpleNamespace(value="1")
        self.ctx = SimpleNamespace(
            attrs={"hw_serial": "dev-serial"},
            set_timeout=lambda value: None,
            find_device=lambda name: SimpleNamespace(
                find_channel=lambda name, output: SimpleNamespace(
                    attrs={"powerdown": self.powerdown}
                )
            ),
        )
        self.tx_lo = 2_450_000_000
        self.tx_hardwaregain_chan0 = -80
        self.tx_hardwaregain_chan1 = -80
        self.dds_frequencies = [0] * 8
        self.dds_phases = [0] * 8
        self.dds_scales = [0] * 8
        self.dds_enabled = [0] * 8
        self.tone_channels = []

    def disable_dds(self):
        self.dds_enabled = [0] * 8

    def dds_single_tone(self, frequency, scale, channel):
        self.tone_channels.append(channel)
        self.dds_frequencies = [frequency] * 8
        self.dds_phases = [90_000] * 8
        self.dds_scales = [scale if index in (4, 6) else 0 for index in range(8)]
        self.dds_enabled = [1] * 8


def test_tx2_owner_has_bounded_gain_keeps_tx1_attenuated_and_restores():
    radio = FakeTx()
    owner = Tx2ToneOwner(
        "ip:192.168.1.15",
        "dev-serial",
        maximum_seconds=2,
        adi_module=SimpleNamespace(ad9361=lambda uri: radio),
    )
    owner.open()
    owner.start(959_687_500, gain_db=-60)
    assert radio.tone_channels == [1]
    assert radio.tx_hardwaregain_chan0 == -80
    assert radio.tx_hardwaregain_chan1 == -60
    assert radio.powerdown.value == "0"
    owner.close()
    assert radio.dds_scales == [0] * 8
    assert radio.tx_hardwaregain_chan0 == radio.tx_hardwaregain_chan1 == -80
    assert radio.powerdown.value == "1"
    assert radio.tx_lo == 2_450_000_000
    assert owner.restoration_receipt["tx_restored"]


def test_tx_watchdog_mutes_even_when_capture_is_not_returning():
    radio = FakeTx()
    owner = Tx2ToneOwner(
        "ip:192.168.1.15",
        "dev-serial",
        maximum_seconds=0.02,
        adi_module=SimpleNamespace(ad9361=lambda uri: radio),
    )
    owner.open()
    owner.start(959_687_500)
    owner._watchdog.join(timeout=1)
    assert radio.dds_scales == [0] * 8
    assert radio.powerdown.value == "1"
    with pytest.raises(ShortWindowIioError, match="expired"):
        owner.start(959_687_500)
    owner.close()


def test_tx_owner_rejects_preexisting_transmit_without_mutating_it():
    radio = FakeTx()
    radio.dds_scales = [0.2] * 8
    owner = Tx2ToneOwner(
        "ip:192.168.1.15",
        "dev-serial",
        maximum_seconds=2,
        adi_module=SimpleNamespace(ad9361=lambda uri: radio),
    )
    with pytest.raises(ShortWindowIioError, match="initially"):
        owner.open()
    assert radio.dds_scales == [0.2] * 8
    owner.close()
