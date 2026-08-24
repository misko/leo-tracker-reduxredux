"""Narrow hardware port owned by sequential scanning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from leo.scanner.models import ScannerConfiguration, ScannerConfigurationV2


@dataclass(frozen=True, slots=True)
class ScanRadioIdentity:
    radio_id: str
    serial: str
    uri: str


@dataclass(frozen=True, slots=True)
class ScanRadioBlock:
    samples: np.ndarray
    requested_if_center_hz: int
    actual_if_center_hz: int
    tune_ms: float
    listen_ms: float
    host_request_utc_ns: tuple[int, int]
    host_request_monotonic_ns: tuple[int, int]

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        if values.dtype != np.dtype(np.complex64) or values.ndim != 2:
            raise ValueError("scanner IQ must be one sample/receiver complex64 array")
        if not values.flags.c_contiguous:
            raise ValueError("scanner IQ must be C-contiguous")
        if not np.all(np.isfinite(values)):
            raise ValueError("scanner IQ contains non-finite values")
        if self.requested_if_center_hz <= 0 or self.actual_if_center_hz <= 0:
            raise ValueError("scanner IF centers must be positive")
        for name, interval in (
            ("UTC", self.host_request_utc_ns),
            ("monotonic", self.host_request_monotonic_ns),
        ):
            if interval[0] < 0 or interval[0] > interval[1]:
                raise ValueError(f"scanner {name} request bracket is invalid")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


@dataclass(frozen=True, slots=True)
class ScanRadioBlockV2(ScanRadioBlock):
    """One fresh-buffer scanner frame with FPGA timeline evidence."""

    metadata_abi_version: int
    stream_id: int
    buffer_sequence: int
    first_sample_sequence: int
    metadata_flags: int
    sample_time_realtime_ns: tuple[int, int]
    sample_time_monotonic_ns: tuple[int, int]
    sample_time_uncertainty_ns: int
    kernel_buffers_requested: int
    kernel_buffers_readback: int
    reset_episode: int
    missing_samples_before: int
    overflow_observed: bool

    def __post_init__(self) -> None:
        ScanRadioBlock.__post_init__(self)
        for name in (
            "metadata_abi_version",
            "stream_id",
            "buffer_sequence",
            "first_sample_sequence",
            "metadata_flags",
            "sample_time_uncertainty_ns",
            "kernel_buffers_requested",
            "kernel_buffers_readback",
            "reset_episode",
            "missing_samples_before",
        ):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 0:
                raise ValueError(f"scanner {name} must be a nonnegative integer")
        if self.metadata_abi_version not in (1, 2):
            raise ValueError("scanner metadata ABI must be one supported version")
        if self.stream_id == 0 or self.reset_episode == 0:
            raise ValueError("scanner stream and reset episode must be nonzero")
        if self.kernel_buffers_requested < 2:
            raise ValueError("scanner V2 requires at least two kernel buffers")
        if self.kernel_buffers_readback != self.kernel_buffers_requested:
            raise ValueError("scanner kernel-buffer readback disagrees with request")
        for name, interval in (
            ("realtime", self.sample_time_realtime_ns),
            ("monotonic", self.sample_time_monotonic_ns),
        ):
            if interval[0] < 0 or interval[0] >= interval[1]:
                raise ValueError(f"scanner sample-time {name} interval is invalid")
        if self.missing_samples_before:
            raise ValueError(
                f"scanner metadata reports {self.missing_samples_before} missing samples"
            )
        if self.overflow_observed:
            raise ValueError("scanner metadata reports an RX overflow")

    @property
    def last_sample_sequence_exclusive(self) -> int:
        return self.first_sample_sequence + len(self.samples)

    @property
    def stream_generation(self) -> str:
        """Canonical generation encoding shared with continuity V2 contracts."""

        return str(self.stream_id)

    @property
    def source_sequence(self) -> int:
        return self.buffer_sequence

    @property
    def device_sample_counter(self) -> int:
        return self.first_sample_sequence

    @property
    def device_sample_counter_end_exclusive(self) -> int:
        return self.last_sample_sequence_exclusive


class SequentialScanRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def configure_once(self, configuration: ScannerConfiguration) -> None: ...

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock: ...

    def close(self) -> None: ...


class SequentialScanRadioV2(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def configure_once(self, configuration: ScannerConfigurationV2) -> None: ...

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2: ...

    def close(self) -> None: ...


ScanRadioBlockLike = ScanRadioBlock | ScanRadioBlockV2
SequentialScanRadioLike = SequentialScanRadio | SequentialScanRadioV2
