"""Storage-neutral analysis port for device-axis IQ with mandatory validity."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.pipeline.contracts import IqReader


class WindowValidity(StrEnum):
    """Disposition of one requested window on the logical device axis."""

    VALID = "valid"
    GAP_OVERLAP = "gap_overlap"
    CONTINUITY_BOUNDARY = "continuity_boundary"
    OUTSIDE_SPAN = "outside_span"


@dataclass(frozen=True, slots=True)
class WindowClassification:
    """Exact bounded disposition for one global device-axis window."""

    device_sample_start: int
    sample_count: int
    status: WindowValidity
    missing_sample_count: int = 0
    continuity_segment_index: int | None = None
    crossed_segment_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.sample_count <= 0:
            raise ValueError("classified window sample count must be positive")
        if self.missing_sample_count < 0 or self.missing_sample_count > self.sample_count:
            raise ValueError("classified window missing count lies outside its support")
        if tuple(sorted(set(self.crossed_segment_indexes))) != self.crossed_segment_indexes:
            raise ValueError("crossed segment indexes must be unique and ordered")
        if self.status is WindowValidity.VALID:
            if (
                self.device_sample_start < 0
                or self.missing_sample_count
                or self.continuity_segment_index is None
                or self.crossed_segment_indexes
            ):
                raise ValueError("valid window classification has inconsistent evidence")
        elif self.continuity_segment_index is not None:
            raise ValueError("excluded window cannot claim one continuity segment")
        if self.status is WindowValidity.GAP_OVERLAP and self.missing_sample_count == 0:
            raise ValueError("gap-overlap window requires missing sample support")
        if self.status is not WindowValidity.GAP_OVERLAP and self.missing_sample_count:
            raise ValueError("only gap-overlap windows may report missing samples")
        if self.status is WindowValidity.CONTINUITY_BOUNDARY and not self.crossed_segment_indexes:
            raise ValueError("continuity-boundary window requires crossed segments")


@dataclass(frozen=True, slots=True)
class DeviceIqSpan:
    """One bounded device-axis IQ read whose invalid samples are explicit zeros."""

    samples: npt.NDArray[np.int16]
    valid_samples: npt.NDArray[np.bool_]
    continuity_segment_ids: npt.NDArray[np.int32]
    device_sample_start: int
    receiver_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        validity = np.asarray(self.valid_samples)
        segments = np.asarray(self.continuity_segment_ids)
        if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[2] != 2:
            raise ValueError("device IQ samples must have native CI16 sample/receiver/IQ geometry")
        if validity.dtype != np.dtype(np.bool_) or validity.shape != (values.shape[0],):
            raise ValueError("device IQ validity must contain one boolean per sample")
        if segments.dtype != np.dtype(np.int32) or segments.shape != validity.shape:
            raise ValueError("device IQ segment IDs must contain one int32 per sample")
        if values.shape[0] == 0 or values.shape[1] != len(self.receiver_ids):
            raise ValueError("device IQ span must be non-empty and match its receiver inventory")
        if (
            not self.receiver_ids
            or tuple(sorted(set(self.receiver_ids))) != self.receiver_ids
            or self.device_sample_start < 0
        ):
            raise ValueError("device IQ span coordinates and receiver inventory must be canonical")
        if np.any(values[~validity]) or np.any(segments[~validity] != -1):
            raise ValueError("invalid device IQ positions must contain zero IQ and segment -1")
        if np.any(segments[validity] < 0):
            raise ValueError("valid device IQ positions require a continuity segment ID")
        if (
            not values.flags.c_contiguous
            or not validity.flags.c_contiguous
            or not segments.flags.c_contiguous
        ):
            raise ValueError("device IQ arrays must be C-contiguous")
        values.setflags(write=False)
        validity.setflags(write=False)
        segments.setflags(write=False)
        object.__setattr__(self, "samples", values)
        object.__setattr__(self, "valid_samples", validity)
        object.__setattr__(self, "continuity_segment_ids", segments)

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def device_sample_stop(self) -> int:
        return self.device_sample_start + self.sample_count


class ContinuitySegmentIqReader(IqReader, Protocol):
    """A contiguous local reader with an explicit global device-axis mapping."""

    @property
    def segment(self) -> ContinuitySegmentV1: ...

    @property
    def continuity_segment_index(self) -> int: ...

    @property
    def global_device_sample_start(self) -> int: ...

    def to_global_device_sample(self, local_sample: int) -> int: ...


class ValidityAwareIqReader(Protocol):
    """Native-rate logical IQ access that cannot erase observation validity."""

    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def center_frequency_hz(self) -> int: ...

    @property
    def sample_count(self) -> int:
        """Full logical device-axis sample count, including missing positions."""
        ...

    @property
    def observed_sample_count(self) -> int: ...

    @property
    def missing_sample_count(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    @property
    def validity_inventory(self) -> ValidityInventoryV1: ...

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan: ...

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]: ...

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]: ...

    def segment_readers(self) -> tuple[ContinuitySegmentIqReader, ...]: ...

    def classify_window(
        self, device_sample_start: int, sample_count: int
    ) -> WindowClassification: ...

    def close(self) -> None: ...
