"""Serial-selected PPU Fast Lock source with explicitly diagnostic IQ timing.

The public PPU port owns libiio, rate attestation, and buffer lifetime. Legacy
refills have no sample-counter support; a register bracket around recall does
not turn them into hardware-timestamped samples. Every result stays UNKNOWN
until a separate sample-domain switching qualification provides a new provider.
"""

from __future__ import annotations

import importlib
import json
import math
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowAcquisition,
    ShortWindowConfiguration,
    ShortWindowTarget,
    ValidityAuthority,
)


class ShortWindowIioError(RuntimeError):
    """A selected radio failed configuration, capture, or restoration."""


def _ppu_radio(uri: str, serial: str) -> Any:
    module = importlib.import_module("pluto_plus.hardware.iio")
    return module.IioRadioDevice(uri, serial=serial, require_idle_tandem_owner=True)


def complex_block_to_ci16(values: np.ndarray, receivers: int, count: int) -> np.ndarray:
    """Preserve ADC integer codes exactly, with no clipping or power rescaling."""

    samples = np.asarray(values)
    if samples.shape != (receivers, count) or not np.iscomplexobj(samples):
        raise ShortWindowIioError("PPU refill shape/type disagrees with exact window geometry")
    parts = np.stack((samples.real.T, samples.imag.T), axis=-1)
    if not np.all(np.isfinite(parts)) or np.any(parts < -32768) or np.any(parts > 32767):
        raise ShortWindowIioError("PPU refill contains non-finite or out-of-range CI16 codes")
    if not np.all(parts == np.rint(parts)):
        raise ShortWindowIioError("PPU refill contains noninteger ADC codes")
    return np.ascontiguousarray(parts, dtype="<i2")


class IioShortWindowSource:
    """Buffer-reset Fast Lock visits through PPU's public receive interface.

    Context I/O has PPU's finite five-second timeout. Cancellation is checked
    between calls and interrupts guard waiting; an in-flight refill returns or
    times out before cleanup. Fast Lock slot bytes are restored, but the AD9361
    driver cannot expose/restore each slot's initialized flag. This limitation
    is recorded and prevents a claim of lossless volatile-state restoration.
    """

    def __init__(
        self,
        uri: str,
        *,
        expected_serial: str,
        guard_ms: float = 20.0,
        profile_settle_ms: float = 20.0,
        radio_factory: Callable[[str, str], Any] = _ppu_radio,
        cancelled: threading.Event | None = None,
    ) -> None:
        if not re.fullmatch(r"(?:usb:\d+\.\d+\.\d+|ip:[A-Za-z0-9._:-]+)", uri):
            raise ValueError("an explicit concrete USB or IP URI is required")
        if not expected_serial.strip() or expected_serial != expected_serial.strip():
            raise ValueError("an exact nonempty expected serial is required")
        for value in (guard_ms, profile_settle_ms):
            if not math.isfinite(value) or not 0 <= value <= 1000:
                raise ValueError("host guard and profile settle must be in [0, 1000] ms")
        self.uri = uri
        self.expected_serial = expected_serial
        self.guard_ms = guard_ms
        self.profile_settle_ms = profile_settle_ms
        self._factory = radio_factory
        self._cancelled = cancelled or threading.Event()
        self._radio: Any = None
        self._configuration: ShortWindowConfiguration | None = None
        self._snapshot: Any = None
        self._active_snapshot: int | None = None
        self._profiles_snapshot: dict[int, tuple[int, ...]] = {}
        self._profiles: dict[str, tuple[int, int, tuple[int, ...]]] = {}
        self._generation = 0
        self.restoration_receipt: dict[str, Any] | None = None

    @property
    def identity(self) -> dict[str, str]:
        return {"uri": self.uri, "serial": self.expected_serial}

    def configure_once(self, configuration: ShortWindowConfiguration) -> None:
        if self._configuration is not None:
            if configuration != self._configuration:
                raise ShortWindowIioError("radio configuration is immutable within a session")
            return
        if any(receiver not in (0, 1) for receiver in configuration.receiver_ids):
            raise ValueError("PPU receivers must be physical RX1/RX2 indexes 0/1")
        radio = self._factory(self.uri, self.expected_serial)
        self._radio = radio
        try:
            self._check_cancelled()
            radio.open()
            if radio.identity.serial != self.expected_serial or radio.identity.uri != self.uri:
                raise ShortWindowIioError("opened radio URI/serial differs from selection")
            radio.reset_receive_buffer()
            self._snapshot = radio.read_receiver_settings_readback()
            self._active_snapshot = radio.read_active_rx_fastlock_profile()
            self._profiles_snapshot = {
                slot: radio.save_rx_fastlock_profile(slot)
                for slot in range(len(configuration.targets))
            }
            radio.configure_source_locked_receiver_geometry(
                sample_rate_hz=configuration.sample_rate_hz,
                rf_bandwidth_hz=configuration.sample_rate_hz,
                channels=configuration.receiver_ids,
                manual_gain_db=configuration.gain_db,
            )
            if radio.configure_kernel_buffers(1) != 1:
                raise ShortWindowIioError("PPU did not accept one RX kernel buffer")
            for slot, target in enumerate(configuration.targets):
                self._check_cancelled()
                radio.write_center_frequency_bufferless(target.if_center_hz)
                self._wait(self.profile_settle_ms)
                actual = round(radio.read_center_frequency())
                if abs(actual - target.if_center_hz) > 10:
                    raise ShortWindowIioError("profile frequency differs from requested IF")
                registers = radio.store_rx_fastlock_profile(slot)
                if len(registers) != 16:
                    raise ShortWindowIioError("Fast Lock profile readback is incomplete")
                self._profiles[target.target_id] = (slot, actual, registers)
            # Later ordinary tunes can alter a previously selected slot's ALC
            # state. Freeze and reload the bytes after all profile compilation.
            for slot, _, registers in self._profiles.values():
                radio.load_rx_fastlock_profile(slot, registers)
                if radio.save_rx_fastlock_profile(slot) != registers:
                    raise ShortWindowIioError("Fast Lock profile reload changed its bytes")
            self._configuration = configuration
        except BaseException:
            self.close()
            raise

    def capture(self, target: ShortWindowTarget, sample_count: int) -> ShortWindowAcquisition:
        configuration, radio = self._configuration, self._radio
        if configuration is None or radio is None:
            raise ShortWindowIioError("configure the selected source before capture")
        if sample_count != configuration.window_samples:
            raise ValueError("PPU visits require exactly 50,000 samples")
        if target not in configuration.targets:
            raise ValueError("target is outside the immutable profile table")
        self._check_cancelled()
        # Destroying the previous buffer avoids intentional reuse across retunes.
        # It does not prove device-side continuity or identify a valid sample.
        radio.reset_receive_buffer()
        slot, actual, registers = self._profiles[target.target_id]
        utc_before, mono_before = time.time_ns(), time.monotonic_ns()
        counter_before = radio.read_device_sample_counter_low32()
        radio.recall_rx_fastlock_profile(slot)
        counter_after = radio.read_device_sample_counter_low32()
        mono_after, utc_after = time.monotonic_ns(), time.time_ns()
        if radio.read_active_rx_fastlock_profile() != slot:
            raise ShortWindowIioError(
                "Fast Lock recall was not acknowledged by active-slot readback"
            )
        self._wait(self.guard_ms)
        listen_start = time.monotonic_ns()
        block = radio.read_block(sample_count)
        final = time.monotonic_ns()
        self._check_cancelled()
        samples = complex_block_to_ci16(
            block.samples, len(configuration.receiver_ids), sample_count
        )
        self._generation += 1
        receipt = {
            "provider": "ppu-buffer-reset-fastlock-diagnostic-v1",
            "uri": self.uri,
            "serial": self.expected_serial,
            "slot": slot,
            "profile_id": target.profile_id,
            "profile_registers": registers,
            "profile_if_readback_hz": actual,
            "frequency_authority": "profile_store_readback_and_active_slot",
            "counter_before_low32": counter_before,
            "counter_after_low32": counter_after,
            "counter_bracket_authority": "register_reads_only_no_iq_boundary",
            "buffer_reset": True,
            "discarded_sample_count_authority": "unknown_device_queue",
        }
        return ShortWindowAcquisition(
            samples=samples,
            requested_if_center_hz=target.if_center_hz,
            actual_if_center_hz=actual,
            generation=self._generation,
            sample_start=0,
            counter_authority=CounterAuthority.SOFTWARE_DELIVERY_ORDINAL,
            validity_authority=ValidityAuthority.DIAGNOSTIC_HOST_GUARD,
            host_request_utc_ns=(min(utc_before, utc_after), max(utc_before, utc_after)),
            host_request_monotonic_ns=(mono_before, mono_after),
            host_final_sample_monotonic_ns=final,
            quality_flags=("post_retune_validity_unqualified", "continuity_unobservable"),
            tune_ms=(mono_after - mono_before) / 1e6,
            listen_ms=(final - listen_start) / 1e6,
            guard_ms=self.guard_ms,
            retune_receipt=json.dumps(receipt, sort_keys=True),
        )

    def cancel(self) -> None:
        self._cancelled.set()

    def close(self) -> None:
        radio, self._radio = self._radio, None
        self._configuration = None
        if radio is None:
            return
        errors: list[str] = []
        # Each cleanup action runs even if an earlier restoration step failed.
        actions: list[Callable[[], Any]] = [radio.mute_transmit, radio.reset_receive_buffer]
        for slot, registers in self._profiles_snapshot.items():
            actions.append(
                lambda slot=slot, registers=registers: radio.load_rx_fastlock_profile(
                    slot, registers
                )
            )
        if self._snapshot is not None:
            actions.append(lambda: radio.restore_receiver_settings_readback(self._snapshot))
        if self._active_snapshot is not None:
            actions.append(lambda: radio.recall_rx_fastlock_profile(self._active_snapshot))
        actions.append(radio.close)
        for action in actions:
            try:
                action()
            except BaseException as error:
                errors.append(f"{type(error).__name__}: {error}")
        self.restoration_receipt = {
            "receiver_settings_restored": self._snapshot is not None and not errors,
            "fastlock_bytes_restored": len(self._profiles_snapshot),
            "fastlock_initialized_flags_restorable": False,
            "tx_muted_cleanup_requested": True,
            "errors": errors,
        }
        self._snapshot = None
        self._profiles_snapshot.clear()
        self._profiles.clear()
        if errors:
            raise ShortWindowIioError("radio cleanup failed: " + "; ".join(errors))

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise ShortWindowIioError("capture cancelled")

    def _wait(self, milliseconds: float) -> None:
        if self._cancelled.wait(milliseconds / 1000):
            self._check_cancelled()


class Tx2ToneOwner:
    """Explicitly selected, bounded TX2 DDS tone for a cabled qualification.

    Receive capture uses PPU; PPU's receive-only port has no TX generator. This
    owner uses pyadi's public DDS interface and public libiio attributes, never
    its private device fields. The watchdog independently mutes at the deadline.
    """

    def __init__(
        self,
        uri: str,
        expected_serial: str,
        *,
        maximum_seconds: float,
        adi_module: Any = None,
    ) -> None:
        if not 0 < maximum_seconds <= 120:
            raise ValueError("loopback TX duration must be positive and at most 120 seconds")
        self.uri, self.expected_serial = uri, expected_serial
        self.maximum_seconds = maximum_seconds
        self._adi_module = adi_module
        self._device: Any = None
        self._snapshot: dict[str, Any] = {}
        self._powerdown: Any = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._watchdog: threading.Thread | None = None
        self.watchdog_error: str | None = None
        self.restoration_receipt: dict[str, Any] | None = None
        self.context_facts: dict[str, str] = {}

    def open(self) -> None:
        module = self._adi_module or importlib.import_module("adi")
        device = module.ad9361(uri=self.uri)
        self._device = device
        if str(device.ctx.attrs.get("hw_serial")) != self.expected_serial:
            self._device = None
            raise ShortWindowIioError("TX owner serial differs from selected development radio")
        self.context_facts = {str(key): str(value) for key, value in device.ctx.attrs.items()}
        device.ctx.set_timeout(5000)
        self._powerdown = (
            device.ctx.find_device("ad9361-phy")
            .find_channel("altvoltage1", True)
            .attrs["powerdown"]
        )
        names = (
            "tx_lo",
            "tx_hardwaregain_chan0",
            "tx_hardwaregain_chan1",
            "dds_frequencies",
            "dds_phases",
            "dds_scales",
            "dds_enabled",
        )
        self._snapshot = {name: getattr(device, name) for name in names}
        self._snapshot["powerdown"] = str(self._powerdown.value)
        if any(float(getattr(device, name)) > -80 for name in names[1:3]) or any(
            float(value) != 0 for value in device.dds_scales
        ):
            self._device = None
            raise ShortWindowIioError("TX owner requires initially attenuated and zero-scale DDS")

    def start(self, frequency_hz: int, *, tone_hz: int = 100_000, gain_db: float = -80) -> None:
        if not 70_000_000 <= frequency_hz <= 6_000_000_000:
            raise ValueError("TX LO is outside supported range")
        if not -80 <= gain_db <= -30 or not 0 < tone_hz < 1_250_000:
            raise ValueError("TX attenuation/tone is outside bounded loopback limits")
        with self._lock:
            device = self._device
            if device is None or self._stop.is_set():
                raise ShortWindowIioError("TX owner is closed or expired")
            if self._watchdog is None:
                self._watchdog = threading.Thread(target=self._expire, daemon=True)
                self._watchdog.start()
            self._mute()
            device.tx_lo = frequency_hz
            if abs(round(device.tx_lo) - frequency_hz) > 10:
                raise ShortWindowIioError("TX LO readback differs from requested frequency")
            self._powerdown.value = "0"
            device.tx_hardwaregain_chan1 = gain_db
            device.dds_single_tone(tone_hz, 0.25, channel=1)
            if float(device.tx_hardwaregain_chan0) > -80:
                raise ShortWindowIioError("physical TX1 was not kept attenuated")

    def _mute(self) -> None:
        device = self._device
        if device is None:
            return
        device.tx_hardwaregain_chan0 = -80
        device.tx_hardwaregain_chan1 = -80
        device.dds_scales = [0.0] * len(device.dds_scales)
        device.disable_dds()
        self._powerdown.value = "1"
        if (
            any(float(value) != 0 for value in device.dds_scales)
            or str(self._powerdown.value) != "1"
        ):
            raise ShortWindowIioError("TX-off cleanup failed readback")

    def _expire(self) -> None:
        if not self._stop.wait(self.maximum_seconds):
            with self._lock:
                self._stop.set()
                try:
                    self._mute()
                except BaseException as error:
                    self.watchdog_error = f"{type(error).__name__}: {error}"

    def close(self) -> None:
        self._stop.set()
        errors: list[str] = []
        with self._lock:
            device = self._device
            if device is None:
                return
            try:
                self._mute()
            except BaseException as error:
                errors.append(str(error))
            for name, value in self._snapshot.items():
                try:
                    if name == "powerdown":
                        self._powerdown.value = value
                    else:
                        setattr(device, name, value)
                except BaseException as error:
                    errors.append(f"{name}: {error}")
            try:
                # Verify restoration cannot leave a waveform transmitting.
                if any(float(value) != 0 for value in device.dds_scales):
                    raise ShortWindowIioError("restored TX DDS has nonzero scale")
                for name, expected in self._snapshot.items():
                    actual = self._powerdown.value if name == "powerdown" else getattr(device, name)
                    if actual != expected:
                        raise ShortWindowIioError(f"TX restoration readback differs: {name}")
            except BaseException as error:
                errors.append(str(error))
                try:
                    self._mute()
                except BaseException as mute_error:
                    errors.append(str(mute_error))
            self._device = None
            close = getattr(device.ctx, "close", None)
            if callable(close):
                close()
        if self._watchdog is not None:
            self._watchdog.join(timeout=1)
        self.restoration_receipt = {"tx_restored": not errors, "errors": errors}
        if errors:
            raise ShortWindowIioError("TX restoration failed: " + "; ".join(errors))
