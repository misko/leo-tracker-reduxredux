"""Persistent Pluto+ adapter for short sequential scanner dwells."""

from __future__ import annotations

import importlib
import time
from typing import Any

import numpy as np

from leo.contracts.states import GainMode
from leo.scanner.models import ScannerConfiguration
from leo.scanner.ports import ScanRadioBlock, ScanRadioIdentity

_LO_READBACK_TOLERANCE_HZ = 10


class PlutoScannerError(RuntimeError):
    pass


class PlutoSequentialScanRadio:
    """Keep one pyadi context and buffer while changing only the RX LO.

    Sample rate, RF bandwidth, channels and gain are written exactly once.
    The RX kernel queue is forced to depth one before the userspace buffer is
    created, eliminating already-queued samples from the preceding tuning.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str = "scanner-pluto",
        adi_module: Any | None = None,
    ) -> None:
        if not host.strip() or host != host.strip():
            raise ValueError("Pluto host must be one trimmed nonempty value")
        if not expected_serial.strip() or expected_serial != expected_serial.strip():
            raise ValueError("expected serial must be one trimmed nonempty value")
        self._host = host
        self._expected_serial = expected_serial
        self._identity = ScanRadioIdentity(radio_id, expected_serial, f"ip:{host}")
        self._adi_module = adi_module
        self._device: Any | None = None
        self._configuration: ScannerConfiguration | None = None

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        if self._device is not None:
            raise PlutoScannerError("scanner radio is already open")
        module = self._adi_module or importlib.import_module("adi")
        device = module.ad9361(uri=f"ip:{self._host}")
        try:
            device.rx_destroy_buffer()
            facts = _context_facts(device.ctx)
            serial = str(facts.get("serial") or "")
            if serial != self._expected_serial:
                raise PlutoScannerError(
                    f"opened Pluto serial {serial!r}, expected {self._expected_serial!r}"
                )
            self._device = device
            self._identity = ScanRadioIdentity(self._identity.radio_id, serial, f"ip:{self._host}")
            return self._identity
        except Exception:
            _release(device)
            raise

    def configure_once(self, configuration: ScannerConfiguration) -> None:
        device = self._require_device()
        if self._configuration is not None:
            if self._configuration != configuration:
                raise PlutoScannerError(
                    "refusing to change scanner sample rate, bandwidth, gain or channels"
                )
            return
        device.rx_destroy_buffer()
        device.rx_enabled_channels = list(configuration.receiver_ids)
        device.sample_rate = configuration.sample_rate_hz
        device.rx_rf_bandwidth = configuration.bandwidth_hz
        for receiver_id in configuration.receiver_ids:
            setattr(device, f"gain_control_mode_chan{receiver_id}", configuration.gain_mode.value)
            if configuration.gain_mode is GainMode.MANUAL:
                setattr(device, f"rx_hardwaregain_chan{receiver_id}", configuration.gain_db)
        device.rx_buffer_size = configuration.dwell_samples
        rx_device = getattr(device, "_rxadc", None)
        setter = getattr(rx_device, "set_kernel_buffers_count", None)
        if not callable(setter):
            raise PlutoScannerError("installed libiio cannot set RX kernel buffer count")
        result = setter(configuration.kernel_buffers)
        if isinstance(result, int) and result < 0:
            raise PlutoScannerError(f"kernel buffer configuration failed with error {result}")
        actual_buffers = getattr(rx_device, "kernel_buffers_count", None)
        if actual_buffers is not None and int(actual_buffers) != 1:
            raise PlutoScannerError(
                f"RX kernel buffer readback is {actual_buffers}, expected exactly 1"
            )
        self._configuration = configuration

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock:
        device = self._require_device()
        configuration = self._configuration
        if configuration is None:
            raise PlutoScannerError("scanner radio must be configured before tuning")
        if sample_count != configuration.dwell_samples:
            raise ValueError("scanner reads must use the configured dwell block size")
        tune_started = time.perf_counter()
        device.rx_lo = if_center_hz
        actual = int(round(float(device.rx_lo)))
        tune_ms = (time.perf_counter() - tune_started) * 1_000
        if abs(actual - if_center_hz) > _LO_READBACK_TOLERANCE_HZ:
            raise PlutoScannerError(f"RX LO readback is {actual}, requested {if_center_hz}")
        listen_started = time.perf_counter()
        utc_before = time.time_ns()
        monotonic_before = time.monotonic_ns()
        raw = device.rx()
        monotonic_after = time.monotonic_ns()
        utc_after = time.time_ns()
        listen_ms = (time.perf_counter() - listen_started) * 1_000
        values = np.asarray(raw)
        receiver_count = len(configuration.receiver_ids)
        if receiver_count == 1 and values.ndim == 1:
            values = values[np.newaxis, :]
        if values.shape != (receiver_count, sample_count):
            raise PlutoScannerError(
                f"Pluto returned {values.shape}, expected ({receiver_count}, {sample_count})"
            )
        return ScanRadioBlock(
            samples=np.ascontiguousarray(values.T, dtype=np.complex64),
            requested_if_center_hz=if_center_hz,
            actual_if_center_hz=actual,
            tune_ms=tune_ms,
            listen_ms=listen_ms,
            host_request_utc_ns=(min(utc_before, utc_after), max(utc_before, utc_after)),
            host_request_monotonic_ns=(
                min(monotonic_before, monotonic_after),
                max(monotonic_before, monotonic_after),
            ),
        )

    def close(self) -> None:
        device, self._device = self._device, None
        self._configuration = None
        if device is not None:
            _release(device)

    def _require_device(self) -> Any:
        if self._device is None:
            raise PlutoScannerError("scanner radio is not open")
        return self._device


def _context_facts(context: Any) -> dict[str, object]:
    try:
        module = importlib.import_module("pluto_plus.hardware.iio")
        facts = module.context_facts(context)
    except Exception as error:
        raise PlutoScannerError(f"could not attest Pluto context: {error}") from error
    return dict(facts)


def _release(device: Any) -> None:
    try:
        device.rx_destroy_buffer()
    finally:
        context = getattr(device, "ctx", None)
        if context is not None and hasattr(context, "destroy"):
            context.destroy()
