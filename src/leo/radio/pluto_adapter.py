"""Lazy anti-corruption adapter for serial-attested Ethernet Pluto+ capture."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

import numpy as np

from leo.contracts.radio import (
    IqBlockMetadataV1,
    NanosecondIntervalV1,
    RadioCapabilitiesV1,
    RadioIdentityV1,
    RadioSettingsV1,
    ReceiverGainV1,
)
from leo.contracts.states import (
    ContinuityStatus,
    GainMode,
    RadioTransport,
    TimingMethod,
)
from leo.domain.iq import IqBlock

DeviceFactory = Callable[..., Any]
SettingsFactory = Callable[..., Any]


class PlutoAdapterError(RuntimeError):
    pass


class PlutoDependencyError(PlutoAdapterError):
    pass


class PlutoIioRadioSource:
    """Map ``pluto-plus-utils`` objects into Leo contracts without leaking them."""

    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        radio_id: str | None = None,
        device_factory: DeviceFactory | None = None,
        settings_factory: SettingsFactory | None = None,
        utc_ns: Callable[[], int] = time.time_ns,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if not host.strip() or host != host.strip():
            raise ValueError("Pluto host must be one non-empty value without surrounding spaces")
        if not expected_serial.strip() or expected_serial != expected_serial.strip():
            raise ValueError("expected Pluto serial must be one exact non-empty value")
        self._host = host
        self._expected_serial = expected_serial
        self._radio_id = radio_id or expected_serial
        self._device_factory = device_factory
        self._settings_factory = settings_factory
        self._utc_ns = utc_ns
        self._monotonic_ns = monotonic_ns
        self._device: Any | None = None
        self._identity = RadioIdentityV1(
            radio_id=self._radio_id,
            serial=expected_serial,
            uri=f"ip:{host}",
            transport=RadioTransport.IIO_IP,
        )
        self._capabilities = RadioCapabilitiesV1(
            receiver_ids=(0, 1),
            minimum_sample_rate_hz=520_833,
            maximum_sample_rate_hz=30_720_000,
            supports_device_sample_counter=False,
            supports_continuity_sequence=False,
        )
        self._settings: RadioSettingsV1 | None = None
        self._sample_cursor = 0
        self._block_index = 0

    @property
    def identity(self) -> RadioIdentityV1:
        return self._identity

    @property
    def capabilities(self) -> RadioCapabilitiesV1:
        return self._capabilities

    def open(self) -> RadioIdentityV1:
        if self._device is not None:
            raise PlutoAdapterError("Pluto adapter is already open")
        factory = self._device_factory or _load_device_factory()
        try:
            device = factory(
                f"ip:{self._host}",
                serial=self._expected_serial,
                radio_id=self._radio_id,
            )
        except Exception as error:
            raise PlutoAdapterError(f"Pluto construction failed: {error}") from error
        try:
            device.open()
            identity = _map_identity(device.identity, radio_id=self._radio_id)
            if identity.serial != self._expected_serial:
                raise PlutoAdapterError(
                    f"opened Pluto serial {identity.serial!r}, expected {self._expected_serial!r}"
                )
            if identity.transport is not RadioTransport.IIO_IP:
                raise PlutoAdapterError("Ethernet Pluto adapter opened a non-IP transport")
            self._identity = identity
            self._capabilities = _map_capabilities(device.capabilities)
            self._device = device
            return identity
        except Exception as error:
            with suppress(Exception):
                device.close()
            if isinstance(error, PlutoAdapterError):
                raise
            raise PlutoAdapterError(f"Pluto open failed: {error}") from error

    def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
        device = self._require_device()
        if any(
            receiver not in self.capabilities.receiver_ids for receiver in settings.receiver_ids
        ):
            raise PlutoAdapterError("settings request an unsupported Pluto receiver")
        if not (
            self.capabilities.minimum_sample_rate_hz
            <= settings.sample_rate_hz
            <= self.capabilities.maximum_sample_rate_hz
        ):
            raise PlutoAdapterError("settings request an unsupported Pluto sample rate")
        gain_db = _common_manual_gain(settings)
        factory = self._settings_factory or _load_settings_factory()
        try:
            upstream = factory(
                center_frequency_hz=float(settings.center_frequency_hz),
                sample_rate_hz=float(settings.sample_rate_hz),
                bandwidth_hz=float(settings.bandwidth_hz),
                gain_mode=settings.gain_mode.value,
                gain_db=gain_db,
                channels=settings.receiver_ids,
            )
            actual = _map_settings(device.apply_settings(upstream))
            _validate_readback(settings, actual)
        except PlutoAdapterError:
            raise
        except Exception as error:
            raise PlutoAdapterError(f"Pluto configuration failed: {error}") from error
        self._settings = actual
        self._sample_cursor = 0
        self._block_index = 0
        return actual

    def read_block(self, sample_count: int) -> IqBlock:
        device = self._require_device()
        settings = self._settings
        if settings is None:
            raise PlutoAdapterError("Pluto must be configured before capture")
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        utc_before = self._utc_ns()
        monotonic_before = self._monotonic_ns()
        try:
            block = device.read_block(sample_count)
        except Exception as error:
            raise PlutoAdapterError(f"Pluto refill failed: {error}") from error
        monotonic_after = self._monotonic_ns()
        utc_after = self._utc_ns()
        samples = _complex_to_ci16(block.samples, len(settings.receiver_ids), sample_count)
        upstream_utc_ns = int(getattr(block, "utc_ns", 0))
        metadata = IqBlockMetadataV1(
            radio_id=self.identity.radio_id,
            receiver_ids=settings.receiver_ids,
            sample_count=sample_count,
            session_sample_start=self._sample_cursor,
            host_request_utc_ns=NanosecondIntervalV1(
                lower_ns=min(utc_before, utc_after),
                upper_ns=max(utc_before, utc_after),
            ),
            host_request_monotonic_ns=NanosecondIntervalV1(
                lower_ns=min(monotonic_before, monotonic_after),
                upper_ns=max(monotonic_before, monotonic_after),
            ),
            timing_method=TimingMethod.HOST_BRACKET,
            continuity=ContinuityStatus.UNKNOWN,
            hardware_metadata={
                "adapter": "pluto-plus-utils-iio",
                "upstream_utc_ns": upstream_utc_ns,
                "host_block_index": self._block_index,
            },
        )
        result = IqBlock(samples=samples, metadata=metadata)
        self._sample_cursor += sample_count
        self._block_index += 1
        return result

    def close(self) -> None:
        device, self._device = self._device, None
        self._settings = None
        self._sample_cursor = 0
        self._block_index = 0
        if device is not None:
            try:
                device.close()
            except Exception as error:
                raise PlutoAdapterError(f"Pluto close failed: {error}") from error

    def _require_device(self) -> Any:
        if self._device is None:
            raise PlutoAdapterError("Pluto adapter is not open")
        return self._device


def _load_device_factory() -> DeviceFactory:
    try:
        module = importlib.import_module("pluto_plus.hardware.iio")
    except ImportError as error:
        raise PlutoDependencyError(
            "Pluto hardware capture requires pluto-plus-utils at the pinned provenance revision"
        ) from error
    factory = getattr(module, "IioRadioDevice", None)
    if not callable(factory):
        raise PlutoDependencyError("pluto-plus-utils does not expose IioRadioDevice")
    return factory


def _load_settings_factory() -> SettingsFactory:
    try:
        module = importlib.import_module("pluto_plus.models")
    except ImportError as error:
        raise PlutoDependencyError(
            "Pluto hardware capture requires pluto-plus-utils at the pinned provenance revision"
        ) from error
    factory = getattr(module, "RadioSettings", None)
    if not callable(factory):
        raise PlutoDependencyError("pluto-plus-utils does not expose RadioSettings")
    return factory


def _map_identity(value: Any, *, radio_id: str) -> RadioIdentityV1:
    transport = str(getattr(value, "transport", ""))
    if transport != RadioTransport.IIO_IP.value:
        raise PlutoAdapterError(f"unsupported upstream Pluto transport: {transport!r}")
    return RadioIdentityV1(
        radio_id=radio_id,
        serial=str(value.serial),
        uri=str(value.uri),
        transport=RadioTransport.IIO_IP,
        model=str(getattr(value, "model", "Pluto+")),
        firmware_version=_optional_string(getattr(value, "firmware_version", None)),
        hardware_revision=_optional_string(getattr(value, "hardware_revision", None)),
    )


def _map_capabilities(value: Any) -> RadioCapabilitiesV1:
    receivers = tuple(int(item) for item in value.receiver_channels)
    minimum = getattr(value, "minimum_sample_rate_hz", None)
    maximum = getattr(value, "maximum_sample_rate_hz", None)
    if minimum is None or maximum is None:
        raise PlutoAdapterError("upstream Pluto capabilities omit sample-rate bounds")
    return RadioCapabilitiesV1(
        receiver_ids=receivers,
        minimum_sample_rate_hz=round(float(minimum)),
        maximum_sample_rate_hz=round(float(maximum)),
        supports_device_sample_counter=False,
        supports_continuity_sequence=False,
    )


def _map_settings(value: Any) -> RadioSettingsV1:
    mode_text = str(value.gain_mode)
    try:
        mode = GainMode(mode_text)
    except ValueError as error:
        raise PlutoAdapterError(f"unsupported upstream gain mode: {mode_text!r}") from error
    receivers = tuple(int(item) for item in value.channels)
    gain_db = getattr(value, "gain_db", None)
    gains = (
        tuple(
            ReceiverGainV1(receiver_id=receiver, gain_db=float(gain_db)) for receiver in receivers
        )
        if mode is GainMode.MANUAL and gain_db is not None
        else ()
    )
    return RadioSettingsV1(
        center_frequency_hz=round(float(value.center_frequency_hz)),
        sample_rate_hz=round(float(value.sample_rate_hz)),
        bandwidth_hz=round(float(value.bandwidth_hz)),
        receiver_ids=receivers,
        gain_mode=mode,
        gains=gains,
    )


def _common_manual_gain(settings: RadioSettingsV1) -> float | None:
    if settings.gain_mode is not GainMode.MANUAL:
        if settings.gain_mode is GainMode.HYBRID:
            raise PlutoAdapterError("pluto-plus-utils IIO adapter does not support hybrid gain")
        return None
    values = tuple(gain.gain_db for gain in settings.gains)
    if max(values) - min(values) > 0.25:
        raise PlutoAdapterError(
            "pluto-plus-utils IIO control requires one common manual gain for paired receivers"
        )
    return sum(values) / len(values)


def _validate_readback(requested: RadioSettingsV1, actual: RadioSettingsV1) -> None:
    for field in ("center_frequency_hz", "sample_rate_hz", "bandwidth_hz"):
        expected = float(getattr(requested, field))
        observed = float(getattr(actual, field))
        if abs(expected - observed) > max(1.0, abs(expected) * 1e-6):
            raise PlutoAdapterError(
                f"{field} readback mismatch: requested {expected}, observed {observed}"
            )
    if requested.receiver_ids != actual.receiver_ids:
        raise PlutoAdapterError("receiver readback mismatch")
    if requested.gain_mode is not actual.gain_mode:
        raise PlutoAdapterError("gain-mode readback mismatch")
    if requested.gain_mode is GainMode.MANUAL:
        for requested_gain, actual_gain in zip(requested.gains, actual.gains, strict=True):
            if abs(requested_gain.gain_db - actual_gain.gain_db) > 0.25:
                raise PlutoAdapterError("manual-gain readback mismatch")


def _complex_to_ci16(value: Any, receiver_count: int, sample_count: int) -> np.ndarray:
    samples = np.asarray(value)
    if receiver_count == 1 and samples.ndim == 1:
        samples = samples[np.newaxis, :]
    if samples.shape != (receiver_count, sample_count) or not np.iscomplexobj(samples):
        raise PlutoAdapterError(
            f"upstream IQ shape is {samples.shape}, expected ({receiver_count}, {sample_count})"
        )
    real = np.asarray(samples.real)
    imag = np.asarray(samples.imag)
    if not np.all(np.isfinite(real)) or not np.all(np.isfinite(imag)):
        raise PlutoAdapterError("upstream IQ contains non-finite values")
    rounded_real = np.rint(real)
    rounded_imag = np.rint(imag)
    if not np.array_equal(real, rounded_real) or not np.array_equal(imag, rounded_imag):
        raise PlutoAdapterError("upstream IQ is not exact integer-valued CI16 evidence")
    if (
        rounded_real.min(initial=0) < -32_768
        or rounded_real.max(initial=0) > 32_767
        or rounded_imag.min(initial=0) < -32_768
        or rounded_imag.max(initial=0) > 32_767
    ):
        raise PlutoAdapterError("upstream IQ exceeds the CI16 range")
    output = np.empty((sample_count, receiver_count, 2), dtype="<i2")
    output[:, :, 0] = rounded_real.T.astype("<i2")
    output[:, :, 1] = rounded_imag.T.astype("<i2")
    return output


def _optional_string(value: Any) -> str | None:
    return None if value in (None, "") else str(value)
