"""Metadata-attested Pluto+ adapter for short sequential scanner dwells."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

import numpy as np

from leo.contracts.states import GainMode
from leo.scanner.metadata import metadata_reports_rx_overflow
from leo.scanner.models import ScannerConfigurationV2
from leo.scanner.ports import ScanRadioBlockV2, ScanRadioIdentity

_LO_READBACK_TOLERANCE_HZ = 10
_EXPECTED_METADATA_ABI = 1

DeviceFactory = Callable[..., Any]
SettingsFactory = Callable[..., Any]


class PlutoScannerError(RuntimeError):
    pass


class PlutoSequentialScanRadio:
    """Capture every retuned target through a newly armed metadata buffer.

    The order is deliberately strict: destroy/reset the preceding buffer,
    tune and verify the LO, wait the configured settling guard, create a fresh
    metadata buffer with verified kernel depth, refill once, then synchronously
    destroy that buffer.  No userspace or kernel queue can therefore carry IQ
    across a retune boundary.
    """

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str = "scanner-pluto",
        device_factory: DeviceFactory | None = None,
        settings_factory: SettingsFactory | None = None,
        sleep: Callable[[float], None] = time.sleep,
        utc_ns: Callable[[], int] = time.time_ns,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if not host.strip() or host != host.strip():
            raise ValueError("Pluto host must be one trimmed nonempty value")
        if not expected_serial.strip() or expected_serial != expected_serial.strip():
            raise ValueError("expected serial must be one trimmed nonempty value")
        self._host = host
        self._expected_serial = expected_serial
        self._identity = ScanRadioIdentity(radio_id, expected_serial, f"ip:{host}")
        self._device_factory = device_factory
        self._settings_factory = settings_factory
        self._sleep = sleep
        self._utc_ns = utc_ns
        self._monotonic_ns = monotonic_ns
        self._device: Any | None = None
        self._configuration: ScannerConfigurationV2 | None = None
        self._metadata_abi_version: int | None = None
        self._reset_episode = 0
        self._stream_generations: set[int] = set()

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        if self._device is not None:
            raise PlutoScannerError("scanner radio is already open")
        factory = self._device_factory or _load_device_factory()
        device: Any | None = None
        try:
            device = factory(
                f"ip:{self._host}",
                serial=self._expected_serial,
                radio_id=self._identity.radio_id,
                expected_metadata_abi=_EXPECTED_METADATA_ABI,
            )
            device.open()
            serial = str(device.identity.serial)
            if serial != self._expected_serial:
                raise PlutoScannerError(
                    f"opened Pluto serial {serial!r}, expected {self._expected_serial!r}"
                )
            facts = dict(device.diagnostic_facts())
            metadata_abi = facts.get("buffer_metadata_abi")
            if metadata_abi != _EXPECTED_METADATA_ABI:
                raise PlutoScannerError(
                    "Pluto scanner requires the installed IIO metadata ABI "
                    f"{_EXPECTED_METADATA_ABI}; observed {metadata_abi!r}"
                )
            _require_metadata_api(device)
            self._device = device
            self._metadata_abi_version = metadata_abi
            self._identity = ScanRadioIdentity(self._identity.radio_id, serial, f"ip:{self._host}")
            return self._identity
        except Exception:
            if device is not None:
                with suppress(Exception):
                    device.close()
            raise

    def configure_once(self, configuration: ScannerConfigurationV2) -> None:
        device = self._require_device()
        if not isinstance(configuration, ScannerConfigurationV2):
            raise PlutoScannerError("live scanner capture requires ScannerConfigurationV2")
        if self._configuration is not None:
            if self._configuration != configuration:
                raise PlutoScannerError(
                    "refusing to change scanner sample rate, bandwidth, gain or channels"
                )
            return
        factory = self._settings_factory or _load_settings_factory()
        requested = factory(
            center_frequency_hz=float(configuration.targets[0].if_center_hz),
            sample_rate_hz=float(configuration.sample_rate_hz),
            bandwidth_hz=float(configuration.bandwidth_hz),
            gain_mode=configuration.gain_mode.value,
            gain_db=(configuration.gain_db if configuration.gain_mode is GainMode.MANUAL else None),
            channels=configuration.receiver_ids,
        )
        try:
            actual = device.apply_settings(requested)
            _validate_settings_readback(configuration, actual)
            device.reset_receive_buffer()
        except Exception as error:
            raise PlutoScannerError(f"scanner configuration failed: {error}") from error
        self._configuration = configuration

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2:
        device = self._require_device()
        configuration = self._configuration
        metadata_abi = self._metadata_abi_version
        if configuration is None or metadata_abi is None:
            raise PlutoScannerError("scanner radio must be configured before tuning")
        if sample_count != configuration.dwell_samples:
            raise ValueError("scanner reads must use the configured dwell block size")
        self._reset_episode += 1
        reset_episode = self._reset_episode
        try:
            device.reset_receive_buffer()
            tune_started = time.perf_counter()
            actual = int(round(float(device.tune_center_frequency(float(if_center_hz)))))
            tune_ms = (time.perf_counter() - tune_started) * 1_000
            if abs(actual - if_center_hz) > _LO_READBACK_TOLERANCE_HZ:
                raise PlutoScannerError(f"RX LO readback is {actual}, requested {if_center_hz}")
            self._sleep(configuration.tuning_settle_us / 1_000_000)

            listen_started = time.perf_counter()
            utc_before = self._utc_ns()
            monotonic_before = self._monotonic_ns()
            with device.begin_metadata_capture(
                sample_count,
                kernel_buffers=configuration.kernel_buffers,
            ) as capture:
                kernel_buffers_readback = int(capture.kernel_buffers)
                if kernel_buffers_readback != configuration.kernel_buffers:
                    raise PlutoScannerError(
                        "RX kernel buffer readback is "
                        f"{kernel_buffers_readback}, expected {configuration.kernel_buffers}"
                    )
                upstream = capture.read_block()
                stream_generation = _required_stream_generation(upstream)
                if stream_generation in self._stream_generations:
                    raise PlutoScannerError(
                        "metadata stream generation was reused across reset episodes"
                    )
                self._stream_generations.add(stream_generation)
            monotonic_after = self._monotonic_ns()
            utc_after = self._utc_ns()
            listen_ms = (time.perf_counter() - listen_started) * 1_000
            return _map_metadata_block(
                upstream,
                configuration=configuration,
                metadata_abi_version=metadata_abi,
                requested_if_center_hz=if_center_hz,
                actual_if_center_hz=actual,
                tune_ms=tune_ms,
                listen_ms=listen_ms,
                host_request_utc_ns=(min(utc_before, utc_after), max(utc_before, utc_after)),
                host_request_monotonic_ns=(
                    min(monotonic_before, monotonic_after),
                    max(monotonic_before, monotonic_after),
                ),
                kernel_buffers_readback=kernel_buffers_readback,
                reset_episode=reset_episode,
                expected_stream_generation=stream_generation,
            )
        except PlutoScannerError:
            raise
        except Exception as error:
            raise PlutoScannerError(
                f"metadata scanner capture failed at IF {if_center_hz}: {error}"
            ) from error

    def close(self) -> None:
        device, self._device = self._device, None
        self._configuration = None
        self._metadata_abi_version = None
        self._reset_episode = 0
        self._stream_generations.clear()
        if device is not None:
            try:
                device.reset_receive_buffer()
            finally:
                device.close()

    def _require_device(self) -> Any:
        if self._device is None:
            raise PlutoScannerError("scanner radio is not open")
        return self._device


def _map_metadata_block(
    upstream: Any,
    *,
    configuration: ScannerConfigurationV2,
    metadata_abi_version: int,
    requested_if_center_hz: int,
    actual_if_center_hz: int,
    tune_ms: float,
    listen_ms: float,
    host_request_utc_ns: tuple[int, int],
    host_request_monotonic_ns: tuple[int, int],
    kernel_buffers_readback: int,
    reset_episode: int,
    expected_stream_generation: int,
) -> ScanRadioBlockV2:
    raw_block_abi = getattr(upstream, "metadata_abi", None)
    if not isinstance(raw_block_abi, int):
        raise PlutoScannerError("metadata capture omitted the per-block ABI")
    block_abi = raw_block_abi
    if block_abi != metadata_abi_version:
        raise PlutoScannerError(
            f"metadata block ABI {block_abi} disagrees with context ABI {metadata_abi_version}"
        )
    values = np.asarray(upstream.samples)
    expected_shape = (len(configuration.receiver_ids), configuration.dwell_samples)
    if values.shape != expected_shape:
        raise PlutoScannerError(
            f"Pluto returned {values.shape}, expected {expected_shape} receiver/sample IQ"
        )
    realtime = _required_interval(
        upstream,
        "sample_time_realtime_start_ns",
        "sample_time_realtime_end_ns",
    )
    monotonic = _required_interval(
        upstream,
        "sample_time_monotonic_start_ns",
        "sample_time_monotonic_end_ns",
    )
    uncertainty = getattr(upstream, "sample_time_uncertainty_ns", None)
    if not isinstance(uncertainty, int) or uncertainty < 0:
        raise PlutoScannerError("metadata capture lacks sample-time uncertainty")
    stream_id = int(upstream.stream_id)
    stream_generation = int(upstream.stream_generation)
    if stream_generation != expected_stream_generation:
        raise PlutoScannerError("metadata stream generation changed while mapping the block")
    if stream_generation != stream_id:
        raise PlutoScannerError("metadata stream generation disagrees with raw stream ID")
    metadata_flags = int(upstream.metadata_flags)
    overflow_from_flags = metadata_reports_rx_overflow(metadata_flags)
    raw_overflow = getattr(upstream, "overflow_observed", None)
    if not isinstance(raw_overflow, bool):
        raise PlutoScannerError("metadata capture omitted the canonical overflow boolean")
    if raw_overflow != overflow_from_flags:
        raise PlutoScannerError("metadata overflow boolean disagrees with flags bit 11")
    return ScanRadioBlockV2(
        samples=np.ascontiguousarray(values.T, dtype=np.complex64),
        requested_if_center_hz=requested_if_center_hz,
        actual_if_center_hz=actual_if_center_hz,
        tune_ms=tune_ms,
        listen_ms=listen_ms,
        host_request_utc_ns=host_request_utc_ns,
        host_request_monotonic_ns=host_request_monotonic_ns,
        metadata_abi_version=metadata_abi_version,
        stream_id=stream_id,
        buffer_sequence=int(upstream.buffer_sequence),
        first_sample_sequence=int(upstream.first_sample_sequence),
        metadata_flags=metadata_flags,
        sample_time_realtime_ns=realtime,
        sample_time_monotonic_ns=monotonic,
        sample_time_uncertainty_ns=uncertainty,
        kernel_buffers_requested=configuration.kernel_buffers,
        kernel_buffers_readback=kernel_buffers_readback,
        reset_episode=reset_episode,
        missing_samples_before=int(upstream.missing_samples_before),
        overflow_observed=overflow_from_flags,
    )


def _required_stream_generation(upstream: Any) -> int:
    stream_id = getattr(upstream, "stream_id", None)
    stream_generation = getattr(upstream, "stream_generation", None)
    if (
        not isinstance(stream_id, int)
        or isinstance(stream_id, bool)
        or stream_id <= 0
        or not isinstance(stream_generation, int)
        or isinstance(stream_generation, bool)
        or stream_generation <= 0
    ):
        raise PlutoScannerError("metadata capture lacks a valid stream generation")
    if stream_generation != stream_id:
        raise PlutoScannerError("metadata stream generation disagrees with raw stream ID")
    return stream_generation


def _required_interval(upstream: Any, lower_name: str, upper_name: str) -> tuple[int, int]:
    lower = getattr(upstream, lower_name, None)
    upper = getattr(upstream, upper_name, None)
    if not isinstance(lower, int) or not isinstance(upper, int) or lower < 0 or lower >= upper:
        label = lower_name.removesuffix("_start_ns")
        raise PlutoScannerError(f"metadata capture lacks a valid {label}")
    return lower, upper


def _require_metadata_api(device: Any) -> None:
    for name in (
        "apply_settings",
        "reset_receive_buffer",
        "tune_center_frequency",
        "begin_metadata_capture",
    ):
        if not callable(getattr(device, name, None)):
            raise PlutoScannerError(f"installed pluto-plus-utils lacks required {name} API")


def _validate_settings_readback(configuration: ScannerConfigurationV2, actual: Any) -> None:
    expected = {
        "sample_rate_hz": configuration.sample_rate_hz,
        "bandwidth_hz": configuration.bandwidth_hz,
        "channels": configuration.receiver_ids,
        "gain_mode": configuration.gain_mode.value,
    }
    if configuration.gain_mode is GainMode.MANUAL:
        expected["gain_db"] = configuration.gain_db
    for name, value in expected.items():
        observed = getattr(actual, name)
        if name == "channels":
            observed = tuple(int(item) for item in observed)
        elif name == "gain_mode":
            observed = str(observed)
        elif name == "gain_db":
            observed = float(observed)
            if abs(observed - configuration.gain_db) <= 0.25:
                continue
        else:
            observed = round(float(observed))
        if observed != value:
            raise PlutoScannerError(f"scanner {name} readback is {observed!r}, requested {value!r}")


def _load_device_factory() -> DeviceFactory:
    try:
        module = importlib.import_module("pluto_plus.hardware.iio")
    except ImportError as error:
        raise PlutoScannerError(
            "metadata scanner capture requires the pinned pluto-plus-utils hardware extra"
        ) from error
    factory = getattr(module, "IioRadioDevice", None)
    if not callable(factory):
        raise PlutoScannerError("pluto-plus-utils does not expose IioRadioDevice")
    return factory


def _load_settings_factory() -> SettingsFactory:
    try:
        module = importlib.import_module("pluto_plus.models")
    except ImportError as error:
        raise PlutoScannerError(
            "metadata scanner capture requires the pinned pluto-plus-utils hardware extra"
        ) from error
    factory = getattr(module, "RadioSettings", None)
    if not callable(factory):
        raise PlutoScannerError("pluto-plus-utils does not expose RadioSettings")
    return factory
