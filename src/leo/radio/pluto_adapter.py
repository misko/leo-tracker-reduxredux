"""Lazy anti-corruption adapter for serial-attested Ethernet Pluto+ capture."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from leo.contracts.radio import (
    IqBlockMetadataV1,
    IqBlockMetadataV2,
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
from leo.domain.continuity import ContinuityChainValidator
from leo.domain.iq import IqBlock, receiver_major_complex_to_ci16

DeviceFactory = Callable[..., Any]
SettingsFactory = Callable[..., Any]
ExactSettingsApplier = Callable[[Any, Any], Any]
_EXPECTED_METADATA_ABI = 1


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
        exact_settings_applier: ExactSettingsApplier | None = None,
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
        self._exact_settings_applier = exact_settings_applier
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
        self._metadata_session: Any | None = None
        self._metadata_refill_samples: int | None = None
        self._kernel_buffers: int | None = None
        self._continuity_validator: ContinuityChainValidator | None = None
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
                expected_metadata_abi=_EXPECTED_METADATA_ABI,
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
        return self._configure(settings, exact_readback=False)

    def configure_exact(self, settings: RadioSettingsV1) -> RadioSettingsV1:
        """Apply settings through PPU's bounded exact-readback LO search."""

        return self._configure(settings, exact_readback=True)

    def _configure(
        self,
        settings: RadioSettingsV1,
        *,
        exact_readback: bool,
    ) -> RadioSettingsV1:
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
            if exact_readback:
                applier = self._exact_settings_applier or _load_exact_settings_applier()
                application = applier(device, upstream)
                applied = getattr(application, "applied", None)
                if applied is None:
                    raise PlutoAdapterError(
                        "pluto-plus-utils exact settings result omits applied readback"
                    )
                actual = _map_settings(applied)
            else:
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

    def reset_receive_buffer(self) -> None:
        device = self._require_device()
        session, self._metadata_session = self._metadata_session, None
        self._metadata_refill_samples = None
        self._kernel_buffers = None
        self._continuity_validator = None
        try:
            if session is not None:
                session.close()
            device.reset_receive_buffer()
        except Exception as error:
            raise PlutoAdapterError(f"Pluto receive-buffer reset failed: {error}") from error

    def begin_metadata_capture(self, sample_count: int, *, kernel_buffers: int) -> int:
        device = self._require_device()
        if self._settings is None:
            raise PlutoAdapterError("Pluto must be configured before metadata capture")
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if kernel_buffers < 2:
            raise ValueError("metadata capture requires at least two kernel buffers")
        if not (
            self.capabilities.supports_device_sample_counter
            and self.capabilities.supports_continuity_sequence
        ):
            raise PlutoAdapterError("Pluto does not attest counter-authoritative metadata")
        if self._metadata_session is not None:
            raise PlutoAdapterError("Pluto metadata capture session is already active")
        try:
            session = device.begin_metadata_capture(sample_count, kernel_buffers=kernel_buffers)
            readback = int(session.kernel_buffers)
            if readback != kernel_buffers:
                session.close()
                raise PlutoAdapterError(
                    f"kernel-buffer readback mismatch: requested {kernel_buffers}, got {readback}"
                )
        except PlutoAdapterError:
            raise
        except Exception as error:
            raise PlutoAdapterError(f"Pluto metadata capture start failed: {error}") from error
        self._metadata_session = session
        self._metadata_refill_samples = sample_count
        self._kernel_buffers = readback
        self._continuity_validator = ContinuityChainValidator(
            require_metadata=True,
            require_generation=True,
        )
        self._sample_cursor = 0
        self._block_index = 0
        return readback

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
            if self._metadata_session is None:
                block = device.read_block(sample_count)
            else:
                configured = self._metadata_refill_samples
                if configured is None or sample_count > configured:
                    raise PlutoAdapterError(
                        "metadata refill request exceeds the configured capture buffer"
                    )
                block = self._metadata_session.read_block()
        except Exception as error:
            raise PlutoAdapterError(f"Pluto refill failed: {error}") from error
        monotonic_after = self._monotonic_ns()
        utc_after = self._utc_ns()
        upstream_sample_count = int(getattr(block, "sample_count", sample_count))
        if upstream_sample_count < sample_count:
            raise PlutoAdapterError(
                f"upstream IQ returned {upstream_sample_count} samples, requested {sample_count}"
            )
        upstream_samples = block.samples
        if upstream_sample_count != sample_count:
            upstream_samples = upstream_samples[:, :sample_count]
        try:
            samples = receiver_major_complex_to_ci16(
                upstream_samples,
                len(settings.receiver_ids),
                sample_count,
            )
        except ValueError as error:
            raise PlutoAdapterError(str(error).replace("complex IQ", "upstream IQ")) from error
        upstream_utc_ns = int(getattr(block, "utc_ns", 0))
        common = dict(
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
        )
        if self._metadata_session is None:
            metadata: IqBlockMetadataV1 = IqBlockMetadataV1.model_validate(
                {
                    **common,
                    "timing_method": TimingMethod.HOST_BRACKET,
                    "continuity": ContinuityStatus.UNKNOWN,
                    "hardware_metadata": {
                        "adapter": "pluto-plus-utils-iio-legacy-unobservable",
                        "upstream_utc_ns": upstream_utc_ns,
                        "host_block_index": self._block_index,
                    },
                }
            )
        else:
            metadata = self._map_metadata_block(
                block,
                common,
                upstream_sample_count=upstream_sample_count,
            )
        result = IqBlock(samples=samples, metadata=metadata)
        self._sample_cursor += sample_count
        self._block_index += 1
        return result

    def close(self) -> None:
        device, self._device = self._device, None
        session, self._metadata_session = self._metadata_session, None
        self._settings = None
        self._metadata_refill_samples = None
        self._kernel_buffers = None
        self._continuity_validator = None
        self._sample_cursor = 0
        self._block_index = 0
        if device is not None:
            try:
                if session is not None:
                    session.close()
                device.close()
            except Exception as error:
                raise PlutoAdapterError(f"Pluto close failed: {error}") from error

    def _require_device(self) -> Any:
        if self._device is None:
            raise PlutoAdapterError("Pluto adapter is not open")
        return self._device

    def _map_metadata_block(
        self,
        block: Any,
        common: dict[str, Any],
        *,
        upstream_sample_count: int,
    ) -> IqBlockMetadataV2:
        validator = self._continuity_validator
        if validator is None or self._kernel_buffers is None:
            raise PlutoAdapterError("metadata capture validator is unavailable")
        try:
            raw_stream_id = block.stream_id
            stream_generation = str(getattr(block, "stream_generation", raw_stream_id))
            buffer_sequence = int(block.buffer_sequence)
            first_sample_sequence = int(block.first_sample_sequence)
            metadata_flags = int(block.metadata_flags)
            abi_value = getattr(block, "metadata_abi", None)
            if abi_value is None:
                abi_value = getattr(block, "metadata_abi_version", None)
            if abi_value is None:
                abi_value = getattr(self._metadata_session, "metadata_abi", None)
            if abi_value is None:
                abi_value = getattr(self._metadata_session, "metadata_abi_version", None)
            if abi_value is None:
                raise ValueError("metadata header omits ABI version")
            abi_version = int(abi_value)
            realtime = _optional_interval(
                getattr(block, "sample_time_realtime_start_ns", None),
                getattr(block, "sample_time_realtime_end_ns", None),
            )
            monotonic = _optional_interval(
                getattr(block, "sample_time_monotonic_start_ns", None),
                getattr(block, "sample_time_monotonic_end_ns", None),
            )
            requested_sample_count = int(common["sample_count"])
            if requested_sample_count < upstream_sample_count:
                assert self._settings is not None
                realtime = _prefix_interval(
                    realtime,
                    requested_sample_count,
                    self._settings.sample_rate_hz,
                )
                monotonic = _prefix_interval(
                    monotonic,
                    requested_sample_count,
                    self._settings.sample_rate_hz,
                )
            uncertainty = getattr(block, "sample_time_uncertainty_ns", None)
            overflow = bool(getattr(block, "overflow_observed", getattr(block, "overflow", False)))
            metadata = IqBlockMetadataV2(
                **common,
                timing_method=TimingMethod.DEVICE_COUNTER_ANCHORED,
                device_sample_counter=first_sample_sequence,
                source_sequence=buffer_sequence,
                continuity=ContinuityStatus.UNKNOWN,
                overflow_observed=overflow,
                stream_generation=stream_generation,
                metadata_abi_version=abi_version,
                metadata_flags=metadata_flags,
                kernel_buffers=self._kernel_buffers,
                sample_time_realtime_ns=realtime,
                sample_time_monotonic_ns=monotonic,
                sample_time_uncertainty_ns=(None if uncertainty is None else int(uncertainty)),
                hardware_metadata={
                    "adapter": "pluto-plus-utils-metadata",
                    "stream_id": raw_stream_id,
                    "stream_generation": stream_generation,
                    "buffer_sequence": buffer_sequence,
                    "first_sample_sequence": first_sample_sequence,
                    "upstream_missing_samples_before": int(
                        getattr(block, "missing_samples_before", 0)
                    ),
                    "metadata_abi_version": abi_version,
                    "metadata_flags": metadata_flags,
                    "kernel_buffers_readback": self._kernel_buffers,
                    "upstream_sample_count": upstream_sample_count,
                    "sample_time_realtime_start_ns": getattr(
                        block, "sample_time_realtime_start_ns", None
                    ),
                    "sample_time_realtime_end_ns": getattr(
                        block, "sample_time_realtime_end_ns", None
                    ),
                    "sample_time_monotonic_start_ns": getattr(
                        block, "sample_time_monotonic_start_ns", None
                    ),
                    "sample_time_monotonic_end_ns": getattr(
                        block, "sample_time_monotonic_end_ns", None
                    ),
                    "upstream_utc_ns": int(getattr(block, "utc_ns", 0)),
                    "host_block_index": self._block_index,
                },
            )
            return IqBlockMetadataV2.model_validate(
                validator.observe(metadata).model_dump(mode="json")
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise PlutoAdapterError(f"invalid Pluto metadata header: {error}") from error


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


def _load_exact_settings_applier() -> ExactSettingsApplier:
    try:
        module = importlib.import_module("pluto_plus.hardware")
    except ImportError as error:
        raise PlutoDependencyError(
            "exact Pluto tuning requires the pinned pluto-plus-utils hardware API"
        ) from error
    applier = getattr(module, "apply_settings_exact", None)
    if not callable(applier):
        raise PlutoDependencyError(
            "pinned pluto-plus-utils does not expose exact settings application"
        )
    return applier


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
        supports_device_sample_counter=bool(
            getattr(value, "supports_device_sample_counter", False)
        ),
        supports_continuity_sequence=bool(getattr(value, "supports_continuity_sequence", False)),
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


def _optional_string(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _optional_interval(lower: Any, upper: Any) -> NanosecondIntervalV1 | None:
    if lower is None and upper is None:
        return None
    if lower is None or upper is None:
        raise ValueError("sample-time interval has only one endpoint")
    return NanosecondIntervalV1(lower_ns=int(lower), upper_ns=int(upper))


def _prefix_interval(
    interval: NanosecondIntervalV1 | None,
    sample_count: int,
    sample_rate_hz: int,
) -> NanosecondIntervalV1 | None:
    if interval is None:
        return None
    return NanosecondIntervalV1(
        lower_ns=interval.lower_ns,
        upper_ns=interval.lower_ns + sample_count * 1_000_000_000 // sample_rate_hz,
    )
