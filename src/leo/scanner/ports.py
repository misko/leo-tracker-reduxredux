"""Narrow hardware port owned by sequential scanning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from leo.scanner.models import ScannerConfiguration


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


class SequentialScanRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def configure_once(self, configuration: ScannerConfiguration) -> None: ...

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock: ...

    def close(self) -> None: ...
