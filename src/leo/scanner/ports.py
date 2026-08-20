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


@dataclass(frozen=True, slots=True)
class ScanRadioBlock:
    samples: np.ndarray
    requested_if_center_hz: int
    actual_if_center_hz: int
    tune_ms: float
    listen_ms: float


class SequentialScanRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def configure_once(self, configuration: ScannerConfiguration) -> None: ...

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock: ...

    def close(self) -> None: ...
